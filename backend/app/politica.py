"""Política de resposta: o que a API faz com a evidência que tem.

Cinco modos, decididos por regras sobre a busca, a validação e a verificação do texto gerado — nunca pela
confiança que o modelo de linguagem declara:

- **responder** — fundamentação suficiente;
- **responder_com_ressalvas** — responde, mas diz o que falta (texto não conferido, revisão pendente,
  ligação fraca com a pergunta, norma fora da base, data incerta);
- **pedir_esclarecimento** — a resposta depende de algo que a pergunta não diz (a data dos fatos, uma data
  que não existe);
- **nao_verificado** — a base não tem o assunto: não há conclusão a dar;
- **recomendar_profissional** — a pergunta pede decisão sobre o caso concreto (processar? aceitar? vou
  ganhar? quanto vou receber?): a resposta dá a regra geral e diz por que o caso precisa de advogado ou da
  Defensoria. O sistema não prevê resultado nem calcula valores.

Texto gerado por LLM que não passa na verificação (`verificador.py`) não é entregue: a API usa a resposta
extrativa e diz por quê.
"""

from __future__ import annotations

import re
import unicodedata

MODOS = {
    "responder": "Resposta fundamentada nas fontes encontradas",
    "responder_com_ressalvas": "Resposta parcial: veja o que não foi possível confirmar",
    "pedir_esclarecimento": "Preciso de mais informação para responder com segurança",
    "nao_verificado": "Não foi possível verificar com a base disponível",
    "recomendar_profissional": "Seu caso precisa de análise individual por profissional",
}

_CASO_INDIVIDUAL = re.compile(
    r"\b(devo (?:processar|entrar na justica|aceitar|assinar|pedir demissao|pagar|recorrer|fazer acordo)|"
    r"vale a pena (?:processar|entrar|recorrer)|vou ganhar|tenho chance|tenho chances|quais as minhas chances|"
    r"quanto (?:eu )?(?:vou|irei) (?:receber|ganhar|pagar)|quanto tenho (?:a|para) receber|calcul(?:e|ar) (?:a |o )?minh[ao]|"
    r"o juiz vai|vou ser pres[oa]|vao me prender|ganho a causa|perco a causa)\b"
)
_FORA_DA_BASE = re.compile(
    r"\b(lei estadual|lei municipal|lei organica do municipio|codigo de posturas|constituicao do estado|"
    r"em portugal|nos estados unidos|na argentina|no exterior|outro pais|direito estrangeiro)\b"
)
PROXIMOS_PASSOS = (
    "Para o seu caso concreto, procure a Defensoria Pública (gratuita para quem não pode pagar), um advogado "
    "ou, em questões de consumo, o Procon. Leve os documentos e as datas dos fatos."
)


def _plano(texto: str) -> str:
    sem = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem if not unicodedata.combining(c))


def caso_individual(pergunta: str) -> bool:
    return bool(_CASO_INDIVIDUAL.search(_plano(pergunta)))


def decidir(pergunta: str, consulta, validacao: dict, problemas_do_texto: list[dict] | None,
            termos_casados: list[str] | None = None, termos_da_pergunta: int = 0) -> dict:
    """Modo da resposta, os motivos (em linguagem simples) e os próximos passos seguros."""
    motivos: list[str] = []
    plano = _plano(pergunta)

    if consulta.abstencao:
        modo = "nao_verificado"
        motivos.append("a base do DireitoAberto não tem dispositivos que tratem do assunto com segurança")
    elif consulta.temporal.pede_esclarecimento:
        modo = "pedir_esclarecimento"
        motivos.append(consulta.temporal.motivo or "a resposta depende de uma data que a pergunta não informa")
    elif caso_individual(pergunta):
        modo = "recomendar_profissional"
        motivos.append("a pergunta pede uma decisão ou previsão sobre o seu caso, o que exige análise individual; "
                       "abaixo está só a regra geral")
    else:
        modo = "responder"

    if modo in ("responder", "recomendar_profissional"):
        if m := _FORA_DA_BASE.search(plano):
            motivos.append(f"a pergunta menciona “{m.group(0)}”, e a base cobre só normas federais brasileiras")
        if termos_casados is not None and len(termos_casados) == 1 and termos_da_pergunta >= 3:
            motivos.append(f"ligação fraca com a pergunta: só “{termos_casados[0]}” coincide com o dispositivo mais "
                           "próximo — pode não ser o seu assunto")
        if validacao["estado"] in ("revisao_humana_recomendada", "conflito_de_fontes",
                                   "fonte_desatualizada_ou_indisponivel"):
            falhas = [v["detalhe"] for v in validacao["verificacoes"] if v["ok"] is False]
            motivos.append(f"{validacao['rotulo'].lower()}: " + "; ".join(falhas[:2]))
        nao_conferidos = [a.artigo for a in consulta.artigos if not getattr(a, "trechos_oficiais", None)]
        if nao_conferidos:
            motivos.append("sem texto oficial conferido nesta base para: " + ", ".join(nao_conferidos[:3]))
        if problemas_do_texto:
            motivos.append("o texto gerado por IA não passou na verificação e foi substituído pela resposta extrativa "
                           f"({problemas_do_texto[0]['detalhe']})")
        if modo == "responder" and motivos:
            modo = "responder_com_ressalvas"

    return {"modo": modo, "rotulo": MODOS[modo], "motivos": motivos,
            "proximos_passos": PROXIMOS_PASSOS if modo != "nao_verificado" else
            "Tente reformular com outras palavras, ou procure a Defensoria Pública, o Procon ou um advogado."}
