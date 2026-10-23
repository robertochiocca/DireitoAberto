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


def test_redacao_tachada_e_revogada_nao_entra():
    """Nas páginas compiladas do Planalto, a redação revogada vem tachada logo
    antes da vigente. Antes, ela entrava como um segundo artigo."""
    html = (
        "<p><strike>Art. 6º São direitos sociais a educação, a saúde e o trabalho.</strike></p>"
        "<p>Art. 6º São direitos sociais a educação, a saúde, a alimentação, o trabalho e a moradia. "
        "(Redação dada pela Emenda Constitucional nº 90, de 2015)</p>"
    )
    artigos = extrair_artigos(html)
    assert [a["numero"] for a in artigos] == ["6"]
    assert "alimentação" in artigos[0]["texto"]


def test_tachado_por_estilo_nao_entra_no_texto_vigente():
    """A página da Lei 8.666/1993 risca a redação antiga do art. 3º com `text-decoration:line-through`,
    não com <strike>; 16 das 34 páginas monitoradas usam o estilo (22/10/2026). Antes, esse texto riscado
    era lido como vigente."""
    from app.ingestao import extrair_texto_html

    html = (
        "<p><span style='color: black; text-decoration:line-through'>Art. 3º Redação antiga "
        "<span>com trecho aninhado</span> do artigo.</span></p>"
        "<p>Art. 3º Redação vigente do artigo.</p>"
        "<p style=\"font-size:10pt; TEXT-DECORATION: line-through\">§ 1º Parágrafo riscado sem fechar o p"
        "<p>§ 2º Parágrafo vigente.</p>"
    )
    vigente = extrair_texto_html(html)
    assert "Redação antiga" not in vigente and "aninhado" not in vigente and "Parágrafo riscado" not in vigente
    assert "Redação vigente do artigo" in vigente and "§ 2º Parágrafo vigente" in vigente  # o <p> aberto fecha
    completo = extrair_texto_html(html, incluir_tachado=True)
    assert "Redação antiga com trecho aninhado" in completo and "Parágrafo riscado" in completo
    # A leitura anterior (só tags) continua disponível para o monitor separar mudança da página de
    # mudança da leitura.
    assert "Redação antiga" in extrair_texto_html(html, riscado_por_estilo=False)



def test_riscado_por_estilo_nao_engole_texto_vigente():
    """Revisão de 22/10/2026: marcação comum fazia o riscado "vazar" e apagar o resto da página."""
    from app.ingestao import extrair_texto_html, ler_html

    lt = "style='text-decoration:line-through'"
    casos = {
        "riscados aninhados": f"<p><span {lt}>velho <span {lt}>mais velho</span> velho</span></p><p>Art. 2 vigente</p>",
        "elemento vazio riscado": f"<p>Art. 1 vigente<br {lt}>resto</p><p>Art. 2 vigente</p>",
        "<p> riscado fechado pelo ancestral": f"<table><tr><td><p {lt}>velho</td></tr></table><p>Art. 2 vigente</p>",
        "<td> sem fechamento": f"<table><tr><td {lt}>velho<td>Art. 2 vigente</table>",
        "<li> sem fechamento": f"<ul><li {lt}>velho<li>Art. 2 vigente</ul>",
        "text-decoration-line": "<p style='text-decoration-line: line-through'>velho</p><p>Art. 2 vigente</p>",
    }
    for nome, html in casos.items():
        texto = extrair_texto_html(html)
        assert "Art. 2 vigente" in texto and "velho" not in texto, nome
        assert not ler_html(html)[1], nome
    # Riscado que nunca fecha e engole a página: a leitura avisa (o monitor trata como coleta suspeita).
    _, alertas = ler_html(f"<p>Art. 1 vigente</p><span {lt}>" + "texto " * 5000)
    assert alertas
