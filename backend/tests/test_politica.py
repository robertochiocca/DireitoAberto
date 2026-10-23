"""Verificação do texto gerado (app/verificador.py) e política de resposta (app/politica.py). Sem LLM real:
o texto "gerado" é fixo, para testar o que a API faz com ele."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.consulta import consultar
from app.main import app
from app.politica import caso_individual
from app.retrieval import Resultado, Retriever
from app.verificador import verificar

client = TestClient(app)
HOJE = date(2026, 10, 21)

CDC_49 = {
    "id": "cdc-49", "lei": "Código de Defesa do Consumidor — Lei nº 8.078/1990", "artigo": "Art. 49", "tema": "consumidor",
    "texto": "O consumidor pode desistir do contrato, no prazo de 7 dias.", "resumo": "Compra fora da loja: 7 dias.",
    "fonte": "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm", "norma": "cdc",
    "trechos_oficiais": [{"dispositivo": "art. 49", "texto": "Art. 49. O consumidor pode desistir do contrato, no "
                          "prazo de 7 dias a contar de sua assinatura ou do ato de recebimento do produto ou serviço, "
                          "sempre que a contratação de fornecimento de produtos e serviços ocorrer fora do "
                          "estabelecimento comercial, especialmente por telefone ou a domicílio."}],
    "vigencia": {"status": "vigente", "conferida_em": "2026-10-16"},
}


def _art():
    return [Resultado.de_artigo(CDC_49, 9.0)]


# ---------------------------------------------------------------- verificador
def test_texto_fiel_as_fontes_nao_tem_problema():
    texto = ('Pelo art. 49 do CDC, o consumidor pode desistir em 7 dias: "O consumidor pode desistir do contrato, '
             'no prazo de 7 dias a contar de sua assinatura". Procure o Procon.')
    assert verificar(texto, _art()) == []


@pytest.mark.parametrize("texto, tipo", [
    ('A lei diz: "o consumidor tem 30 dias para desistir de qualquer compra".', "citacao_sem_fonte"),
    ('Como diz a lei, "Compra fora da loja: 7 dias".', "resumo_citado_como_lei"),  # vem do resumo, não da lei
    ('A lei fala em "7 dias".', None),  # menos de 4 palavras: não é citação
    ('A lei diz: "O consumidor pode desistir do contrato, no prazo de 7 dias." Ou seja, você tem tempo.', None),
    ("Pelo art. 18 do CDC, a loja troca.", "dispositivo_nao_recuperado"),
    ("A Lei nº 14.181/2021 garante isso.", "norma_nao_recuperada"),
    ("Você tem 45 dias para desistir.", "numero_sem_fonte"),
    ("Com certeza você vai ganhar a causa.", "linguagem_de_certeza"),
])
def test_verificador_aponta_o_que_nao_tem_fonte(texto, tipo):
    tipos = [p["tipo"] for p in verificar(texto, _art())]
    assert (tipo in tipos) if tipo else tipos == []


def test_resumo_da_base_citado_entre_aspas_como_lei():
    art = dict(CDC_49, texto="Quem compra pela internet tem uma semana para se arrepender, sem dar motivo.")
    texto = 'A lei diz que "quem compra pela internet tem uma semana para se arrepender".'
    assert [p["tipo"] for p in verificar(texto, [Resultado.de_artigo(art, 9.0)])] == ["resumo_citado_como_lei"]


def test_numero_por_extenso_no_texto_oficial_confere():
    art = dict(CDC_49, trechos_oficiais=[{"dispositivo": "art. 3º, I",
                                          "texto": "I - as causas cujo valor não exceda a quarenta vezes o salário mínimo;"}])
    assert verificar("O juizado julga causas de até 40 salários mínimos.", [Resultado.de_artigo(art, 9.0)]) == []


def test_texto_reprovado_nao_e_entregue(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "gerar_resposta",
                        lambda *a, **k: 'Você tem "trinta dias corridos para devolver qualquer produto" e com certeza ganha.')
    corpo = client.post("/api/v1/perguntar", json={"pergunta": "Comprei pela internet e me arrependi"}).json()
    assert corpo["gerado_por_llm"] is False and "com certeza ganha" not in corpo["resposta"]
    assert {p["tipo"] for p in corpo["verificacao_do_texto"]} >= {"citacao_sem_fonte", "linguagem_de_certeza"}


# ---------------------------------------------------------------- política de resposta
@pytest.mark.parametrize("pergunta", [
    "Devo processar meu chefe?", "Vou ganhar a causa contra o banco?", "Quanto vou receber na rescisão?",
    "Tenho chance de ganhar?", "Vale a pena processar a empresa aérea?",
])
def test_caso_individual_e_reconhecido(pergunta):
    assert caso_individual(pergunta)


@pytest.mark.parametrize("pergunta", ["Fui demitido, quais são meus direitos?", "Posso devolver um produto?"])
def test_pergunta_geral_nao_e_caso_individual(pergunta):
    assert not caso_individual(pergunta)


@pytest.mark.parametrize("pergunta, modo", [
    ("Comprei pela internet e me arrependi, posso devolver?", {"responder", "responder_com_ressalvas"}),
    ("Como faço para tirar o passaporte?", {"nao_verificado"}),
    ("Antigamente, como era a guarda dos filhos?", {"pedir_esclarecimento"}),
    ("Devo processar a loja que não trocou meu celular com defeito?", {"recomendar_profissional"}),
])
def test_modo_da_resposta(pergunta, modo):
    corpo = client.post("/api/v1/perguntar", json={"pergunta": pergunta}).json()
    assert corpo["politica"]["modo"] in modo
    assert corpo["politica"]["proximos_passos"]
    if corpo["politica"]["modo"] != "responder":
        assert corpo["politica"]["motivos"]


def test_caso_individual_ainda_traz_a_regra_geral():
    corpo = client.post("/api/v1/perguntar",
                        json={"pergunta": "Devo processar a loja que não trocou meu celular com defeito?"}).json()
    assert corpo["artigos"] and corpo["resposta"].startswith("⚑ Seu caso precisa de análise individual")


def test_ligacao_fraca_vira_ressalva():
    # "multa por não votar" casa só "eleição" num dispositivo do ECA: a resposta tem de dizer que pode não ser o
    # assunto (ou se abster).
    corpo = client.post("/api/v1/perguntar", json={"pergunta": "Qual é a multa por não votar na eleição?"}).json()
    assert corpo["politica"]["modo"] in ("nao_verificado", "responder_com_ressalvas")
    if corpo["politica"]["modo"] == "responder_com_ressalvas":
        assert any("ligação fraca" in m for m in corpo["politica"]["motivos"])


# ---------------------------------------------------------------- documento junto da pergunta
NOTA_FISCAL = ("NOTA FISCAL DE VENDA AO CONSUMIDOR. Produto: notebook. Garantia de 90 dias. Defeito na tela. "
               "Loja: Eletro Exemplo Ltda. Troca e devolução conforme o Código de Defesa do Consumidor.")


def test_documento_nao_sequestra_pergunta_fora_do_escopo():
    # Antes: a nota fiscal somada à pergunta trazia o CDC para "habeas corpus" e desligava a abstenção.
    c = consultar(Retriever(), "Como funciona o habeas corpus?", HOJE, contexto_documento=NOTA_FISCAL)
    assert c.abstencao


def test_documento_ajuda_pergunta_vaga_e_nao_atrapalha_a_especifica():
    vaga = consultar(Retriever(), "O que significa isso?", HOJE, contexto_documento=NOTA_FISCAL)
    assert not vaga.abstencao and vaga.artigos[0].tema == "consumidor"
    especifica = consultar(Retriever(), "A loja não quer trocar meu notebook com defeito", HOJE,
                           contexto_documento=NOTA_FISCAL)
    sem_documento = consultar(Retriever(), "A loja não quer trocar meu notebook com defeito", HOJE)
    assert especifica.artigos[0].id == sem_documento.artigos[0].id
