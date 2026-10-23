# Roadmap de engenharia

> Atualizado a cada ciclo. Diferencia **concluído** (implementado, testado, documentado),
> **parcial** e **planejado**. O roadmap de produto, com o histórico do projeto, continua no README.

## Rodada 9.0

> 22/10/2026. Pedido: melhorias executadas e verificadas, por prioridade — P0 integridade jurídica, P1
> confiabilidade e leitor, P2 segurança e LGPD, P3 monitor operacional, P4 feedback e qualidade, P5
> prontidão comercial (hipóteses). Base: auditoria read-only com 7 auditores (82 problemas confirmados:
> P0 31, P1 23, P2 15, P3 12, P4 1). Nada foi publicado em produção, nenhum serviço externo foi ativado e
> nenhuma cobrança foi implementada. Suíte ao fim: **642 testes passando, 1 pulado** (o semântico, sem
> chromadb); ruff e mypy limpos; build do web limpo.

### Ciclo 1 (P0) — proveniência, literalidade e estado incerto
- **Problema:** o campo `texto` misturava transcrição, paráfrase e interpretação sem marcar; só 8 de 79
  entradas eram transcrição literal; vigência "vigente" sem data de conferência.
- **Arquivos:** `app/corpus/` (novo), `scripts/corpus.py` (novo), `app/vigencia.py`, `app/retrieval.py`,
  `app/llm.py`, `app/main.py`, `data/legislacao.json`, `data/normas*.json`, `data/corpus_historico.json`,
  `data/corpus_versoes/`, `web/components/AnswerPanel.tsx`, `frontend/index.html`, CI.
- **Testes:** `test_proveniencia.py` (com guardas sobre o corpus real), `test_vigencia.py`.
- **Antes → depois:** trechos oficiais conferidos 0 → 141 (68 de 79 entradas); natureza declarada 0 →
  79; problemas de integridade → 0 (verificado no CI); 28 erros de conteúdo abertos como revisão.
- **Riscos:** os trechos vêm de capturas de linha de base sem revisão humana; nenhum texto conferido com
  o DOU (0 `literal`).
- **Não verificado:** conferência jurídica humana; URN LexML.

### Ciclo 2 (P0) — recuperação temporal
- **Problema:** a redação antiga aparecia antes da vigente em 39% (pergunta atual) e 48% (histórica) dos
  casos; nenhuma noção de data de referência.
- **Arquivos:** `app/temporal.py`, `app/consulta.py`, `app/avaliacao_temporal.py` (novos),
  `data/avaliacao/temporal_v2.json`, `app/main.py`, `app/llm.py`.
- **Testes:** `test_temporal.py`, benchmark temporal v2 no portão.
- **Antes → depois:** versão certa primeiro 60,9% → 100% (atual) e 52,2% → 95,7% (histórica; 100% com
  incerteza declarada); intenção e data em 20/20 perguntas escritas à mão.
- **Riscos:** regras de intenção afinadas no próprio conjunto; datas de redação com precisão de ano.
- **Não verificado:** conjunto separado nunca visto.

### Ciclo 3 (P0/P1) — verificador, política de resposta e precisão
- **Problema:** texto gerado sem verificação; respostas com artigos irrelevantes; nenhuma resposta
  intermediária entre responder e se abster.
- **Arquivos:** `app/verificador.py`, `app/politica.py`, `app/calibracao.py` (novos),
  `app/retrieval.py`, `app/avaliacao.py`, `scripts/avaliar.py`.
- **Testes:** `test_politica.py`, `test_validacao.py`, portão de avaliação.
- **Antes → depois:** precisão só relevante 46,5% → 57,6% (61,4% fora da amostra); fora do escopo sem
  proteção 10/26 → 3/26; ressalva indevida dentro do escopo 5/86; documento fora do escopo 3/3 abstenções.
- **Riscos:** números da política otimistas (mesmo conjunto); verificador testado com textos escritos à
  mão.
- **Não verificado:** texto real de LLM (sem chave).

### Ciclo 4 (P1) — leitor de processos
- **Problema:** `.txt` sem limite (derrubava a API), análise quadrática, página digitalizada contada como
  lida, acórdão que reforma a sentença ignorado ("Eu ganhei?" → "Sim"), injeção estrutural forjando
  trânsito, processos > 300 páginas recusados.
- **Arquivos:** `app/leitor/*`, `app/leitor/avaliacao.py` e `conjunto_adversarial.py` (novos),
  `data/exemplos/adversariais/` (31 documentos fictícios + gabaritos), `app/avaliacao.py`,
  `web/lib/leitor.ts`.
- **Testes:** `test_leitor.py` (sem alteração), `test_leitor_auditoria.py`, `test_leitor_conjunto.py`,
  `test_leitor_revisao.py` (87; 68 falham no código anterior à revisão, os outros 19 guardam o que já estava
  certo).
- **Revisão adversarial independente:** 14 problemas (5 altos: recursos esgotáveis com poucos KB,
  segmentação que engolia a sentença, decisão interlocutória e sentença reformada apresentadas como
  resultado, embargos acolhidos ignorados, trânsito forjado com quebra de página). Todos corrigidos e
  conferidos de novo com os roteiros do revisor.
- **Antes → depois:** conjunto adversarial 29/104 → 182/182 (0/31 → 31/31 documentos, incluindo 14 novos
  a partir das variações do revisor, que davam 25/78); análise de PDF de 300 páginas densas 18,6 s → 3,5 s,
  JSON 21 MB → 433 KB; `.txt` de 138 KB com sentenças alternadas 84 s / 1,1 GB → 2,5 s / 51 MB; 2,7 KB de
  carimbos "fls." 849 MB → 35 MB; PDF de 301 páginas recusado → processado.
- **Riscos:** gabaritos escritos pelo projeto; **não validado em processos reais**; sem OCR; em
  exportações em que a data só está na tarja de assinatura (PJe), o leitor se abstém muito.
- **Não verificado:** processos reais ou anonimizados; layouts de PJe, e-SAJ e Eproc; documentos
  digitalizados.

### Ciclo 5 (P3) — monitor operacional
- **Problema:** anotação de inconstitucionalidade aceita sozinha como "editorial"; revogação total
  descartada como coleta suspeita, com saída 0; sem alerta, sem agendamento, sem publicação controlada;
  decisões fora de ordem voltavam o ponteiro; escritas concorrentes perdidas; texto riscado por CSS lido
  como vigente.
- **Arquivos:** `app/monitor/*` (`eventos.py`, `alertas.py` novos), `app/ingestao.py`,
  `scripts/monitor.py`, `scripts/corpus.py`, `.github/workflows/monitor.yml` (novo), `app/main.py`,
  `app/validacao.py`.
- **Testes:** `test_monitor_operacao.py` (59), `test_ingestao.py`, `test_monitor.py`.
- **Antes → depois:** os 11 cenários da auditoria passaram de errados a corretos (tabela em
  [monitor-legislativo.md](monitor-legislativo.md#antes-e-depois-cenários-reproduzíveis)); revisão
  adversarial do ciclo: 16 problemas, 16 corrigidos; simulação real: 18 fontes sem mudança e 16
  releituras puras, registro intacto.
- **Operação (23/10/2026, autorizado pelo mantenedor):** rodada controlada real — 16 releituras pendentes,
  18 sem mudança, regressão 11/11; agendamento ativado nos dias úteis.
- **Riscos:** as 16 releituras e as 34 linhas de base esperam revisão humana; o job agendado fica vermelho
  até lá.
- **Não verificado:** workflow no GitHub; DOU.

### Ciclo 6 (P2) — segurança e LGPD
- **Problema:** 15 achados (P2-01 a P2-15): bloqueio de login da vítima, sem trilha de auditoria,
  retenção preguiçosa, limite de corpo tardio, dependências vulneráveis, sem CSP no Next, Google Fonts…
- **Arquivos:** `app/auditoria.py`, `app/manutencao.py` (novos), `app/auth.py`, `app/seguranca.py`,
  `app/main.py`, `app/db.py`, `requirements.txt`, CI, `web/next.config.mjs`, `web/app/conta`,
  `web/app/privacidade`, `web/app/layout.tsx`, `frontend/index.html`.
- **Testes:** `test_seguranca.py` (vítima × atacante, *rehash*, trilha sem dado pessoal, exportação,
  limite de corpo, retenção), `test_frontend_estatico.py`.
- **Antes → depois:** 15 achados → 12 corrigidos, 2 corrigidos em parte (P2-07: falta recuperação de
  senha; P2-09: falta controlador, encarregado e termos) e 1 aberto (P2-08: limite atrás do proxy real).
- **Riscos:** CSP com `'unsafe-inline'`; controles técnicos não são conformidade com a LGPD.
- **Não verificado:** produção.

### Ciclo 7 (P4/P5) — feedback, acessibilidade, prontidão comercial e documentação
- **Problema:** nenhum canal de erro do usuário; contraste abaixo de 4,5:1 e foco invisível; nenhuma
  análise de prontidão.
- **Arquivos:** `app/feedback.py`, `scripts/feedback.py`, `web/components/FeedbackDispositivo.tsx`
  (novos), `app/db.py`, `app/main.py`, `web/app/globals.css`, `frontend/index.html`, `docs/*`.
- **Testes:** `test_feedback.py` (inclui: dez relatos iguais não mudam resposta nem corpus); auditoria
  axe e teclado com Playwright (fora da suíte).
- **Antes → depois:** violações WCAG automáticas (axe, só contraste) em 12 de 20 combinações página × tema, 277 ocorrências → 0; elementos sem anel de foco visível no percurso por Tab: ao menos 5 (a medida inicial listou só os 5 primeiros) → 0.
- **Riscos:** triagem só por linha de comando; máscara de dado pessoal não pega nomes.
- **Não verificado:** leitor de tela real; teste com pessoas.

### Próxima prioridade
1. **Revisão jurídica humana** das 28 pendências e do corpus de uma área piloto.
2. **Revisar as 16 releituras e as 34 linhas de base** do monitor (a rodada controlada foi feita em
   23/10/2026; o agendamento está ativo).
3. **Conjunto de avaliação separado** (nunca visto) para busca, temporal e política.
4. Leitor com processos anonimizados e gabarito de profissional; OCR opcional.
5. Decisões de produção que faltam: canal de alerta além do job, nomes do controlador e do encarregado,
   recuperação de senha.

## Ordem de execução e por que ela difere da lista original (rodada de 19/10/2026)

O pedido prioriza três entregas: (1) leitor de processos, (2) monitor de mudanças jurídicas,
(3) avaliação e confiabilidade. A auditoria impôs dois ajustes:

1. **Segurança antes do leitor.** O leitor vai guardar processos judiciais por usuário. Tokens que
   nunca expiram (A1), upload sem limite de memória (A3) e ausência de retenção (A4) teriam de ser
   corrigidos de qualquer forma antes de receber esse tipo de documento.
2. **Vigência dinâmica antes de tudo o que é jurídico.** O Decreto 13.135/2026 entra em vigor em
   02/11/2026; com o status estático (A5), a API passaria a dizer que a regra vigente "ainda não
   está em vigor". É um erro com data marcada.

## Lista priorizada (estado da auditoria de 19/10/2026)

| Prioridade | Item | Origem | Estado |
|---|---|---|---|
| Crítica | Next.js com vulnerabilidade crítica | security-audit C1 | **concluído (ciclo 0)** |
| Alta | Vigência recalculada pela data, no fuso de Brasília | A5, M4 | **concluído (ciclo 1)** |
| Alta | Expiração e revogação de tokens; logout | A1 | **concluído (ciclo 1)** |
| Alta | Limitação de requisições em login, registro, perguntas e upload | A2 | **parcial (ciclo 1)**: em memória, por processo; cadeia de proxies de produção não verificada |
| Alta | Upload com leitura limitada, limite de páginas, erro genérico | A3 | **concluído (ciclo 1)** |
| Alta | Minimização: não gravar texto de pergunta anônima; apagar histórico | A4 | **concluído (ciclo 1)**; limpar linhas antigas em produção depende de autorização |
| Alta | Documento delimitado como dado não confiável no prompt | A6 | **concluído (ciclo 1)**; eficácia contra injeção não medida (sem chave de LLM) |
| Alta | Revisão da entrada `cf-7-xiii` contra a EC 141/2026 | legal-data-sources | **parcial (ciclo 1)**: corrigida com evidência e marcada `revisao: pendente`; falta revisão jurídica |
| Média | CORS restrito e configurável | M1 | **concluído (ciclo 1)** |
| Média | Log das falhas do LLM | M2 | **concluído (ciclo 1)** |
| Média | Enumeração de contas por tempo de resposta | M3 | **concluído (ciclo 1)** |
| Média | `base_atualizada_em` honesto | M5 | **concluído (ciclo 1)** |
| Média | XSS no frontend estático | M7 | **concluído (ciclo 1)** |
| Alta (produto) | Leitor de processos: backend | pedido, entrega 1 | **concluído (ciclo 2)** — ver [leitor-de-processos.md](leitor-de-processos.md) |
| Alta (produto) | Leitor de processos: interface | pedido, entrega 1 | **concluído (ciclo 3)** |
| Alta (produto) | Monitor de mudanças: snapshots, diff, relatório, fila de revisão | pedido, entrega 2 | **concluído (ciclo 4)** — ver [monitor-legislativo.md](monitor-legislativo.md) |
| Alta (dados) | Separar no corpus o texto oficial literal da explicação (15 dispositivos divergentes, 21 condensados) | ciclo 4 | planejado; exige revisão jurídica |
| Média | Agendar o monitor (workflow que abre PR com `data/monitor/`) | ciclo 4 | planejado; decisão do mantenedor |
| Alta (produto) | Estados de validação e avaliação reproduzível | pedido, entrega 3 | **concluído (ciclo 5)** — ver [avaliacao/relatorio.md](avaliacao/relatorio.md) |
| Alta (qualidade) | Melhorar a abstenção: 5 de 13 perguntas fora do escopo ainda recebem lei de outro assunto | ciclo 5 | planejado (ex.: sinal de cobertura por tema, julgamento de pertinência) |
| Média | Avaliar o texto gerado por LLM (fidelidade às fontes, afirmações sem suporte) com chave de API | ciclo 5 | planejado; exige chave e orçamento |
| Média | CI (pytest + build do web) | B4 | **concluído (ciclo 6)** |
| Média | Migrações com Alembic | M6 | planejado |
| Média | Next.js 16 (elimina o `postcss` vulnerável embutido) | C1 residual | planejado |
| Média | Conteúdo jurídico dos frontends sob controle de vigência | legal-data-sources | planejado |
| Baixa | Cabeçalhos de segurança, e-mail sem distinção de maiúsculas | B1, B2 | **concluído (ciclo 1)** |
| Decisão do projeto | Modelo de LLM: `claude-opus-4-8` é válido; a geração atual é `claude-opus-5-5`. Trocar exige rodar uma avaliação com chave | auditoria | aberto |

## Ciclos

### Ciclo 0 — auditoria (concluído)

- Linha de base: 141 testes passando e 1 pulado (retriever semântico, sem chromadb), com
  `playwright==1.56.0` para o teste de navegador;
  `pip-audit` limpo; `npm audit` com 1 crítica e 4 altas; build do Next passando.
- Documentos: [architecture.md](architecture.md), [security-audit.md](security-audit.md),
  [legal-data-sources.md](legal-data-sources.md), este roadmap.
- Corrigido: Next.js 15.5.20 → 15.5.28 e dependências transitivas (`npm audit fix`); build e
  `tsc` passam.

### Ciclo 1 — segurança, privacidade e vigência (concluído)

**Objetivo:** fechar os riscos altos que bloqueiam o leitor de processos e o erro de vigência com
data marcada (02/11/2026).

**Implementado e testado**

- `app/vigencia.py`: situação de vigência na data da consulta, em Brasília; transição
  `em_vacatio → vigente` só pela data que a própria norma fixa, com `status_registrado` para a fila.
  Data de referência fixa (`DIREITO_ABERTO_DATA_REFERENCIA`) para testes e avaliações reproduzíveis.
- `app/seguranca.py`: limitação de requisições (janela deslizante), CORS por variável de ambiente,
  cabeçalhos de segurança.
- `auth.py`: validade de 30 dias sem migração (sobre `criado_em`), logout, revogação total,
  login de custo constante, e-mail normalizado.
- `documentos.py`: leitura em blocos, limite de páginas, PDF com senha, erro sem detalhe interno.
- `main.py`: novas rotas (`/auth/sair`, `DELETE /historico`, `/conta/excluir`), consentimento para
  enviar documento ao LLM, pergunta anônima sem texto, estatísticas sem `mtime`.
- `llm.py`: documento delimitado e tratado como dado, aviso "EM REVISÃO", log de falhas por tipo.
- Corpus: `cf-7-xiii` corrigida contra a EC 141/2026 e marcada para revisão; fonte do Decreto
  13.135/2026 trocada pelo texto oficial.
- Frontends: XSS do estático corrigido; o Next revoga o token no logout, mostra "em vigor desde" e
  "em revisão" e permite apagar o histórico.
- `backend/pyproject.toml`: ruff e mypy versionados; ambos limpos.

**Testes:** 177 passando, 1 pulado (semântico) — eram 141. Novos: `tests/test_seguranca.py` (25),
10 em `tests/test_vigencia.py`, 2 de navegador em `tests/test_frontend_estatico.py`. Rodados contra o
código anterior, 22 dos testes de segurança e os 2 de navegador **falham**, ou seja, detectam os
defeitos. Benchmark temporal idêntico antes e depois (24/24, 10/24 de inversão, 24/24 com aviso).
`tsc` e `next build` passam. A suíte agora fixa a data de referência: antes, testes que esperavam
normas em vacatio quebrariam sozinhos em 02/11/2026.

**Riscos pendentes:** limite por processo e por proxy (A2); linhas antigas com texto de perguntas
anônimas no banco de produção; resistência a injeção de prompt não medida; revisão jurídica de
`cf-7-xiii`.

**Próximo incremento:** leitor de processos (backend), sobre esta base de upload e sessões.

### Ciclo 2 — leitor de processos: backend (concluído)

**Objetivo:** ler um processo e explicar o que ele contém sem inventar fatos — cada informação com
página, folha e natureza (alegação, pedido, decisão, fato registrado…).

**Implementado e testado:** pacote `app/leitor/` — extração por página com estado e carimbo de folha;
validação do número CNJ; divisão em peças; partes, linha do tempo, alegações, pedidos, decisões,
obrigações, prazos, recursos, trânsito em julgado, folhas faltantes, glossário; resumo, próximos passos e
perguntas para advogado por regras; perguntas livres com abstenção; verificação de toda citação contra a
página; API com dono, retenção, exclusão e limite por usuário; processo fictício de demonstração e
gabarito. Detalhes e números em [leitor-de-processos.md](leitor-de-processos.md).

**Testes:** 226 passando, 1 pulado (eram 177): 49 novos em `tests/test_leitor.py`, incluindo
não-invenção (todas as citações conferidas), IDOR, retenção, injeção de instrução no documento e a
regressão de um erro encontrado durante o desenvolvimento — o resumo chegou a dizer que a sentença era
de *improcedência* porque pegava o último "julgo" (capítulo acessório) em vez do dispositivo principal.

**Limitações:** sem OCR; medido só no documento sintético; sem geração por LLM (a verificação de
citações geradas já existe e está testada).

**Próximo incremento:** interface "Ler documentos jurídicos" no Next.js.

### Ciclo 3 — leitor de processos: interface (concluído)

**Implementado:** página `/documentos` no Next.js (`app/documentos/page.tsx`, `components/leitor/*`,
`lib/leitor.ts`) e o item "Ler documento" na navegação; rota pública com o PDF do exemplo; rótulos de
campos com a grafia do documento. O cliente `api()` deixou de forçar `Content-Type: application/json`
em uploads multipart.

**Verificação:** `tsc` e `next build` passam; roteiro no navegador (Playwright) com conta, envio,
análise, PDF original, pergunta e exclusão, sem erro de console; capturas em 1360, 960 e 390 px, claro e
escuro. Defeitos achados e corrigidos na verificação visual: visualizador "fixo" que não acompanhava a
rolagem (o `sticky` estava num elemento sem espaço para se mover), citações iguais lado a lado,
cabeçalho do visualizador sob a barra no celular, e o `X-Frame-Options: DENY` do ciclo 1 impedindo o
PDF do exemplo no iframe.

**Testes:** 227 no backend (+1: iframe só para o PDF do exemplo).

**Pendências:** roteiro de navegador fora da CI; limite de corpo de requisição da Vercel no caminho do
upload não verificado.

**Próximo incremento:** monitor de mudanças legislativas.

### Ciclo 4 — monitor legislativo (concluído)

**Objetivo:** detectar mudanças em normas oficiais, comparar versões e gerar relatórios verificáveis,
sem publicar nada sem revisão.

**Implementado:** pacote `app/monitor/` (coleta, texto vigente sem tachado, divisão em artigos,
classificação, impacto no corpus e regressão, relatório, registro com estados, decisão, reversão e
diário, fidelidade do corpus), `scripts/monitor.py`, `GET /api/v1/monitor` e o sinal "em revisão" na
API para dispositivos afetados por mudança pendente. Linha de base real de 9 fontes do Planalto.

**Defeitos encontrados:** a ingestão do Planalto incluía a redação revogada (tachada) como se fosse
vigente — corrigido, com teste; a primeira versão do classificador aceitava sozinha uma anotação nova
de norma alteradora com o texto igual — virou `norma_nova_citada`, risco médio; a regra "rótulo sem
artigo existente cobre a norma inteira" marcava dispositivos demais — restringida a rótulos que não
começam por "Art.".

**Medidas:** duas coletas seguidas das 9 fontes com o mesmo hash; fidelidade de 46 dispositivos (8
literais, 2 quase literais, 21 condensados, 15 divergentes), com os divergentes conferidos.

**Testes:** 30 em `tests/test_monitor.py` (+1 em `test_ingestao.py`), todos sem rede; 258 no total.

**Próximo incremento:** estados de validação na resposta e avaliação reproduzível (ciclo 5).

### Ciclo 5 — validação das respostas e avaliação reproduzível (concluído)

**Implementado:** `app/validacao.py` (estado de validação de cada resposta, por verificações
determinísticas; abstenção abaixo do limiar de evidência; conferência de citações de texto gerado),
`app/avaliacao.py` + `scripts/avaliar.py` (Recall@k, MRR, nDCG com julgamento graduado, precisão,
abstenção por conjunto, desempenho por tema, armadilha temporal, leitor, fidelidade e latência, com
comparação contra a linha de base), `data/avaliacao/fora_do_escopo.json` (26 perguntas, metade para
calibrar), o selo de validação nos dois frontends e a linha de base em `docs/avaliacao/`.

**Achado:** o README dizia que perguntas fora do vocabulário "podem não encontrar nada — e o sistema
diz isso". Na prática, quase nunca: "multa por não votar" voltava com ECA e condomínio. A abstenção
calibrada passou a pegar 8 de 13 na validação, ao custo de 3 de 75 perguntas legítimas sem resposta.

**Calibração:** limiar 6,0 = o maior sem abstenção indevida nas 11 perguntas de calibração, escolhido
antes de olhar a validação.

**Testes:** 274 passando, 1 pulado (eram 258): 11 de validação, 5 de avaliação, incluindo o portão que
roda a avaliação inteira e falha se qualquer métrica piorar em relação ao `resultados.json` versionado.

**Próximo incremento:** CI e documentação final (ciclo 6).

### Ciclo 6 — CI e documentação (concluído)

**Implementado:** `.github/workflows/ci.yml` (Python 3.10 e 3.13: ruff, mypy, pytest com teste de
navegador e portão de avaliação, `avaliar.py --comparar`; Next: `tsc`, build, `npm audit` no nível
crítico), `backend/requirements-dev.txt` com versões fixas, README atualizado, visão geral em inglês
(`docs/overview.en.md`), `CHANGELOG.md`, diagrama de arquitetura com os módulos novos.

**Verificação final:** 274 testes passando (+ os do retriever semântico, pulados sem chromadb); ruff e
mypy limpos; avaliação sem regressão; `pip-audit` sem vulnerabilidade; `npm audit` sem crítica (restam
as duas pendências do postcss embutido no Next 15). No GitHub, a 1ª execução do CI falhou antes dos
testes: o `ubuntu-latest` já é o 26.04, onde o Playwright 1.56 não instala o Chromium. Com o job do
backend fixado em `ubuntu-24.04`, a 2ª execução passou em todas as etapas (Python 3.10 e 3.13, e o
frontend).

## Estado ao fim da rodada de 19/10/2026

| Entrega pedida | Estado |
|---|---|
| Leitor inteligente de processos (PDF, citações por página, resumo, linha do tempo, sem inventar) | **concluído** para PDFs com texto; sem OCR; medido em processo fictício |
| Monitor de mudanças jurídicas (conjunto pequeno de normas oficiais, diff, versões, relatório) | **concluído** para 9 páginas do Planalto; sem agendamento e sem DOU |
| Avaliação e confiabilidade (benchmark reproduzível, critérios claros) | **concluído** para busca, abstenção, vigência, leitor e fidelidade; sem medida de LLM e de compreensão |

## Próximo incremento recomendado (19/10/2026 — feito na rodada 9.0)

**Separar no corpus o texto oficial literal da explicação.** É o achado de dados com maior efeito na
confiabilidade: hoje 15 dos 46 dispositivos conferidos têm paráfrase ou explicação no campo `texto`, e
um deles funde interpretação do STF à redação do artigo. Proposta:

1. acrescentar `texto_oficial` (transcrição, conferida automaticamente por `monitor.py fidelidade`, que
   passa a exigir 100%) e manter `texto` como explicação marcada;
2. a resposta cita `texto_oficial`; a explicação aparece como tal;
3. o portão de avaliação passa a cobrar fidelidade literal dos dispositivos migrados;
4. revisão por profissional do Direito antes de publicar cada lote — a começar pela entrada
   `cf-7-xiii` (EC 141/2026), que já está marcada para revisão.

Em seguida, por ordem: agendar o monitor (workflow que abre PR com `data/monitor/`), melhorar a
abstenção (5 de 13 perguntas fora do escopo ainda passam) e OCR no leitor.
