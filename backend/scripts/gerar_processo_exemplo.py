"""Gera o processo FICTÍCIO usado na demonstração e na avaliação do leitor.

    python scripts/gerar_processo_exemplo.py

Escreve `data/exemplos/processo-ficticio.pdf`. Pessoas, empresa, juízo, comarca
e número são inventados: o número tem formato e dígito verificador válidos,
mas o sequencial 0000000 e o tribunal 99 não existem, para não coincidir com
processo real.

O conteúdo foi escrito para exercitar o que o leitor precisa distinguir:
alegações das duas partes, pedidos, decisão interlocutória, certidões, uma
folha digitalizada sem texto (o aviso de recebimento), folhas citadas que não
estão no arquivo (fls. 9 e 21), numeração de folhas diferente da numeração
do PDF e uma sentença sem certidão de trânsito em julgado. O gabarito do que
deve ser encontrado está em `data/exemplos/processo-ficticio.gabarito.json`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.leitor.pdf_simples import gerar_pdf

DESTINO = Path(__file__).resolve().parent.parent / "data" / "exemplos" / "processo-ficticio.pdf"
NUMERO = "0000000-58.2026.8.99.0001"
AVISO = "DOCUMENTO FICTÍCIO PARA DEMONSTRAÇÃO — nomes, números e fatos são inventados."

PAGINAS: list[list[str] | None] = [
    [  # p. 1 — fls. 1
        "# DOCUMENTO FICTÍCIO — DEMONSTRAÇÃO DO DIREITOABERTO",
        "Nenhuma pessoa, empresa, juízo ou processo real é retratado. Nomes, números e fatos são inventados.",
        "# AUTUAÇÃO",
        f"Processo nº {NUMERO}",
        "Classe: Procedimento do Juizado Especial Cível",
        "Assunto: Indenização por Dano Moral; Produto com defeito",
        "Juízo: 1º Juizado Especial Cível da Comarca de Vila Ficta",
        "Autora: Ana Exemplo da Silva",
        "Ré: Loja Ficta Comércio de Eletrônicos Ltda.",
        "Distribuído em 12/02/2026.",
    ],
    [  # p. 2 — fls. 2
        "# PETIÇÃO INICIAL",
        "EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DO 1º JUIZADO ESPECIAL CÍVEL DA COMARCA DE VILA FICTA",
        "ANA EXEMPLO DA SILVA, brasileira, professora, vem propor AÇÃO DE OBRIGAÇÃO DE FAZER CUMULADA COM "
        "INDENIZAÇÃO POR DANOS MORAIS em face de LOJA FICTA COMÉRCIO DE ELETRÔNICOS LTDA., pelos fatos a seguir.",
        "# DOS FATOS",
        "Em 10/01/2026, a autora comprou na loja da ré um notebook pelo valor de R$ 3.499,00, conforme nota "
        "fiscal de fls. 9.",
        "Em 25/01/2026, o aparelho deixou de ligar, e a autora o levou no mesmo dia à assistência técnica "
        "indicada pela ré.",
        "Passados mais de 30 dias, o defeito não foi sanado e a ré se recusa a trocar o produto ou a devolver o "
        "valor pago.",
        "A autora alega que ficou sem o computador que usa para trabalhar e que precisou alugar outro "
        "equipamento.",
        "# DO DIREITO",
        "O art. 18, § 1º, do Código de Defesa do Consumidor garante ao consumidor, não sanado o vício em 30 "
        "dias, a substituição do produto, a restituição da quantia paga ou o abatimento do preço.",
    ],
    [  # p. 3 — fls. 3
        "# DOS PEDIDOS",
        "Diante do exposto, requer:",
        "a) a concessão de tutela de urgência para que a ré entregue um notebook novo, do mesmo modelo, no "
        "prazo de 5 (cinco) dias;",
        "b) a condenação da ré à restituição da quantia paga, de R$ 3.499,00, caso não seja possível a "
        "substituição;",
        "c) a condenação da ré ao pagamento de indenização por danos morais de R$ 10.000,00;",
        "d) a inversão do ônus da prova, nos termos do art. 6º, VIII, do CDC.",
        "Dá-se à causa o valor de R$ 13.499,00.",
        "Vila Ficta, 12 de fevereiro de 2026.",
        "Advogado Fictício — OAB/XX 000.000",
    ],
    [  # p. 4 — fls. 4
        "# DECISÃO",
        f"Processo nº {NUMERO}",
        "Vistos. Recebo a inicial.",
        "INDEFIRO, por ora, o pedido de tutela de urgência, porque não há nos autos prova de que a "
        "substituição imediata seja indispensável: a autora não demonstrou depender exclusivamente do aparelho.",
        "DEFIRO a inversão do ônus da prova, nos termos do art. 6º, VIII, do CDC.",
        "Cite-se a ré. Designo audiência de conciliação para 14/04/2026, às 14h00.",
        "Intimem-se.",
        "Vila Ficta, 20 de fevereiro de 2026.",
        "Juíza de Direito Fictícia",
    ],
    [  # p. 5 — fls. 5
        "# CERTIDÃO",
        "Certifico que, em 03/03/2026, a ré foi citada por carta com aviso de recebimento, conforme o AR "
        "juntado a seguir.",
        "Vila Ficta, 5 de março de 2026.",
        "Escrevente Fictício",
    ],
    None,  # p. 6 — fls. 6: aviso de recebimento digitalizado, sem camada de texto
    [  # p. 7 — fls. 7
        "# TERMO DE AUDIÊNCIA DE CONCILIAÇÃO",
        "Aos 14 dias do mês de abril de 2026, presentes a autora e a preposta da ré, a tentativa de "
        "conciliação foi infrutífera.",
        "A ré apresentará contestação no prazo de 15 (quinze) dias.",
        "Conciliadora Fictícia",
    ],
    [  # p. 8 — fls. 18 (as fls. 8 a 17 e 19 a 29 não estão neste arquivo)
        "# CONTESTAÇÃO",
        "LOJA FICTA COMÉRCIO DE ELETRÔNICOS LTDA., ré nos autos da ação movida por ANA EXEMPLO DA SILVA, "
        "apresenta sua contestação.",
        "A ré sustenta que o defeito decorreu de mau uso, pois o laudo técnico juntado às fls. 21 aponta sinais "
        "de líquido na placa do aparelho.",
        "A ré afirma, ainda, que ofereceu o conserto do notebook e que a autora o recusou.",
        "Alega também que não houve dano moral, mas mero aborrecimento do cotidiano.",
        "Requer a improcedência de todos os pedidos.",
        "Vila Ficta, 28 de abril de 2026.",
        "Advogada Fictícia — OAB/XX 111.111",
    ],
    [  # p. 9 — fls. 30
        "# SENTENÇA",
        f"Processo nº {NUMERO}",
        "Vistos. Dispensado o relatório, nos termos do art. 38 da Lei nº 9.099/1995.",
        "A relação é de consumo. O laudo de fls. 21, produzido pela assistência técnica indicada pela própria "
        "ré, não é conclusivo quanto ao mau uso, e a ré não se desincumbiu do ônus da prova, que foi invertido.",
        "Não sanado o vício no prazo de 30 dias, a autora tem direito à restituição da quantia paga, nos termos "
        "do art. 18, § 1º, II, do CDC.",
        "Quanto ao dano moral, a privação do equipamento de trabalho por mais de dois meses ultrapassa o mero "
        "aborrecimento.",
        "Ante o exposto, JULGO PARCIALMENTE PROCEDENTES os pedidos para:",
        "a) CONDENAR a ré a restituir à autora a quantia de R$ 3.499,00, com correção monetária desde "
        "10/01/2026 e juros desde a citação;",
        "b) CONDENAR a ré ao pagamento de R$ 4.000,00 a título de danos morais.",
        "Após o pagamento, a ré deverá retirar o notebook defeituoso na residência da autora no prazo de 15 "
        "(quinze) dias.",
        "Julgo improcedente o pedido de substituição do produto, prejudicado pela restituição.",
        "Sem custas e honorários nesta instância, nos termos do art. 55 da Lei nº 9.099/1995.",
        "Publique-se. Intimem-se.",
        "Vila Ficta, 10 de junho de 2026.",
        "Juíza de Direito Fictícia",
    ],
    [  # p. 10 — fls. 31
        "# CERTIDÃO",
        "Certifico que a sentença foi disponibilizada no Diário da Justiça Eletrônico em 12/06/2026 e que as "
        "partes foram intimadas por meio de seus advogados.",
        "Certifico, ainda, que o prazo para a interposição de recurso inominado é de 10 (dez) dias.",
        "Vila Ficta, 12 de junho de 2026.",
        "Escrevente Fictício",
    ],
]
FOLHAS = ["1", "2", "3", "4", "5", "6", "7", "18", "30", "31"]


def main() -> None:
    paginas = [p if p is None else p + [AVISO] for p in PAGINAS]
    rodapes = [f"fls. {f}" for f in FOLHAS]
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_bytes(gerar_pdf(paginas, rodapes))
    print(f"{DESTINO} ({len(paginas)} páginas)")


if __name__ == "__main__":
    main()
