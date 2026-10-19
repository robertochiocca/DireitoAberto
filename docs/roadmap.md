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
| Alta | Vigência recalculada pela data, no fuso de Brasília | A5, M4 | planejado (ciclo 1) |
| Alta | Expiração e revogação de tokens; logout | A1 | planejado (ciclo 1) |
| Alta | Limitação de requisições em login, registro, perguntas e upload | A2 | planejado (ciclo 1) |
| Alta | Upload com leitura limitada, limite de páginas, erro genérico | A3 | planejado (ciclo 1) |
| Alta | Minimização: não gravar texto de pergunta anônima; apagar histórico | A4 | planejado (ciclo 1) |
| Alta | Documento delimitado como dado não confiável no prompt | A6 | planejado (ciclo 1) |
| Alta | Revisão da entrada `cf-7-xiii` contra a EC 141/2026 | legal-data-sources | planejado (ciclo 1: marcar para revisão com evidência) |
| Média | CORS restrito e configurável | M1 | planejado (ciclo 1) |
| Média | Log das falhas do LLM | M2 | planejado (ciclo 1) |
| Média | Enumeração de contas por tempo de resposta | M3 | planejado (ciclo 1) |
| Média | `base_atualizada_em` honesto | M5 | planejado (ciclo 1) |
| Média | XSS no frontend estático | M7 | planejado (ciclo 1) |
| Alta (produto) | Leitor de processos: backend | pedido, entrega 1 | planejado (ciclo 2) |
| Alta (produto) | Leitor de processos: interface | pedido, entrega 1 | planejado (ciclo 3) |
| Alta (produto) | Monitor de mudanças: snapshots, diff, relatório, fila de revisão | pedido, entrega 2 | planejado (ciclo 4) |
| Alta (produto) | Estados de validação e avaliação reproduzível | pedido, entrega 3 | planejado (ciclo 5) |
| Média | CI (pytest + build do web) | B4 | planejado (ciclo 6) |
| Média | Migrações com Alembic | M6 | planejado |
| Média | Next.js 16 (elimina o `postcss` vulnerável embutido) | C1 residual | planejado |
| Média | Conteúdo jurídico dos frontends sob controle de vigência | legal-data-sources | planejado |
| Baixa | Cabeçalhos de segurança, e-mail sem distinção de maiúsculas | B1, B2 | planejado |
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
