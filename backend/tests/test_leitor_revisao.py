"""Regressões da revisão adversarial do leitor (rodada 9.0).

Cada teste reproduz um defeito confirmado por um revisor independente na versão
anterior do leitor — com documento fictício montado aqui — e prende o
comportamento corrigido. Os testes de recurso (H1) medem contagens, tetos e
memória, que são determinísticos; quando há tempo, o limite é folgado (a versão
anterior levava dezenas de vezes mais).
"""

import json
import time
import tracemalloc

import pytest
from fastapi.testclient import TestClient

from app.leitor import analise as analise_mod
from app.leitor import avaliacao
from app.leitor import conjunto_adversarial as conjunto_mod
from app.leitor import extracao as extracao_mod
from app.leitor import rotas as rotas_mod
from app.leitor.analise import analisar
from app.leitor.extracao import extrair
from app.leitor.pdf_simples import gerar_pdf
from app.leitor.perguntas import responder
from app.leitor.texto import RE_ASSINATURA
from app.main import app

client = TestClient(app)

INICIAL = ["# PETIÇÃO INICIAL", "Processo nº 0000000-55.2026.8.99.0002", "Autora: Maria Exemplo", "Ré: Loja Teste Ltda.",
           "A autora alega que comprou uma geladeira em 10/01/2026 e que ela nunca foi entregue pela ré.",
           "Diante do exposto, requer a condenação da ré à restituição de R$ 3.000,00.",
           "Vila Teste, 12 de fevereiro de 2026."]
PROCEDENTE = "Ante o exposto, JULGO PROCEDENTE o pedido para condenar a ré a restituir R$ 3.000,00."


def _sentenca(dispositivo, data="10 de junho de 2026", titulo="# SENTENÇA"):
    return [titulo, "Vistos.", "A ré não comprovou a entrega do produto.", dispositivo, f"Vila Teste, {data}.",
            "Juíza de Direito Fictícia"]


def _analise(paginas, rodapes=None):
    doc = extrair("p.pdf", gerar_pdf(paginas, rodapes))
    return doc, analisar(doc)


def _pecas(a):
    return [(p["tipo"], p["pagina_inicial"]) for p in a["pecas"]]


def _resposta(doc, a, pergunta):
    return responder(doc, a, pergunta)["resposta"]


# ---------------------------------------------------------------- H1. recursos limitados na análise
def test_muitas_sentencas_divergentes_nao_comparam_todos_os_pares(monkeypatch):
    """Antes: cada par de decisões finais virava citação (O(n²)); 138 KB levavam 84 s e 1,1 GB."""
    chamadas = []
    original = analise_mod._citacao_do_final

    def contar(m, final):
        chamadas.append(1)
        return original(m, final)

    monkeypatch.setattr(analise_mod, "_citacao_do_final", contar)
    bloco = ["SENTENÇA\nJULGO PROCEDENTE o pedido.\nVila Teste, 1 de março de 2026.\n",
             "SENTENÇA\nJULGO IMPROCEDENTE o pedido.\nVila Teste, 1 de março de 2026.\n"]
    doc = extrair("x.txt", "".join(bloco[i % 2] for i in range(400)).encode())
    a = analisar(doc)
    assert len(chamadas) <= 20  # antes: ~40 mil
    divergentes = [i for i in a["inconsistencias"] if i["tipo"] == "decisoes_finais_divergentes"]
    assert 1 <= len(divergentes) <= analise_mod.LIMITE_DIVERGENCIAS
    assert len(a["pecas"]) <= analise_mod.LIMITE_PECAS and a["contagens"]["pecas"]["total"] == 400


def test_muitas_partes_rotuladas_tem_teto_e_poucas_citacoes(monkeypatch):
    """Antes: cada nome era comparado com todos os anteriores e citado (4.000 linhas, 100 KB: 52 s)."""
    citacoes = []
    original = analise_mod.citar

    def contar(doc, pagina, trecho):
        citacoes.append(1)
        return original(doc, pagina, trecho)

    monkeypatch.setattr(analise_mod, "citar", contar)
    texto = "PETIÇÃO INICIAL\n" + "".join(f"Autora: Fulana Nome{i:05d}\n" for i in range(2000))
    doc = extrair("x.txt", texto.encode())
    inicio = time.monotonic()
    a = analisar(doc)
    assert time.monotonic() - inicio < 6  # antes: ~13 s
    assert len(a["partes"]) <= analise_mod.LIMITE_PARTES
    assert a["contagens"]["partes"]["total"] == 2000
    assert len(citacoes) < 1000  # antes: duas citações por linha rotulada
    nomes = next(i for i in a["inconsistencias"] if i["tipo"] == "nomes_divergentes")
    assert len(nomes["citacoes"]) <= 4


def test_folhas_ausentes_em_faixas_sem_expandir_os_numeros():
    """Antes: "fls. 1" e "fls. 999999" alternados expandiam range() inteiro (40 páginas, 2,7 KB: 849 MB)."""
    paginas = [f"Texto qualquer da pagina numero {i} com letras suficientes.\nfls. {1 if i % 2 == 0 else 999999}"
               for i in range(4)]
    doc = extrair("x.txt", "\f".join(paginas).encode())
    tracemalloc.start()
    try:
        saida = analise_mod._folhas_ausentes(doc)
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert pico < 5_000_000  # antes: ~130 MB com 4 páginas
    texto = next(i["texto"] for i in saida if i["tipo"] == "folhas_ausentes")
    assert "fls. 2 a 999998" in texto


def test_faixas_de_intervalos_agrupa_sem_listar_numeros():
    assert extracao_mod.faixas_de_intervalos([(3, 8), (10, 39)]) == "3 a 8 e 10 a 39"
    assert extracao_mod.faixas_de_intervalos([(5, 5), (6, 6), (9, 10)]) == "5, 6, 9 e 10"
    assert extracao_mod.faixas_de_intervalos([(2, 999_998)]) == "2 a 999998"
    assert extracao_mod.faixas([1, 2, 3, 5, 9, 10]) == "1 a 3, 5, 9 e 10"


def test_carimbo_em_linha_enorme_nao_e_quadratico():
    """Antes: a regex da tarja retrocedia de forma quadrática (112 mil caracteres: 10 s)."""
    linha = "x assinado digitalmente por " * 4000
    inicio = time.monotonic()
    assert not extracao_mod.eh_carimbo(linha)
    assert time.monotonic() - inicio < 1


def test_extracao_com_linhas_enormes_fica_no_orcamento():
    """Antes: a classificação das páginas rodava depois do laço com orçamento (392 KB: 65 s com orçamento de 5 s)."""
    linha = "x assinado digitalmente por " * 4000
    texto = "\f".join(["PETIÇÃO INICIAL\nTexto legível da petição com várias palavras.\n" + linha] * 2)
    inicio = time.monotonic()
    doc = extrair("x.txt", texto.encode(), orcamento_s=5)
    assert time.monotonic() - inicio < 5
    assert [p.estado for p in doc.paginas] == ["lida", "lida"]


def test_classificacao_das_paginas_tambem_tem_orcamento(monkeypatch):
    def devagar(texto):
        time.sleep(0.05)
        return 0.0

    monkeypatch.setattr(extracao_mod, "proporcao_ilegivel", devagar)
    texto = "\f".join(f"A autora alega que a ré não entregou o item {i} comprado." for i in range(30))
    doc = extrair("x.txt", texto.encode(), orcamento_s=0.01)
    cortadas = doc.paginas_por_estado("nao_processada")
    assert cortadas and 1 not in cortadas
    assert all(not doc.pagina(n).texto for n in cortadas)
    assert any("limite de tempo" in aviso for aviso in doc.avisos)


def test_numeros_de_processo_tem_teto():
    from app.leitor import cnj

    linhas = []
    for i in range(300):
        seq = f"{i:07d}"
        dv = cnj.digito_verificador(seq, "2026", "8", "99", "0001")
        linhas.append(f"Processo nº {seq}-{dv}.2026.8.99.0001")
    doc = extrair("x.txt", ("CERTIDÃO\n" + "\n".join(linhas)).encode())
    a = analisar(doc)
    assert len(a["numeros_processo"]) <= analise_mod.LIMITE_NUMEROS
    assert a["contagens"]["numeros_processo"]["total"] == 300


def test_texto_guardado_grande_demais_e_recusado_antes_da_analise(monkeypatch):
    def nao_devia_analisar(doc):
        raise AssertionError("a análise rodou antes de conferir o tamanho do texto")

    monkeypatch.setattr(rotas_mod, "LIMITE_JSON_BYTES", 500)
    monkeypatch.setattr(rotas_mod, "analisar", nao_devia_analisar)
    resp = client.post("/api/v1/auth/registrar", json={"email": "texto-grande@example.com", "senha": "senha-muito-segura"})
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}
    conteudo = ("A autora alega que a ré não entregou o produto comprado.\n" * 40).encode()
    enviado = client.post("/api/v1/documentos", files={"arquivo": ("p.txt", conteudo, "text/plain")}, headers=headers)
    assert enviado.status_code == 413 and "texto extraído" in enviado.json()["detail"]


def test_paginas_cortadas_pelo_limite_sao_guardadas_sem_texto(monkeypatch):
    """Caminho real (e não um Pagina montado à mão): páginas além do limite chegam ao banco sem texto."""
    monkeypatch.setattr(extracao_mod, "LIMITE_PAGINAS", 1)
    resp = client.post("/api/v1/auth/registrar", json={"email": "limite-paginas@example.com", "senha": "senha-muito-segura"})
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}
    conteudo = "\f".join(f"A autora alega que a ré não entregou o item {i} comprado na loja." for i in range(3)).encode()
    enviado = client.post("/api/v1/documentos", files={"arquivo": ("p.txt", conteudo, "text/plain")}, headers=headers)
    assert enviado.status_code == 201
    guardado = client.get(f"/api/v1/documentos/{enviado.json()['id']}", headers=headers).json()
    assert [(p["estado"], bool(p["texto"])) for p in guardado["paginas"]] == [
        ("lida", True), ("nao_processada", False), ("nao_processada", False)]


# ---------------------------------------------------------------- H2. segmentação
@pytest.mark.parametrize("linha", [
    "São Paulo/SP, 20 de setembro de 2026.", "Vila Teste (TS), 20 de setembro de 2026.",
    "Vila Teste – TS, 20 de setembro de 2026.", "Vila Teste-TS, 20 de setembro de 2026.",
    "Vila Teste, 20 de Setembro de 2026.", "Vila Teste, 20/09/2026.", "Vila Teste, em 20 de setembro de 2026.",
])
def test_linha_de_local_e_data_em_outros_formatos(linha):
    assert RE_ASSINATURA.match(linha)


@pytest.mark.parametrize("assinatura_inicial", ["Vila Teste/TS, 12 de fevereiro de 2026.",
                                                "Vila Teste, 12 de fevereiro de 2026."])
@pytest.mark.parametrize("cabecalho", [
    ["Processo Digital nº: 0000000-55.2026.8.99.0002", "Classe - Assunto: Procedimento Comum Cível - Indenização",
     "Requerente: Maria Exemplo", "Requerido: Loja Teste Ltda."],
    ["Juízo de Direito da 1ª Vara Cível da Comarca de Vila Teste"],
    ["Classe - Assunto: Procedimento Comum Cível"],
])
def test_cabecalho_do_juizo_antes_da_sentenca_nao_a_cola_na_peticao(cabecalho, assinatura_inicial):
    """Antes: a sentença caía dentro da petição e "JULGO PROCEDENTE" virava alegação da autora."""
    inicial = [*INICIAL[:-1], assinatura_inicial]
    doc, a = _analise([inicial, [*cabecalho, *_sentenca(PROCEDENTE)]])
    assert _pecas(a) == [("peticao_inicial", 1), ("sentenca", 2)]
    assert (a["decisao_principal"]["tipo"], a["decisao_principal"]["resultado"]) == ("sentenca", "procedente")
    assert not any("JULGO PROCEDENTE" in it["texto"] for it in a["alegacoes"])
    assert "Não localizei decisão" not in _resposta(doc, a, "O juiz já decidiu?")


@pytest.mark.parametrize("classe", ["APELAÇÃO CÍVEL", "RECURSO INOMINADO CÍVEL"])
def test_apelacao_com_numero_na_linha_seguinte_e_cabecalho_do_acordao(classe):
    """Antes: "APELAÇÃO CÍVEL" abria peça de parte e o "ACORDAM… dar provimento" virava alegação."""
    acordao = ["TRIBUNAL DE JUSTIÇA DO ESTADO DE TESTE", classe, "Processo nº 0000000-55.2026.8.99.0002",
               "Apelante: Loja Teste Ltda.", "Apelada: Maria Exemplo",
               "Ementa: Apelação cível. Consumidor. Entrega comprovada. Sentença reformada. Recurso provido.",
               "# ACÓRDÃO", "Vistos, relatados e discutidos estes autos, ACORDAM os Desembargadores, por unanimidade, "
               "em dar provimento ao recurso para julgar improcedente o pedido.", "Vila Teste, 20 de setembro de 2026."]
    doc, a = _analise([INICIAL, _sentenca(PROCEDENTE), acordao])
    assert _pecas(a) == [("peticao_inicial", 1), ("sentenca", 2), ("acordao", 3)]
    dp = a["decisao_principal"]
    assert (dp["tipo"], dp["resultado"], dp["consequencia"]) == ("acordao", "recurso provido", "improcedente")
    assert not any("ACORDAM" in it["texto"] for it in a["alegacoes"])
    assert "RECURSO PROVIDO" in _resposta(doc, a, "Eu ganhei?")


def test_conjunto_adversarial_com_assinaturas_com_uf(tmp_path):
    """Antes: trocar "Vila Teste, " por "Vila Teste/TS, " fazia o acórdão sumir dentro da sentença."""
    for nome, (paginas, rodapes) in conjunto_mod.DOCUMENTOS.items():
        novas = [[linha.replace("Vila Teste, ", "Vila Teste/TS, ") for linha in p] if isinstance(p, list) else p
                 for p in paginas]
        (tmp_path / f"{nome}.pdf").write_bytes(gerar_pdf(novas, rodapes))
        (tmp_path / f"{nome}.gabarito.json").write_text(
            (avaliacao.CONJUNTO / f"{nome}.gabarito.json").read_text(encoding="utf-8"), encoding="utf-8")
    medida = avaliacao.avaliar_conjunto(tmp_path)
    assert {nome: d["falhas"] for nome, d in medida["documentos"].items() if d["falhas"]} == {}


def test_titulo_do_juizo_recusado_dentro_de_peticao_gera_aviso():
    _, a = _analise([INICIAL, _sentenca("Ante o exposto, JULGO IMPROCEDENTE o pedido."),
                     ["# MANIFESTAÇÃO", "A autora informa o que segue e junta documentos.",
                      "# CERTIDÃO", "Certifico que a sentença transitou em julgado em 01/07/2026.",
                      "Vila Teste, 2 de julho de 2026."]])
    assert _pecas(a) == [("peticao_inicial", 1), ("sentenca", 2), ("manifestacao", 3)]
    assert any("CERTIDÃO" in aviso and "p. 3" in aviso and "não foram tratados como peça" in aviso
               for aviso in a["avisos"])


# ---------------------------------------------------------------- H3. decisão que vale
def test_acordao_sem_data_confiavel_nao_perde_para_a_sentenca_pela_data_do_corpo():
    """Antes: sem linha de assinatura reconhecida, a data do acórdão era a 1ª do corpo (a do ajuizamento)."""
    acordao = ["# ACÓRDÃO", "Trata-se de apelação contra a sentença na ação ajuizada em 12/02/2026 pela autora.",
               "Vistos, relatados e discutidos estes autos, ACORDAM os Desembargadores, por unanimidade, em dar "
               "provimento ao recurso para julgar improcedente o pedido.", "Desembargador Fictício"]
    doc, a = _analise([INICIAL, _sentenca(PROCEDENTE), acordao])
    dp = a["decisao_principal"]
    assert (dp["tipo"], dp["resultado"]) == ("acordao", "recurso provido")
    assert dp["data"] is None  # data inferida do corpo não é apresentada como data da decisão
    assert "acórdão (p. 3, 12/02/2026)" not in " ".join(f["texto"] for f in a["resumo"])
    assert "PROCEDENTE:" not in _resposta(doc, a, "Eu ganhei?")


def test_acordao_com_assinatura_com_uf_e_a_decisao_que_vale():
    acordao = ["# ACÓRDÃO", "Trata-se de apelação contra a sentença na ação ajuizada em 12/02/2026 pela autora.",
               "Vistos, relatados e discutidos estes autos, ACORDAM os Desembargadores, por unanimidade, em dar "
               "provimento ao recurso para julgar improcedente o pedido.", "Vila Teste/TS, 20 de setembro de 2026.",
               "Desembargador Fictício"]
    _, a = _analise([INICIAL, _sentenca(PROCEDENTE), acordao])
    dp = a["decisao_principal"]
    assert (dp["tipo"], dp["data"], dp["resultado"]) == ("acordao", "2026-09-20", "recurso provido")


def test_decisao_sobre_agravo_de_instrumento_nao_e_o_resultado_da_causa():
    """Antes: a decisão monocrática do agravo (contra a liminar) era apresentada como a decisão final que vale."""
    doc, a = _analise([
        INICIAL,
        ["# DECISÃO", "Defiro a tutela de urgência para determinar que a ré entregue o produto em 5 dias.",
         "Vila Teste, 20 de fevereiro de 2026."],
        ["# DECISÃO MONOCRÁTICA", "Trata-se de agravo de instrumento interposto pela ré contra a decisão que deferiu a "
         "tutela de urgência.", "Ausentes os requisitos para a reforma da decisão agravada.",
         "Ante o exposto, nego provimento ao agravo de instrumento.",
         "Documento assinado eletronicamente por Desembargador Fictício em 15/03/2026."],
        _sentenca("Ante o exposto, JULGO IMPROCEDENTE o pedido e revogo a tutela de urgência."),
    ])
    dp = a["decisao_principal"]
    assert (dp["tipo"], dp["pagina"], dp["resultado"]) == ("sentenca", 4, "improcedente")
    resposta = _resposta(doc, a, "Eu ganhei?")
    assert "IMPROCEDENTE" in resposta and "RECURSO NÃO PROVIDO:" not in resposta
    assert any("agravo" in f["texto"] and "não é o resultado da causa" in f["texto"] for f in a["resumo"])


def test_extincao_do_cumprimento_nao_e_o_resultado_da_causa():
    """Antes: a sentença que extingue o cumprimento virava o resultado e rebaixava a certidão de trânsito."""
    doc, a = _analise([
        INICIAL, _sentenca(PROCEDENTE),
        ["# CERTIDÃO", "Certifico que a sentença transitou em julgado em 10/07/2026.", "Vila Teste, 11 de julho de 2026.",
         "Escrevente Fictício"],
        ["# CUMPRIMENTO DE SENTENÇA", "A autora requer a intimação da ré para pagar o valor da condenação.",
         "Vila Teste, 1 de agosto de 2026."],
        _sentenca("Ante o exposto, JULGO EXTINTO o cumprimento de sentença, nos termos do art. 924, II, do CPC.",
                  data="20 de setembro de 2026"),
    ])
    dp = a["decisao_principal"]
    assert (dp["pagina"], dp["resultado"]) == (2, "procedente")
    assert [t["citacoes"][0]["pagina"] for t in a["transito_em_julgado"]] == [3]
    tipos = [i["tipo"] for i in a["inconsistencias"]]
    assert "transito_antes_da_decisao" not in tipos and "decisoes_finais_divergentes" not in tipos
    assert ("manifestacao", 4) in _pecas(a)
    assert any("A autora requer" in it["texto"] for it in a["pedidos"])


def test_datas_que_nao_permitem_ordenar_as_decisoes_sao_ditas_e_nao_escolhidas():
    doc, a = _analise([
        INICIAL,
        ["# SENTENÇA", "Vistos.", "Ante o exposto, JULGO PROCEDENTE o pedido.", "Juíza de Direito Fictícia"],
        ["# SENTENÇA", "Vistos.", "Ante o exposto, JULGO IMPROCEDENTE o pedido.", "Juíza de Direito Fictícia"],
    ])
    dp = a["decisao_principal"]
    assert dp["incerta"] and dp["resultado"] is None
    resposta = _resposta(doc, a, "Eu ganhei?")
    assert "Não consegui determinar" in resposta and "PROCEDENTE" in resposta and "IMPROCEDENTE" in resposta
    assert not any(f["texto"].startswith("Resultado da") for f in a["resumo"])


def test_decisoes_com_a_mesma_data_e_resultados_diferentes_nao_sao_ordenadas_pela_posicao():
    doc, a = _analise([INICIAL, _sentenca(PROCEDENTE), _sentenca("Ante o exposto, JULGO IMPROCEDENTE o pedido.")])
    dp = a["decisao_principal"]
    assert dp["incerta"] and dp["resultado"] is None and "mesma data" in dp["motivo_incerteza"]
    assert "Não consegui determinar" in _resposta(doc, a, "Explique a decisão de forma simples")


# ---------------------------------------------------------------- H4. embargos de declaração acolhidos
@pytest.mark.parametrize("frase,esperado", [
    ("ACOLHO os embargos de declaração, com efeitos infringentes, para julgar IMPROCEDENTE o pedido.",
     "embargos de declaração acolhidos"),
    ("JULGO IMPROCEDENTES os embargos de declaração.", "embargos de declaração rejeitados"),
    ("REJEITO os embargos de declaração, para manter a sentença.", "embargos de declaração rejeitados"),
    ("Conheço dos embargos de declaração e nego-lhes provimento.", "embargos de declaração rejeitados"),
    ("ACOLHO PARCIALMENTE os embargos de declaração.", "embargos de declaração acolhidos em parte"),
    ("ACOLHO os embargos de declaração para julgar PARCIALMENTE PROCEDENTE o pedido.",
     "embargos de declaração acolhidos"),
])
def test_resultado_dos_embargos_pelo_verbo_aplicado_a_eles(frase, esperado):
    assert analise_mod._resultado_de_embargos(analise_mod.dobrar(frase)) == esperado


def _com_embargos(dispositivo):
    return [INICIAL, _sentenca(PROCEDENTE),
            ["# EMBARGOS DE DECLARAÇÃO", "A ré alega omissão quanto ao comprovante de entrega.",
             "Diante do exposto, requer o acolhimento dos embargos.", "Vila Teste, 17 de junho de 2026."],
            ["# SENTENÇA", "Trata-se de embargos de declaração opostos pela ré contra a sentença.",
             "Há omissão: o comprovante de entrega assinado pela autora não foi examinado.", dispositivo,
             "Vila Teste, 30 de junho de 2026.", "Juíza de Direito Fictícia"]]


def test_embargos_acolhidos_com_efeitos_infringentes_mudam_o_resultado():
    """Antes: "ACOLHO… para julgar IMPROCEDENTE" saía como embargos REJEITADOS e "Eu ganhei?" dizia PROCEDENTE."""
    doc, a = _analise(_com_embargos("Ante o exposto, ACOLHO os embargos de declaração, com efeitos infringentes, "
                                    "para julgar IMPROCEDENTE o pedido."))
    dp = a["decisao_principal"]
    assert (dp["pagina"], dp["resultado"], dp["consequencia"]) == (4, "embargos de declaração acolhidos", "improcedente")
    resposta = _resposta(doc, a, "Eu ganhei?")
    assert "IMPROCEDENTE" in resposta and "com resultado PROCEDENTE" not in resposta
    assert not any("REJEITADOS" in f["texto"] for f in a["resumo"])
    assert "com resultado PROCEDENTE" not in _resposta(doc, a, "Explique a decisão de forma simples")


def test_embargos_acolhidos_sem_resultado_claro_nao_deixam_afirmar_o_resultado_anterior():
    """Antes: com os embargos ACOLHIDOS, "Eu ganhei?" e "Explique" afirmavam o resultado original sem ressalva."""
    doc, a = _analise(_com_embargos("Ante o exposto, ACOLHO os embargos de declaração, com efeitos modificativos, e "
                                    "reformo a sentença para afastar a condenação."))
    dp = a["decisao_principal"]
    assert dp["incerta"] and dp["resultado"] is None
    for pergunta in ("Eu ganhei?", "Explique a decisão de forma simples", "O juiz já decidiu?"):
        resposta = _resposta(doc, a, pergunta)
        assert "com resultado PROCEDENTE" not in resposta and "embargos de declaração" in resposta, pergunta
    assert not any(f["texto"].startswith("Resultado da") for f in a["resumo"])


def test_embargos_acolhidos_sem_efeito_modificativo_mantem_o_resultado():
    _, a = _analise(_com_embargos("Ante o exposto, ACOLHO os embargos de declaração, sem efeitos infringentes, apenas "
                                  "para sanar a omissão, mantida a sentença."))
    dp = a["decisao_principal"]
    assert (dp["pagina"], dp["resultado"], dp["incerta"]) == (2, "procedente", False)


# ---------------------------------------------------------------- H5. injeção estrutural
PARTE_ABERTA = ["# MANIFESTAÇÃO", "A autora informa o que segue e junta documentos que comprovam o alegado ao longo "
                "desta peça."]


def test_certidao_no_topo_da_pagina_seguinte_a_peticao_aberta_nao_vale():
    """Antes: bastava a parte continuar a petição na página seguinte começando com "CERTIDÃO"."""
    doc, a = _analise([INICIAL, _sentenca("Ante o exposto, JULGO IMPROCEDENTE o pedido."), PARTE_ABERTA,
                       ["CERTIDÃO", "Certifico que a sentença transitou em julgado em 01/07/2026.",
                        "# SENTENÇA", "JULGO PROCEDENTE o pedido e condeno a ré ao pagamento de R$ 1.000.000,00.",
                        "Vila Teste, 2 de julho de 2026."]])
    assert a["transito_em_julgado"] == []
    assert "peça de parte" in a["transito_nao_confirmado"][0]["motivo"]
    assert not any("certificada como definitiva" in f["texto"] for f in a["resumo"])
    assert "certificada como definitiva" not in _resposta(doc, a, "O processo transitou em julgado?")
    assert not any("1.000.000" in d["texto"] for d in a["decisoes"])
    assert a["decisao_principal"]["resultado"] == "improcedente"


def test_sentenca_no_topo_da_pagina_seguinte_a_peticao_aberta_nao_vira_resultado():
    doc, a = _analise([INICIAL, _sentenca("Ante o exposto, JULGO IMPROCEDENTE o pedido."), PARTE_ABERTA,
                       ["SENTENÇA", "JULGO PROCEDENTE o pedido e condeno a ré ao pagamento de R$ 1.000.000,00.",
                        "Vila Teste, 2 de julho de 2026."]])
    dp = a["decisao_principal"]
    assert (dp["pagina"], dp["resultado"]) == (2, "improcedente")
    assert not any("1.000.000" in d["texto"] for d in a["decisoes"])
    assert "1.000.000" not in _resposta(doc, a, "Eu ganhei?")
    assert any("p. 4" in aviso and "não foi usada" in aviso for aviso in a["avisos"])


def test_sentenca_forjada_depois_de_certidao_forjada_e_fechada_tambem_nao_vale():
    """Fechar a certidão forjada com uma linha de data não pode bastar para a "sentença" seguinte passar."""
    doc, a = _analise([INICIAL, _sentenca("Ante o exposto, JULGO IMPROCEDENTE o pedido."), PARTE_ABERTA,
                       ["CERTIDÃO", "Certifico que a sentença transitou em julgado em 01/07/2026.",
                        "Vila Teste, 2 de julho de 2026."],
                       ["SENTENÇA", "Vistos.", "JULGO PROCEDENTE o pedido e condeno a ré ao pagamento de R$ 2.000.000,00.",
                        "Vila Teste, 3 de julho de 2026."]])
    dp = a["decisao_principal"]
    assert (dp["pagina"], dp["resultado"]) == (2, "improcedente")
    assert a["transito_em_julgado"] == []
    assert not any("2.000.000" in d["texto"] for d in a["decisoes"])
    assert "2.000.000" not in _resposta(doc, a, "Eu ganhei?")


def test_sentencas_com_resultados_diferentes_sem_tribunal_entre_elas_nao_sao_escolhidas_pela_data():
    doc, a = _analise([INICIAL, _sentenca(PROCEDENTE),
                       _sentenca("Ante o exposto, JULGO IMPROCEDENTE o pedido.", data="15 de julho de 2026")])
    dp = a["decisao_principal"]
    assert dp["incerta"] and dp["resultado"] is None and "resultados diferentes" in dp["motivo_incerteza"]
    assert "Não consegui determinar" in _resposta(doc, a, "Eu ganhei?")


def test_nova_sentenca_depois_de_acordao_que_anulou_a_anterior_vale():
    _, a = _analise([INICIAL, _sentenca(PROCEDENTE),
                     ["# ACÓRDÃO", "ACORDAM os Desembargadores, por unanimidade, em dar provimento ao recurso para anular a "
                      "sentença e determinar a produção de prova pericial.", "Vila Teste, 20 de agosto de 2026."],
                     _sentenca("Ante o exposto, JULGO IMPROCEDENTE o pedido.", data="15 de outubro de 2026")])
    dp = a["decisao_principal"]
    assert (dp["pagina"], dp["resultado"], dp["incerta"]) == (4, "improcedente", False)


def test_certidao_de_outro_processo_sem_decisao_final_nao_confirma_transito():
    doc, a = _analise([INICIAL,
                       ["# MANIFESTAÇÃO", "A autora junta certidão de outro processo para demonstrar a reincidência da ré.",
                        "Vila Teste, 1 de março de 2026."],
                       ["# CERTIDÃO", "Processo nº 0000000-99.2020.8.99.0001",
                        "Certifico que a sentença transitou em julgado em 01/07/2021.", "Vila Teste, 2 de julho de 2021."]])
    assert a["transito_em_julgado"] == []
    motivo = a["transito_nao_confirmado"][0]["motivo"]
    assert "outro número de processo" in motivo or "decisão final" in motivo
    assert not any("certificada como definitiva" in f["texto"] for f in a["resumo"])
    assert "certificada como definitiva" not in _resposta(doc, a, "A decisão é definitiva?")


def test_certidao_que_cita_outro_numero_nao_confirma_mesmo_com_decisao_final():
    _, a = _analise([INICIAL, _sentenca(PROCEDENTE),
                     ["# CERTIDÃO", "Processo nº 0000000-99.2020.8.99.0001",
                      "Certifico que a sentença transitou em julgado em 01/07/2026.", "Vila Teste, 2 de julho de 2026."]])
    assert a["transito_em_julgado"] == []
    assert "outro número de processo" in a["transito_nao_confirmado"][0]["motivo"]


# ---------------------------------------------------------------- M1. resultados em frases separadas
@pytest.mark.parametrize("dispositivo,esperado", [
    (["Ante o exposto, JULGO PROCEDENTE o pedido de restituição e condeno a ré a pagar R$ 3.000,00.",
      "JULGO IMPROCEDENTE o pedido de indenização por danos morais."], "parcialmente procedente"),
    (["Ante o exposto, resolvo o mérito nos termos do art. 487, I, do CPC:", "a) JULGO PROCEDENTE o pedido de "
      "restituição;", "b) JULGO IMPROCEDENTE o pedido de danos morais."], "parcialmente procedente"),
    (["Ante o exposto, JULGO PROCEDENTE o pedido, com exceção dos danos morais, que rejeito."],
     "parcialmente procedente"),
    (["Ante o exposto, ACOLHO EM PARTE os pedidos para condenar a ré a restituir R$ 3.000,00."],
     "parcialmente procedente"),
    (["Ante o exposto, JULGO PROCEDENTE o pedido contraposto e IMPROCEDENTE o pedido inicial."], "misto"),
    ([PROCEDENTE], "procedente"),
])
def test_resultado_junta_os_capitulos_do_dispositivo(dispositivo, esperado):
    sentenca = ["# SENTENÇA", "Vistos.", *dispositivo, "Vila Teste, 10 de junho de 2026."]
    _, a = _analise([INICIAL, sentenca])
    assert a["decisao_principal"]["resultado"] == esperado


# ---------------------------------------------------------------- M2. trânsito em julgado
@pytest.mark.parametrize("frase", [
    "Certifico que, não havendo recurso, transitou em julgado a sentença em 10/07/2026.",
    "Certifico que, decorrido o prazo sem recurso, transitou em julgado a sentença em 10/07/2026.",
    "Certifico que, após o prazo, transitou em julgado a sentença em 10/07/2026.",
])
def test_transito_depois_de_oracao_negativa_e_certificado(frase):
    """Antes: "não havendo recurso, transitou" era lido como "NÃO transitou" — o oposto do texto."""
    _, a = _analise([_sentenca(PROCEDENTE), ["# CERTIDÃO", frase, "Vila Teste, 11 de julho de 2026."]])
    assert [t["citacoes"][0]["pagina"] for t in a["transito_em_julgado"]] == [2]
    assert not any("NÃO tinha transitado" in f["texto"] for f in a["resumo"])


@pytest.mark.parametrize("frase", [
    "Certifico que a sentença ainda não transitou em julgado.",
    "Certifico que não houve o trânsito em julgado da sentença.",
    "Certifico que, após o trânsito em julgado, os autos serão arquivados.",
    "Certifico que os autos aguardam o trânsito em julgado da sentença.",
])
def test_transito_negado_ou_futuro_nao_e_certificado(frase):
    _, a = _analise([_sentenca(PROCEDENTE), ["# CERTIDÃO", frase, "Vila Teste, 11 de julho de 2026."]])
    assert a["transito_em_julgado"] == [] and a["transito_nao_confirmado"]


# ---------------------------------------------------------------- M3. fim do relatório
@pytest.mark.parametrize("fim", ["É o sucinto relatório.", "É o breve relato.", "É o relatório. Decido.",
                                 "Relatei. Decido.", "Relatados. Decido.", "É o que importa relatar."])
def test_fim_do_relatorio_em_outras_formas(fim):
    sentenca = ["# SENTENÇA", "# RELATÓRIO", "A autora alega que não recebeu a geladeira.", fim,
                "A ré não comprovou a entrega.", PROCEDENTE, "Vila Teste, 10 de junho de 2026."]
    _, a = _analise([INICIAL, sentenca])
    assert a["decisao_principal"]["resultado"] == "procedente"


# ---------------------------------------------------------------- M4. acórdão no formato do TJSP
def test_voto_depois_da_data_do_acordao_e_parte_do_mesmo_acordao():
    """Antes: o "VOTO" na página seguinte abria outro acórdão e o voto vencido virava a decisão que vale."""
    doc, a = _analise([
        INICIAL, _sentenca(PROCEDENTE),
        ["# ACÓRDÃO", "Vistos, relatados e discutidos estes autos, ACORDAM os Desembargadores, por maioria, em negar "
         "provimento ao recurso, vencido o Relator.", "Vila Teste, 20 de setembro de 2026."],
        ["# RELATÓRIO", "Trata-se de apelação interposta pela ré.", "É o relatório.", "# VOTO",
         "O comprovante de entrega é válido.", "Ante o exposto, dou provimento ao recurso para julgar improcedente o "
         "pedido."],
    ])
    assert _pecas(a) == [("peticao_inicial", 1), ("sentenca", 2), ("acordao", 3)]
    dp = a["decisao_principal"]
    assert (dp["tipo"], dp["pagina"], dp["resultado"], dp["decisoes_finais"]) == ("acordao", 3, "recurso não provido", 2)
    assert "RECURSO NÃO PROVIDO" in _resposta(doc, a, "Eu ganhei?")


# ---------------------------------------------------------------- M5. título desconhecido depois de certidão
def test_peticao_com_titulo_fora_da_lista_depois_de_certidao_nao_vira_certidao():
    _, a = _analise([
        ["# CERTIDÃO", "Certifico que a sentença transitou em julgado em 10/07/2026.", "Vila Teste, 11 de julho de 2026.",
         "Escrevente Fictício"],
        ["# REQUERIMENTO DE PENHORA ONLINE", "A autora pede a penhora de valores da ré em 05/07/2026.",
         "Vila Teste, 1 de agosto de 2026."],
    ])
    assert not any("A autora pede" in e["texto"] and e["natureza"] == "fato_registrado" for e in a["linha_do_tempo"])
    assert a["pecas"][0]["data"] == "2026-07-11"  # a data da certidão não é a da petição seguinte


@pytest.mark.parametrize("titulo", ["# CUMPRIMENTO DE SENTENÇA", "# EXCEÇÃO DE PRÉ-EXECUTIVIDADE",
                                    "# IMPUGNAÇÃO AO CUMPRIMENTO DE SENTENÇA"])
def test_titulos_de_peticao_da_fase_de_cumprimento(titulo):
    _, a = _analise([["# CERTIDÃO", "Certifico que a sentença transitou em julgado em 10/07/2026.",
                      "Vila Teste, 11 de julho de 2026."],
                     [titulo, "A autora requer a intimação da ré para pagar o valor da condenação.",
                      "Vila Teste, 1 de agosto de 2026."]])
    assert ("parte", 2) in [(p["origem"], p["pagina_inicial"]) for p in a["pecas"]]
    assert any("A autora requer" in it["texto"] and it["natureza"] == "pedido" for it in a["pedidos"])


# ---------------------------------------------------------------- L1. prazos
@pytest.mark.parametrize("frase,duracao", [
    ("Concedo 15 (quinze) dias de prazo para a autora emendar a inicial.", "15 (quinze) dias"),
    ("Intime-se a ré para, no prazo de quinze (15) dias, pagar o débito.", "quinze (15) dias"),
])
def test_prazo_em_outras_formas(frase, duracao):
    assert analise_mod.prazo_em(frase) == duracao


def test_todos_os_prazos_da_frase_sao_listados():
    frase = "Cite-se a ré, com prazo de 15 dias para contestar, e a audiência será em 30 dias."
    assert analise_mod.prazos_em(frase) == ["15 dias", "30 dias"]
    _, a = _analise([["# DESPACHO", frase, "Vila Teste, 20 de fevereiro de 2026."]])
    assert a["prazos"][0]["duracao"] == "15 dias" and a["prazos"][0]["duracoes"] == ["15 dias", "30 dias"]


# ---------------------------------------------------------------- L3. conteúdo parecido com tarja
@pytest.mark.parametrize("linha", [
    "o contrato foi assinado digitalmente por ambas as partes em 10/01/2026, e a ré o descumpriu.",
    "A autora informou o código de verificação do boleto pago em 10/01/2026.",
    "Para conferir o original, a autora juntou a nota fiscal emitida pela ré.",
])
def test_frase_de_conteudo_parecida_com_tarja_nao_e_apagada(linha):
    assert not extracao_mod.eh_carimbo(linha)
    doc, a = _analise([["# PETIÇÃO INICIAL", "A autora alega, em resumo, que a ré não cumpriu o que foi combinado e que",
                        linha, "Vila Teste, 12 de fevereiro de 2026."]])
    assert any(linha[:30] in it["texto"] for it in a["alegacoes"])
    assert a["controle"]["citacoes_descartadas"] == 0


@pytest.mark.parametrize("tarja", [
    "Documento assinado digitalmente por SISTEMA FICTÍCIO, protocolado em 12/06/2026 às 10:15.",
    "Este documento é cópia do original, assinado digitalmente por FULANO FICTÍCIO, liberado nos autos em 12/06/2026.",
    "Para conferir o original, acesse o site https://exemplo.invalid, informe o processo e o código 1A2B3C.",
    "Assinado eletronicamente por: Fulano Fictício - 12/06/2026 10:15:00",
    "Num. 12345 - Pág. 1",
])
def test_tarjas_do_sistema_continuam_reconhecidas(tarja):
    assert extracao_mod.eh_carimbo(tarja)


def test_tarja_no_meio_do_paragrafo_nao_faz_a_frase_perder_a_citacao():
    doc, a = _analise([["# PETIÇÃO INICIAL", "A autora alega que comprou uma geladeira na loja da ré e que o",
                        "Documento assinado digitalmente por SISTEMA FICTÍCIO, protocolado em 12/06/2026 às 10:15.",
                        "produto nunca foi entregue no endereço combinado.", "Vila Teste, 12 de fevereiro de 2026."]])
    assert a["controle"]["citacoes_descartadas"] == 0
    assert any("comprou uma geladeira" in it["texto"] for it in a["alegacoes"])


# ---------------------------------------------------------------- L4. página com uma linha enorme
def test_pagina_com_titulo_e_uma_linha_enorme_nao_perde_o_texto(monkeypatch):
    monkeypatch.setattr(extracao_mod, "LIMITE_CARACTERES_PAGINA", 5000)
    texto = "PETIÇÃO INICIAL\n" + "A autora alega que a ré não entregou o produto comprado e " * 200
    doc = extrair("p.txt", texto.encode())
    pagina = doc.paginas[0]
    assert pagina.truncada and pagina.estado == "lida" and len(pagina.texto) > 4000


# ---------------------------------------------------------------- auditoria
def test_envio_e_exclusao_de_documento_vao_para_a_trilha_sem_conteudo():
    from sqlalchemy import select

    from app.db import EventoAuditoria, SessionLocal

    resp = client.post("/api/v1/auth/registrar", json={"email": "auditoria-leitor@example.com",
                                                       "senha": "senha-muito-segura"})
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}
    with SessionLocal() as db:
        antes = db.scalar(select(EventoAuditoria.id).order_by(EventoAuditoria.id.desc())) or 0
    conteudo = "PETIÇÃO INICIAL\nA autora Fulana Sigilosa alega que a ré não entregou o produto.".encode()
    enviado = client.post("/api/v1/documentos", files={"arquivo": ("nome-secreto.txt", conteudo, "text/plain")},
                          headers=headers)
    assert enviado.status_code == 201
    assert client.delete(f"/api/v1/documentos/{enviado.json()['id']}", headers=headers).status_code == 204
    with SessionLocal() as db:
        eventos = db.scalars(select(EventoAuditoria).where(EventoAuditoria.id > antes)
                             .order_by(EventoAuditoria.id)).all()
    nomes = [e.evento for e in eventos]
    assert "documento_enviado" in nomes and "documento_apagado" in nomes
    assert nomes.index("documento_enviado") < nomes.index("documento_apagado")
    for e in eventos:
        campos = json.dumps([e.evento, e.conta, e.rede, e.resultado], ensure_ascii=False)
        assert "nome-secreto" not in campos and "Sigilosa" not in campos and "@" not in campos
        assert e.conta is None or len(e.conta) == 32
