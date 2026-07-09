"""Persistência (SQLAlchemy): usuários, tokens de sessão e histórico de consultas.

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

    consultas: Mapped[list["Consulta"]] = relationship(back_populates="usuario")


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


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
