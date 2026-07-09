import pytest
from fastapi.testclient import TestClient

from app.documentos import DocumentoInvalido, extrair_texto
from app.main import app

client = TestClient(app)


def test_extrair_texto_txt():
    texto = extrair_texto("nota.txt", "Nota fiscal 123\n  notebook  com defeito".encode())
    assert texto == "Nota fiscal 123 notebook com defeito"


def test_extrair_texto_formato_invalido():
    with pytest.raises(DocumentoInvalido):
        extrair_texto("planilha.xlsx", b"binario")


def test_extrair_texto_vazio():
    with pytest.raises(DocumentoInvalido):
        extrair_texto("vazio.txt", b"   ")


def test_extrair_texto_pdf():
    from pypdf import PdfWriter

    import io

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    # PDF em branco não tem texto extraível -> erro claro, não crash
    with pytest.raises(DocumentoInvalido):
        extrair_texto("doc.pdf", buf.getvalue())


def test_perguntar_com_documento_txt():
    conteudo = (
        "NOTA FISCAL 4567 - Notebook ABC 15 polegadas. "
        "Produto apresentou defeito na tela 10 dias após a entrega."
    ).encode()
    resp = client.post(
        "/api/v1/perguntar-documento",
        data={"pergunta": "A loja precisa trocar?"},
        files={"arquivo": ("nota.txt", conteudo, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    ids = [a["id"] for a in body["artigos"]]
    assert "cdc-18" in ids, f"esperava cdc-18 nos artigos, veio {ids}"


def test_perguntar_com_documento_formato_errado():
    resp = client.post(
        "/api/v1/perguntar-documento",
        data={"pergunta": "isso vale?"},
        files={"arquivo": ("dados.csv", b"a,b,c", "text/csv")},
    )
    assert resp.status_code == 422
