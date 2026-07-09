"""Camada de geração com LLM via API.

A geração é opcional: sem credenciais (ANTHROPIC_API_KEY ou perfil
`ant auth login`), a API responde com o modo extrativo — os artigos
recuperados e uma orientação padrão. Assim o projeto roda de ponta a
ponta sem nenhuma chave.
"""

from __future__ import annotations

import os

try:
    import anthropic
except ImportError:  # dependência opcional
    anthropic = None

MODEL = os.environ.get("DIREITO_ABERTO_MODEL", "claude-opus-4-8")

SYSTEM_PROMPT = """\
Você é o assistente do DireitoAberto, uma plataforma de letramento jurídico \
para o cidadão comum brasileiro. Sua função é INFORMAR, nunca decidir o caso.

Regras:
- Responda em português simples, sem juridiquês, em no máximo 4 parágrafos curtos.
- Baseie-se EXCLUSIVAMENTE nos artigos de lei fornecidos no contexto. Se eles \
não bastarem para responder, diga isso com clareza.
- Use linguagem cautelosa ("em regra", "possivelmente", "no caso típico") — \
detalhes do caso concreto podem mudar a resposta.
- Cite os artigos pelo nome (ex.: "art. 18 do CDC") ao usá-los.
- Termine SEMPRE orientando a procurar a Defensoria Pública (gratuita), o \
Procon ou um advogado para decidir o caso concreto.
- Não invente jurisprudência, números de lei ou prazos que não estejam no contexto.\
"""


def _montar_contexto(artigos) -> str:
    blocos = []
    for art in artigos:
        blocos.append(f"[{art.lei} — {art.artigo}]\n{art.texto}\nFonte: {art.fonte}")
    return "\n\n".join(blocos)


def gerar_resposta(pergunta: str, artigos) -> str | None:
    """Gera a resposta com o LLM. Retorna None se ele estiver indisponível."""
    if anthropic is None or not artigos:
        return None
    if os.environ.get("DIREITO_ABERTO_USAR_LLM", "1") != "1":
        return None
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Artigos de lei recuperados para esta dúvida:\n\n"
                        f"{_montar_contexto(artigos)}\n\n"
                        f"Dúvida do cidadão: {pergunta}"
                    ),
                }
            ],
        )
        if response.stop_reason == "refusal":
            return None
        texto = "".join(b.text for b in response.content if b.type == "text").strip()
        return texto or None
    except Exception:
        # Sem credenciais, sem rede ou erro da API: cai no modo extrativo.
        return None


def resposta_extrativa(pergunta: str, artigos) -> str:
    """Fallback sem LLM: apresenta os artigos encontrados com orientação padrão."""
    if not artigos:
        return (
            "Não encontrei, na base atual do DireitoAberto, artigos de lei "
            "diretamente relacionados à sua dúvida. Tente reformular com "
            "palavras como 'produto com defeito', 'demissão', 'multa', "
            "'aluguel' ou 'nome negativado' — ou procure a Defensoria "
            "Pública (gratuita) para orientação sobre o seu caso."
        )
    linhas = ["Encontrei possível relação da sua situação com os seguintes dispositivos legais:\n"]
    for art in artigos:
        linhas.append(f"• {art.lei}, {art.artigo}: {art.resumo}")
    linhas.append(
        "\nIsto é informação geral, não uma decisão sobre o seu caso. Para agir "
        "com segurança, procure a Defensoria Pública (gratuita), o Procon (em "
        "questões de consumo) ou um advogado."
    )
    return "\n".join(linhas)
