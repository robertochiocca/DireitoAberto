"""Relatório em Markdown de uma versão nova de uma fonte monitorada."""

from __future__ import annotations

_ORDEM_RISCO = {"alto": 0, "medio": 1, "baixo": 2}
_ROTULO_TIPO = {
    "formatacao": "Formatação",
    "anotacao_editorial": "Anotação editorial",
    "norma_nova_citada": "Norma alteradora nova citada (texto igual)",
    "indicio_alteracao_legislativa": "Indício de alteração legislativa",
    "indicio_revogacao": "Indício de revogação",
    "texto_alterado_sem_norma_indicada": "Texto alterado sem norma indicada",
    "indicio_inclusao": "Indício de inclusão",
    "artigo_novo_na_pagina": "Artigo novo na página",
    "artigo_ausente_na_pagina": "Artigo ausente na página",
}


def _rotulo_artigo(chave: str) -> str:
    if chave in ("preambulo", "fecho"):
        return "Preâmbulo" if chave == "preambulo" else "Fecho (assinaturas e nota do DOU)"
    numero, _, repeticao = chave.partition("#")
    return f"Art. {numero}" + (f" (ocorrência {repeticao} na página)" if repeticao else "")


def _citar(texto: str | None) -> str:
    if not texto:
        return "> —"
    return "\n".join(f"> {linha}" for linha in texto.splitlines() or [texto])


def gerar(fonte: dict, versao: dict, anterior: dict | None) -> str:
    mudancas = sorted(versao["mudancas"], key=lambda m: (_ORDEM_RISCO[m["risco"]], m["artigo"]))
    contagem = versao["resumo_mudancas"]
    linhas = [
        f"# Monitor legislativo — {fonte['nome']}",
        "",
        "> Este relatório compara duas coletas da página oficial. Ele aponta **indícios**: a confirmação de "
        "qualquer alteração legislativa é feita no Diário Oficial, e nada aqui foi publicado na base do "
        "DireitoAberto sem revisão humana.",
        "",
        "| | |",
        "|---|---|",
        f"| Fonte | [{fonte['url']}]({fonte['url']}) |",
        f"| Órgão emissor | {fonte.get('orgao_emissor', '—')} |",
        f"| Título na página | {versao.get('titulo') or '—'} |",
        f"| Publicação no DOU (informada pela página) | {versao.get('publicado_no_dou') or 'não identificada'} |",
        f"| Versão anterior | `{anterior['versao']}` (capturada em {anterior['capturada_em']}) |"
        if anterior else "| Versão anterior | — |",
        f"| Versão nova | `{versao['versao']}` (capturada em {versao['capturada_em']}) |",
        f"| Integridade (SHA-256 do texto vigente) | `{versao['hash_sha256']}` |",
        f"| Estado | **{versao['estado']}** |",
        "",
        f"**Mudanças:** {contagem.get('alto', 0)} de risco alto, {contagem.get('medio', 0)} de risco médio, "
        f"{contagem.get('baixo', 0)} de risco baixo.",
        "",
    ]
    if versao["dispositivos_afetados"]:
        linhas += ["## Dispositivos da base afetados", "",
                   *[f"- `{i}`" for i in versao["dispositivos_afetados"]], "",
                   "Enquanto a revisão estiver pendente, a API mostra esses dispositivos como **em revisão**.", ""]
    else:
        linhas += ["## Dispositivos da base afetados", "", "Nenhum dispositivo da base usa os artigos alterados.", ""]
    if versao.get("regressao"):
        falhas = [r for r in versao["regressao"] if not r["ok"]]
        linhas += ["## Regressão da busca", "",
                   f"{len(versao['regressao']) - len(falhas)} de {len(versao['regressao'])} perguntas do gabarito "
                   "ligadas a esses dispositivos continuam com o dispositivo esperado no top-3 (a base ainda não "
                   "foi alterada; rode de novo depois de atualizá-la).", ""]
        linhas += [f"- ❌ \"{r['pergunta']}\" → esperado `{r['esperado']}`" for r in falhas]
        linhas.append("")
    linhas += ["## Mudanças, da maior para a menor prioridade", ""]
    for m in mudancas:
        linhas += [
            f"### {_rotulo_artigo(m['artigo'])} — {_ROTULO_TIPO[m['tipo']]} (risco {m['risco']})",
            "",
            m["explicacao"],
            "",
        ]
        if m["normas_citadas"]:
            linhas += [f"Normas citadas nas anotações novas: {', '.join(m['normas_citadas'])}.", ""]
        linhas += ["**Antes:**", "", _citar(m["trecho_anterior"]), "", "**Depois:**", "", _citar(m["trecho_novo"]), ""]
    linhas += [
        "## Como decidir",
        "",
        "```bash",
        f"python scripts/monitor.py decidir --versao {versao['versao']} --resultado sem_impacto "
        "--responsavel \"Nome\" --nota \"o que foi conferido\"",
        "# resultados: sem_impacto · corpus_atualizado · rejeitada",
        "```",
        "",
    ]
    return "\n".join(linhas)
