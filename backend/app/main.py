"""API do DireitoAberto — RAG jurídico sobre legislação brasileira.

Versionamento: a API pública vive em `/api/v1/...`; os caminhos `/api/...`
são mantidos como alias de compatibilidade com o frontend/MVP.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import auth
from .db import Consulta, DocumentoProcesso, Usuario, agora, get_db, init_db
from .documentos import DocumentoGrandeDemais, DocumentoInvalido, extrair_texto, ler_upload_limitado
from .leitor.rotas import router as leitor_router
from .llm import gerar_resposta, resposta_extrativa
from .retrieval import normalizar
from .seguranca import CABECALHOS_SEGURANCA, limitar, origens_cors, verificar_limite
from .semantic import criar_retriever
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


@app.middleware("http")
async def cabecalhos_de_seguranca(request: Request, call_next):
    resposta = await call_next(request)
    for nome, valor in CABECALHOS_SEGURANCA.items():
        resposta.headers.setdefault(nome, valor)
    return resposta


init_db()
retriever = criar_retriever()

router = APIRouter()


# ---------------------------------------------------------------- schemas
class Pergunta(BaseModel):
    pergunta: str = Field(..., min_length=3, max_length=1000, examples=[
        "A empresa não quer trocar meu notebook defeituoso"
    ])
    tema: str | None = Field(
        None, description="Filtra a busca por área (ex.: consumidor, trabalho, familia)."
    )


class Vigencia(BaseModel):
    status: str = Field(
        "vigente",
        description=(
            "vigente · em_vacatio (publicada, ainda sem efeito) · revogada · "
            "inconstitucional (declarada pelo STF)"
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


class ArtigoEncontrado(BaseModel):
    id: str
    lei: str
    artigo: str
    tema: str
    texto: str
    resumo: str
    fonte: str
    score: float
    vigencia: Vigencia = Vigencia(status="vigente")
    revisao: Revisao | None = None


class Resposta(BaseModel):
    resposta: str
    artigos: list[ArtigoEncontrado]
    gerado_por_llm: bool
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
    consulta_busca = f"{pergunta} {contexto_documento}" if contexto_documento else pergunta
    # Adaptativa: devolve menos artigos quando os demais são fracos, em vez de
    # completar as vagas com lei de outro assunto.
    artigos = retriever.buscar(consulta_busca, tema=tema, adaptativo=True)
    # O documento enriquece a busca local sempre; ao provedor de IA ele só vai
    # com autorização expressa do cidadão.
    texto_llm = gerar_resposta(
        pergunta, artigos, documento=contexto_documento if documento_para_ia else None
    )

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

    return Resposta(
        resposta=texto_llm or resposta_extrativa(pergunta, artigos),
        artigos=[ArtigoEncontrado(**vars(a)) for a in artigos],
        gerado_por_llm=texto_llm is not None,
    )


# ---------------------------------------------------------------- endpoints
@router.get("/saude", tags=["infra"])
def saude():
    return {"status": "ok", "artigos_no_corpus": len(retriever.artigos)}


def _vigencia(art: dict) -> dict:
    """Vigência como vale hoje (ver app/vigencia.py), não como foi gravada."""
    return vigencia_efetiva(art.get("vigencia"))


def _em_revisao(art: dict) -> bool:
    return (art.get("revisao") or {}).get("estado") == "pendente"


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
                "vigencia": _vigencia(art),
                **({"revisao": art["revisao"]} if _em_revisao(art) else {}),
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
    tema: str | None = Form(None),
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
        texto = extrair_texto(arquivo.filename or "", conteudo)
    except DocumentoGrandeDemais as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except DocumentoInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _responder(
        pergunta, tema, db, usuario,
        contexto_documento=texto, documento_para_ia=permitir_ia_externa,
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
def registrar(payload: Credenciais, db: Session = Depends(get_db)):
    # O 409 revela que o e-mail tem conta; é o preço de uma mensagem útil no
    # cadastro, contido pela limitação de requisições.
    if _buscar_usuario(db, payload.email):
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
    usuario = Usuario(
        email=auth.normalizar_email(payload.email),
        senha_hash=auth.gerar_hash_senha(payload.senha),
    )
    db.add(usuario)
    db.commit()
    return _token_resposta(db, usuario)


@router.post(
    "/auth/entrar", response_model=TokenResposta, tags=["auth"], dependencies=[Depends(limitar("auth"))]
)
def entrar(payload: Credenciais, db: Session = Depends(get_db)):
    # Limite também por conta: força bruta distribuída entre muitos endereços.
    verificar_limite("auth-email", auth.normalizar_email(payload.email))
    usuario = _buscar_usuario(db, payload.email)
    # Calcula o hash mesmo sem conta, para o tempo de resposta não revelar
    # quais e-mails estão cadastrados.
    senha_ok = auth.verificar_senha_ou_gastar_tempo(payload.senha, usuario.senha_hash if usuario else None)
    if usuario is None or not senha_ok:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    return _token_resposta(db, usuario)


@router.post("/auth/sair", status_code=204, tags=["auth"])
def sair(
    credenciais: HTTPAuthorizationCredentials | None = Depends(auth.esquema_bearer),
    db: Session = Depends(get_db),
):
    """Revoga o token usado na requisição. Idempotente: token inválido também dá 204."""
    if credenciais is not None:
        auth.revogar_token(db, credenciais.credentials)


@router.post("/conta/excluir", status_code=204, tags=["auth"], dependencies=[Depends(limitar("auth"))])
def excluir_conta(
    payload: ConfirmacaoSenha,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(auth.usuario_obrigatorio),
):
    """Apaga a conta, o histórico, os documentos do leitor e todas as sessões. Pede a senha de novo."""
    if not auth.verificar_senha(payload.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="Senha incorreta.")
    db.execute(delete(Consulta).where(Consulta.usuario_id == usuario.id))
    db.execute(delete(DocumentoProcesso).where(DocumentoProcesso.usuario_id == usuario.id))
    auth.revogar_todos(db, usuario)
    db.delete(usuario)
    db.commit()


@router.get("/historico", response_model=list[ConsultaHistorico], tags=["auth"])
def historico(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(auth.usuario_obrigatorio),
    limite: int = Query(20, ge=1, le=100),
):
    consultas = db.scalars(
        select(Consulta)
        .where(Consulta.usuario_id == usuario.id)
        .order_by(Consulta.criado_em.desc())
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
    db.commit()


router.include_router(leitor_router)

# API pública versionada + aliases de compatibilidade do MVP.
app.include_router(router, prefix="/api/v1")
app.include_router(router, prefix="/api", include_in_schema=False)


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/dados.js", include_in_schema=False)
def frontend_dados():
    return FileResponse(FRONTEND_DIR / "dados.js")
