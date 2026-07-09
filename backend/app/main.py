"""API do DireitoAberto — RAG jurídico sobre legislação brasileira.

Versionamento: a API pública vive em `/api/v1/...`; os caminhos `/api/...`
são mantidos como alias de compatibilidade com o frontend/MVP.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import auth
from .db import Consulta, Usuario, get_db, init_db
from .documentos import DocumentoInvalido, extrair_texto
from .llm import gerar_resposta, resposta_extrativa
from .retrieval import DATA_PATH, normalizar
from .semantic import criar_retriever

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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


class ArtigoEncontrado(BaseModel):
    id: str
    lei: str
    artigo: str
    tema: str
    texto: str
    resumo: str
    fonte: str
    score: float


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
) -> Resposta:
    consulta_busca = f"{pergunta} {contexto_documento}" if contexto_documento else pergunta
    artigos = retriever.buscar(consulta_busca, tema=tema)
    pergunta_llm = (
        f"{pergunta}\n\nTrecho do documento enviado pelo cidadão:\n{contexto_documento}"
        if contexto_documento
        else pergunta
    )
    texto_llm = gerar_resposta(pergunta_llm, artigos)

    db.add(Consulta(
        usuario_id=usuario.id if usuario else None,
        pergunta=pergunta,
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


@router.get("/estatisticas", tags=["infra"])
def estatisticas(db: Session = Depends(get_db)):
    leis = {art["lei"] for art in retriever.artigos}
    jurisprudencias = [a for a in retriever.artigos if a.get("tipo") == "jurisprudencia"]
    atualizado_em = datetime.fromtimestamp(DATA_PATH.stat().st_mtime, tz=timezone.utc)
    total_consultas = db.scalar(select(func.count(Consulta.id))) or 0
    return {
        "leis_indexadas": len(leis),
        "artigos_indexados": len(retriever.artigos),
        "jurisprudencias_indexadas": len(jurisprudencias),
        "temas": retriever.temas(),
        "consultas_realizadas": total_consultas,
        "base_atualizada_em": atualizado_em.isoformat(),
    }


@router.get("/artigos", tags=["corpus"])
def listar_artigos(
    tema: str | None = Query(None, description="Filtra por área temática."),
    tribunal: str | None = Query(None, description="Filtra jurisprudência por tribunal (STF, STJ, TST)."),
    busca: str | None = Query(
        None, description="Filtra por trecho do nome da lei ou do artigo (ex.: '8.078' ou 'art. 18')."
    ),
):
    artigos = retriever.artigos
    if tema:
        artigos = [a for a in artigos if a["tema"] == tema]
    if tribunal:
        artigos = [a for a in artigos if a.get("tribunal", "").upper() == tribunal.upper()]
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
                **({"tipo": art["tipo"], "tribunal": art.get("tribunal")}
                   if art.get("tipo") == "jurisprudencia" else {}),
            }
            for art in artigos
        ],
    }


@router.post("/perguntar", response_model=Resposta, tags=["rag"])
def perguntar(
    payload: Pergunta,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(auth.usuario_opcional),
):
    return _responder(payload.pergunta, payload.tema, db, usuario)


@router.post("/perguntar-documento", response_model=Resposta, tags=["rag"])
async def perguntar_com_documento(
    arquivo: UploadFile = File(..., description="Documento .txt ou .pdf (nota fiscal, contrato…)"),
    pergunta: str = Form(..., min_length=3, max_length=1000),
    tema: str | None = Form(None),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(auth.usuario_opcional),
):
    conteudo = await arquivo.read()
    if len(conteudo) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo maior que 5 MB.")
    try:
        texto = extrair_texto(arquivo.filename or "", conteudo)
    except DocumentoInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _responder(pergunta, tema, db, usuario, contexto_documento=texto)


# ---------------------------------------------------------------- auth + histórico
@router.post("/auth/registrar", response_model=TokenResposta, status_code=201, tags=["auth"])
def registrar(payload: Credenciais, db: Session = Depends(get_db)):
    existente = db.scalar(select(Usuario).where(Usuario.email == payload.email))
    if existente:
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
    usuario = Usuario(email=payload.email, senha_hash=auth.gerar_hash_senha(payload.senha))
    db.add(usuario)
    db.commit()
    return TokenResposta(token=auth.criar_token(db, usuario))


@router.post("/auth/entrar", response_model=TokenResposta, tags=["auth"])
def entrar(payload: Credenciais, db: Session = Depends(get_db)):
    usuario = db.scalar(select(Usuario).where(Usuario.email == payload.email))
    if not usuario or not auth.verificar_senha(payload.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    return TokenResposta(token=auth.criar_token(db, usuario))


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


# API pública versionada + aliases de compatibilidade do MVP.
app.include_router(router, prefix="/api/v1")
app.include_router(router, prefix="/api", include_in_schema=False)


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/dados.js", include_in_schema=False)
def frontend_dados():
    return FileResponse(FRONTEND_DIR / "dados.js")
