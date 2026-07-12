import pytest

from app.ingestao_jurisprudencia import extrair_sumulas, gerar_esqueletos_jurisprudencia

HTML_STF = """
<html><body>
<p>SÚMULA VINCULANTE Nº 25</p>
<p>É ilícita a prisão civil de depositário infiel, qualquer que seja a
modalidade do depósito.</p>
<p>SÚMULA VINCULANTE Nº 26</p>
<p>Para efeito de progressão de regime no cumprimento de pena por crime
hediondo, o juízo da execução observará a inconstitucionalidade do art. 2º
da Lei nº 8.072/90.</p>
</body></html>
"""

HTML_STJ = """
<html><body>
<p>Súmula N. 479</p>
<p>As instituições financeiras respondem objetivamente pelos danos gerados
por fortuito interno relativo a fraudes e delitos praticados por terceiros
no âmbito de operações bancárias.</p>
<p>Súmula nº 385</p>
<p>Da anotação irregular em cadastro de proteção ao crédito, não cabe
indenização por dano moral quando preexistente legítima inscrição.</p>
</body></html>
"""

HTML_TST = """
<html><body>
<p>SUM-443 DISPENSA DISCRIMINATÓRIA. PRESUNÇÃO. EMPREGADO PORTADOR DE
DOENÇA GRAVE. Presume-se discriminatória a despedida de empregado portador
do vírus HIV ou de outra doença grave que suscite estigma ou preconceito.</p>
<p>SUM-338 JORNADA DE TRABALHO. REGISTRO. ÔNUS DA PROVA. É ônus do
empregador que conta com mais de 10 empregados o registro da jornada.</p>
</body></html>
"""


def test_extrair_sumulas_stf_vinculantes():
    sumulas = extrair_sumulas(HTML_STF)
    assert [s["numero"] for s in sumulas] == ["25", "26"]
    assert all(s["vinculante"] for s in sumulas)
    assert "depositário infiel" in sumulas[0]["texto"]


def test_extrair_sumulas_stj_formatos_de_numero():
    sumulas = extrair_sumulas(HTML_STJ)
    assert [s["numero"] for s in sumulas] == ["479", "385"]
    assert not any(s["vinculante"] for s in sumulas)
    assert "instituições financeiras" in sumulas[0]["texto"]


def test_extrair_sumulas_tst_formato_sum():
    sumulas = extrair_sumulas(HTML_TST)
    assert [s["numero"] for s in sumulas] == ["443", "338"]
    assert "discriminatória a despedida" in sumulas[0]["texto"]


def test_esqueletos_seguem_convencao_do_corpus():
    stf = gerar_esqueletos_jurisprudencia(HTML_STF, "stf", numeros=["25"])
    assert len(stf) == 1
    assert stf[0]["id"] == "stf-sv25"
    assert stf[0]["tribunal"] == "STF"
    assert stf[0]["tipo"] == "jurisprudencia"
    assert stf[0]["artigo"] == "Súmula Vinculante 25"
    assert stf[0]["revisado"] is False
    assert stf[0]["resumo"].startswith("TODO")

    stj = gerar_esqueletos_jurisprudencia(HTML_STJ, "stj", numeros=["479"])
    assert stj[0]["id"] == "stj-sumula479"
    assert stj[0]["lei"] == "Súmula nº 479 do Superior Tribunal de Justiça"

    tst = gerar_esqueletos_jurisprudencia(HTML_TST, "tst", numeros=["338"])
    assert tst[0]["id"] == "tst-sumula338"
    assert tst[0]["tribunal"] == "TST"


def test_tribunal_invalido():
    with pytest.raises(ValueError):
        gerar_esqueletos_jurisprudencia(HTML_STF, "trf1")
