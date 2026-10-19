# Monitor legislativo

> Estado: **concluído (ciclo 4)** para páginas do Planalto, com linha de base real de 9 fontes. Não há
> agendamento configurado nem integração com o Diário Oficial (ver "Limitações").

## O que ele faz

Acompanha páginas oficiais de normas usadas pela base, detecta quando o texto vigente muda, compara
versão com versão artigo por artigo, classifica cada mudança, aponta os dispositivos da base afetados,
roda os testes de busca ligados a eles, gera um relatório e **não publica nada sozinho**: mudança de
risco médio ou alto fica pendente até uma pessoa decidir. Enquanto estiver pendente, a API mostra os
dispositivos afetados como **em revisão**.

```bash
cd backend
python scripts/monitor.py verificar                 # todas as fontes de data/monitor/fontes.json
python scripts/monitor.py pendentes
python scripts/monitor.py decidir --versao <v> --resultado corpus_atualizado --responsavel "Nome" --nota "..."
python scripts/monitor.py reverter --fonte cdc --responsavel "Nome"
python scripts/monitor.py historico --fonte cdc
python scripts/monitor.py fidelidade --json ../docs/avaliacao/fidelidade-corpus.json
```

`GET /api/v1/monitor` mostra, de forma pública, as fontes acompanhadas, a versão aceita de cada uma e
as mudanças pendentes.

## Decisões de desenho

| Decisão | Por quê |
|---|---|
| Hash sobre o **texto vigente normalizado**, não sobre o HTML | O HTML do Planalto muda a cada requisição (o anti-robô injeta tokens); o texto não. Duas coletas seguidas das 9 fontes deram o mesmo hash em todas. |
| Texto tachado (`<strike>`) fica fora | É como o Planalto mostra a redação revogada — a Constituição tem 777 trechos tachados. O mesmo defeito existia na ingestão (`ingestao.py`) e foi corrigido. |
| Comparação **por artigo** | "O art. 18 mudou" é acionável; "a página mudou" não. |
| Classificação conservadora, sempre "indício" | A página compilada é consolidação editorial da Casa Civil; a publicação oficial é o DOU. |
| Artigo ausente **não** é revogação | Exigência explícita: página que perde um artigo pode ser erro da página ou da coleta. |
| Coleta suspeita não gera mudança | Se a página nova tem menos de 80% dos artigos da aceita, é provável página de erro ou bloqueio; nada é inferido e a versão não é registrada. |
| Só risco baixo é aceito sem pessoa | Formatação e anotação editorial ("Vide", "Vigência") são aceitas automaticamente, com a decisão registrada como automática. Norma alteradora nova citada, mesmo com o texto igual, vai para revisão (o teste pegou a primeira versão aceitando isso sozinha). |
| Histórico nunca é apagado | Rejeitar não move a versão aceita; reverter volta o ponteiro para a anterior e fica no diário. |
| Snapshots no git, comprimidos e determinísticos | Linha de base reproduzível e auditável (832 KB para as 9 fontes); `gzip` com `mtime=0`, então o mesmo texto gera o mesmo arquivo. |

## Classificação

| Tipo | Risco | Quando |
|---|---|---|
| `formatacao` | baixo | só espaço, pontuação ou maiúsculas |
| `anotacao_editorial` | baixo | só anotações como "(Vide …)", "(Vigência)" |
| `norma_nova_citada` | médio | anotação nova de "Redação dada / Incluído pela …" com o texto extraído igual |
| `indicio_inclusao` | médio | artigo novo com "(Incluído pela …)" |
| `artigo_novo_na_pagina` | médio | artigo novo sem anotação |
| `indicio_alteracao_legislativa` | alto | texto mudou e há norma alteradora nova citada |
| `indicio_revogacao` | alto | o dispositivo passou a ser marcado como revogado |
| `texto_alterado_sem_norma_indicada` | alto | texto mudou sem norma indicada — retificação, republicação ou correção? |
| `artigo_ausente_na_pagina` | alto | o artigo sumiu da página (não é revogação) |

## Registro de cada versão

Cada versão em `data/monitor/registro.json` tem: fonte, URL, órgão emissor (em `fontes.json`), título do
ato e data de publicação no DOU **quando a própria página informa**, data da captura, SHA-256 do texto
vigente, número de artigos, versão anterior, mudanças (com trechos antes/depois e normas citadas),
dispositivos afetados, resultado da regressão, relatório, estado (`linha_de_base`, `pendente_revisao`,
`aceita`, `rejeitada`) e a decisão (resultado, responsável, data, nota). Data de vigência e situação
jurídica não são inferidas da página: continuam no bloco `vigencia` do corpus, com revisão humana.

## Linha de base real (19/10/2026)

| Fonte | Artigos na página | Versão |
|---|---|---|
| Constituição Federal (corpo + ADCT) | 412 | `ca8cfa3680b8e03d` |
| Código Civil | 2.082 | `647ba409698f8064` |
| CDC | 130 | `ef77eb7adba54b04` |
| CTB | 390 | `6c561394171b78e0` |
| CLT | 861 | `e638322b979c7b37` |
| Lei 9.099/1995 | 99 | `07c334937ce23744` |
| Lei 6.015/1973 | 321 | `34ecfe1211596408` |
| Lei 8.245/1991 | 92 | `8d1cbec9f0b25080` |
| Decreto 13.135/2026 | 25 | `1006fb39092e8b13` |

A contagem inclui artigos com letra (54-A…) e repetições numeradas (o ADCT recomeça no art. 1º). Uma
segunda rodada, minutos depois, deu `sem_mudanca` nas 9.

## Fidelidade do corpus ao texto oficial vigente

`monitor.py fidelidade` compara o `texto` de cada dispositivo do corpus cuja fonte é monitorada com os
artigos que o rótulo nomeia, na versão aceita (sem tachado). A medida é a fração das sequências de 8
palavras do corpus que aparecem no texto oficial (marcadores de lista ignorados dos dois lados).
Resultado completo: [avaliacao/fidelidade-corpus.json](avaliacao/fidelidade-corpus.json).

| Classe | Dispositivos | Leitura |
|---|---|---|
| literal (≥ 98%) | 8 | transcrição |
| quase literal (≥ 85%) | 2 | transcrição com cortes |
| condensado (≥ 35%) | 21 | resumo com trechos do texto |
| divergente (< 35%) | 15 | paráfrase ou explicação |

**O que os divergentes mostram** (conferidos um a um nos casos abaixo): o campo `texto` do corpus mistura
transcrição com explicação. `cc-1790` traz uma explicação no lugar do artigo; `cc-1723` funde ao texto do
artigo a interpretação do STF (ADI 4.277), como se fosse redação legal; `cf-226` inclui regra do art. 733
do CPC; `ctb-259-261` reescreve a escala de pontos com algarismos. Dois divergentes são esperados:
`ctb-262` é marcador histórico de dispositivo revogado (o texto vigente não o contém) e `cf-7-xiii`
transcreve também os arts. 6º e 10 da EC 141/2026, que não estão na página da Constituição.

**Consequência:** hoje o sistema cita o `texto` como "o que a lei diz". Para citação verificável, o
corpus precisa separar o **texto oficial literal** (conferível por esta mesma régua) da **explicação**. É
o próximo item de dados do roadmap; mexer em 79 dispositivos pede revisão jurídica e não foi feito aqui.

## Limitações

- Só páginas HTML do Planalto foram exercitadas; Senado bloqueia acesso automatizado (403), e os
  portais dos tribunais têm anti-robô.
- Não há integração com o DOU: a confirmação de uma mudança continua manual.
- Não há agendamento ativo. Para rodar periodicamente, use o agendador do servidor ou um workflow
  agendado que rode `verificar` e abra um PR com `data/monitor/` — não foi criado, porque publicar
  automaticamente no repositório é decisão do mantenedor.
- A divisão em artigos depende do padrão "Art. N" das páginas compiladas; normas com estrutura muito
  diferente podem precisar de ajuste.
- A medida de fidelidade diz **onde olhar**, não se uma condensação está juridicamente correta.
