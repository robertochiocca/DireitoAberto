import pytest

from app.comparacao import carregar_casos_busca
from app.retrieval import Retriever, normalizar


@pytest.fixture(scope="module")
def retriever():
    return Retriever()


def test_normalizar_remove_acentos_stopwords_e_plural():
    tokens = normalizar("A empresa não quer trocar os produtos defeituosos")
    assert "empresa" in tokens
    assert "produto" in tokens  # plural reduzido
    assert "defeituoso" in tokens
    assert "nao" not in tokens and "não" not in tokens  # stopword
    assert "os" not in tokens


def test_contracoes_e_plural_de_stopword_nao_viram_termo_de_busca(retriever):
    tokens = normalizar("caí num golpe pelos bancos deles nesses casos")
    assert tokens == ["cai", "golpe", "banco", "caso"], tokens
    # "num" tinha IDF alto e casava com "num mesmo contrato" (Lei do Inquilinato).
    ids = [r.id for r in retriever.buscar("caí num golpe do pix")]
    assert "lei8245-37" not in ids, ids


def test_expansao_nao_repete_sinonimo_alcancavel_por_dois_caminhos(retriever):
    """"dono" e "aluguel" expandem os dois para "locador".

    Sem deduplicação o termo pontuava em dobro e bastava um artigo citar
    muito o locador para enterrar o dispositivo que responde à pergunta.
    """
    termos = retriever._expandir_consulta("o dono quer aumentar o aluguel")
    assert len(termos) == len(set(termos)), f"termos repetidos: {termos}"
    assert "locador" in termos


def test_sinonimo_pesa_menos_que_a_palavra_do_cidadao(retriever):
    pesos = retriever._expandir_consulta("o plano negou a cirurgia")
    assert pesos["negou"] == 1.0
    assert pesos["negativa"] == Retriever.PESO_SINONIMO < 1.0
    # Palavra escrita pelo cidadão mantém o peso cheio, mesmo sendo também
    # sinônimo de outra ("aluguel" expande para "locador").
    assert retriever._expandir_consulta("aluguel do locador")["locador"] == 1.0


def test_sinonimo_solto_nao_traz_lei_de_outro_assunto(retriever):
    """"negou" expande para "negativa", que a LAI usa no sentido de pedido de
    informação negado, e para "indeferido", do recurso ao INSS. Casar só um
    desses sinônimos não pode pôr essas leis na resposta sobre plano de saúde."""
    ids = [r.id for r in retriever.buscar("O plano de saúde negou minha cirurgia")]
    assert "lei9656-35c" in ids
    assert "lai-10-11" not in ids, ids
    assert "lei8213-126" not in ids, ids


# Gabarito em data/casos_busca.json, compartilhado com scripts/comparar_retrievers.py:
# um caso por dispositivo do corpus original e um por dispositivo acrescentado na
# expansão — cada novo artigo entra competindo com os demais e pode enterrar um vizinho.
CASOS = carregar_casos_busca()


@pytest.mark.parametrize("pergunta,esperado", CASOS)
def test_artigo_relevante_no_top_3(retriever, pergunta, esperado):
    ids = [r.id for r in retriever.buscar(pergunta, top_k=3)]
    assert esperado in ids, f"esperava {esperado} no top-3, veio {ids}"


def test_pergunta_irrelevante_retorna_vazio_ou_pouco(retriever):
    resultados = retriever.buscar("qual a receita de bolo de cenoura")
    assert len(resultados) <= 1


def test_filtro_por_tema(retriever):
    resultados = retriever.buscar("prazo de cinco anos", tema="tributos")
    assert resultados, "deveria haver resultado no tema tributos"
    assert all(r.tema == "tributos" for r in resultados)


def test_lista_de_temas(retriever):
    temas = retriever.temas()
    assert "consumidor" in temas and "familia" in temas and "previdencia" in temas


def test_scores_ordenados_decrescentes(retriever):
    resultados = retriever.buscar("produto com defeito e a loja não troca")
    scores = [r.score for r in resultados]
    assert scores == sorted(scores, reverse=True)
    assert resultados, "consulta típica deveria retornar resultados"
