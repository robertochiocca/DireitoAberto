"""API do DireitoAberto — RAG jurídico sobre legislação brasileira.

Versionamento: a API pública vive em `/api/v1/...`; os caminhos `/api/...`
são mantidos como alias de compatibilidade com o frontend/MVP.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from . import auditoria, auth
from .consulta import consultar
from .corpus.proveniencia import NATUREZAS
from .db import Consulta, DocumentoProcesso, Feedback, Usuario, agora, get_db, init_db
from .documentos import LIMITE_BYTES, DocumentoGrandeDemais, DocumentoInvalido, extrair_texto, ler_upload_limitado
from .feedback import router as feedback_router
from .leitor.rotas import LIMITE_BYTES as LIMITE_BYTES_LEITOR
from .leitor.rotas import router as leitor_router
from .llm import gerar_resposta, llm_ativo, resposta_extrativa
from .manutencao import expurgar_se_preciso
from .monitor.registro import Registro
from .monitor.sinais import fonte_desatualizada, revisao_do_monitor
from .politica import decidir as decidir_politica
from .retrieval import normalizar
from .seguranca import (
    CABECALHOS_SEGURANCA,
    endereco_do_cliente,
    esquecer_falhas_de_login,
    limitar,
    login_bloqueado,
    origens_cors,
    registrar_falha_de_login,
)
from .semantic import criar_retriever
from .validacao import avaliar
from .verificador import verificar as verificar_texto
from .vigencia import hoje, vigencia_efetiva

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

AVISO_LEGAL = (
    "O DireitoAberto oferece informação jurídica geral, não aconselhamento "
    "sobre casos concretos. Procure a Defensoria Pública (gratuita) ou um "
    "advogado antes de tomar decisões."
)

DESCRICAO_API = """\
API pública do DireitoAberto: letramento jurídico com RAG sobre legislação
brasileira e jurisprudência selecionada (STF, STJ, TST).

- **Base atual**: `/api/v1` (esta versão). Os caminhos `/api/...` são aliases
  de compatibilidade e podem ser removidos no futuro.
- **Autenticação**: opcional. Com um token (`Authorization: Bearer ...`),
  as consultas ficam no seu histórico (`/api/v1/historico`).
- **Aviso legal**: as respostas são informação geral, não aconselhamento.
"""

app = FastAPI(
    title="DireitoAberto API",
    description=DESCRICAO_API,
    version="1.0.0",
    contact={"name": "DireitoAberto"},
    license_info={"name": "MIT"},
)
# CORS restrito (ver app/seguranca.py): nenhum dos frontends do projeto
# precisa dele em produção; o padrão libera só o Next.js em desenvolvimento.
app.add_middleware(
    CORSMiddleware,
    allow_origins=origens_cors(),
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


class _CorpoGrandeDemais(Exception):
    pass


class LimiteDeCorpo:
    """Recusa (413) o corpo maior que o limite da rota ANTES de o formulário ser lido.

    O limite de `ler_upload_limitado` só agia depois de o Starlette receber o arquivo inteiro e gravá-lo em
    disco (e depois da autenticação e da limitação de requisições, que rodam após a leitura do formulário):
    60 MB chegavam inteiros para serem recusados. Aqui o cabeçalho Content-Length é conferido na entrada e,
    para corpos sem ele (chunked), os bytes são contados enquanto chegam.
    """

    def __init__(self, app, limites: dict[str, int], padrao: int):
        self.app, self.limites, self.padrao = app, limites, padrao

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        limite = self.limites.get(scope["path"].rstrip("/"), self.padrao)
        declarado = dict(scope.get("headers") or []).get(b"content-length")
        if declarado is not None and declarado.isdigit() and int(declarado) > limite:
            return await self._recusar(send, limite)
        recebidos, iniciada = 0, False

        async def receber():
            nonlocal recebidos
            mensagem = await receive()
            if mensagem["type"] == "http.request":
                recebidos += len(mensagem.get("body", b""))
                if recebidos > limite:
                    raise _CorpoGrandeDemais
            return mensagem

        async def enviar(mensagem):
            nonlocal iniciada
            iniciada = iniciada or mensagem["type"] == "http.response.start"
            await send(mensagem)

        try:
            await self.app(scope, receber, enviar)
        except _CorpoGrandeDemais:
            if not iniciada:
                await self._recusar(send, limite)

    @staticmethod
    async def _recusar(send, limite: int) -> None:
        corpo = json.dumps({"detail": f"Envio grande demais: o limite é {limite // (1024 * 1024) or 1} MB."}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(corpo)).encode())]})
        await send({"type": "http.response.body", "body": corpo})


_FOLGA_MULTIPART = 256 * 1024  # cabeçalhos do multipart e campos do formulário
_LIMITES_DE_CORPO = {
    f"{prefixo}{rota}": limite + _FOLGA_MULTIPART
    for prefixo in ("/api/v1", "/api")
    for rota, limite in (("/perguntar-documento", LIMITE_BYTES), ("/documentos", LIMITE_BYTES_LEITOR))
}
app.add_middleware(LimiteDeCorpo, limites=_LIMITES_DE_CORPO, padrao=256 * 1024)


@app.middleware("http")
async def cabecalhos_de_seguranca(request: Request, call_next):
    await run_in_threadpool(expurgar_se_preciso)  # retenção (app/manutencao.py): no máximo 1 vez por hora
    resposta = await call_next(request)
    for nome, valor in CABECALHOS_SEGURANCA.items():
        resposta.headers.setdefault(nome, valor)
    return resposta


init_db()
retriever = criar_retriever()

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------- schemas
class Pergunta(BaseModel):
    pergunta: str = Field(..., min_length=3, max_length=1000, examples=[
        "A empresa não quer trocar meu notebook defeituoso"
    ])
    tema: str | None = Field(
        None, max_length=50, description="Filtra a busca por área (ex.: consumidor, trabalho, familia)."
    )


class Vigencia(BaseModel):
    status: str = Field(
        "nao_verificada",
        description=(
            "vigente · em_vacatio (publicada, ainda sem efeito) · revogada · "
            "inconstitucional (declarada pelo STF) · nao_verificada (sem conferência registrada: "
            "não tratar como em vigor)"
        ),
    )
    entra_em_vigor_em: str | None = None
    alterada_por: list[str] = []
    nota: str | None = None
    conferida_em: str | None = None
    status_registrado: str | None = Field(
        None,
        description=(
            "Presente quando a situação de hoje difere da gravada na base: a data de "
            "início fixada pela norma chegou, mas a revisão do registro ainda não."
        ),
    )
    vigente_desde: str | None = None


class Revisao(BaseModel):
    estado: str = Field(..., description="pendente: a informação está sendo conferida.")
    motivo: str
    evidencia: list[str] = []
    aberta_em: str | None = None


class TrechoOficial(BaseModel):
    dispositivo: str
    tipo: str = Field(..., description=(
        "consolidado: redação atualizada, transcrita da página oficial na data da coleta · "
        "literal: transcrição conferida com a publicação oficial do ato"))
    texto: str = Field(..., description="Transcrição sem as anotações editoriais da página")
    contexto: str | None = Field(None, description="Enunciado do caput, quando o trecho é um inciso")
    fonte: str
    versao_fonte: str
    coletado_em: str
    hash_sha256: str
    alertas: list[str] = []


class ArtigoEncontrado(BaseModel):
    id: str
    lei: str
    artigo: str
    tema: str
    texto: str = Field(..., description="Texto curado da base; a natureza diz se é transcrição ou explicação")
    texto_natureza: str = Field("nao_conferido", description=(
        "consolidado · literal · resumo_explicativo · interpretacao_juridica · nao_conferido. "
        "Só consolidado e literal são transcrição; o resto nunca deve ser citado como texto de lei"))
    texto_natureza_rotulo: str = ""
    trechos_oficiais: list[TrechoOficial] = []
    lacunas: list[str] = Field([], description="O que não foi conferido com a fonte oficial e por quê")
    norma: str | None = None
    dispositivos: list[dict] = Field([], description="Dispositivos citados (artigo, parágrafo, inciso, alínea)")
    versao_de: str | None = Field(None, description="Redação anterior: id da entrada que a substituiu")
    resumo: str
    fonte: str
    score: float
    vigencia: Vigencia = Vigencia(status="nao_verificada")
    revisao: Revisao | None = None


class Verificacao(BaseModel):
    nome: str
    ok: bool | None = Field(None, description="None quando a verificação não se aplica")
    detalhe: str


class Validacao(BaseModel):
    estado: str = Field(..., description=(
        "fonte_e_versao_verificadas · evidencia_suficiente · fonte_localizada · revisao_humana_recomendada · "
        "conflito_de_fontes · fonte_desatualizada_ou_indisponivel · evidencia_insuficiente"
    ))
    rotulo: str
    verificacoes: list[Verificacao]
    aviso: str


class Temporal(BaseModel):
    intencao: str = Field(..., description="atual · historica · mudanca · revogacao · fundamento")
    data_referencia: str = Field(..., description="Data a que a resposta se refere (padrão: a da consulta)")
    data_explicita: bool = Field(False, description="A pergunta trouxe a data")
    so_ano: bool = False
    expressao: str | None = None
    pede_esclarecimento: bool = Field(False, description="A resposta depende de uma data que a pergunta não deu")
    motivo: str | None = None
    avisos: list[str] = []


class Politica(BaseModel):
    modo: str = Field(..., description=(
        "responder · responder_com_ressalvas · pedir_esclarecimento · nao_verificado · recomendar_profissional"))
    rotulo: str
    motivos: list[str] = []
    proximos_passos: str


class ProblemaDoTexto(BaseModel):
    tipo: str = Field(..., description=(
        "citacao_sem_fonte · resumo_citado_como_lei · dispositivo_nao_recuperado · norma_nao_recuperada · "
        "numero_sem_fonte · linguagem_de_certeza"))
    detalhe: str


class Resposta(BaseModel):
    resposta: str
    artigos: list[ArtigoEncontrado]
    gerado_por_llm: bool
    validacao: Validacao
    temporal: Temporal | None = None
    politica: Politica | None = None
    verificacao_do_texto: list[ProblemaDoTexto] = Field([], description=(
        "Problemas do texto gerado por IA; quando há algum, o texto não é entregue e a resposta é a extrativa"))
    aviso: str = AVISO_LEGAL


class Credenciais(BaseModel):
    email: EmailStr
    senha: str = Field(..., min_length=8, max_length=128)


class TokenResposta(BaseModel):
    token: str
    tipo: str = "bearer"
    expira_em: datetime


class ConfirmacaoSenha(BaseModel):
    senha: str = Field(..., min_length=1, max_length=128)


class ConsultaHistorico(BaseModel):
    id: int
    pergunta: str
    tema: str | None
    artigos_ids: list[str]
    gerado_por_llm: bool
    criado_em: datetime


# ---------------------------------------------------------------- núcleo RAG
def _responder(
    pergunta: str,
    tema: str | None,
    db: Session,
    usuario: Usuario | None,
    contexto_documento: str | None = None,
    documento_para_ia: bool = False,
) -> Resposta:
    if tema is not None and tema not in retriever.temas():
        # Tema desconhecido não é gravado nem usado: a lista de temas é a do corpus.
        raise HTTPException(status_code=422, detail=f"Tema desconhecido. Use um de: {', '.join(retriever.temas())}.")
    data_consulta = hoje()
    consulta = consultar(retriever, pergunta, data_consulta, tema=tema, contexto_documento=contexto_documento)
    consulta_temporal, encontrados, abstencao, calibrado = (consulta.temporal, consulta.encontrados,
                                                            consulta.abstencao, consulta.calibrado)
    artigos, avisos_temporais = consulta.artigos, consulta.avisos
    for a in artigos:
        # Mudança detectada pelo monitor e ainda não revisada também deixa o dispositivo "em revisão".
        a.revisao = a.revisao or revisao_do_monitor(a.id)
    # O documento enriquece a busca local sempre; ao provedor de IA ele só vai
    # com autorização expressa do cidadão.
    texto_llm = gerar_resposta(
        pergunta, artigos, documento=contexto_documento if documento_para_ia else None,
        temporal=[f"Data de referência: {consulta_temporal.como_dict(data_consulta)['data_referencia']}"
                  f" (intenção: {consulta_temporal.intencao})", *avisos_temporais],
    )

    # O texto gerado só é entregue se passar na verificação contra as fontes (app/verificador.py).
    problemas = verificar_texto(texto_llm, artigos) if texto_llm else []
    if problemas:
        logger.warning("Texto do LLM reprovado na verificação (%d problemas); modo extrativo.", len(problemas))
        texto_llm = None

    db.add(Consulta(
        usuario_id=usuario.id if usuario else None,
        # Minimização (LGPD, art. 6º, III): o texto da pergunta só é guardado
        # para quem tem histórico. Da consulta anônima fica só a contagem e os
        # artigos devolvidos — a pergunta pode trazer saúde, violência, dívidas.
        pergunta=pergunta if usuario else "",
        tema=tema,
        artigos_ids=",".join(a.id for a in artigos),
        gerado_por_llm="sim" if texto_llm else "nao",
    ))
    db.commit()

    validacao = avaliar(encontrados if abstencao else artigos, data_consulta, texto_gerado=texto_llm,
                        calibrado=calibrado, abstencao=abstencao)
    decisao = decidir_politica(pergunta, consulta, validacao, problemas, consulta.termos_casados,
                               consulta.termos_da_pergunta)
    abertura = [] if decisao["modo"] == "responder" else [
        f"{decisao['rotulo']}: " + "; ".join(decisao["motivos"]) + "."]
    if texto_llm:
        texto_llm = "\n\n".join([*(f"⚠ {linha}" for linha in abertura), texto_llm])
    return Resposta(
        resposta=texto_llm or resposta_extrativa(pergunta, artigos, avisos=[*abertura, *avisos_temporais]),
        artigos=[_artigo_encontrado(a) for a in artigos],
        gerado_por_llm=texto_llm is not None,
        validacao=Validacao(**validacao),
        temporal=Temporal(**consulta_temporal.como_dict(data_consulta), avisos=avisos_temporais),
        politica=Politica(**decisao),
        verificacao_do_texto=[ProblemaDoTexto(**p) for p in problemas],
    )


def _artigo_encontrado(a) -> ArtigoEncontrado:
    return ArtigoEncontrado(**vars(a), texto_natureza_rotulo=NATUREZAS.get(a.texto_natureza, ""))


# ---------------------------------------------------------------- endpoints
@router.get("/saude", tags=["infra"])
def saude():
    return {"status": "ok", "artigos_no_corpus": len(retriever.artigos),
            # A interface avisa que a pergunta vai para o provedor de IA quando isto é verdadeiro.
            "llm_ativo": llm_ativo()}


def _vigencia(art: dict) -> dict:
    """Vigência como vale hoje (ver app/vigencia.py), não como foi gravada."""
    return vigencia_efetiva(art.get("vigencia"))


def _revisao(art: dict) -> dict | None:
    """Pendência registrada no corpus ou, na falta dela, a do monitor legislativo."""
    propria = art.get("revisao")
    if propria and propria.get("estado") == "pendente":
        return propria
    return revisao_do_monitor(art["id"])


def _em_revisao(art: dict) -> bool:
    return _revisao(art) is not None


@router.get("/estatisticas", tags=["infra"])
def estatisticas(db: Session = Depends(get_db)):
    leis = {art["lei"] for art in retriever.artigos}
    jurisprudencias = [a for a in retriever.artigos if a.get("tipo") == "jurisprudencia"]
    total_consultas = db.scalar(select(func.count(Consulta.id))) or 0
    por_status = Counter(_vigencia(a)["status"] for a in retriever.artigos)
    conferidas = [c for a in retriever.artigos if (c := _vigencia(a).get("conferida_em"))]
    return {
        "leis_indexadas": len(leis),
        "artigos_indexados": len(retriever.artigos),
        "jurisprudencias_indexadas": len(jurisprudencias),
        "temas": retriever.temas(),
        "consultas_realizadas": total_consultas,
        # A conferência mais recente registrada no corpus. Antes vinha da data
        # de modificação do arquivo, que num deploy é a hora do checkout — a
        # API anunciava uma atualização que não tinha acontecido.
        "base_atualizada_em": max(conferidas) if conferidas else None,
        "dispositivos_por_status": dict(por_status),
        "dispositivos_em_revisao": sum(1 for a in retriever.artigos if _em_revisao(a)),
        # A data mais ANTIGA, não a mais recente: o campo serve para dizer o
        # quanto a base pode estar velha, e o agregado honesto é o pior caso.
        "vigencia_conferida_em": min(conferidas) if conferidas else None,
    }


@router.get("/vigencia", tags=["corpus"])
def fila_de_vigencia(
    dias: int = Query(120, ge=1, le=3650, description="Janela futura, em dias."),
):
    """Fila de monitoramento: o que já mudou e o que está prestes a mudar.

    Normas publicadas mas ainda sem efeito (vacatio legis) são o maior risco de
    um RAG jurídico — responder com a regra nova antes da hora é tão errado
    quanto responder com a antiga depois dela.
    """
    dia = hoje()  # em Brasília, não no fuso do servidor
    limite = dia + timedelta(days=dias)
    entrando: list[dict] = []
    ja_valendo: list[dict] = []
    for art in retriever.artigos:
        # A fila trabalha com o status GRAVADO: o que ela mostra é justamente
        # o que precisa de revisão no corpus.
        v = art.get("vigencia") or {}
        if v.get("status") != "em_vacatio" or not v.get("entra_em_vigor_em"):
            continue
        inicio = date.fromisoformat(v["entra_em_vigor_em"])
        item = {
            "id": art["id"],
            "lei": art["lei"],
            "artigo": art["artigo"],
            "tema": art["tema"],
            "resumo": art["resumo"],
            "entra_em_vigor_em": v["entra_em_vigor_em"],
            "dias_restantes": (inicio - dia).days,
            "nota": v.get("nota"),
            "fonte": art["fonte"],
        }
        (ja_valendo if inicio <= dia else entrando).append(item)

    entrando = sorted(
        (i for i in entrando if date.fromisoformat(i["entra_em_vigor_em"]) <= limite),
        key=lambda i: i["entra_em_vigor_em"],
    )
    return {
        "hoje": dia.isoformat(),
        "janela_dias": dias,
        "entram_em_vigor": entrando,
        "marcadas_como_futuras_mas_ja_vigentes": ja_valendo,
    }


@router.get("/monitor", tags=["corpus"])
def monitor_legislativo():
    """Transparência do monitor: fontes oficiais acompanhadas, versão aceita, atualidade e mudanças pendentes."""
    registro = Registro()
    fontes = []
    for f in registro.fontes():
        aceita = registro.versao_aceita(f["id"])
        fontes.append({
            "id": f["id"],
            "nome": f["nome"],
            "url": f["url"],
            "versao_aceita": aceita["versao"] if aceita else None,
            "estado_da_versao_aceita": aceita["estado"] if aceita else None,
            "capturada_em": aceita["capturada_em"] if aceita else None,
            "ultima_verificacao": registro.dados["verificacoes"].get(f["id"]),
            "desatualizada": fonte_desatualizada(f["id"]),
        })
    pendentes = [
        {**{k: v[k] for k in ("fonte", "versao", "capturada_em", "resumo_mudancas", "dispositivos_afetados", "relatorio")},
         "eventos": [e["tipo"] for e in v.get("eventos", [])]}
        for v in registro.pendentes()
    ]
    return {"fontes": fontes, "pendentes": pendentes}


@router.get("/artigos", tags=["corpus"])
def listar_artigos(
    tema: str | None = Query(None, description="Filtra por área temática."),
    tribunal: str | None = Query(None, description="Filtra jurisprudência por tribunal (STF, STJ, TST)."),
    status: str | None = Query(
        None,
        description="Filtra por situação: vigente, em_vacatio, revogada ou inconstitucional.",
    ),
    busca: str | None = Query(
        None, description="Filtra por trecho do nome da lei ou do artigo (ex.: '8.078' ou 'art. 18')."
    ),
):
    artigos = retriever.artigos
    if tema:
        artigos = [a for a in artigos if a["tema"] == tema]
    if tribunal:
        artigos = [a for a in artigos if a.get("tribunal", "").upper() == tribunal.upper()]
    if status:
        artigos = [a for a in artigos if _vigencia(a)["status"] == status.lower()]
    if busca:
        alvo = normalizar(busca)
        artigos = [
            a for a in artigos
            if all(t in normalizar(f"{a['lei']} {a['artigo']}") for t in alvo)
        ]
    return {
        "total": len(artigos),
        "artigos": [
            {
                **{k: art[k] for k in ("id", "lei", "artigo", "tema", "resumo", "fonte")},
                "texto_natureza": art.get("texto_natureza", "nao_conferido"),
                "vigencia": _vigencia(art),
                **({"revisao": revisao} if (revisao := _revisao(art)) else {}),
                **({"tipo": art["tipo"], "tribunal": art.get("tribunal")}
                   if art.get("tipo") == "jurisprudencia" else {}),
            }
            for art in artigos
        ],
    }


@router.post(
    "/perguntar", response_model=Resposta, tags=["rag"], dependencies=[Depends(limitar("perguntar"))]
)
def perguntar(
    payload: Pergunta,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(auth.usuario_opcional),
):
    return _responder(payload.pergunta, payload.tema, db, usuario)


@router.post(
    "/perguntar-documento",
    response_model=Resposta,
    tags=["rag"],
    dependencies=[Depends(limitar("documento"))],
)
async def perguntar_com_documento(
    arquivo: UploadFile = File(..., description="Documento .txt ou .pdf (nota fiscal, contrato…)"),
    pergunta: str = Form(..., min_length=3, max_length=1000),
    tema: str | None = Form(None, max_length=50),
    permitir_ia_externa: bool = Form(
        False,
        description=(
            "Autoriza enviar o texto do documento ao provedor de IA. Sem isso, o "
            "documento só orienta a busca local e não sai do servidor."
        ),
    ),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(auth.usuario_opcional),
):
    try:
        conteudo = await ler_upload_limitado(arquivo)
        # Ler o PDF e chamar o LLM são operações bloqueantes: fora do laço de eventos, para uma consulta
        # pesada não travar as outras (antes, /saude levava 4,5 s durante um PDF de 300 páginas).
        texto = await run_in_threadpool(extrair_texto, arquivo.filename or "", conteudo)
    except DocumentoGrandeDemais as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except DocumentoInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await run_in_threadpool(
        _responder, pergunta, tema, db, usuario, contexto_documento=texto, documento_para_ia=permitir_ia_externa,
    )


# ---------------------------------------------------------------- auth + histórico
def _buscar_usuario(db: Session, email: str) -> Usuario | None:
    # Sem distinção de maiúsculas, inclusive para contas criadas antes da
    # normalização (que podem ter o e-mail gravado com maiúsculas).
    return db.scalar(select(Usuario).where(func.lower(Usuario.email) == auth.normalizar_email(email)))


def _token_resposta(db: Session, usuario: Usuario) -> TokenResposta:
    return TokenResposta(token=auth.criar_token(db, usuario), expira_em=agora() + auth.VALIDADE_TOKEN)


@router.post(
    "/auth/registrar",
    response_model=TokenResposta,
    status_code=201,
    tags=["auth"],
    dependencies=[Depends(limitar("auth"))],
)
def registrar(payload: Credenciais, request: Request, db: Session = Depends(get_db)):
    # O 409 revela que o e-mail tem conta; é o preço de uma mensagem útil no
    # cadastro, contido pela limitação de requisições.
    if _buscar_usuario(db, payload.email):
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
    usuario = Usuario(
        email=auth.normalizar_email(payload.email),
        senha_hash=auth.gerar_hash_senha(payload.senha),
    )
    db.add(usuario)
    db.flush()
    auditoria.registrar(db, "conta_criada", usuario_id=usuario.id, endereco=endereco_do_cliente(request))
    db.commit()
    return _token_resposta(db, usuario)


@router.post(
    "/auth/entrar", response_model=TokenResposta, tags=["auth"], dependencies=[Depends(limitar("auth"))]
)
def entrar(payload: Credenciais, request: Request, db: Session = Depends(get_db)):
    email, endereco = auth.normalizar_email(payload.email), endereco_do_cliente(request)
    if espera := login_bloqueado(email, endereco):
        # Muitas senhas erradas para esta conta a partir desta rede. Outras redes (o dono da conta) seguem
        # podendo entrar.
        auditoria.registrar(db, "login_bloqueado", endereco=endereco, resultado="bloqueado")
        db.commit()
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde um pouco e tente de novo.",
                            headers={"Retry-After": str(max(1, round(espera)))})
    usuario = _buscar_usuario(db, payload.email)
    # Calcula o hash mesmo sem conta, para o tempo de resposta não revelar
    # quais e-mails estão cadastrados.
    senha_ok = auth.verificar_senha_ou_gastar_tempo(payload.senha, usuario.senha_hash if usuario else None)
    if usuario is None or not senha_ok:
        registrar_falha_de_login(email, endereco)
        auditoria.registrar(db, "login_falha", usuario_id=usuario.id if usuario else None, endereco=endereco,
                            resultado="falha")
        db.commit()
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    esquecer_falhas_de_login(email, endereco)
    if auth.precisa_refazer_hash(usuario.senha_hash):
        usuario.senha_hash = auth.gerar_hash_senha(payload.senha)  # hash antigo → parâmetros atuais
    auditoria.registrar(db, "login", usuario_id=usuario.id, endereco=endereco)
    db.commit()
    return _token_resposta(db, usuario)


@router.post("/auth/sair", status_code=204, tags=["auth"])
def sair(
    credenciais: HTTPAuthorizationCredentials | None = Depends(auth.esquema_bearer),
    db: Session = Depends(get_db),
):
    """Revoga o token usado na requisição. Idempotente: token inválido também dá 204."""
    if credenciais is not None:
        auth.revogar_token(db, credenciais.credentials)
        auditoria.registrar(db, "sessao_encerrada")
        db.commit()


@router.post("/auth/sair-de-todas", status_code=204, tags=["auth"])
def sair_de_todas(db: Session = Depends(get_db), usuario: Usuario = Depends(auth.usuario_obrigatorio)):
    """Encerra todas as sessões da conta, inclusive a atual (aparelho perdido, senha vazada)."""
    auth.revogar_todos(db, usuario)
    auditoria.registrar(db, "sessoes_encerradas", usuario_id=usuario.id)
    db.commit()


class TrocaDeSenha(BaseModel):
    senha_atual: str = Field(..., min_length=1, max_length=128)
    senha_nova: str = Field(..., min_length=8, max_length=128)


@router.post("/conta/senha", status_code=204, tags=["auth"], dependencies=[Depends(limitar("auth"))])
def trocar_senha(
    payload: TrocaDeSenha,
    credenciais: HTTPAuthorizationCredentials | None = Depends(auth.esquema_bearer),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(auth.usuario_obrigatorio),
):
    """Troca a senha e encerra as outras sessões; a atual continua valendo."""
    if not auth.verificar_senha(payload.senha_atual, usuario.senha_hash):
        auditoria.registrar(db, "senha_trocada", usuario_id=usuario.id, resultado="falha")
        db.commit()
        raise HTTPException(status_code=401, detail="Senha atual incorreta.")
    usuario.senha_hash = auth.gerar_hash_senha(payload.senha_nova)
    auth.revogar_todos(db, usuario, exceto=credenciais.credentials if credenciais else None)
    auditoria.registrar(db, "senha_trocada", usuario_id=usuario.id)
    db.commit()


@router.get("/conta/exportar", tags=["auth"], dependencies=[Depends(limitar("auth"))])
def exportar_dados(db: Session = Depends(get_db), usuario: Usuario = Depends(auth.usuario_obrigatorio)):
    """Tudo o que a base guarda sobre a conta, em JSON (LGPD, art. 18, II e V): conta, histórico completo e
    documentos do leitor com a análise e feedbacks. Não inclui o hash da senha nem a trilha de auditoria
    (pseudônima)."""
    consultas = db.scalars(select(Consulta).where(Consulta.usuario_id == usuario.id)
                           .order_by(Consulta.criado_em)).all()
    documentos = db.scalars(select(DocumentoProcesso).where(DocumentoProcesso.usuario_id == usuario.id)).all()
    feedbacks = db.scalars(select(Feedback).where(Feedback.usuario_id == usuario.id).order_by(Feedback.criado_em)).all()
    dados = {
        "gerado_em": agora().isoformat(),
        "conta": {"email": usuario.email, "criada_em": usuario.criado_em.isoformat()},
        "historico": [{"pergunta": c.pergunta, "tema": c.tema, "artigos": [i for i in c.artigos_ids.split(",") if i],
                       "gerado_por_llm": c.gerado_por_llm == "sim", "em": c.criado_em.isoformat()} for c in consultas],
        "documentos_do_leitor": [{"id": d.id, "nome": d.nome, "paginas": d.total_paginas,
                                  "enviado_em": d.criado_em.isoformat(), "apagado_automaticamente_em": d.expira_em.isoformat(),
                                  "analise": json.loads(d.analise_json)} for d in documentos],
        "feedbacks": [{"id": f.id, "dispositivo": f.dispositivo_id, "categoria": f.categoria, "comentario": f.comentario,
                       "estado": f.estado, "enviado_em": f.criado_em.isoformat()} for f in feedbacks],
    }
    auditoria.registrar(db, "dados_exportados", usuario_id=usuario.id)
    db.commit()
    return JSONResponse(dados, headers={"Content-Disposition": 'attachment; filename="direitoaberto-meus-dados.json"',
                                        "Cache-Control": "no-store"})


@router.post("/conta/excluir", status_code=204, tags=["auth"], dependencies=[Depends(limitar("auth"))])
def excluir_conta(
    payload: ConfirmacaoSenha,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(auth.usuario_obrigatorio),
):
    """Apaga a conta, o histórico, os documentos do leitor, os feedbacks e todas as sessões. Pede a senha de novo."""
    if not auth.verificar_senha(payload.senha, usuario.senha_hash):
        auditoria.registrar(db, "conta_excluida", usuario_id=usuario.id, resultado="falha")
        db.commit()
        raise HTTPException(status_code=401, detail="Senha incorreta.")
    db.execute(delete(Consulta).where(Consulta.usuario_id == usuario.id))
    db.execute(delete(DocumentoProcesso).where(DocumentoProcesso.usuario_id == usuario.id))
    db.execute(delete(Feedback).where(Feedback.usuario_id == usuario.id))
    auth.revogar_todos(db, usuario)
    # O evento fica (pseudônimo, sem e-mail) pelo prazo de retenção da auditoria: prova que a exclusão foi feita.
    auditoria.registrar(db, "conta_excluida", usuario_id=usuario.id)
    db.delete(usuario)
    db.commit()


@router.get("/historico", response_model=list[ConsultaHistorico], tags=["auth"])
def historico(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(auth.usuario_obrigatorio),
    limite: int = Query(20, ge=1, le=100),
    deslocamento: int = Query(0, ge=0, description="Quantas consultas pular (paginação; o histórico inteiro "
                                                    "também sai em /conta/exportar)"),
):
    consultas = db.scalars(
        select(Consulta)
        .where(Consulta.usuario_id == usuario.id)
        .order_by(Consulta.criado_em.desc(), Consulta.id.desc())
        .offset(deslocamento)
        .limit(limite)
    ).all()
    return [
        ConsultaHistorico(
            id=c.id,
            pergunta=c.pergunta,
            tema=c.tema,
            artigos_ids=[i for i in c.artigos_ids.split(",") if i],
            gerado_por_llm=c.gerado_por_llm == "sim",
            criado_em=c.criado_em,
        )
        for c in consultas
    ]


@router.delete("/historico", status_code=204, tags=["auth"])
def apagar_historico(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(auth.usuario_obrigatorio),
):
    db.execute(delete(Consulta).where(Consulta.usuario_id == usuario.id))
    auditoria.registrar(db, "historico_apagado", usuario_id=usuario.id)
    db.commit()


router.include_router(leitor_router)
router.include_router(feedback_router)

# API pública versionada + aliases de compatibilidade do MVP.
app.include_router(router, prefix="/api/v1")
app.include_router(router, prefix="/api", include_in_schema=False)


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/dados.js", include_in_schema=False)
def frontend_dados():
    return FileResponse(FRONTEND_DIR / "dados.js")
