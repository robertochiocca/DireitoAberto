# Fontes jurídicas: inventário, proveniência e verificação

> Estado em 19/10/2026. Este documento separa o que foi **conferido contra a fonte oficial**
> nesta auditoria do que apenas **consta do corpus**. Conferência técnica de texto não é revisão
> jurídica: nenhum item aqui foi revisado por profissional do Direito.

## O que existe no banco

O conhecimento jurídico do sistema vive em um único arquivo versionado no git,
`backend/data/legislacao.json`. Não há banco de normas, nem coleta automática: o texto foi
consolidado à mão a partir das fontes oficiais.

| Item | Valor |
|---|---|
| Dispositivos | 79 (72 de lei/decreto/resolução, 7 súmulas) |
| Situação declarada | 75 `vigente`, 2 `em_vacatio`, 1 `revogada`, 1 `inconstitucional` |
| Última conferência de vigência (`conferida_em`) | 51 em 16/10/2026, 3 em 17/10/2026, 25 em 18/10/2026 |
| Domínio da fonte | planalto.gov.br 70 · stj.jus.br 4 · jurisprudencia.tst.jus.br 2 · portal.stf.jus.br 1 · gov.br 1 · anac.gov.br 1 |
| Campo `revisado` | ausente em todas as entradas (existe só nos esqueletos gerados pelos scripts de ingestão) |

Cada entrada tem `id`, `lei`, `artigo`, `tema`, `texto`, `resumo`, `palavras_chave`, `fonte` e o
bloco `vigencia` (`status`, `entra_em_vigor_em`, `alterada_por`, `nota`, `conferida_em`).

### O que falta para rastreabilidade

Nenhuma entrada registra:

- **quando o texto foi capturado** e de qual versão da página compilada (só a vigência tem data);
- **hash** do texto de origem, para detectar que a fonte mudou;
- **se o `texto` é transcrição literal ou condensação**. Seis entradas marcam "(síntese)" no campo
  `artigo`; as demais não dizem, e a amostra abaixo mostra condensações sem marca;
- **quem revisou** e quando;
- **data de publicação** da norma (diferente de vigência e de conferência).

Sem isso, o sistema não consegue provar que a citação corresponde ao texto oficial, nem perceber
quando o Planalto atualiza a página compilada. Os ciclos 4 e 5 do roadmap tratam disso.

## Conferência contra a fonte oficial (amostra desta auditoria)

As páginas foram baixadas em 19/10/2026 com um `User-Agent` identificado.

### Fidelidade textual — CDC (8 entradas)

Método: texto do corpus e da página compilada normalizados (minúsculas, sem acento, só letras e
números); mede-se quantas janelas de 8 palavras do corpus aparecem na página.

| Entrada | Janelas encontradas | Leitura |
|---|---|---|
| `cdc-14` (art. 14, caput) | 29/29 | literal |
| `cdc-42` | 51/51 | literal |
| `cdc-42a` | 36/36 | literal |
| `cdc-49` | 70/70 | literal |
| `cdc-18` (caput e § 1º) | 78/86 | quase literal, com trechos condensados |
| `cdc-26` | 58/74 | condensado |
| `cdc-43` (§§ 1º e 2º) | 50/68 | condensado |
| `cdc-54a` (arts. 54-A e 104-A) | 35/77 | condensado |

**Conclusão:** metade da amostra é literal; a outra metade condensa o texto sem marcar. Para o
cidadão, a condensação pode ser útil; para citação verificável, o sistema precisa saber qual é qual.

### Normas de outubro de 2026

| Entrada | Conferência | Resultado |
|---|---|---|
| `decreto13135-sac` | texto oficial no Planalto (`_ato2023-2026/2026/decreto/d13135.htm`) | **Existe.** Art. 25: "entra em vigor vinte dias após a data de sua publicação"; DOU de 13/10/2026. Pela LC 95/1998, art. 8º, § 1º (conta-se o dia da publicação e o último dia), o 20º dia é 01/11 e a vigência começa em **02/11/2026** — igual ao corpus. **Problema de proveniência:** a `fonte` do corpus é uma notícia do Ministério da Justiça, não o texto normativo |
| `cf-7-xiii` (EC 141/2026) | texto oficial no Planalto (`emendas/emc/emc141.htm`) e CF compilada | **Existe.** Publicada no DOU de 16/10/2026 (edição extra). **Divergências com o corpus:** (1) o corpus diz que as 42 horas valem "60 dias após a publicação" e fixa 15/12/2026; o art. 6º, I diz "**2 (dois) meses** após a publicação"; (2) o `texto` do corpus apresenta como redação do inciso XIII "quarenta e duas horas semanais, com dois dias de descanso", mas a nova redação oficial do XIII é "8 (oito) horas diárias e 40 (quarenta) horas semanais" — as 42 horas estão na regra de transição (art. 6º) e os dois dias de repouso no inciso XV; (3) o art. 10 põe em vigor o inciso XV após 2 meses e **os demais dispositivos na data da publicação**, o que torna discutível rotular o inciso XIII como `em_vacatio`. **Encaminhamento:** revisão jurídica; ver "Pendências de revisão" |

### Disponibilidade das fontes a partir deste ambiente

| Fonte | Acesso automatizado | Observação |
|---|---|---|
| Planalto (`www.planalto.gov.br/ccivil_03`) | sim, com `User-Agent` declarado (sem ele, a conexão é encerrada) | HTML em Windows-1252; página compilada traz as anotações "(Redação dada pela…)", "(Vide…)", "(Revogado)" |
| Câmara — Dados Abertos (`dadosabertos.camara.leg.br/api/v2`) | sim (JSON) | proposições, não texto consolidado de lei |
| Senado (`legis.senado.leg.br`) | **403** | bloqueia acesso automatizado deste ambiente |
| Diário Oficial (`in.gov.br`) | redireciona (301) | não explorado |
| STF/STJ/TST | não testado nesta auditoria | o README registra bloqueio anti-robô; a ingestão aceita HTML salvo do navegador |

Nenhuma fonte oficial oferece um feed uniforme de alterações por dispositivo. O monitor do roadmap
compara versões da página compilada do Planalto — que é consolidação editorial da Casa Civil, não
publicação oficial (esta é o DOU) — e por isso classifica o que muda como **indício** até revisão.

## Conteúdo jurídico fora do corpus

Os dois frontends têm texto jurídico próprio que **não** passa pelo controle de vigência:

- `frontend/dados.js` — 16 situações curadas, com prazos, valores ("JEC até 40 salários mínimos"),
  passo a passo e citações de artigos;
- `web/lib/ajuda.ts` — canais de ajuda e os quatro degraus (espelha `frontend/dados.js`).

Uma mudança legal que o corpus registre não chega a esses textos. Não foram conferidos nesta
auditoria.

## Dados de avaliação

| Arquivo | Conteúdo | Ressalva já documentada |
|---|---|---|
| `data/casos_busca.json` | 62 perguntas com o dispositivo esperado | gabarito do projeto, sem revisão profissional |
| `data/benchmark_temporal.json` | 24 casos de armadilha temporal | os textos "obsoletos" são paráfrases, não transcrições |
| `data/relevancia_julgada.json` | 586 rótulos de relevância em 86 perguntas | julgados pelo projeto, sem revisão profissional |

## Pendências de revisão

| Entrada | Motivo | Evidência | Estado |
|---|---|---|---|
| `cf-7-xiii` | prazo e texto divergentes da EC 141/2026 (acima) | EC 141/2026, arts. 1º, 2º, 6º e 10; DOU 16/10/2026, ed. extra | **corrigido com evidência e em revisão (ciclo 1)** — ver abaixo |
| `decreto13135-sac` | fonte era notícia | Decreto 13.135/2026, art. 25; DOU 13/10/2026 | **corrigido (ciclo 1)**: `fonte` aponta para o texto oficial no Planalto |
| entradas condensadas sem marca | o `texto` não é transcrição literal | tabela de fidelidade acima (amostra do CDC) | aberto (ciclo 4: verificação de fidelidade de todo o corpus) |

### O que mudou em `cf-7-xiii` e o que continua em aberto

- `texto` agora transcreve a redação oficial (caput do art. 7º, incisos XIII e XV na redação da EC
  141/2026, e os arts. 6º e 10 da emenda). Cada trecho foi conferido, normalizado, contra as páginas
  oficiais baixadas em 19/10/2026.
- `nota` e `resumo` falam em "2 meses", como a emenda; "60 dias" saiu do corpus e do benchmark.
- `entra_em_vigor_em` passou de 15/12 para **16/12/2026**: dois meses contados de 16/10, pela regra
  de contagem de meses do Código Civil (art. 132, § 3º).
- A entrada ganhou um bloco `revisao` com `estado: pendente`, motivo e evidência. A API devolve o
  bloco, o LLM recebe a marca "EM REVISÃO" com instrução de recomendar a fonte oficial, e os dois
  frontends mostram o aviso.
- **Em aberto, para revisão jurídica:** (1) se a regra vale a partir de 16 ou de 17/12 ("após
  decorridos 2 meses"); (2) se o rótulo `em_vacatio` do inciso XIII se sustenta diante do art. 10, II,
  que põe em vigor na publicação os dispositivos que não o XV; (3) a afirmação, mantida do texto
  anterior, de que até a primeira etapa vale o limite de 44 horas.

### Formato do bloco de revisão

```json
"revisao": {
  "estado": "pendente",
  "motivo": "frase que o cidadão e o LLM vão ler",
  "evidencia": ["URL ou citação da fonte oficial que fundamenta a dúvida"],
  "aberta_em": "2026-10-19"
}
```
