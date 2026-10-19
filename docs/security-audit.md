# Auditoria de segurança e privacidade

> Auditoria de 19/10/2026 sobre o código do repositório (branch `main`, commit `2db388e`).
> Cobre o backend FastAPI (`backend/`), o frontend estático (`frontend/`) e o Next.js (`web/`).
> **Não cobre** a configuração real de produção (Render/Vercel), que não está acessível daqui.
> Nada aqui equivale a certificação de segurança ou a declaração de conformidade com a LGPD.

## Como a auditoria foi feita

| Verificação | Ferramenta | Resultado na linha de base |
|---|---|---|
| Leitura integral do backend | manual (13 módulos, 3 scripts, 13 arquivos de teste) | achados abaixo |
| Testes | `pytest` (venv limpo, `requirements.txt` + `playwright==1.56.0`, versão que casa com o Chromium pré-instalado) | **141 passaram, 1 pulado** (retriever semântico: chromadb ausente). Sem Playwright: 138 passam e 2 módulos são pulados |
| Lint e regras de segurança | `ruff check --select S,B,ASYNC app` | nenhum achado `S` (bandit); 14 `B008` (idioma do FastAPI, falso positivo), 1 `B033` (stopword duplicada), 1 `B905` |
| Tipos | `mypy app --ignore-missing-imports` | 5 erros de anotação, nenhum de lógica |
| Dependências Python | `pip-audit -r requirements.txt` | nenhuma vulnerabilidade conhecida |
| Dependências do `web/` | `npm audit --omit=dev` | **1 crítica, 4 altas** (Next.js 15.5.20 e transitivas) |
| Build do `web/` | `tsc --noEmit` + `next build` | passam |

Classificação dos achados:

- **Confirmado**: visto no código e, quando indicado, reproduzido.
- **Potencial**: o código permite, mas a exploração não foi demonstrada.
- **Não verificado**: depende de algo fora do alcance desta auditoria.

## Modelo de ameaças (resumo)

| Ativo | Por que importa | Quem ameaça |
|---|---|---|
| Perguntas dos cidadãos | podem conter saúde, violência doméstica, dívidas, processos | vazamento do banco, logs, terceiros com acesso ao provedor de LLM |
| Documentos enviados (nota fiscal, contrato; no futuro, processos) | dados pessoais de terceiros, segredo de justiça | acesso cruzado entre usuários (IDOR), retenção indefinida, envio ao LLM |
| Contas e tokens | dão acesso ao histórico | força bruta, roubo de token (XSS), token que nunca expira |
| Corpus jurídico | a resposta só é tão boa quanto ele | edição sem revisão, fonte desatualizada |
| Custo de LLM | cada pergunta pode custar uma chamada paga | abuso automatizado sem limite de requisições |

## Achados

Estados: **aberto**, **corrigido (ciclo N)**, **mitigado** (risco reduzido, não eliminado), **aceito** (decisão documentada).

| # | Sev. | Achado | Evidência | Tipo | Estado |
|---|---|---|---|---|---|
| C1 | Crítica | Next.js 15.5.20 com 12 avisos de segurança (RCE em Image Optimization, SSRF em rewrites, cache poisoning) | `npm audit` | Confirmado | **corrigido (ciclo 0)**: `next@15.5.28` (backport) + `npm audit fix`. Resta o `postcss` embutido no Next, usado só no build sobre o CSS do próprio projeto; sair dele exige o Next 16 (ver roadmap) |
| A1 | Alta | Tokens de sessão nunca expiram e não podem ser revogados: "Sair" no frontend só apaga o `localStorage`; o token continua válido no servidor para sempre | `auth.py` (`TokenSessao` sem validade, nenhum endpoint de logout) | Confirmado | aberto |
| A2 | Alta | Nenhuma limitação de requisições: login (força bruta), registro (criação em massa), `/perguntar` (custo de LLM) e upload. Cada login custa 240 mil iterações de PBKDF2 — amplificação de CPU | `main.py` | Confirmado | aberto |
| A3 | Alta | Upload lido inteiro na memória **antes** de checar o tamanho (`await arquivo.read()`); sem limite de páginas no PDF; a mensagem de erro repassa a exceção interna do `pypdf` ao cliente | `main.py:perguntar_com_documento`, `documentos.py` | Confirmado | aberto |
| A4 | Alta | Perguntas anônimas gravadas com o texto integral, sem prazo de retenção e sem uso no produto (só o histórico do usuário logado lê `pergunta`). Nenhum meio de o usuário apagar o próprio histórico ou a conta | `db.py:Consulta`, `main.py:_responder` | Confirmado | aberto |
| A5 | Alta | Status de vigência é estático: `em_vacatio` continua "AINDA NÃO ESTÁ EM VIGOR" depois da data de início, até alguém editar o JSON. O Decreto 13.135/2026 (SAC) começa a valer em 02/11/2026 — a partir daí a API passaria a dizer ao cidadão que a regra vigente ainda não vale | `llm.py:rotulo_vigencia`, `retrieval.py:em_vigor` | Confirmado | aberto |
| A6 | Alta | Texto do documento enviado vai ao LLM externo (quando há chave) sem consentimento explícito e sem delimitação: instruções escritas dentro do PDF entram no prompt como se fossem parte da pergunta | `main.py:_responder` (`pergunta_llm`) | Confirmado (envio); Potencial (injeção) | aberto |
| M1 | Média | CORS `allow_origins=["*"]` com todos os métodos e cabeçalhos. Atenuante: tokens vão em cabeçalho, não em cookie. Nenhum dos dois frontends precisa de CORS (o estático é servido pela API; o Next repassa `/api` pelo servidor) | `main.py` | Confirmado | aberto |
| M2 | Média | Falhas do LLM são engolidas sem log (`except Exception: return None`): chave inválida ou modelo inexistente viram "modo extrativo" sem ninguém saber | `llm.py:gerar_resposta` | Confirmado | aberto |
| M3 | Média | Enumeração de contas: registro devolve 409 para e-mail existente; login responde mais rápido quando o e-mail não existe (não calcula PBKDF2) | `main.py:registrar/entrar` | Confirmado (código); tempo não medido | aberto |
| M4 | Média | `date.today()` usa o fuso do servidor (UTC no Render): entre 21h e 0h de Brasília, a fila de vigência conta um dia a mais | `main.py:fila_de_vigencia` | Confirmado | aberto |
| M5 | Média | `base_atualizada_em` vem do `mtime` do arquivo do corpus: num deploy, é a hora do checkout, não a da última revisão — a API afirma uma atualização que não houve | `main.py:estatisticas` | Confirmado | aberto |
| M6 | Média | Sem migrações: `create_all` não altera tabelas existentes; qualquer coluna nova quebra bancos já criados | `db.py:init_db` | Confirmado | aberto (roadmap: Alembic) |
| M7 | Média | Frontend estático: histórico local inserido em `innerHTML` sem escape (`${q}`) e com escape de atributo quebrável (`&quot;` digitado pelo usuário vira aspas). É *self-XSS* (o texto vem do próprio usuário), mas o mesmo padrão com dado externo seria XSS real. `esc()` não escapa aspas e é usado em `href` | `frontend/index.html:renderHistorico`, `perguntarAPI` | Confirmado | aberto |
| B1 | Baixa | E-mail sensível a maiúsculas: `Fulano@x.com` e `fulano@x.com` viram duas contas | `main.py` | Confirmado | aberto |
| B2 | Baixa | Sem cabeçalhos de segurança no frontend estático servido pela API (`X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors`) | `main.py` | Confirmado | aberto |
| B3 | Baixa | Token no `localStorage` (roubável por XSS). Atenuantes: React escapa por padrão; o projeto não usa `dangerouslySetInnerHTML` com dado externo | `web/lib/api.ts` | Aceito por ora | aceito |
| B4 | Baixa | Sem CI, sem configuração de lint/tipos versionada | repositório | Confirmado | aberto |

## Não verificado

- Configuração de produção (variáveis no Render, domínio da Vercel, TLS, logs do provedor).
- Backups: o `render.yaml` usa o PostgreSQL gratuito, que expira em 30 dias; não há rotina de backup no repositório.
- Comportamento real do LLM (não há chave neste ambiente): resistência a injeção de prompt e aderência às regras do *system prompt* não foram medidas.
- Retriever semântico: pulado por falta de `chromadb` e do modelo e5.
- Política de privacidade e termos de uso: não existem no repositório.

## Riscos específicos do módulo de leitura de processos (antes de construí-lo)

O módulo pedido no roadmap recebe **processos judiciais**, que podem estar em segredo de justiça e trazem dados de terceiros (partes contrárias, testemunhas, menores). Requisitos mínimos derivados desta auditoria:

1. Documento sempre ligado a um dono; toda leitura confere o dono (teste de IDOR).
2. Prazo de retenção curto e configurável, exclusão explícita pelo usuário, e exclusão também dos dados derivados.
3. Guardar o texto extraído, não o arquivo original (o navegador já tem o arquivo para exibir).
4. Por padrão, nenhum envio a LLM externo; quando habilitado, só com consentimento por documento.
5. Texto do documento tratado como dado não confiável, nunca como instrução.
6. Limites de tamanho, de páginas e de tempo de processamento.
