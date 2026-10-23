"""Persistência (SQLAlchemy): usuários, sessões, histórico e documentos do leitor.

Por padrão usa SQLite em `backend/data/direitoaberto.db` — zero configuração.
Para PostgreSQL, basta apontar a variável de ambiente:

    DIREITO_ABERTO_DATABASE_URL=postgresql+psycopg://usuario:senha@host/direitoaberto

Os modelos usam apenas tipos portáveis, então a troca não exige migração de código.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

_DEFAULT_SQLITE = f"sqlite:///{Path(__file__).resolve().parent.parent / 'data' / 'direitoaberto.db'}"
DATABASE_URL = os.environ.get("DIREITO_ABERTO_DATABASE_URL", _DEFAULT_SQLITE)

# Provedores gerenciados (Render, Railway, Heroku…) entregam URLs "postgres://"
# ou "postgresql://"; o SQLAlchemy precisa do driver explícito (psycopg 3).
for _prefixo in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(_prefixo):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(_prefixo):]
        break

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    consultas: Mapped[list[Consulta]] = relationship(back_populates="usuario")


class TokenSessao(Base):
    __tablename__ = "tokens_sessao"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    usuario: Mapped[Usuario] = relationship()


class Consulta(Base):
    __tablename__ = "consultas"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True, index=True
    )
    pergunta: Mapped[str] = mapped_column(Text)
    tema: Mapped[str | None] = mapped_column(String(50), nullable=True)
    artigos_ids: Mapped[str] = mapped_column(Text, default="")  # ids separados por vírgula
    gerado_por_llm: Mapped[str] = mapped_column(String(3), default="nao")  # sim/nao
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    usuario: Mapped[Usuario | None] = relationship(back_populates="consultas")


class DocumentoProcesso(Base):
    """Documento enviado ao leitor de processos.

    Guarda só o texto extraído por página e a análise — nunca o arquivo
    original (o navegador do usuário já o tem para exibir). Sempre ligado a
    um dono, e apagado em `expira_em` ou quando o dono pede.
    """

    __tablename__ = "documentos_processo"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # aleatório, não sequencial
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    nome: Mapped[str] = mapped_column(String(255))
    hash_sha256: Mapped[str] = mapped_column(String(64))
    total_paginas: Mapped[int] = mapped_column()
    paginas_json: Mapped[str] = mapped_column(Text)
    analise_json: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EventoAuditoria(Base):
    """Trilha de operações sensíveis (login, exclusão, exportação, documentos). Sem conteúdo pessoal: nada de
    pergunta, documento, e-mail ou senha — a conta aparece só como pseudônimo (HMAC do id) e o endereço só
    como prefixo de rede. Apagada depois de `DIREITO_ABERTO_RETENCAO_AUDITORIA_DIAS` (app/manutencao.py)."""

    __tablename__ = "eventos_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)
    evento: Mapped[str] = mapped_column(String(40), index=True)
    conta: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    rede: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resultado: Mapped[str] = mapped_column(String(20), default="ok")


class Feedback(Base):
    """Problema apontado por quem usa num dispositivo citado (app/feedback.py). Entra numa fila de triagem
    humana e nunca muda o corpus, a vigência ou a confiança sozinho. Guarda o mínimo: dispositivo,
    categoria, comentário curto (com dado pessoal mascarado) e, com conta, a conta — para sair na
    exportação e na exclusão. Apagado depois de `DIREITO_ABERTO_RETENCAO_FEEDBACK_DIAS`."""

    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    dispositivo_id: Mapped[str] = mapped_column(String(64), index=True)
    categoria: Mapped[str] = mapped_column(String(40))
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="novo", index=True)
    triado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    nota_da_triagem: Mapped[str | None] = mapped_column(Text, nullable=True)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
