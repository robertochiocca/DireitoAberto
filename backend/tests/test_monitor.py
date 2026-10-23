"""Testes do monitor legislativo (app/monitor), sem rede: páginas sintéticas no formato do Planalto."""

import json

import pytest
from fastapi.testclient import TestClient

from app.monitor import coleta
from app.monitor.artigos import dividir
from app.monitor.comparar import classificar, coleta_suspeita
from app.monitor.fidelidade import classe, cobertura, verificar_corpus
from app.monitor.impacto import artigos_do_rotulo, dispositivos_afetados
from app.monitor.registro import DecisaoInvalida, Registro
from app.monitor.servico import _corpus, verificar

URL_CDC = "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"
FONTE = {"id": "cdc", "nome": "CDC (página sintética)", "url": URL_CDC, "orgao_emissor": "teste"}

ART18 = ("Art. 18. Os fornecedores de produtos de consumo duráveis ou não duráveis respondem solidariamente "
         "pelos vícios de qualidade ou quantidade.")


def pagina(*artigos: str, token: str = "abc", fecho: str = "") -> bytes:
    corpo = "".join(f"<p>{a}</p>" for a in artigos)
    return (
        "<html><head><meta charset='utf-8'><title>Lei</title></head><body>"
        "<p>LEI Nº 8.078, DE 11 DE SETEMBRO DE 1990.</p>"
        f"{corpo}<p>Brasília, 11 de setembro de 1990.</p>{fecho}"
        "<p>Este texto não substitui o publicado no DOU de 12.9.1990</p>"
        f"<script>var f5_token='{token}';</script></body></html>"
    ).encode()


BASE = [
    "Art. 1º O presente código estabelece normas de proteção e defesa do consumidor.",
    "Art. 2º Consumidor é toda pessoa física ou jurídica que adquire ou utiliza produto ou serviço.",
    ART18,
    "Art. 26. O direito de reclamar pelos vícios aparentes caduca em trinta dias.",
    "Art. 49. O consumidor pode desistir do contrato, no prazo de 7 dias.",
]


@pytest.fixture
def registro(tmp_path, monkeypatch):
    (tmp_path / "fontes.json").write_text(json.dumps({"fontes": [FONTE]}), encoding="utf-8")
    monkeypatch.setenv("DIREITO_ABERTO_MONITOR_DIR", str(tmp_path))
    return Registro(tmp_path)


def _verificar(registro, html: bytes) -> dict:
    r = verificar(FONTE, registro, baixar=lambda _url: html)
    registro.salvar()
    return r


# ---------------------------------------------------------------- texto vigente
def test_texto_vigente_ignora_tachado_e_script():
    html = pagina("<strike>Art. 6º Redação antiga.</strike>", "Art. 6º Redação nova.")
    texto = coleta.texto_vigente(html)
    assert "Redação nova" in texto and "Redação antiga" not in texto and "f5_token" not in texto


def test_hash_estavel_quando_so_o_html_muda(registro):
    assert _verificar(registro, pagina(*BASE, token="aaa"))["resultado"] == "linha_de_base"
    assert _verificar(registro, pagina(*BASE, token="bbb"))["resultado"] == "sem_mudanca"


def test_decodifica_windows_1252():
    bruto = "<p>Art. 1º Proteção do consumidor.</p>".encode("cp1252")
    assert "Proteção" in coleta.texto_vigente(bruto)


@pytest.mark.parametrize("codificacao, bom", [("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff"),
                                              ("utf-8", b"\xef\xbb\xbf")])
def test_decodifica_pela_marca_de_ordem_de_bytes(codificacao, bom):
    # A página da Lei 11.340/2006 vem em UTF-16 com BOM; lida como Windows-1252, perdia todos os artigos.
    bruto = bom + "<p>Art. 1º Esta Lei cria mecanismos para coibir a violência.</p>".encode(codificacao)
    texto = coleta.texto_vigente(bruto)
    assert "Art. 1º Esta Lei cria mecanismos" in texto
    assert list(dividir(texto)) == ["1"]


def test_pagina_sem_artigos_nao_vira_linha_de_base(registro):
    r = _verificar(registro, "<html><body><p>Serviço indisponível. Tente mais tarde.</p></body></html>".encode())
    assert r["resultado"] == "coleta_suspeita"
    assert registro.versoes_da_fonte("cdc") == [] and registro.versao_aceita("cdc") is None
    assert registro.dados["verificacoes"]["cdc"]["resultado"] == "coleta_suspeita"


def test_metadados_da_pagina():
    meta = coleta.metadados(coleta.texto_vigente(pagina(*BASE)))
    assert meta == {"titulo": "LEI Nº 8.078, DE 11 DE SETEMBRO DE 1990", "publicado_no_dou": "1990-09-12"}


# ---------------------------------------------------------------- divisão em artigos
def test_divisao_em_artigos():
    texto = ("Preâmbulo. Art. 1º Primeiro, nos termos do art. 2º. Art. 2o Segundo. "
             "Art. 54-A. Com letra. Art. 1.694. Com milhar. \"Art. 21. Citado entre aspas.\" "
             "Brasília, 1 de janeiro de 2020; fecho.")
    artigos = dividir(texto)
    assert list(artigos) == ["preambulo", "1", "2", "54-A", "1694", "fecho"]
    assert "nos termos do art. 2º" in artigos["1"]  # referência não divide
    assert "Citado entre aspas" in artigos["1694"]  # artigo de outra lei citado não divide


# ---------------------------------------------------------------- classificação
@pytest.mark.parametrize("antigo, novo, tipo, risco", [
    ("Art. 1º Esta lei regula os exemplos.", "Art. 1º Esta Lei regula, os exemplos.", "formatacao", "baixo"),
    ("Art. 4º Vigora na publicação.", "Art. 4º Vigora na publicação. (Vide Decreto nº 1, de 2021)",
     "anotacao_editorial", "baixo"),
    ("Art. 2º O prazo é de trinta dias.",
     "Art. 2º O prazo é de quarenta e cinco dias. (Redação dada pela Lei nº 15.000, de 2026)",
     "indicio_alteracao_legislativa", "alto"),
    # Norma alteradora nova sem mudança no texto extraído: não é "editorial", vai para revisão.
    ("Art. 2º O prazo é de trinta dias.",
     "Art. 2º O prazo é de trinta dias. (Redação dada pela Lei nº 15.000, de 2026)", "norma_nova_citada", "medio"),
    ("Art. 3º Fica criado o cadastro.", "Art. 3º (Revogado pela Lei nº 15.000, de 2026)", "indicio_revogacao", "alto"),
    ("Art. 5º O prazo é de trinta dias.", "Art. 5º O prazo é de sessenta dias.",
     "texto_alterado_sem_norma_indicada", "alto"),
    (None, "Art. 3º-A Novo dispositivo. (Incluído pela Lei nº 15.000, de 2026)", "indicio_inclusao", "medio"),
    (None, "Art. 9º Novo sem anotação.", "artigo_novo_na_pagina", "medio"),
    ("Art. 7º Existia.", None, "artigo_ausente_na_pagina", "alto"),
])
def test_classificacao(antigo, novo, tipo, risco):
    m = classificar("x", antigo, novo)
    assert (m.tipo, m.risco) == (tipo, risco)


def test_alteracao_cita_a_norma_e_mostra_o_trecho():
    m = classificar("2", "Art. 2º O prazo é de trinta dias.",
                    "Art. 2º O prazo é de quarenta e cinco dias. (Redação dada pela Lei nº 15.000, de 2026)")
    assert m.normas_citadas == ["Lei nº 15.000/2026"]
    assert "trinta" in m.trecho_anterior and "quarenta" in m.trecho_novo


def test_artigo_ausente_nao_e_revogacao():
    m = classificar("7", "Art. 7º Existia.", None)
    assert "NÃO significa revogação" in m.explicacao


def test_pagina_encolhida_e_coleta_suspeita():
    antigos = {str(i): f"Art. {i}." for i in range(1, 21)}
    assert coleta_suspeita(antigos, {"1": "Art. 1."}) is not None
    assert coleta_suspeita(antigos, {}) is not None
    assert coleta_suspeita(antigos, dict(list(antigos.items())[:18])) is None


# ---------------------------------------------------------------- impacto
def test_artigos_do_rotulo():
    assert artigos_do_rotulo("Art. 18, caput e § 1º") == {"18"}
    assert artigos_do_rotulo("Arts. 98 e 99") == {"98", "99"}
    assert artigos_do_rotulo("Arts. 20 a 27 (síntese)") == {str(n) for n in range(20, 28)}
    assert artigos_do_rotulo("Art. 7º, XIII e XV") == {"7"}
    assert artigos_do_rotulo("Art. 42-A") == {"42-A"}
    assert artigos_do_rotulo("Arts. 282 e 285 a 288 (síntese)") == {"282", "285", "286", "287", "288"}
    # Artigo com letra no meio da lista não corta o resto (lei11340-22).
    assert artigos_do_rotulo("Arts. 7º, 12-C, 22 e 24-A") == {"7", "12-C", "22", "24-A"}


def test_dispositivos_afetados_pela_url_e_pelo_artigo():
    corpus = _corpus()
    assert dispositivos_afetados(corpus, URL_CDC, {"18"}) == ["cdc-18"]
    assert dispositivos_afetados(corpus, URL_CDC.replace("https://www.", "http://"), {"26"}) == ["cdc-26"]
    assert dispositivos_afetados(corpus, URL_CDC, {"117"}) == []
    # Entrada cujo rótulo não nomeia artigo cobre a norma inteira.
    sac = "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/decreto/d13135.htm"
    assert dispositivos_afetados(corpus, sac, {"5"}) == ["decreto13135-sac"]


# ---------------------------------------------------------------- fluxo completo
def test_mudanca_de_alto_risco_fica_pendente_com_relatorio(registro):
    _verificar(registro, pagina(*BASE))
    alterado = list(BASE)
    alterado[2] = ART18.replace("solidariamente", "subsidiariamente") + " (Redação dada pela Lei nº 15.000, de 2026)"
    r = _verificar(registro, pagina(*alterado))
    assert r["resultado"] == "nova_versao" and r["detalhe"] == "pendente_revisao"
    v = registro.versao(r["versao"])
    assert v["dispositivos_afetados"] == ["cdc-18"]
    assert v["regressao"] and all(c["ok"] for c in v["regressao"])
    assert v["publicado_no_dou"] == "1990-09-12"
    assert registro.versao_aceita("cdc")["estado"] == "linha_de_base"  # a base não mudou sozinha
    texto = (registro.base / v["relatorio"]).read_text(encoding="utf-8")
    assert "Indício de alteração legislativa" in texto and "Lei nº 15.000/2026" in texto and "`cdc-18`" in texto


def test_mudanca_so_de_formatacao_e_aceita_automaticamente(registro):
    _verificar(registro, pagina(*BASE))
    formatado = [BASE[0].replace("normas", "Normas"), *BASE[1:]]
    r = _verificar(registro, pagina(*formatado))
    v = registro.versao(r["versao"])
    assert v["estado"] == "aceita" and v["decisao"]["resultado"] == "aceita_automaticamente"
    assert registro.versao_aceita("cdc")["versao"] == r["versao"]


def test_coleta_suspeita_nao_registra_versao(registro):
    _verificar(registro, pagina(*BASE))
    r = _verificar(registro, pagina(BASE[0]))  # página cortada / de erro
    assert r["resultado"] == "coleta_suspeita"
    assert len(registro.versoes_da_fonte("cdc")) == 1


def test_falha_de_rede_nao_e_mudanca(registro):
    def falha(_url):
        raise coleta.FalhaDeColeta("HTTP 503")

    r = verificar(FONTE, registro, baixar=falha)
    assert r["resultado"] == "falha_de_coleta" and registro.versoes_da_fonte("cdc") == []


def test_decisao_humana_historico_e_reversao(registro):
    base = _verificar(registro, pagina(*BASE))["versao"]
    alterado = [*BASE[:3], "Art. 26. O direito de reclamar caduca em noventa dias.", BASE[4]]
    nova = _verificar(registro, pagina(*alterado))["versao"]

    with pytest.raises(DecisaoInvalida):
        registro.decidir(nova, "aprovado", "Fulana")  # resultado inexistente
    with pytest.raises(DecisaoInvalida):
        registro.decidir(nova, "corpus_atualizado", " ")  # sem responsável
    registro.decidir(nova, "corpus_atualizado", "Fulana", "texto do art. 26 conferido no DOU")
    assert registro.versao_aceita("cdc")["versao"] == nova
    with pytest.raises(DecisaoInvalida):
        registro.decidir(nova, "rejeitada", "Fulana")  # já decidida

    registro.reverter("cdc", "Fulana", "teste de reversão")
    assert registro.versao_aceita("cdc")["versao"] == base
    assert [e["acao"] for e in registro.dados["diario"]] == ["decisao:corpus_atualizado", "reversao"]
    assert len(registro.versoes_da_fonte("cdc")) == 2  # nada apagado


def test_rejeicao_mantem_a_versao_aceita(registro):
    base = _verificar(registro, pagina(*BASE))["versao"]
    nova = _verificar(registro, pagina(*BASE[:4], "Art. 49. Texto estranho de página quebrada."))["versao"]
    registro.decidir(nova, "rejeitada", "Fulano", "página servida com erro")
    assert registro.versao_aceita("cdc")["versao"] == base
    assert _verificar(registro, pagina(*BASE[:4], "Art. 49. Texto estranho de página quebrada."))["resultado"] == \
        "versao_ja_registrada"


def test_snapshot_e_deterministico(registro):
    _verificar(registro, pagina(*BASE))
    v = registro.versao_aceita("cdc")
    primeiro = registro.caminho_snapshot("cdc", v["versao"]).read_bytes()
    registro.gravar_snapshot("cdc", v["versao"], registro.ler_snapshot("cdc", v["versao"]))
    assert registro.caminho_snapshot("cdc", v["versao"]).read_bytes() == primeiro


# ---------------------------------------------------------------- API
def test_pendencia_do_monitor_aparece_na_api_ate_a_decisao(registro):
    from app.main import app

    client = TestClient(app)
    _verificar(registro, pagina(*BASE))
    alterado = list(BASE)
    alterado[2] = ART18.replace("solidariamente", "subsidiariamente") + " (Redação dada pela Lei nº 15.000, de 2026)"
    versao = _verificar(registro, pagina(*alterado))["versao"]

    resposta = client.post("/api/v1/perguntar", json={"pergunta": "A empresa não quer trocar meu notebook defeituoso"})
    cdc18 = next(a for a in resposta.json()["artigos"] if a["id"] == "cdc-18")
    assert cdc18["revisao"]["estado"] == "pendente" and "monitor" in cdc18["revisao"]["motivo"]
    assert "EM REVISÃO" in resposta.json()["resposta"]
    status = client.get("/api/v1/monitor").json()
    assert status["pendentes"][0]["dispositivos_afetados"] == ["cdc-18"]

    registro.decidir(versao, "sem_impacto", "Fulana", "conferido")
    registro.salvar()
    resposta = client.post("/api/v1/perguntar", json={"pergunta": "A empresa não quer trocar meu notebook defeituoso"})
    cdc18 = next(a for a in resposta.json()["artigos"] if a["id"] == "cdc-18")
    assert cdc18["revisao"] is None


# ---------------------------------------------------------------- fidelidade
def test_cobertura_e_classe():
    oficial = "Art. 49. O consumidor pode desistir do contrato, no prazo de 7 dias a contar de sua assinatura."
    assert cobertura("O consumidor pode desistir do contrato, no prazo de 7 dias", oficial) == 1.0
    assert classe(1.0) == "literal" and classe(0.5) == "condensado" and classe(0.1) == "divergente"
    assert cobertura("O fornecedor pode cobrar multa de qualquer valor sem aviso prévio algum", oficial) == 0.0


def test_fidelidade_do_corpus_contra_a_versao_aceita(registro):
    corpus = [{"id": "cdc-18", "artigo": "Art. 18", "fonte": URL_CDC,
               "texto": "Os fornecedores de produtos de consumo duráveis ou não duráveis respondem solidariamente "
                        "pelos vícios de qualidade ou quantidade."},
              {"id": "cdc-26", "artigo": "Art. 26", "fonte": URL_CDC,
               "texto": "Reclamar de defeito aparente: noventa dias para bens duráveis, trinta para os demais."}]
    _verificar(registro, pagina(*BASE))
    resultado = {r["id"]: r for r in verificar_corpus(corpus, registro)}
    assert resultado["cdc-18"]["classe"] == "literal"
    assert resultado["cdc-26"]["classe"] in ("condensado", "divergente")


def test_condensar_lista_sem_os_marcadores_nao_e_divergencia():
    oficial = ("Constituem justa causa: a) ato de improbidade; b) incontinência de conduta ou mau procedimento; "
               "c) desídia no desempenho das respectivas funções;")
    condensado = "Constituem justa causa: ato de improbidade; incontinência de conduta ou mau procedimento; desídia"
    assert cobertura(condensado, oficial) >= 0.85
