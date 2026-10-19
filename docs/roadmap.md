# Roadmap de engenharia

> Atualizado a cada ciclo. Diferencia **concluído** (implementado, testado, documentado),
> **parcial** e **planejado**. O roadmap de produto, com o histórico do projeto, continua no README.

## Ordem de execução e por que ela difere da lista original

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
as duas pendências do postcss embutido no Next 15). O CI ainda não rodou no GitHub no momento em que
este ciclo foi escrito — a primeira execução acontece no push da branch.

## Estado ao fim desta rodada

| Entrega pedida | Estado |
|---|---|
| Leitor inteligente de processos (PDF, citações por página, resumo, linha do tempo, sem inventar) | **concluído** para PDFs com texto; sem OCR; medido em processo fictício |
| Monitor de mudanças jurídicas (conjunto pequeno de normas oficiais, diff, versões, relatório) | **concluído** para 9 páginas do Planalto; sem agendamento e sem DOU |
| Avaliação e confiabilidade (benchmark reproduzível, critérios claros) | **concluído** para busca, abstenção, vigência, leitor e fidelidade; sem medida de LLM e de compreensão |

## Próximo incremento recomendado

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
