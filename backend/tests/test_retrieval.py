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
    ("O plano quer limitar os dias de internação na UTI", "stj-sumula302"),
    ("Não recebo horas extras e a empresa não mostra o ponto", "tst-sumula338"),
    ("Fui demitido por causa de doença grave, é discriminação?", "tst-sumula443"),
    ("Podem me prender por dívida no cartão de crédito?", "stf-sv25"),
]

# Um caso por dispositivo acrescentado na expansão do corpus. Serve de rede:
# cada novo artigo entra competindo com os demais e pode enterrar um vizinho.
CASOS += [
    ("Quais são os direitos sociais na Constituição?", "cf-6"),
    ("Pessoa com deficiência pode assinar contrato sozinha?", "cc-3-4"),
    ("União estável entre duas mulheres é reconhecida?", "cc-1723"),
    ("Herdei junto com a companheira do meu pai, como divide?", "cc-1790"),
    ("Qual o juros de uma dívida atrasada sem contrato?", "cc-389-406"),
    ("Posso alegar que não sabia da lei?", "lindb-3"),
    ("Quantos pontos na carteira dão suspensão?", "ctb-259-261"),
    ("Não era eu dirigindo, como indico o condutor da multa?", "ctb-257"),
    ("Posso recusar o bafômetro?", "ctb-165"),
    ("Tenho desconto se pagar a multa antes do vencimento?", "ctb-284"),
    ("O carro fica apreendido 30 dias no pátio?", "ctb-262"),
    ("Crime de pequena gravidade vai para qual juizado?", "lei9099-61"),
    ("Prazo no juizado conta em dias úteis?", "lei9099-12a"),
    ("Posso trocar meu primeiro nome no cartório?", "lei6015-56"),
    ("Quero tirar o sobrenome do meu ex-marido", "lei6015-57"),
    ("Meu nome saiu escrito errado na certidão", "lei6015-110"),
    ("Nunca fui registrado, como tiro certidão de nascimento?", "lei6015-46"),
    ("Quanto tempo dura o mandato de conselheiro tutelar?", "eca-132"),
    ("Pedi vaga em creche para meu filho de 3 anos", "eca-54"),
    ("Rede social pode deixar criança criar conta sozinha?", "eca-digital"),
    ("Qual a lei do código florestal hoje?", "lei12651-1"),
    ("Quanto tempo o órgão público tem para decidir?", "lei9784-49"),
    ("Pedi informação na prefeitura e não responderam", "lai-10-11"),
    ("Reclamei na ouvidoria e ninguém me respondeu", "lei13460-16"),
    ("Quero que a empresa apague meus dados pessoais", "lgpd-18"),
    ("Recebi uma cobrança sem dizer quem está cobrando", "cdc-42a"),
    ("Minhas dívidas passaram do que ganho, dá para renegociar tudo?", "cdc-54a"),
    ("Comprei num site e quero cancelar, como estornam?", "decreto7962-5"),
    ("Podem tomar minha casa por causa de dívida?", "lei8009-1"),
    ("O dono exige fiador e depósito ao mesmo tempo", "lei8245-37"),
    ("Estou devendo aluguel e vou ser despejado, posso pagar?", "lei8245-62"),
    ("Não tenho dinheiro para pagar as custas do processo", "cpc-98"),
    ("Onde consigo advogado gratuito?", "lc80-1"),
    ("Quero processar a prefeitura, qual o valor máximo?", "lei12153-2"),
    ("Fui demitido por justa causa, isso é legal?", "clt-482"),
    ("Meu patrão não deposita o FGTS, posso sair com direitos?", "clt-483"),
    ("Preciso de advogado para entrar na justiça do trabalho?", "clt-791"),
    ("Como pedir medida protetiva contra meu marido?", "lei11340-22"),
    ("Com quantos anos o ônibus é gratuito para idoso?", "lei10741-39"),
    ("Posso receber o BPC sem nunca ter contribuído?", "loas-20"),
    ("A curatela tira todos os direitos da pessoa?", "lei13146-84"),
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
