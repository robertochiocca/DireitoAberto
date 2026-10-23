"""Proveniência do corpus (app/corpus): trechos oficiais, natureza do texto, selos e histórico. Sem rede."""

import json
from datetime import date

import pytest

from app.corpus.dispositivos import (
    DispositivoAmbiguo,
    DispositivoNaoEncontrado,
    Ref,
    interpretar_rotulo,
    limpar,
    localizar,
    repeticoes,
)
from app.corpus.proveniencia import (
    Fontes,
    carregar_historico,
    classificar,
    conferir_trechos,
    divergencias,
    ler_versao,
    proveniencia,
    registrar,
    selo,
    versao_anterior,
)
from app.monitor.artigos import dividir
from app.monitor.registro import Registro
from app.monitor.servico import verificar

HOJE = date(2026, 10, 21)
URL = "https://www.planalto.gov.br/ccivil_03/leis/l9999.htm"
FONTE = {"id": "lei9999", "nome": "Lei de teste", "url": URL, "orgao_emissor": "Congresso Nacional", "tipo": "lei"}

ART_7 = ("Art. 7º São direitos dos trabalhadores urbanos e rurais, além de outros que visem à melhoria de sua "
         "condição social: I - relação de emprego protegida contra despedida arbitrária; II - seguro-desemprego, "
         "em caso de desemprego involuntário; (Redação dada pela Lei nº 1.111, de 2001) III - duração do trabalho "
         "normal não superior a 8 (oito) horas diárias, nos termos do § 1º deste artigo; IV - (VETADO) § 1º A "
         "jornada poderá ser compensada: a) por acordo individual; b) por convenção coletiva. Produção de efeitos "
         "§ 2º Aplica-se o disposto no inciso III - salvo exceção. (Incluído pela Lei nº 2.222, de 2010) (Vigência)")


# ---------------------------------------------------------------- rótulos
@pytest.mark.parametrize("rotulo, esperado", [
    ("Arts. 98 e 99", ["art. 98", "art. 99"]),
    ("Art. 7º, XIII e XV", ["art. 7º, XIII", "art. 7º, XV"]),
    ("Art. 226, § 6º", ["art. 226, § 6º"]),
    ("Arts. 1.583 e 1.584, § 2º", ["art. 1.583", "art. 1.584, § 2º"]),
    ("Art. 206, § 3º, V e § 5º, I", ["art. 206, § 3º, V", "art. 206, § 5º, I"]),
    ("Art. 284 e § 1º", ["art. 284, caput", "art. 284, § 1º"]),
    ("Art. 281, caput e parágrafo único", ["art. 281, caput", "art. 281, parágrafo único"]),
    ("Arts. 282 e 285 a 288 (síntese)", ["art. 282", "art. 285", "art. 286", "art. 287", "art. 288"]),
    ("Arts. 7º, 12-C, 22 e 24-A", ["art. 7º", "art. 12-C", "art. 22", "art. 24-A"]),
    ("Art. 487, II (e aviso prévio proporcional)", ["art. 487, II"]),
    ("Súmula 479 (c/ regras do Pix — MED)", []),
    ("Decreto 13.135/2026 (síntese)", []),
])
def test_rotulo_vira_referencias_estruturadas(rotulo, esperado):
    assert [r.rotulo() for r in interpretar_rotulo(rotulo)] == esperado


# ---------------------------------------------------------------- localização
def test_localiza_caput_inciso_paragrafo_e_alinea():
    assert localizar(ART_7, Ref("7", inciso="III")).startswith("III - duração do trabalho normal")
    assert localizar(ART_7, Ref("7", inciso="III")).endswith("nos termos do § 1º deste artigo;")
    paragrafo = localizar(ART_7, Ref("7", "1"))
    assert paragrafo.startswith("§ 1º A jornada") and "b) por convenção coletiva." in paragrafo
    assert localizar(ART_7, Ref("7", "1", alinea=None)) == paragrafo
    assert localizar(ART_7, Ref("7", "caput")).endswith("IV - (VETADO)")
    assert localizar(ART_7, Ref("7")) == ART_7


def test_citacao_no_meio_do_texto_nao_abre_dispositivo():
    # "§ 1º deste artigo" e "inciso III - salvo" estão no meio de frases: não são marcadores.
    assert localizar(ART_7, Ref("7", inciso="III")).count("III") == 1
    assert localizar(ART_7, Ref("7", "2")).startswith("§ 2º Aplica-se o disposto no inciso III - salvo exceção.")
    with pytest.raises(DispositivoNaoEncontrado):
        localizar(ART_7, Ref("7", "2", inciso="III"))


def test_dispositivo_ausente_e_lacuna_nao_palpite():
    with pytest.raises(DispositivoNaoEncontrado):
        localizar(ART_7, Ref("7", "unico"))   # o artigo tem §§ numerados, não parágrafo único
    with pytest.raises(DispositivoNaoEncontrado):
        localizar(ART_7, Ref("7", inciso="XXI"))
    with pytest.raises(DispositivoNaoEncontrado):  # lista que "começa" no XIII não é lista de incisos
        localizar("Art. 9º Vale o seguinte: XIII - um; XIV - dois.", Ref("9", inciso="XIII"))


def test_inciso_repetido_e_ambiguo():
    # Redação antiga sem tachado ao lado da nova (acontece no Código Florestal).
    repetido = "Art. 4º Considera-se: I - a faixa de 30 metros; I - a faixa de 50 metros; II - as encostas."
    with pytest.raises(DispositivoAmbiguo):
        localizar(repetido, Ref("4", inciso="I"))
    assert repeticoes(repetido) == ["inciso I (em caput)"]
    assert repeticoes(ART_7) == []


# ---------------------------------------------------------------- limpeza
def test_limpeza_tira_anotacoes_e_guarda_a_evidencia():
    limpo = limpar(ART_7)
    assert "Redação dada" not in limpo.texto and "Incluído" not in limpo.texto
    assert "Produção de efeitos" not in limpo.texto and "Vigência" not in limpo.texto
    assert "8 (oito) horas" in limpo.texto and "IV - (VETADO)" in limpo.texto  # parêntese de lei fica
    assert "(Redação dada pela Lei nº 1.111, de 2001)" in limpo.anotacoes
    assert "(Incluído pela Lei nº 2.222, de 2010)" in limpo.anotacoes
    plano = " ".join(ART_7.split())
    assert all(s in plano for s in limpo.segmentos)  # nenhuma palavra veio de fora da página


def test_marca_de_revogacao_fica_no_lugar_do_texto():
    limpo = limpar("Art. 3º São incapazes: I - (Revogado pela Lei nº 13.146, de 2015) (Vigência) II - os pródigos.")
    assert limpo.texto == "Art. 3º São incapazes: I - (Revogado pela Lei nº 13.146, de 2015) II - os pródigos."


def test_cabecalho_do_capitulo_seguinte_e_parentese_aberto_saem():
    assert limpar("Art. 3º Texto final. CAPÍTULO II DAS ÁREAS Seção I Da Delimitação").texto == "Art. 3º Texto final."
    assert limpar("Art. 46. Texto. (Incluído pela Lei nº 14.382, de 2022").texto == "Art. 46. Texto."


# ---------------------------------------------------------------- divisão (correção de 21/10/2026)
def test_travessao_do_titulo_nao_vira_letra_de_artigo():
    texto = ("Art. 58 - A duração normal do trabalho não excederá de 8 horas. "
             "Art. 58-A. Considera-se trabalho em regime de tempo parcial. Art. 483 - O empregado poderá considerar.")
    assert list(dividir(texto)) == ["58", "58-A", "483"]


# ---------------------------------------------------------------- proveniência de ponta a ponta
def _pagina(*artigos: str) -> bytes:
    corpo = "".join(f"<p>{a}</p>" for a in artigos)
    return ("<html><body><p>LEI Nº 9.999, DE 1º DE JANEIRO DE 2001.</p>" + corpo +
            "<p>Brasília, 1º de janeiro de 2001.</p></body></html>").encode()


@pytest.fixture
def fontes(tmp_path):
    (tmp_path / "fontes.json").write_text(json.dumps({"fontes": [FONTE]}), encoding="utf-8")
    registro = Registro(tmp_path)
    paginas = [
        ART_7,
        "Art. 8º O empregado tem direito a férias anuais remuneradas.",
        "Art. 12. Todo imóvel deve manter reserva:",
        "Art. 12. Todo imóvel deve manter reserva, excetuados os casos do art. 68: (Redação dada pela Lei nº 3, de 2012)",
    ]
    assert verificar(FONTE, registro, baixar=lambda _u: _pagina(*paginas))["resultado"] == "linha_de_base"
    registro.salvar()
    return Fontes(registro)


def _entrada(**campos):
    return {"id": "t", "lei": "Lei 9.999/2001", "artigo": "Art. 8º", "tema": "trabalho", "fonte": URL,
            "texto": "O empregado tem direito a férias anuais remuneradas.", "resumo": "Férias.", **campos}


def test_transcricao_conferida_e_consolidado_com_trecho_e_hash(fontes):
    p = proveniencia(_entrada(), fontes, HOJE)
    assert p["texto_natureza"] == "consolidado" and p["texto_cobertura_oficial"] == 1.0
    (trecho,) = p["trechos_oficiais"]
    assert trecho["texto"] == "Art. 8º O empregado tem direito a férias anuais remuneradas."
    assert trecho["tipo"] == "consolidado" and trecho["fonte"] == URL and len(trecho["hash_sha256"]) == 64
    assert trecho["versao_fonte"] and trecho["coletado_em"] and trecho["revisao_humana"] is None
    assert p["norma"] == "lei9999" and p["dispositivos"] == [{"artigo": "8"}]


def test_parafrase_nunca_e_rotulada_como_transcricao(fontes):
    p = proveniencia(_entrada(texto="Todo trabalhador tem férias pagas uma vez por ano, em regra de 30 dias."),
                     fontes, HOJE)
    assert p["texto_natureza"] == "resumo_explicativo"
    assert p["trechos_oficiais"]  # o texto oficial continua disponível, separado do resumo


def test_texto_com_entendimento_de_tribunal_e_interpretacao(fontes):
    texto = "O empregado tem direito a férias. O STF decidiu que o terço também vale para férias indenizadas."
    assert proveniencia(_entrada(texto=texto), fontes, HOJE)["texto_natureza"] == "interpretacao_juridica"
    sumula = _entrada(artigo="Súmula 1", tipo="jurisprudencia", fonte="https://www.stj.jus.br/x.pdf")
    assert proveniencia(sumula, fontes, HOJE)["texto_natureza"] == "interpretacao_juridica"


def test_transcricao_parcial_nao_e_consolidado(fontes):
    # Art. 8º existe; art. 99 não: mesmo com o texto do 8º literal, a entrada não é transcrição conferida.
    p = proveniencia(_entrada(artigo="Arts. 8º e 99"), fontes, HOJE)
    assert p["texto_natureza"] != "consolidado"
    assert any("art. 99" in lacuna and "não encontrado" in lacuna for lacuna in p["lacunas"])


def test_fonte_sem_coleta_nao_e_conferida(fontes):
    p = proveniencia(_entrada(fonte="https://exemplo.gov.br/norma"), fontes, HOJE)
    assert p["texto_natureza"] == "nao_conferido" and p["trechos_oficiais"] == []
    assert "não foi conferido" in p["lacunas"][0]


def test_artigo_repetido_em_sequencia_fica_sem_trecho(fontes):
    p = proveniencia(_entrada(artigo="Art. 12"), fontes, HOJE)
    assert p["trechos_oficiais"] == [] and "revisão humana" in p["lacunas"][0]


def test_inciso_leva_o_enunciado_do_caput(fontes):
    p = proveniencia(_entrada(artigo="Art. 7º, III"), fontes, HOJE)
    (trecho,) = p["trechos_oficiais"]
    assert trecho["contexto"].startswith("Art. 7º São direitos dos trabalhadores")
    assert trecho["texto"].startswith("III - duração do trabalho")


def test_conferencia_detecta_trecho_adulterado(fontes):
    art = {**_entrada(), **proveniencia(_entrada(), fontes, HOJE)}
    assert conferir_trechos([art], fontes) == []
    adulterado = json.loads(json.dumps(art))
    adulterado["trechos_oficiais"][0]["texto"] += " Inclusive em dobro."
    assert "hash" in conferir_trechos([adulterado], fontes)[0]
    # Mesmo recalculando o hash, a extração refeita na mesma versão denuncia o texto inventado.
    from app.corpus.proveniencia import sha256

    adulterado["trechos_oficiais"][0]["hash_sha256"] = sha256(adulterado["trechos_oficiais"][0]["texto"])
    assert "outro texto" in conferir_trechos([adulterado], fontes)[0]


def test_classificar_sem_trecho():
    assert classificar("qualquer texto", [], sem_trecho=True) == ("nao_conferido", None)


# ---------------------------------------------------------------- selos e histórico
def test_historico_registra_criacao_alteracao_remocao_e_reverte(tmp_path):
    loja, historico = tmp_path / "versoes", carregar_historico(tmp_path / "h.json")
    corpus = [{"id": "a", "texto": "um"}, {"id": "b", "texto": "dois"}]
    eventos = registrar(corpus, historico, loja, responsavel="Ana", motivo="registro inicial", em="2026-10-21")
    assert [e["acao"] for e in eventos] == ["criada", "criada"]
    assert divergencias(corpus, historico) == []

    corpus[0]["texto"] = "um, corrigido"
    assert divergencias(corpus, historico) == ["a: conteúdo mudou sem registro no histórico"]
    with pytest.raises(ValueError):
        registrar(corpus, historico, loja, responsavel=" ", motivo="x", em="2026-10-21")
    (evento,) = registrar(corpus, historico, loja, responsavel="Ana", motivo="correção", em="2026-10-22",
                          evidencia=["https://www.planalto.gov.br/x"])
    assert evento["acao"] == "alterada" and evento["campos"] == ["texto"]
    assert ler_versao(loja, evento["selo_anterior"]) == {"id": "a", "texto": "um"}
    assert versao_anterior(historico, loja, "a") == {"id": "a", "texto": "um"}
    assert divergencias(corpus, historico) == []

    del corpus[1]
    assert divergencias(corpus, historico) == ["b: entrada removida sem registro no histórico"]
    (remocao,) = registrar(corpus, historico, loja, responsavel="Ana", motivo="duplicada", em="2026-10-23")
    assert remocao["acao"] == "removida" and divergencias(corpus, historico) == []
    assert selo({"id": "a", "texto": "um, corrigido"}) == historico["selos"]["a"]["selo"]


# ---------------------------------------------------------------- o corpus publicado
def test_corpus_publicado_tem_proveniencia_integra():
    """Toda entrada tem selo no histórico, todo trecho oficial confere com a fonte, e nada que não seja
    transcrição conferida aparece como tal. Editar legislacao.json sem `scripts/corpus.py registrar`
    (ou `extrair`) faz este teste falhar."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import corpus as script_corpus

    from app.monitor.registro import DIR_PADRAO

    assert script_corpus.problemas_de_integridade(Registro(DIR_PADRAO)) == []


def test_corpus_publicado_nunca_rotula_resumo_como_transcricao():
    """Só é "consolidado" o texto cujas frases estão, todas, no texto oficial transcrito da entrada."""
    from app.corpus.proveniencia import transcricao_exata
    from app.retrieval import DATA_PATH

    artigos = json.loads(DATA_PATH.read_text(encoding="utf-8"))["artigos"]
    assert all("texto_natureza" in a for a in artigos)
    transcricoes = [a for a in artigos if a["texto_natureza"] in ("consolidado", "literal")]
    assert transcricoes  # a regra não pode passar por não haver nada a conferir
    for a in transcricoes:
        referencia = " ".join(t.get("contexto", "") + " " + t["texto"] for t in a["trechos_oficiais"])
        assert transcricao_exata(a["texto"], referencia), a["id"]
    # A CF, art. 6º, que a medida antiga chamava de literal, não passa: troca uma vírgula por "e".
    assert next(a for a in artigos if a["id"] == "cf-6")["texto_natureza"] != "consolidado"


# ---------------------------------------------------------------- erros achados na revisão adversarial (22/10/2026)
def test_rotulo_solto_e_cabecalho_depois_de_anotacao_saem():
    # cc-389: "(Redação dada …) Produção de efeitos Parágrafo único."; cdc-42a: "(Incluído …) SEÇÃO VI …"
    art_389 = ("Art. 389. Não cumprida a obrigação, responde o devedor por perdas e danos. (Redação dada pela Lei nº "
               "14.905, de 2024) Produção de efeitos Parágrafo único. Na hipótese de o índice não ter sido convencionado, "
               "aplica-se o IPCA. (Incluído pela Lei nº 14.905, de 2024) Produção de efeitos")
    limpo = limpar(art_389)
    assert "Produção de efeitos" not in limpo.texto
    assert limpo.texto.endswith("aplica-se o IPCA.") and "Parágrafo único. Na hipótese" in limpo.texto
    art_42a = ("Art. 42-A. Em todos os documentos de cobrança deverão constar o nome do fornecedor. (Incluído pela Lei "
               "nº 12.039, de 2009) SEÇÃO VI Dos Bancos de Dados e Cadastros de Consumidores")
    assert limpar(art_42a).texto == "Art. 42-A. Em todos os documentos de cobrança deverão constar o nome do fornecedor."
    lgpd = "V - portabilidade dos dados; (Redação dada pela Lei nº 13.853, de 2019) Vigência VI - eliminação dos dados;"
    assert "Vigência" not in limpar(lgpd).texto


def test_linha_de_pena_repetida_e_redacao_antiga():
    # Art. 24-A da Lei 11.340/2006: a pena de 2018 ficou sem tachado ao lado da de 2024.
    art = ("Art. 24-A. Descumprir decisão judicial que defere medidas protetivas: Pena – detenção, de 3 (três) meses a 2 "
           "(dois) anos. Pena – reclusão, de 2 (dois) a 5 (cinco) anos, e multa. § 1º A configuração do crime independe.")
    assert repeticoes(art) == ["linha de pena (no caput)"]
    assert repeticoes("Art. 1º Matar alguém: Pena - reclusão, de seis a vinte anos. § 1º Se o agente comete.") == []


def test_algarismo_romano_partido_e_ordinal_sobrescrito_da_pagina():
    # Decreto 7.962/2013, art. 4º: a página quebra o "II" em duas linhas ("I" / "I - fornecer").
    art = "Art. 4º O fornecedor deverá: I - apresentar sumário do contrato; I I - fornecer ferramentas; III - confirmar."
    assert repeticoes(art) == []
    assert localizar(art, Ref("4", inciso="II")) == "II - fornecer ferramentas;"
    assert limpar("Art. 3 o São absolutamente incapazes os menores de 16 (dezesseis) anos.").texto.startswith("Art. 3o São")


def test_inciso_de_paragrafo_leva_os_dois_enunciados():
    # cc-206: sem o "§ 3º Em três anos:", o trecho do inciso V não dizia o prazo.
    from app.corpus.dispositivos import enunciado_do_paragrafo

    assert enunciado_do_paragrafo(ART_7, "1") == ("§ 1º A jornada poderá ser compensada: a) por acordo individual; "
                                                  "b) por convenção coletiva. Produção de efeitos")
    art_206 = ("Art. 206. Prescreve: § 1º Em um ano: I - a pretensão dos hospedeiros; § 3º Em três anos: I - a pretensão "
               "relativa a aluguéis; II - a pretensão para receber prestações; III - a pretensão de juros; IV - a pretensão "
               "de ressarcimento; V - a pretensão de reparação civil;")
    assert enunciado_do_paragrafo(art_206, "3") == "§ 3º Em três anos:"


def test_lei_alteradora_ja_incorporada_nao_e_lacuna(fontes):
    # O art. 7º, II, traz "(Redação dada pela Lei nº 1.111, de 2001)": citar essa lei no nome não é lacuna.
    entrada = _entrada(artigo="Art. 7º, II", lei="Lei 9.999/2001 (c/ Lei nº 1.111/2001)", texto="seguro-desemprego")
    assert not any("1.111" in lacuna for lacuna in proveniencia(entrada, fontes, HOJE)["lacunas"])
    outra = _entrada(artigo="Art. 7º, II", lei="Lei 9.999/2001 (c/ Lei nº 5.555/2015)", texto="seguro-desemprego")
    assert any("5.555" in lacuna for lacuna in proveniencia(outra, fontes, HOJE)["lacunas"])
    citada_no_texto = _entrada(texto="O empregado tem direito a férias (Lei 13.146/2015).")
    assert any("13146/2015" in lacuna for lacuna in proveniencia(citada_no_texto, fontes, HOJE)["lacunas"])


# ---------------------------------------------------------------- segunda leva da revisão (22/10/2026)
def test_marca_de_revogacao_orfa_nao_e_do_dispositivo_anterior():
    # Art. 792 da CLT revogado: a página tachou o rótulo e deixou "(Revogado …)" depois do art. 791-A.
    limpo = limpar("Art. 791-A. Ao advogado serão devidos honorários. § 5º São devidos honorários na reconvenção. "
                   "(Incluído pela Lei nº 13.467, de 2017) (Revogado pela Lei nº 13.467, de 2017)")
    assert limpo.texto.endswith("§ 5º São devidos honorários na reconvenção.")
    assert "(Revogado" not in limpo.texto and any("sem dispositivo" in d for d in limpo.descartado)
    from app.corpus.proveniencia import relacoes

    assert all(r["tipo"] != "revogado_por" for r in relacoes(limpo.anotacoes))
    # Com o rótulo ("I -", "§ 2º", "Art. 262."), a marca fica: ela ocupa o lugar do texto revogado.
    assert limpar("Art. 262. (Revogado pela Lei nº 13.281, de 2016)").texto == "Art. 262. (Revogado pela Lei nº 13.281, de 2016)"


def test_anotacao_do_titulo_seguinte_nao_vira_historia_do_artigo():
    # Art. 49 da Lei 9.784: o "(Incluído pela Lei nº 14.210, de 2021)" é do Capítulo XI-A, não do artigo.
    limpo = limpar("Art. 49. A Administração tem o prazo de até trinta dias para decidir. CAPÍTULO XI-A DA DECISÃO "
                   "COORDENADA (Incluído pela Lei nº 14.210, de 2021)")
    assert limpo.texto == "Art. 49. A Administração tem o prazo de até trinta dias para decidir."
    assert limpo.anotacoes == [] and limpo.descartado


def test_paragrafo_com_travessao_da_clt_e_anotacao_de_paragrafo_incluido():
    art = ("Art. 487 - Não havendo prazo estipulado, a parte deverá avisar a outra: I - oito dias, se o pagamento for "
           "efetuado por semana; II - trinta dias aos que perceberem por quinzena ou mês. § 1º - A falta do aviso "
           "prévio dá ao empregado o direito aos salários. § 6º O reajustamento salarial integra o aviso. "
           "(Parágrafo incluído pela Lei nº 10.218, de 2001)")
    assert localizar(art, Ref("487", inciso="II")) == "II - trinta dias aos que perceberem por quinzena ou mês."
    assert localizar(art, Ref("487", "1")).startswith("§ 1º - A falta do aviso")
    assert "Parágrafo incluído" not in limpar(art).texto


def test_paragrafo_unico_junto_de_paragrafos_numerados_e_sobra_de_redacao_antiga():
    # LAI, art. 11: o antigo parágrafo único do art. 12 ficou sem tachado depois do § 6º.
    art = ("Art. 11. O órgão deve conceder o acesso. § 1º Não sendo possível, deverá informar. § 6º Caso a "
           "informação esteja disponível ao público. Parágrafo único. Estará isento de ressarcir os custos.")
    assert "parágrafo único junto de §§ numerados" in repeticoes(art)


def test_transcricao_exige_cada_frase_igual_ao_texto_oficial():
    from app.corpus.proveniencia import transcricao_exata

    oficial = ("Art. 6º São direitos sociais a educação, a saúde, a proteção à maternidade e à infância, a assistência "
               "aos desamparados, na forma desta Constituição. Parágrafo único. Todo brasileiro terá direito a renda.")
    assert transcricao_exata("São direitos sociais a educação, a saúde, a proteção à maternidade e à infância, "
                             "a assistência aos desamparados, na forma desta Constituição.", oficial)
    # Uma conjunção trocada já não é transcrição (o erro que a cobertura por janelas deixava passar).
    assert not transcricao_exata("São direitos sociais a educação, a saúde, a proteção à maternidade e à infância e "
                                 "a assistência aos desamparados, na forma desta Constituição.", oficial)
    # Travessão e espaços não contam; parênteses no lugar do travessão contam.
    assert transcricao_exata("Cadastro de Pessoas Físicas — CPF", "Cadastro de Pessoas Físicas – CPF do fornecedor")
    assert not transcricao_exata("Cadastro de Pessoas Físicas (CPF)", "Cadastro de Pessoas Físicas – CPF")


def test_artigo_citado_no_texto_sem_trecho_e_lacuna_e_adicional_vira_trecho(fontes):
    p = proveniencia(_entrada(texto="O empregado tem direito a férias (art. 7º)."), fontes, HOJE)
    assert "o texto da base cita o art. 7, sem trecho oficial na entrada" in p["lacunas"]
    com_adicional = _entrada(texto="O empregado tem direito a férias (art. 7º).",
                             dispositivos_adicionais=[{"norma": "lei9999", "artigo": "7", "inciso": "II"}])
    p = proveniencia(com_adicional, fontes, HOJE)
    assert not any("art. 7" in lacuna for lacuna in p["lacunas"])
    assert [t["dispositivo"] for t in p["trechos_oficiais"]] == ["art. 8º", "art. 7º, II"]
    assert p["texto_natureza"] != "consolidado"  # o adicional não conta como o dispositivo do rótulo


def test_alteracao_recente_anotada_na_pagina_e_nao_registrada_vira_alerta(fontes):
    # O art. 7º, II, traz "(Redação dada pela Lei nº 1.111, de 2001)": antiga demais para o alerta.
    p = proveniencia(_entrada(artigo="Art. 7º, II", texto="seguro-desemprego"), fontes, HOJE)
    assert p["vigencia_alertas"] == []
    from app.corpus.proveniencia import alteracoes_nao_registradas

    trecho = {"dispositivo": "art. 174", "relacoes": [{"tipo": "redacao_dada_por", "ato": "Lei Complementar nº 236, de 2026"}]}
    assert alteracoes_nao_registradas({"vigencia": {"alterada_por": []}}, [trecho]) == [
        "Lei Complementar nº 236, de 2026 (art. 174)"]
    assert alteracoes_nao_registradas({"vigencia": {"alterada_por": ["LC 236/2026"]}}, [trecho]) == []
