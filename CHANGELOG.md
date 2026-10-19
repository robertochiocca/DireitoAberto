# Histórico de mudanças

Mudanças relevantes, da mais recente para a mais antiga. O histórico anterior está no `git log` e no
roadmap do README.

## Auditoria e plataforma de inteligência jurídica verificável — outubro de 2026

Branch `claude/direitoaberto-intelligence`, em ciclos (detalhes em [docs/roadmap.md](docs/roadmap.md)).

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
