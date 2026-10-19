"""Configuração dos testes: LLM desligado, banco SQLite temporário e data fixa.

As variáveis precisam ser definidas ANTES de qualquer import de `app.*`,
por isso vivem no conftest (carregado primeiro pelo pytest).

A data de referência fixa a vigência: sem ela, os testes que esperam normas
em vacatio quebrariam sozinhos no dia em que essas normas entrassem em vigor.
Os testes da transição usam outras datas explicitamente.
"""

import os
import tempfile

import pytest

os.environ["DIREITO_ABERTO_USAR_LLM"] = "0"
os.environ.setdefault(
    "DIREITO_ABERTO_DATABASE_URL",
    "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="direitoaberto-test-"), "test.db"),
)
os.environ.setdefault("DIREITO_ABERTO_DATA_REFERENCIA", "2026-10-19")


@pytest.fixture(autouse=True)
def _limites_zerados():
    """Cada teste começa com a contagem de requisições zerada.

    Os testes reutilizam o mesmo cliente (mesmo endereço) e a mesma conta;
    sem isso, o limite de login de um teste vazaria para o seguinte.
    """
    from app.seguranca import limitador

    limitador.resetar()
    yield
