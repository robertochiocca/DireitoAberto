"""Glossário de termos processuais em linguagem cotidiana.

As explicações são gerais e descrevem o uso mais comum do termo; o sentido
exato pode variar com o tipo de processo. O leitor só mostra os termos que
aparecem no documento, com as páginas em que aparecem.
"""

from __future__ import annotations

import re

from .extracao import dobrar

# termo exibido → (padrão de busca sem acento, explicação)
TERMOS: dict[str, tuple[str, str]] = {
    "Petição inicial": (r"peticao inicial|\binicial\b",
        "O pedido que abre o processo: quem entra com a ação conta os fatos e diz o que quer do juiz."),
    "Contestação": (r"contestacao",
        "A defesa de quem foi processado: responde aos fatos e aos pedidos da petição inicial."),
    "Réplica": (r"\breplica\b",
        "A resposta de quem abriu o processo aos argumentos da contestação."),
    "Citação": (r"\bcitad[oa]s?\b|\bcitacao\b|\bcite-se\b",
        "O ato que avisa oficialmente a pessoa processada de que existe a ação, para que possa se defender."),
    "Intimação": (r"intimad[oa]s?|intimacao|intimem-se|intime-se",
        "Aviso oficial a uma das partes sobre um ato do processo. Muitos prazos começam a contar a partir dela."),
    "Despacho": (r"\bdespacho\b",
        "Ordem do juiz para o processo andar (ex.: mandar citar, marcar audiência), sem decidir quem tem razão."),
    "Decisão interlocutória": (r"decisao interlocutoria|\bdecisao\b",
        "Decisão do juiz no meio do processo sobre uma questão específica (ex.: um pedido urgente), sem encerrá-lo."),
    "Sentença": (r"\bsentenca\b",
        "A decisão do juiz que encerra a fase principal do processo na primeira instância. Em regra, ainda cabe recurso."),
    "Acórdão": (r"\bacordao\b",
        "Decisão tomada por um grupo de juízes (desembargadores ou ministros) de um tribunal, geralmente ao julgar recurso."),
    "Procedente / improcedente": (r"procedente",
        "Procedente: o juiz deu razão ao pedido. Improcedente: negou. Parcialmente procedente: aceitou só uma parte."),
    "Tutela de urgência / liminar": (r"tutela de urgencia|tutela antecipada|liminar",
        "Pedido para o juiz decidir algo logo, antes do fim do processo, porque esperar causaria prejuízo."),
    "Deferir / indeferir": (r"\bdefiro\b|\bdeferid|\bindefiro\b|\bindeferid",
        "Deferir é aceitar um pedido; indeferir é negar."),
    "Inversão do ônus da prova": (r"onus da prova",
        "Quem precisa provar os fatos passa a ser a outra parte (comum em relação de consumo, a favor do consumidor)."),
    "Audiência de conciliação": (r"audiencia de conciliacao|conciliacao",
        "Encontro para tentar um acordo entre as partes, com conciliador ou juiz, antes de seguir com o processo."),
    "Trânsito em julgado": (r"transit\w* em julgado",
        "Quando não cabe mais recurso contra a decisão: ela se torna definitiva."),
    "Recurso": (r"\brecurso\b|apelacao|agravo|embargos de declaracao|recurso inominado",
        "Pedido para que a decisão seja revista, em regra por um tribunal ou turma recursal. Tem prazo para ser feito."),
    "Recurso inominado": (r"recurso inominado",
        "O recurso contra sentença nos Juizados Especiais Cíveis, julgado por uma Turma Recursal."),
    "Juizado Especial Cível": (r"juizado especial",
        "Justiça para causas de menor valor e complexidade, mais simples e rápida; até certo valor, sem advogado."),
    "Dano moral": (r"danos? mora(l|is)",
        "Indenização por sofrimento, humilhação ou transtorno que ultrapassa o aborrecimento comum."),
    "Dano material": (r"danos? materia(l|is)",
        "Indenização pelo prejuízo financeiro comprovado (o que se perdeu ou se gastou)."),
    "Correção monetária e juros": (r"correcao monetaria|\bjuros\b",
        "Correção atualiza o valor pela inflação; juros remuneram o atraso no pagamento."),
    "Custas e honorários": (r"\bcustas\b|honorarios",
        "Custas são as taxas do processo; honorários são o pagamento do advogado (inclusive o da parte que venceu)."),
    "Gratuidade da justiça": (r"gratuidade|justica gratuita|assistencia judiciaria",
        "Isenção das custas para quem não pode pagá-las sem prejuízo do próprio sustento."),
    "Revelia": (r"\brevel\b|revelia",
        "Quando a pessoa processada não apresenta defesa no prazo; os fatos alegados contra ela podem ser "
        "presumidos verdadeiros."),
    "Cumprimento de sentença": (r"cumprimento de sentenca",
        "Fase em que se cobra o que a decisão mandou pagar ou fazer, se a parte não cumprir por conta própria."),
    "Autos": (r"\bautos\b",
        "O conjunto de todos os documentos do processo."),
    "Folhas (fls.)": (r"\bfls?\.",
        "Numeração das folhas do processo. Pode ser diferente da página do arquivo PDF."),
    "Laudo": (r"\blaudo\b",
        "Documento técnico com a conclusão de um perito ou especialista sobre um fato."),
    "Preposto": (r"preposto|preposta",
        "Pessoa que representa uma empresa na audiência."),
    "Relação de consumo": (r"relacao de consumo|codigo de defesa do consumidor|\bcdc\b",
        "Relação entre consumidor e fornecedor, protegida pelo Código de Defesa do Consumidor."),
    "Restituição": (r"restituir|restituicao",
        "Devolução de valor pago."),
    "Extinção do processo": (r"extin(go|cao) (o|do) processo",
        "Encerramento do processo; pode ocorrer com ou sem decisão sobre quem tem razão (mérito)."),
    "Homologação": (r"homolog",
        "Quando o juiz aprova um ato das partes, como um acordo, dando a ele força de decisão."),
}

_PADROES = {termo: re.compile(padrao, re.IGNORECASE) for termo, (padrao, _) in TERMOS.items()}


def termos_presentes(paginas: list[tuple[int, str]]) -> list[dict]:
    """[(número da página, texto)] → termos que aparecem, com explicação e páginas."""
    achados: dict[str, list[int]] = {}
    for numero, texto in paginas:
        comparavel = dobrar(texto)  # o texto das páginas já vem em NFC (extracao._limpar)
        for termo, padrao in _PADROES.items():
            if padrao.search(comparavel):
                achados.setdefault(termo, []).append(numero)
    return [
        {"termo": termo, "explicacao": TERMOS[termo][1], "paginas": paginas_termo}
        for termo, paginas_termo in achados.items()
    ]


def explicar(termo: str) -> str | None:
    return TERMOS[termo][1] if termo in TERMOS else None
