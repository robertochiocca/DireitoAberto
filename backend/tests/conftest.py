"""Configuração dos testes: LLM desligado e banco SQLite temporário.

As variáveis precisam ser definidas ANTES de qualquer import de `app.*`,
por isso vivem no conftest (carregado primeiro pelo pytest).
"""

import os
import tempfile

os.environ["DIREITO_ABERTO_USAR_LLM"] = "0"
os.environ.setdefault(
    "DIREITO_ABERTO_DATABASE_URL",
    "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="direitoaberto-test-"), "test.db"),
)
