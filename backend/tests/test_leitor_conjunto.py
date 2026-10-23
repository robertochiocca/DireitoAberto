"""Conjunto adversarial do leitor (data/exemplos/adversariais) e a régua que o mede.

O conjunto tem processos FICTÍCIOS que reproduzem as falhas da auditoria do
leitor; cada um tem gabarito escrito à mão. Estes testes garantem que (1) o
leitor passa em tudo, (2) os PDFs versionados são exatamente o que o gerador
produz e (3) a própria régua reprova versões ruins — uma régua que aprova tudo
não mede nada.
"""

import json

import pytest

from app.leitor import avaliacao
from app.leitor.analise import analisar
from app.leitor.conjunto_adversarial import DOCUMENTOS, pdf
from app.leitor.extracao import extrair
from app.leitor.perguntas import responder

CONJUNTO = avaliacao.CONJUNTO
GABARITOS = sorted(CONJUNTO.glob("*.gabarito.json"))


@pytest.fixture(scope="module")
def medida():
    return avaliacao.avaliar_conjunto()


def test_conjunto_adversarial_passa_inteiro(medida):
    falhas = {nome: d["falhas"] for nome, d in medida["documentos"].items() if d["falhas"]}
    assert falhas == {}
    assert medida["total"]["documentos"] == len(DOCUMENTOS) >= 15
    assert medida["citacoes"]["total"] == medida["citacoes"]["verificadas"] > 0


def test_pdfs_versionados_sao_os_que_o_gerador_produz():
    assert {g.name.removesuffix(".gabarito.json") for g in GABARITOS} == set(DOCUMENTOS)
    for nome in DOCUMENTOS:
        assert (CONJUNTO / f"{nome}.pdf").read_bytes() == pdf(nome), nome


def test_gabaritos_so_usam_verificacoes_conhecidas():
    conhecidas = {"pecas", "pecas_contem", "peca_ausente", "peca_origem", "sem_origem", "numero_processo", "parte",
                  "decisao_principal", "transito_certificado", "estado_pagina", "leitura_completa", "aviso_contem",
                  "inconsistencia", "item_presente", "item_ausente", "nenhum_item_com_natureza", "prazo",
                  "prazo_ausente", "resumo_nao_contem", "resposta"}
    for caminho in GABARITOS:
        gabarito = json.loads(caminho.read_text(encoding="utf-8"))
        assert gabarito["verificacoes"] and gabarito["cobre"], caminho.name
        assert {v["tipo"] for v in gabarito["verificacoes"]} <= conhecidas, caminho.name


def test_regua_reprova_versao_que_recusa_o_documento():
    def recusa(nome, conteudo, **_):
        raise ValueError("documento recusado")

    medida = avaliacao.avaliar_conjunto(funcoes=(recusa, analisar, responder))
    assert medida["total"]["aprovadas"] == 0
    assert all(d["erro"] for d in medida["documentos"].values())


def test_regua_detecta_afirmacao_proibida():
    """Uma versão que declarasse trânsito em julgado em todo processo tem de reprovar."""
    def analisar_errado(doc):
        a = analisar(doc)
        a["transito_em_julgado"] = a["decisoes"][:1] or [{"texto": "x", "citacoes": []}]
        return a

    medida = avaliacao.avaliar_conjunto(funcoes=(extrair, analisar_errado, responder))
    reprovados = {nome for nome, d in medida["documentos"].items() if d["falhas"]}
    assert {"injecao-estrutural", "contradicoes", "titulos-repetidos"} <= reprovados
