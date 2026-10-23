# Auditoria de segurança e privacidade

> Auditoria de 19/10/2026 sobre o código do repositório (branch `main`, commit `2db388e`).
> Cobre o backend FastAPI (`backend/`), o frontend estático (`frontend/`) e o Next.js (`web/`).
> **Não cobre** a configuração real de produção (Render/Vercel), que não está acessível daqui.
> Nada aqui equivale a certificação de segurança ou a declaração de conformidade com a LGPD.

## Rodada 9.0 (22/10/2026): modelo de ameaças, achados e controles

> Auditoria read-only refeita sobre o HEAD `22c7f81` (15 achados de segurança/LGPD, `P2-01` a `P2-15`),
> correções com teste e o que continua aberto. **Controles técnicos não são conformidade com a LGPD:**
> falta definir controlador, encarregado e bases legais com assessoria jurídica, e revisar a política de
> privacidade (hoje uma minuta técnica em `web/app/privacidade`).

### Modelo de ameaças (atualizado)

| Ativo | Ameaça | Controle |
|---|---|---|
| Perguntas | vazamento, retenção sem prazo, envio ao LLM sem aviso | anônima não guarda o texto; com conta, 365 dias; aviso na página quando o LLM está ativo (`/saude` → `llm_ativo`); fontes servidas pelo próprio site |
| Documentos do leitor (dados de terceiros, segredo de justiça) | acesso cruzado, retenção, esgotamento de recursos, injeção de instrução | dono checado; 24 h; limites de páginas, caracteres e tempo também no `.txt`; texto como dado, nunca como instrução; sem LLM externo |
| Contas | força bruta, bloqueio malicioso da vítima, token roubado | bloqueio por conta **e** rede de origem, só falhas contam; PBKDF2 600 mil com parâmetros no hash e *rehash*; troca de senha e "sair de todas"; CSP no Next |
| Corpus jurídico publicado | edição sem revisão, coleta falha sobrescrevendo texto, publicação automática | selos e histórico verificados no CI; o monitor nunca escreve no corpus; publicação só por pessoa (`corpus.py publicar`); feedback não muda nada sozinho |
| Registro do monitor | escritas concorrentes, arquivo ilegível para a API | trava `fcntl` + contador de revisão; 0644 |
| Trilha de auditoria | virar ela mesma um depósito de dados pessoais | só evento, resultado, pseudônimo (HMAC do id) e prefixo de rede; 180 dias |
| Feedback | dado pessoal em texto livre, abuso | máscara de CPF/e-mail/telefone/número de processo; 5 envios/10 min por endereço; sai na exportação, some com a conta; 365 dias |
| Disponibilidade | corpo de requisição gigante, *event loop* travado | limite de corpo no ASGI (inclusive *chunked*), PDF em *threadpool* |

### Achados da rodada e estado

| # | Sev. | Achado | Estado |
|---|---|---|---|
| P2-01 | Alta | `.txt` no leitor sem limite de páginas (form feeds derrubam a API) | **corrigido** no ciclo do leitor: limite de páginas e caracteres também no `.txt`, páginas não processadas sem texto gravado, análise com teto ([leitor-de-processos.md](leitor-de-processos.md)) |
| P2-02 | Média | `/perguntar-documento` bloqueava o *event loop* | **corrigido**: extração e resposta em `run_in_threadpool` |
| P2-03 | Média | limite de upload aplicado depois de receber o corpo inteiro | **corrigido**: middleware ASGI `LimiteDeCorpo` corta antes (256 KB por padrão; limites próprios para upload), inclusive corpo *chunked* sem `Content-Length`; teste |
| P2-04 | Média | dependências sem mínimo seguro; `pypdf` com 13 avisos; CI sem `pip-audit` | **corrigido**: `pypdf>=6.21.1`, `python-multipart>=0.0.31`, `starlette>=1.3.1`; o CI audita as versões **instaladas** |
| P2-05 | Média | qualquer pessoa bloqueava o login de outra (5 tentativas de qualquer lugar) | **corrigido**: chave conta + rede (/24 ou /48), só falhas contam, acerto zera; testes de vítima e atacante |
| P2-06 | Média | sem trilha de auditoria | **corrigido**: `app/auditoria.py`, 13 eventos (login, falha, bloqueio, conta criada/excluída, sessões, senha, exportação, histórico, documentos, feedback); teste de que e-mail e conteúdo não entram |
| P2-07 | Média | direitos do titular incompletos | **corrigido em parte**: `GET /conta/exportar` (conta, histórico completo, documentos, feedbacks), histórico paginado, tela `/conta` (exportar, trocar senha, sair de todas, excluir). **Aberto:** recuperação de senha (exige e-mail transacional — serviço externo) |
| P2-08 | Média | limite por IP atrás do proxy (balde único ou XFF falsificável; IPv6 rotaciona) | **aberto**: depende de verificar o X-Forwarded-For real no Render/Vercel. O bloqueio de login já agrupa por /24 e /48 |
| P2-09 | Média | sem política, encarregado nem aviso de envio ao LLM; Google Fonts | **corrigido em parte**: aviso de LLM na página, fontes servidas pelo próprio site (`next/font`; o estático usa fontes do sistema), minuta técnica de privacidade. **Aberto:** controlador, encarregado, bases legais, termos de uso — decisão jurídica |
| P2-10 | Baixa | Next sem cabeçalhos de segurança | **corrigido**: CSP, `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, sem `X-Powered-By`. A CSP ainda permite `'unsafe-inline'` em *scripts* (o Next injeta *scripts* inline; *nonce* fica para depois). HSTS em produção não verificado |
| P2-11 | Baixa | sem troca de senha nem "sair de todas"; PBKDF2 240 mil sem parâmetros no hash | **corrigido**: 600 mil iterações, formato com algoritmo e iterações, *rehash* no login; `/conta/senha` encerra as outras sessões; `/auth/sair-de-todas` |
| P2-12 | Baixa | retenção preguiçosa | **corrigido**: `app/manutencao.py` apaga, no máximo uma vez por hora, sessões vencidas, documentos vencidos, consultas com conta > 365 dias, auditoria > 180 dias, feedback > 365 dias |
| P2-13 | Baixa | `tema` sem limite | **corrigido**: até 50 caracteres e só temas do corpus |
| P2-14 | Baixa | delimitador do documento só neutralizado em minúsculas exatas | **corrigido**: variantes de caixa, espaço e entidade neutralizadas; teste |
| P2-15 | Baixa | estático guardava as perguntas no `localStorage` | **corrigido**: `sessionStorage` (só a aba), e a cópia antiga do `localStorage` é apagada; teste de navegador |

Outros controles desta rodada: texto gerado pelo LLM que falha na verificação determinística não é
entregue (`app/verificador.py`); o workflow do monitor tem permissão só de leitura e recebe as entradas
por variável de ambiente (sem interpolação no *shell*); o registro do monitor e o corpus têm trava entre
processos.

### Não verificado nesta rodada

- Produção: variáveis do Render/Vercel, HSTS, X-Forwarded-For real, logs e backups do provedor.
- LLM: resistência real a injeção de instrução e aderência às regras (sem chave de API neste ambiente).
- Resistência do bloqueio de login a ataque distribuído por muitas redes (o bloqueio é por conta + rede;
  muitas redes diferentes ainda podem tentar senhas, contidas só pelo custo do PBKDF2 e pelo limite por
  endereço).
- Revisão jurídica da minuta de privacidade.

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
| A1 | Alta | Tokens de sessão nunca expiram e não podem ser revogados: "Sair" no frontend só apaga o `localStorage`; o token continua válido no servidor para sempre | `auth.py` (`TokenSessao` sem validade, nenhum endpoint de logout) | Confirmado | **corrigido (ciclo 1)**: validade de 30 dias (`DIREITO_ABERTO_TOKEN_VALIDADE_HORAS`) calculada sobre `criado_em` (sem migração), `POST /auth/sair` revoga, o Next chama o logout no servidor |
| A2 | Alta | Nenhuma limitação de requisições: login (força bruta), registro (criação em massa), `/perguntar` (custo de LLM) e upload. Cada login custa 240 mil iterações de PBKDF2 — amplificação de CPU | `main.py` | Confirmado | **mitigado (ciclo 1)**: janela deslizante em memória por endereço (login/registro 10/min, perguntas 30/min, upload 10/min) e por conta (5 logins/5 min), com `Retry-After`. Ressalvas: vale por processo; atrás de proxy depende de `DIREITO_ABERTO_PROXIES_CONFIAVEIS` — pelo frontend da Vercel, o endereço visto pela API é o do servidor da Vercel, e esses usuários dividem um limite (não verificado em produção) |
| A3 | Alta | Upload lido inteiro na memória **antes** de checar o tamanho (`await arquivo.read()`); sem limite de páginas no PDF; a mensagem de erro repassa a exceção interna do `pypdf` ao cliente | `main.py:perguntar_com_documento`, `documentos.py` | Confirmado | **corrigido (ciclo 1)**: leitura em blocos de 64 KB com corte no limite (413), limite de páginas (`DIREITO_ABERTO_UPLOAD_MAX_PAGINAS`, 300), PDF com senha recusado com mensagem clara, erro genérico ao cliente e tipo da exceção no log |
| A4 | Alta | Perguntas anônimas gravadas com o texto integral, sem prazo de retenção e sem uso no produto (só o histórico do usuário logado lê `pergunta`). Nenhum meio de o usuário apagar o próprio histórico ou a conta | `db.py:Consulta`, `main.py:_responder` | Confirmado | **corrigido (ciclo 1)**: consulta anônima grava só contagem e artigos, sem o texto; `DELETE /historico` e `POST /conta/excluir` (pede a senha). Linhas antigas no banco de produção não foram tocadas — limpá-las é ação destrutiva que depende de autorização |
| A5 | Alta | Status de vigência é estático: `em_vacatio` continua "AINDA NÃO ESTÁ EM VIGOR" depois da data de início, até alguém editar o JSON. O Decreto 13.135/2026 (SAC) começa a valer em 02/11/2026 — a partir daí a API passaria a dizer ao cidadão que a regra vigente ainda não vale | `llm.py:rotulo_vigencia`, `retrieval.py:em_vigor` | Confirmado | **corrigido (ciclo 1)**: `app/vigencia.py` recalcula a situação na data da consulta, em Brasília; a norma aparece como "EM VIGOR desde…" com `status_registrado` para a fila de revisão. Data passada nunca revoga nada |
| A6 | Alta | Texto do documento enviado vai ao LLM externo (quando há chave) sem consentimento explícito e sem delimitação: instruções escritas dentro do PDF entram no prompt como se fossem parte da pergunta | `main.py:_responder` (`pergunta_llm`) | Confirmado (envio); Potencial (injeção) | **mitigado (ciclo 1)**: o documento só vai ao LLM com `permitir_ia_externa=true`; vai delimitado em `<documento_do_cidadao>` com a tag de fechamento neutralizada, e o *system prompt* manda tratá-lo como dado. Resistência real à injeção não medida (sem chave) |
| M1 | Média | CORS `allow_origins=["*"]` com todos os métodos e cabeçalhos. Atenuante: tokens vão em cabeçalho, não em cookie. Nenhum dos dois frontends precisa de CORS (o estático é servido pela API; o Next repassa `/api` pelo servidor) | `main.py` | Confirmado | **corrigido (ciclo 1)**: `DIREITO_ABERTO_CORS_ORIGENS` (padrão: Next em desenvolvimento; vazio no `render.yaml`), métodos e cabeçalhos explícitos |
| M2 | Média | Falhas do LLM são engolidas sem log (`except Exception: return None`): chave inválida ou modelo inexistente viram "modo extrativo" sem ninguém saber | `llm.py:gerar_resposta` | Confirmado | **corrigido (ciclo 1)**: erros da API registrados por tipo e status HTTP, sem o conteúdo do pedido; ausência de credencial continua silenciosa (é o modo normal) |
| M3 | Média | Enumeração de contas: registro devolve 409 para e-mail existente; login responde mais rápido quando o e-mail não existe (não calcula PBKDF2) | `main.py:registrar/entrar` | Confirmado (código); tempo não medido | **mitigado (ciclo 1)**: login sem conta calcula o PBKDF2 de um hash fictício; o 409 do cadastro fica (mensagem útil), contido pela limitação |
| M4 | Média | `date.today()` usa o fuso do servidor (UTC no Render): entre 21h e 0h de Brasília, a fila de vigência conta um dia a mais | `main.py:fila_de_vigencia` | Confirmado | **corrigido (ciclo 1)** |
| M5 | Média | `base_atualizada_em` vem do `mtime` do arquivo do corpus: num deploy, é a hora do checkout, não a da última revisão — a API afirma uma atualização que não houve | `main.py:estatisticas` | Confirmado | **corrigido (ciclo 1)**: conferência mais recente registrada no corpus |
| M6 | Média | Sem migrações: `create_all` não altera tabelas existentes; qualquer coluna nova quebra bancos já criados | `db.py:init_db` | Confirmado | aberto (roadmap: Alembic) |
| M7 | Média | Frontend estático: histórico local inserido em `innerHTML` sem escape (`${q}`) e com escape de atributo quebrável (`&quot;` digitado pelo usuário vira aspas). É *self-XSS* (o texto vem do próprio usuário), mas o mesmo padrão com dado externo seria XSS real. `esc()` não escapa aspas e é usado em `href` | `frontend/index.html:renderHistorico`, `perguntarAPI` | Confirmado | **corrigido (ciclo 1)**: `esc()` escapa aspas, histórico sem `onclick` montado com texto, `href` só aceita http(s); teste de navegador com carga maliciosa |
| B1 | Baixa | E-mail sensível a maiúsculas: `Fulano@x.com` e `fulano@x.com` viram duas contas | `main.py` | Confirmado | **corrigido (ciclo 1)**: e-mail normalizado no cadastro; busca sem distinção de maiúsculas (inclui contas antigas) |
| B2 | Baixa | Sem cabeçalhos de segurança no frontend estático servido pela API (`X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors`) | `main.py` | Confirmado | **corrigido (ciclo 1)**: `nosniff`, `Referrer-Policy`, `X-Frame-Options`, `frame-ancestors 'none'`. CSP completa fica para depois: o estático usa *scripts* e manipuladores inline |
| B3 | Baixa | Token no `localStorage` (roubável por XSS). Atenuantes: React escapa por padrão; o projeto não usa `dangerouslySetInnerHTML` com dado externo | `web/lib/api.ts` | Aceito por ora | aceito |
| B4 | Baixa | Sem CI, sem configuração de lint/tipos versionada | repositório | Confirmado | **corrigido (ciclos 1 e 6)**: ruff e mypy versionados e limpos; `.github/workflows/ci.yml` com lint, tipos, testes, avaliação, build do Next e `npm audit` no nível crítico |

## Não verificado

- Configuração de produção (variáveis no Render, domínio da Vercel, TLS, logs do provedor).
- Backups: o `render.yaml` usa o PostgreSQL gratuito, que expira em 30 dias; não há rotina de backup no repositório.
- Comportamento real do LLM (não há chave neste ambiente): resistência a injeção de prompt e aderência às regras do *system prompt* não foram medidas.
- Retriever semântico: pulado por falta de `chromadb` e do modelo e5.
- Política de privacidade e termos de uso: não existem no repositório.

## Riscos específicos do módulo de leitura de processos

Os seis requisitos abaixo foram definidos antes de construir o módulo e **implementados no ciclo 2**,
com testes (`tests/test_leitor.py`: dono e IDOR, retenção, exclusão com a conta, limites, injeção de
instrução). Ver [leitor-de-processos.md](leitor-de-processos.md).

O módulo pedido no roadmap recebe **processos judiciais**, que podem estar em segredo de justiça e trazem dados de terceiros (partes contrárias, testemunhas, menores). Requisitos mínimos derivados desta auditoria:

1. Documento sempre ligado a um dono; toda leitura confere o dono (teste de IDOR).
2. Prazo de retenção curto e configurável, exclusão explícita pelo usuário, e exclusão também dos dados derivados.
3. Guardar o texto extraído, não o arquivo original (o navegador já tem o arquivo para exibir).
4. Por padrão, nenhum envio a LLM externo; quando habilitado, só com consentimento por documento.
5. Texto do documento tratado como dado não confiável, nunca como instrução.
6. Limites de tamanho, de páginas e de tempo de processamento.
