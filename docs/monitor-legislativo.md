# Monitor legislativo

> Estado: **fluxo operacional com simulação e modo controlado (rodada 9.0, ciclo P3)** para 34 páginas
> do Planalto. Agendado nos dias úteis desde 23/10/2026 (autorização do mantenedor); a primeira rodada
> controlada no registro real foi feita no mesmo dia (16 versões pendentes de revisão). Não há canal de
> alerta além do status do job nem integração com o Diário Oficial (ver "Limitações").

## O que ele faz

Acompanha páginas oficiais de normas usadas pela base, detecta quando o texto vigente muda, compara
versão com versão artigo por artigo, classifica cada mudança, aponta os dispositivos da base afetados,
roda os testes de busca ligados a eles, gera um relatório e **não publica nada sozinho**: mudança de
risco médio ou alto fica pendente até uma pessoa decidir. Enquanto estiver pendente, a API mostra os
dispositivos afetados como **em revisão**.

```bash
cd backend
python scripts/monitor.py verificar --simular       # calcula tudo, não grava nada
python scripts/monitor.py verificar                 # modo controlado: grava no registro do monitor
python scripts/monitor.py verificar --json -        # + resumo para máquina
python scripts/monitor.py pendentes
python scripts/monitor.py decidir --versao <v> --resultado corpus_atualizado --responsavel "Nome" --nota "..."
python scripts/corpus.py publicar --fonte cdc --versao <v> --responsavel "Nome" --motivo "..."
python scripts/monitor.py reverter --fonte cdc --responsavel "Nome"
python scripts/monitor.py historico --fonte cdc
python scripts/monitor.py situacao                  # atualidade de cada fonte
python scripts/monitor.py fidelidade --json ../docs/avaliacao/fidelidade-corpus.json
```

`GET /api/v1/monitor` mostra, de forma pública, as fontes acompanhadas, a versão aceita de cada uma, se
a fonte está desatualizada, e as mudanças pendentes com os eventos indicados.

## Fluxo operacional (rodada 9.0, ciclo P3)

| # | Componente | Existe? | Como rodar | O que NÃO está ativado |
|---|---|---|---|---|
| 1 | Coleta programada | Sim: dias úteis às 6h17 de Brasília, e à mão | `.github/workflows/monitor.yml` (agendado em modo `controlado`; à mão, `simular` ou `controlado`) | O modo controlado do workflow grava só no runner (efêmero) e publica artefatos (resumo, alertas, relatórios, registro, snapshots); nada volta ao repositório nem abre PR — trazer o resultado para o repositório é passo humano. |
| 2 | Identificação de versões | Sim | automático em `verificar` | — |
| 3 | Comparação por artigo | Sim | automático | — |
| 4 | Classificação (risco e tipo) | Sim | automático | — |
| 5 | Dispositivos afetados | Sim (índice de dependências) | automático | — |
| 6 | Testes de regressão | Sim | automático em `verificar` (base atual) e em `corpus.py publicar` (base nova, bloqueia) | — |
| 7 | Alertas | Sim: código de saída, JSON da rodada, arquivo em `data/monitor/alertas/` | `verificar` | Não há e-mail, Slack ou abertura de issue: o aviso é o job vermelho. Outro canal exige conta e autorização. |
| 8 | Revisão humana | Sim | `monitor.py pendentes` / `decidir` | — |
| 9 | Publicação controlada no corpus | Sim | `corpus.py publicar` | Só roda à mão, por pessoa, e só com versão decidida por pessoa. |
| 10 | Rollback | Sim | `monitor.py reverter` (ponteiro da fonte) e `corpus.py reverter` (entrada do corpus) | — |
| 11 | Auditoria | Sim | diário do registro, `historico_verificacoes`, `corpus_historico.json`, alertas | — |

**Modos.** `--simular` baixa (ou lê `--arquivo`), compara, classifica, deriva eventos, calcula
afetados e regressão e imprime tudo — sem gravar registro, snapshot, relatório nem alerta (há teste
que confere o diretório byte a byte). O modo **controlado** grava no registro do monitor e **nunca** no
corpus: `data/legislacao.json` só muda por `corpus.py publicar`, `extrair`, `registrar` ou `reverter`,
sempre com responsável e motivo no histórico.

**Códigos de saída de `verificar`:** 0 — nada a fazer; 1 — há versão pendente de revisão humana (nova
ou antiga na fila); 2 — a rodada ficou incompleta (falha de coleta, coleta suspeita ou erro interno em
alguma fonte). Um erro numa fonte não interrompe as outras: a fonte fica com `erro_interno` e o
traceback vai para a saída de erro. O alerta de cada rodada (os 90 mais recentes ficam) lista versões
novas, falhas, a fila pendente e as fontes desatualizadas, sem texto de norma nem dado pessoal.

**Coleta.** Falha passageira (rede, 429, 5xx) é repetida até 3 vezes com espera exponencial e um pouco
de acaso, respeitando `Retry-After`; espera pedida acima de 120 s não é cumprida na rodada (a fonte fica
para a próxima). Bloqueio (403) e página inexistente (404) **não** são repetidos — insistir contra a
proteção do portal não é aceitável. Redirecionamento para outro site e página com título de outro ato
viram falha/coleta suspeita, nunca versão.

**Versões.** A versão é o SHA-256 do texto vigente. Texto igual ao de uma versão que já foi aceita e
deixou de ser (MP que caducou, reversão, correção da página) vira **evento novo** com id `<hash>-N`,
comparado com a versão aceita hoje, e vai para revisão (`retorno_a_versao_anterior`); antes era
ignorado como "já registrada". Texto igual a uma versão pendente ou rejeitada continua sem duplicar.

**Decisões.** Aceitar uma versão capturada antes da que já está aceita só registra a decisão
(estado `superada`); o ponteiro não volta no tempo. Uma versão aceita automaticamente (só risco baixo)
pode ser **confirmada** por pessoa (`decidir … sem_impacto`), o que a torna publicável; desfazê-la é
`reverter`.

**Publicação controlada** (`corpus.py publicar --fonte F --versao V --responsavel R --motivo M`):
recusa se V não é a versão aceita hoje de F ou não foi decidida por pessoa (linha de base, pendente,
aceita automaticamente sem confirmação, superada, revertida); recusa se o corpus tem alteração manual
não registrada (para não atribuí-la à publicação); recalcula a proveniência só das entradas que
dependem de F (norma própria ou dispositivo adicional); confere os trechos contra os snapshots; roda a
regressão da busca **sobre o corpus novo** e, se alguma pergunta perder o dispositivo esperado, não
grava nada (a menos de `--aceitar-falha-de-regressao`, que fica registrado); só então grava o corpus e o
histórico, com a versão do monitor e o resultado da regressão no motivo e na evidência, e anota
`publicacao_no_corpus` no diário do monitor.

**`extrair`** passou a deixar de fora as entradas cuja fonte não tem versão decidida por pessoa (linha de
base ou aceita automaticamente) e diz quais; `--incluir-nao-revisadas` (ou `--incluir-linha-de-base`)
mantém o comportamento anterior. As
34 fontes ainda estão na linha de base: os trechos oficiais atuais vieram dessas capturas, como
`docs/legal-data-sources.md` registra.

**Concorrência.** Quem escreve no registro segura uma trava exclusiva (`fcntl.flock` em
`data/monitor/.registro.lock`; no corpus, `data/.corpus.lock`) e, ao gravar, confere o contador
`revisao`: se outro processo gravou desde a leitura, a gravação é recusada em vez de sobrescrever.
`verificar` baixa a página **fora** da trava e só a segura para comparar e gravar, relendo o registro
antes — uma decisão humana no meio da rodada não se perde nem espera a rodada inteira. O registro volta
a ser gravado 0644 (respeitando a umask); antes saía 0600.

**Atualidade.** Cada fonte guarda a data do último sucesso e as 30 últimas verificações. Fonte sem
verificação bem-sucedida há mais de 30 dias (`DIREITO_ABERTO_MONITOR_DIAS_SEM_VERIFICACAO`) aparece
como desatualizada em `GET /monitor`, em `monitor.py situacao` e na validação das respostas: os
dispositivos dela levam o estado "Fonte desatualizada ou indisponível", e a política de resposta põe
ressalva. Falha de coleta não renova a atualidade.

### Eventos jurídicos tipados

Cada versão nova traz `eventos`, derivados dos tipos de mudança — **indícios**, a confirmar no DOU.
Publicação, entrada em vigor, alteração de redação, revogação e consolidação nunca se confundem:

| Evento | Vem de |
|---|---|
| `inicio_do_monitoramento` | primeira captura (não é a data de publicação da norma) |
| `alteracao_redacao` | `indicio_alteracao_legislativa`, `norma_nova_citada` |
| `inclusao` | `indicio_inclusao` |
| `revogacao_parcial` | `indicio_revogacao`, `artigo_tachado_na_pagina` |
| `revogacao_total` | `indicio_revogacao_total` (os artigos riscados por ela não viram também revogações parciais) |
| `entrada_em_vigor` | `anotacao_de_vigencia` |
| `controle_constitucionalidade` | `anotacao_de_controle_constitucional` |
| `consolidacao_ou_republicacao` | `texto_alterado_sem_norma_indicada`, `retorno_a_versao_anterior` |
| `relacao_com_outra_norma` | `remissao_a_norma_nova` |
| `indeterminado` | `artigo_novo_na_pagina`, `artigo_ausente_na_pagina` |

Formatação, anotação de navegação e a releitura do tachado (abaixo) não indicam evento nenhum.

### Revogação: o que é indício e o que não é

- **Página que some, falha, é bloqueada ou volta cortada não é revogação.** Continua `falha_de_coleta`
  ou `coleta_suspeita`, sem versão.
- **Revogação da norma inteira** vira versão pendente de risco alto (`indicio_revogacao_total`) quando o
  cabeçalho da página (com o título do ato, antes de qualquer artigo) anota "Revogada pela …" ou quando
  todos os artigos aparecem riscados — e a versão aceita ainda não mostrava isso. Antes, a
  página toda riscada caía na guarda de "zero artigos" e era descartada como coleta suspeita, sem alerta
  e com saída 0. Conferido em 22/10/2026 com as páginas reais da Lei 8.666/1993 (cabeçalho "(Revogado
  pela Lei nº 14.133, de 2021)", 0 artigos vigentes, 128 riscados) e do CPC de 1973 ("Revogada pela Lei
  nº 13.105, de 2015", 40 artigos ainda sem risco, 1.226 riscados): as duas viram
  `indicio_revogacao_total` com a norma revogadora certa. Nenhuma das 34 fontes monitoradas tem a
  anotação no cabeçalho.
- **Revogação em massa** (mais de 20% dos artigos riscados de uma vez) deixou de ser "coleta suspeita":
  artigo riscado conta como presente na página; só o que some sem estar riscado indica página cortada.
- **Rótulo riscado.** Em `<strike>Art. 3º …</strike> (Revogado pela …)`, a anotação ficava colada no
  art. 2º, que aparecia como revogado, e o 3º como "ausente". Agora a anotação é devolvida ao artigo
  que sumiu quando o anterior ganhou só anotações de revogação no fim, uma por artigo sumido; na dúvida,
  nada é reatribuído e o sumido continua "ausente" (que não é revogação).

### Tachado por estilo: a leitura 2

As páginas do Planalto riscam a redação revogada de dois jeitos: com as tags `<strike>`/`<del>` e com o
estilo `text-decoration: line-through`. A leitura só reconhecia as tags. Em 22/10/2026, **16 das 34
páginas** monitoradas usavam o estilo (LGPD, CLT, Lei 12.651, Lei 8.036, Lei 8.213, CPC, ECA e outras):
redações de medidas provisórias que perderam a validade (MP 869/2018 na LGPD, MP 808/2017 na CLT, com
"Vigência encerrada"), o § 2º do art. 1.029 do CPC (revogado pela Lei 13.256/2016) e redações antigas
duplicadas eram lidos como texto vigente. A leitura 2 (`app/ingestao.py`) reconhece o estilo.

- **Efeito no corpus: nenhum.** Os 141 trechos oficiais do corpus foram refeitos com a leitura 2 sobre
  as páginas de 22/10/2026: os 141 saem idênticos. Nenhum trecho citado vinha de texto riscado.
- **Efeito no monitor:** como o snapshot aceito foi gravado com a leitura 1, a próxima rodada real vê
  texto diferente nas 16 fontes. Para não confundir isso com mudança da página, o monitor relê a mesma
  página com a leitura antiga; se ela der exatamente a versão aceita, a versão nova é marcada
  `releitura` e cada diferença vira `tachado_por_estilo_retirado` (risco médio, sem evento jurídico),
  pendente de uma conferência por amostragem.
- **Simulação real (22/10/2026)**, `verificar --simular` com as 34 páginas baixadas uma vez: 18 fontes
  `sem_mudanca`; 16 versões de releitura (225 diferenças, todas `tachado_por_estilo_retirado`, nenhuma de
  outro tipo); regressão da busca sem falha; 8 entradas ficariam "em revisão" até a confirmação
  (`lc80-1`, `eca-132`, `lei11340-22`, `cc-3-4`, `loas-20`, `lai-10-11`, `lgpd-18`, `lei12651-1`). O
  registro real **não** foi alterado (conferido por hash).
- **Rodada controlada real (23/10/2026)**, autorizada pelo mantenedor (`verificar`, as 34 páginas baixadas
  de novo): o mesmo resultado — 18 `sem_mudanca`, 16 versões de releitura pendentes (225 diferenças, todas
  `tachado_por_estilo_retirado`, nenhum evento jurídico), regressão da busca 11/11, saída 1 (revisão
  pendente). As versões aceitas continuam as da primeira captura até a decisão de uma pessoa; enquanto
  isso, as 8 entradas acima aparecem "em revisão" nas respostas.
- Nenhuma das 36 páginas examinadas (34 monitoradas e as 2 revogadas) risca texto por classe CSS em
  folha de estilo; esse caso não é reconhecido.

### Revisão adversarial do ciclo (22/10/2026)

Um revisor independente (agente, sem editar o código) atacou o ciclo e confirmou 16 problemas: 3 altos,
6 médios, 5 baixos e 2 detalhes. Todos foram corrigidos, com teste, e conferidos de novo com os
roteiros de reprodução do revisor e com as páginas reais:

| # | Problema | Correção |
|---|---|---|
| 1 | Página de erro que **menciona** uma revogação ("Lei nº 8.666 — Revogada pela Lei nº 14.133") virava revogação total da norma | página sem artigo vigente **e** sem artigo riscado é sempre coleta suspeita; o sinal do cabeçalho exige o título do ato na página |
| 2 | Página cortada passava pela guarda porque os artigos riscados de sempre contavam como presentes (CLT real cortada em 65–75% virava versão com ~300 "ausentes") | só conta o artigo que passou a aparecer riscado agora; a CLT cortada de 50% a 75% volta a ser coleta suspeita |
| 3 | Riscados por estilo aninhados, elemento vazio riscado ou `<p>`/`<td>`/`<li>` sem fechamento engoliam o texto vigente seguinte | pilha de elementos com fechamento pelo ancestral e implícito; elemento vazio nunca abre; riscado sem fim ou que engole mais de 20 mil caracteres (o maior real tem 798) vira alerta e coleta suspeita. A leitura 1 continua idêntica byte a byte nas 36 páginas |
| 4 | Só o art. 1º revogado (rótulo riscado) virava revogação total | o cabeçalho é procurado antes de qualquer artigo, riscado ou não; o preâmbulo entra na reatribuição |
| 5 | Depois de aceita, a revogação total era "detectada" de novo a cada mudança e desligava a guarda de página cortada | a versão guarda `pagina_indica_revogacao_total`; só é mudança quando a aceita não a mostrava |
| 6 | Mudança real misturada com a releitura gerava eventos falsos (art. 5º "alterado") | a mudança real é comparada com a página lida do mesmo jeito que a aceita; o que só a leitura muda vem à parte |
| 7 | Texto rejeitado que voltava depois de outra versão aceita era engolido como "já registrada" | só é "já registrada" se a aceita ainda é a mesma de quando foi rejeitada; senão, retorno pendente |
| 8 | A reatribuição de "(Revogado…)" punha a revogação no artigo errado (art. 2º alterado virava revogado) | exige o artigo riscado na página; tira do art. anterior só as anotações de revogação novas e classifica o resto |
| 9 | O workflow não publicava os snapshots | publica `snapshots/` junto com o registro |
| 10 | Fonte inexistente ou erro do próprio monitor saíam com 1 ("revisão pendente") | saem com 2 |
| 11 | Depois de um 403, a rodada continuava pedindo as outras páginas do mesmo site | o site bloqueado não é mais consultado naquela rodada |
| 12 | Fonte nova em `fontes.json`, nunca conferida, aparecia em dia | aparece desatualizada |
| 13 | `extrair` aceitava versão aceita automaticamente, que `publicar` recusa | só usa versão decidida por pessoa (ou pede `--incluir-nao-revisadas`) |
| 14 | `publicar` gravava o corpus sem escrita atômica e informava mal uma falha no diário | escrita atômica; mensagem diz exatamente o que foi gravado |
| 15–16 | Ordem dos alertas do mesmo segundo; `text-decoration-line` | corrigidos |

Na mesma passagem, o título das páginas passou a ser reconhecido em mais formatos ("LEI Nº 9.784 , DE…",
"LEI N o 5.869", o título da Constituição) — sem isso, o sinal de revogação do CPC de 1973 deixava de
valer. Limite que fica: artigo que some **sem** estar riscado e cuja anotação de revogação cola no
anterior continua com a revogação no anterior e o sumido como "ausente" (os dois de risco alto, para
revisão) — sem prova na página, o monitor não escolhe.

### Antes e depois (cenários reproduzíveis)

`scratchpad/monitor_p3/cenarios.py` (fora do repositório) roda os mesmos cenários contra o código; os
testes de `tests/test_monitor_operacao.py` cobrem cada um.

| Cenário | Antes | Depois |
|---|---|---|
| "(Declarado inconstitucional…)", "(Suspensa a eficácia…)" com texto igual | `anotacao_editorial`, risco baixo, **aceita sozinha** | `anotacao_de_controle_constitucional`, alto, pendente |
| "(Vigência)", "(Produção de efeitos)" | editorial, baixo | `anotacao_de_vigencia`, médio |
| "(Vide Lei nº …)" nova | editorial, baixo | `remissao_a_norma_nova`, médio ("Vide Decreto" segue baixo) |
| Rótulo do art. 3º riscado + "(Revogado…)" | art. 2º "revogado", art. 3º "ausente" | art. 3º `indicio_revogacao`, art. 2º sem mudança |
| Norma inteira riscada com "(Revogada pela…)" | `coleta_suspeita`, nenhuma versão, saída 0 | versão pendente `indicio_revogacao_total`, norma revogadora citada |
| Metade dos artigos riscados | `coleta_suspeita` | versão pendente, 5 × `indicio_revogacao` |
| Página volta ao texto anterior (MP caducou) | `versao_ja_registrada`, nada a revisar | versão `<hash>-2` pendente, `retorno_a_versao_anterior` |
| Aceitar a versão A depois da B, mais nova | ponteiro volta para A | A fica `superada`, ponteiro em B |
| Permissão de `registro.json` | 0600 | 0644 (umask 022) |
| Duas escritas concorrentes | a segunda apaga a primeira | a segunda é recusada (`RegistroAlteradoPorOutroProcesso`) |
| `verificar` com pendência | saída 0, sem alerta | saída 1 + JSON + arquivo de alerta |

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
| `anotacao_editorial` | baixo | só anotações de navegação: "(Vide <decreto>)", "(Regulamento)", "(Mensagem de veto)" |
| `anotacao_de_vigencia` | médio | anotação nova de vigência, produção de efeitos, veto ou promulgação de partes vetadas |
| `remissao_a_norma_nova` | médio | "(Vide <lei, LC, decreto-lei, MP ou emenda>)" nova, texto igual |
| `tachado_por_estilo_retirado` | médio | a página não mudou; a leitura 2 deixou de contar o riscado por estilo |
| `retorno_a_versao_anterior` | médio | a página voltou a um texto já registrado (página inteira) |
| `norma_nova_citada` | médio | anotação nova de "Redação dada / Incluído pela …" com o texto extraído igual |
| `indicio_inclusao` | médio | artigo novo com "(Incluído pela …)" |
| `artigo_novo_na_pagina` | médio | artigo novo sem anotação |
| `indicio_alteracao_legislativa` | alto | texto mudou e há norma alteradora nova citada |
| `indicio_revogacao` | alto | o dispositivo passou a ser marcado como revogado (inclusive pelo rótulo riscado reatribuído) |
| `artigo_tachado_na_pagina` | alto | o dispositivo passou a aparecer só riscado, sem redação vigente no lugar |
| `anotacao_de_controle_constitucional` | alto | anotação nova de inconstitucionalidade, suspensão, ADI/ADC/ADPF |
| `indicio_revogacao_total` | alto | cabeçalho "Revogada pela …" ou todos os artigos riscados (página inteira) |
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

> Primeira linha de base, com 9 fontes. Em 21/10/2026 a lista passou a 34 fontes (`data/monitor/fontes.json`), todas ainda em `linha_de_base`, sem revisão humana; `monitor.py situacao` mostra o estado atual de cada uma.

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
- O agendamento roda no GitHub (dias úteis), num runner efêmero: o resultado vem como artefatos. Não
  há PR automático com `data/monitor/` — trazer versões novas ao repositório e decidi-las continua sendo
  passo humano. O job fica vermelho enquanto houver revisão pendente, inclusive as 16 releituras de
  23/10/2026.
- O canal de alerta é o código de saída (job vermelho) e o JSON; não há e-mail nem mensageria.
- A detecção de artigo riscado compara números de artigo: com numeração repetida na página (o ADCT na
  Constituição, o decreto que aprova a CLT), um artigo riscado numa parte e vigente na outra passa
  despercebido.
- O sinal de revogação total no cabeçalho cobre as duas formas vistas em páginas reais ("Revogada pela
  Lei nº …" e "(Revogado pela Lei nº …)"). Outra redação do cabeçalho só é pega se todos os artigos
  estiverem riscados.
- A trava entre processos usa `fcntl` (Linux/macOS); no Windows, só o contador de revisão protege.
- Os cenários e os testes são sintéticos ou com páginas reais baixadas uma vez; o modo controlado do
  workflow não foi executado no GitHub (exige disparo manual por quem tem acesso).
- A divisão em artigos depende do padrão "Art. N" das páginas compiladas; normas com estrutura muito
  diferente podem precisar de ajuste.
- A medida de fidelidade diz **onde olhar**, não se uma condensação está juridicamente correta.
