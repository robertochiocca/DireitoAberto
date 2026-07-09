from app.ingestao import extrair_artigos, gerar_esqueletos

HTML_EXEMPLO = """
<html><head><title>Lei Exemplo</title><style>p{color:red}</style></head>
<body>
<p>LEI N&ordm; 9.999, DE 1 DE JANEIRO DE 1999.</p>
<p>Art. 1&ordm; Esta lei regula os exemplos de teste.</p>
<p>Par&aacute;grafo &uacute;nico. Os exemplos ser&atilde;o claros.</p>
<p>Art. 2<sup>o</sup> S&atilde;o direitos do testador:</p>
<p>I - escrever testes;</p>
<p>II - v&ecirc;-los passar.</p>
<p>Art. 3&ordm; (Revogado)</p>
<script>alert('nao deve aparecer')</script>
</body></html>
"""


def test_extrair_artigos_do_html():
    artigos = extrair_artigos(HTML_EXEMPLO)
    numeros = [a["numero"] for a in artigos]
    assert numeros == ["1", "2", "3"]
    assert "regula os exemplos" in artigos[0]["texto"]
    assert "Parágrafo único" in artigos[0]["texto"]  # parágrafo fica com o artigo
    assert "escrever testes" in artigos[1]["texto"]
    assert "alert" not in " ".join(a["texto"] for a in artigos)  # script ignorado


def test_gerar_esqueletos_filtra_e_marca_revisao():
    esqueletos = gerar_esqueletos(
        HTML_EXEMPLO, lei="Lei nº 9.999/1999", fonte="https://exemplo.gov", numeros=["2"]
    )
    assert len(esqueletos) == 1
    art = esqueletos[0]
    assert art["id"] == "lei-no-9-999-1999-2"  # "nº" normaliza para "no"
    assert art["artigo"] == "Art. 2"
    assert art["revisado"] is False
    assert art["resumo"].startswith("TODO")
