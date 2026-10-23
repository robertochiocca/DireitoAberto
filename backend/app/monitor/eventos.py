"""Eventos jurídicos indicados por uma versão nova: o tipo de cada mudança traduzido para o que pode ter
acontecido com a norma.

Publicação, entrada em vigor, alteração de redação, revogação e consolidação são fatos diferentes e
nunca se confundem aqui. Todos são **indícios** tirados da página compilada: a confirmação é no Diário
Oficial. A primeira captura de uma fonte não é a publicação da norma — é o início do monitoramento.
Mudança só de forma ou de anotação de navegação não indica evento jurídico nenhum.
"""

from __future__ import annotations

# tipo de mudança (app/monitor/comparar.py) → evento
EVENTO_DA_MUDANCA = {
    "indicio_alteracao_legislativa": "alteracao_redacao",
    "norma_nova_citada": "alteracao_redacao",
    "indicio_inclusao": "inclusao",
    "indicio_revogacao": "revogacao_parcial",
    "artigo_tachado_na_pagina": "revogacao_parcial",
    "indicio_revogacao_total": "revogacao_total",
    "anotacao_de_vigencia": "entrada_em_vigor",
    "anotacao_de_controle_constitucional": "controle_constitucionalidade",
    "texto_alterado_sem_norma_indicada": "consolidacao_ou_republicacao",
    "retorno_a_versao_anterior": "consolidacao_ou_republicacao",
    "remissao_a_norma_nova": "relacao_com_outra_norma",
    # Sem anotação de origem, não há como dizer o que aconteceu: fica explícito.
    "artigo_novo_na_pagina": "indeterminado",
    "artigo_ausente_na_pagina": "indeterminado",
}

DESCRICAO = {
    "inicio_do_monitoramento": "primeira captura da página (não é a data de publicação da norma)",
    "alteracao_redacao": "possível alteração da redação por outra norma",
    "inclusao": "possível inclusão de dispositivo por outra norma",
    "revogacao_parcial": "possível revogação de dispositivo",
    "revogacao_total": "possível revogação da norma inteira",
    "entrada_em_vigor": "anotação de vigência ou produção de efeitos (a data em que o dispositivo vale pode ter mudado)",
    "controle_constitucionalidade": "anotação de decisão de controle de constitucionalidade",
    "consolidacao_ou_republicacao": "texto mudou sem norma indicada: retificação, republicação ou correção da página?",
    "relacao_com_outra_norma": "remissão nova a outra norma, sem mudança no texto",
    "indeterminado": "mudança na página sem indicação do que aconteceu (não é revogação nem inclusão confirmada)",
}


def derivar(mudancas: list[dict], linha_de_base: bool = False) -> list[dict]:
    """[{tipo, descricao, artigos, normas_citadas}] na ordem da primeira mudança de cada tipo."""
    if linha_de_base:
        return [{"tipo": "inicio_do_monitoramento", "descricao": DESCRICAO["inicio_do_monitoramento"],
                 "artigos": [], "normas_citadas": []}]
    eventos: dict[str, dict] = {}
    # Na revogação da norma inteira, os artigos riscados ou sumidos são consequência dela — não revogações
    # parciais nem mudanças sem explicação.
    total = any(m["tipo"] == "indicio_revogacao_total" for m in mudancas)
    for m in mudancas:
        tipo = EVENTO_DA_MUDANCA.get(m["tipo"])
        if tipo is None or (total and tipo in ("revogacao_parcial", "indeterminado")):
            continue
        e = eventos.setdefault(tipo, {"tipo": tipo, "descricao": DESCRICAO[tipo], "artigos": [], "normas_citadas": []})
        if m["artigo"] not in e["artigos"]:
            e["artigos"].append(m["artigo"])
        for norma in m.get("normas_citadas", []):
            if norma not in e["normas_citadas"]:
                e["normas_citadas"].append(norma)
    return list(eventos.values())
