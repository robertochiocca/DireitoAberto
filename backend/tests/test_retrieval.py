import pytest

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


CASOS = [
    ("A empresa não quer trocar meu notebook defeituoso", "cdc-18"),
    ("Comprei pela internet e me arrependi da compra", "cdc-49"),
    ("Fui demitido sem justa causa, quais meus direitos?", "cf-7"),
    ("Meu nome foi negativado no Serasa por dívida que não reconheço", "cdc-43"),
    ("Recebi uma multa de trânsito injusta, como recorrer?", "ctb-282"),
    ("O dono do imóvel quer aumentar o aluguel antes de um ano", "lei10192-2"),
    ("Posso entrar no juizado especial sem advogado?", "lei9099-9"),
    ("Quanto devo pagar de pensão alimentícia para meu filho?", "cc-1694"),
    ("Quero me divorciar, preciso de processo?", "cf-226"),
    ("Como fica a guarda compartilhada dos filhos?", "cc-1583"),
    ("O plano de saúde negou minha cirurgia de emergência", "lei9656-35c"),
    ("O INSS negou minha aposentadoria, como recorrer?", "lei8213-126"),
    ("Caí num golpe do pix, o banco devolve?", "stj-sumula479"),
    ("Meu voo foi cancelado e a companhia não deu assistência", "anac-400"),
    ("O condomínio me multou e o vizinho faz barulho de madrugada", "cc-1336"),
    ("A prefeitura cobrou IPTU de dez anos atrás", "ctn-174"),
    ("Meu pai faleceu, como faço o inventário da herança?", "cc-1784"),
]


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
