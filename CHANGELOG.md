# Histórico de mudanças

Mudanças relevantes, da mais recente para a mais antiga. O histórico anterior está no `git log` e no
roadmap do README.

## Rodada 9.0 — integridade jurídica verificável — 22/10/2026

Ciclos, números e riscos em [docs/roadmap.md](docs/roadmap.md#rodada-90). Nada foi publicado em produção.

### P0 — proveniência, literalidade e incerteza
- Proveniência por dispositivo (`app/corpus/`, `scripts/corpus.py`): 141 trechos oficiais extraídos do
  snapshot da fonte, com hash, versão e data; natureza de cada texto (consolidado, resumo explicativo,
  interpretação jurídica, não conferido); lacunas declaradas; selos e histórico com responsável e motivo;
  reversão; verificação no CI.
- `nao_verificada` como estado padrão de vigência; `redacao_anterior` automática.
- Recuperação temporal (`app/temporal.py`, `app/consulta.py`): intenção, data de referência, versão
  aplicável primeiro; benchmark temporal v2 (versão certa primeiro: 60,9% → 100% atual, 52,2% → 95,7%
  histórica).
- Verificador determinístico do texto gerado e política de resposta em 5 modos; corte adaptativo da busca
  escolhido por validação cruzada (precisão 46,5% → 57,6%).

### P1 — leitor de processos
- Limites também no `.txt`, tetos de tempo e de armazenamento, página possivelmente digitalizada,
  segmentação de peças, acórdão e decisão que vale, procedência parcial, embargos, trânsito com acento,
  prazos ligados à expressão certa (sem calcular data), inconsistências, injeção estrutural, documentos
  longos processados em parte. Revisão adversarial independente (14 problemas, 5 altos) corrigida:
  decisão interlocutória, sentença reformada ou embargos acolhidos não são mais apresentados como resultado
  errado; quando a ordem das decisões é incerta, o leitor diz que não sabe; trânsito forjado com quebra de
  página não passa; poucos KB não esgotam mais CPU e memória. Conjunto adversarial versionado: 29/104 →
  182/182 (31 documentos). Upload e exclusão de documento entram na trilha de auditoria.

### P2 — segurança e LGPD
- Bloqueio de login por conta + rede, PBKDF2 600 mil com *rehash*, trilha de auditoria sem dado pessoal,
  limite de corpo no ASGI, retenção automática, exportação de dados, troca de senha, sair de todas as
  sessões, CSP no Next, fontes sem Google, `pip-audit` no CI, dependências com mínimo seguro.

### P3 — monitor operacional
- Simulação e modo controlado; retentativas com espera e `Retry-After`; parada no site que bloqueia;
  códigos de saída e alertas; workflow agendado nos dias úteis (autorizado em 23/10/2026); eventos jurídicos tipados; índice de dependências;
  publicação controlada (`corpus.py publicar`) com regressão; trava e contador de revisão; decisões fora de
  ordem; retorno a texto antigo; revogação total e artigo riscado como indícios; atualidade da fonte na
  validação.
- Leitura do tachado por estilo CSS (16 de 34 páginas o usam): os 141 trechos do corpus não mudam.
- Revisão adversarial do ciclo: 16 problemas, todos corrigidos com teste.

### P4/P5
- Feedback por dispositivo com triagem humana; nunca muda a base sozinho.
- Acessibilidade: 0 violações WCAG 2.1 A/AA (regras automáticas do axe) nas 8 páginas do web, na
  resposta e no frontend estático, nos 2 temas; contraste e foco visível corrigidos.
- Análise de prontidão comercial, só com hipóteses (`docs/prontidao-comercial.md`).

## Auditoria e plataforma de inteligência jurídica verificável — outubro de 2026

PR #1, em ciclos (detalhes em [docs/roadmap.md](docs/roadmap.md)).

### Ciclo 0 — auditoria
- Documentos de arquitetura, segurança, fontes jurídicas e roadmap (`docs/`).
- Next.js 15.5.20 → 15.5.28 (backport sem a vulnerabilidade crítica).
- Achado: a entrada da EC 141/2026 registrava "60 dias" onde a emenda diz "2 (dois) meses".

### Ciclo 1 — segurança, privacidade e vigência
- Vigência recalculada na data da consulta, em Brasília (o Decreto 13.135/2026 começa a valer em 02/11/2026).
- Tokens com validade e logout; limitação de requisições; CORS restrito; cabeçalhos de segurança.
- Upload lido em blocos, com limite de páginas e erro sem detalhe interno.
- Pergunta anônima sem texto guardado; exclusão de histórico e de conta.
- Documento ao LLM só com consentimento e delimitado como dado.
- `cf-7-xiii` corrigida contra a EC 141/2026 e marcada para revisão jurídica; XSS no frontend estático.

### Ciclo 2 — leitor de processos (backend)
- `app/leitor`: extração por página, número CNJ, peças, partes, linha do tempo, alegações, pedidos,
  decisões, prazos, recursos, glossário; citação conferida por página; perguntas com abstenção.
- API com dono, retenção de 24 h e exclusão; processo fictício e gabarito.

### Ciclo 3 — leitor de processos (interface)
- Página `/documentos` no Next.js com visualizador e destaque do trecho citado.

### Ciclo 4 — monitor legislativo
- `app/monitor` e `scripts/monitor.py`: coleta, diff por artigo, classificação, impacto, relatório,
  revisão humana, reversão; linha de base de 9 fontes; fidelidade do corpus ao texto oficial.
- Correção: a ingestão do Planalto lia a redação revogada (tachada) como vigente.

### Ciclo 5 — validação e avaliação
- Estado de validação em cada resposta e abstenção calibrada.
- `scripts/avaliar.py` com linha de base versionada e portão de regressão.

### Ciclo 6 — CI e documentação
- GitHub Actions (Python 3.10 e 3.13, ruff, mypy, pytest, avaliação; build do Next).
- `requirements-dev.txt`, visão geral em inglês, este histórico.
