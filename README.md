# DireitoAberto ⚖️

**Plataforma de letramento jurídico baseada em legislação brasileira, que traduz os direitos do cidadão em linguagem simples — agora com busca aumentada por recuperação (RAG) sobre um corpus de leis.**

> *"A lei foi escrita pra você. Só faltava alguém traduzir."*

## Como funciona

O cidadão descreve o problema em linguagem comum e recebe a regra aplicável, os artigos de lei com fonte oficial e o caminho prático — como no caso abaixo, respondido com o art. 18 do CDC:

![Resposta do RAG citando o CDC art. 18, com fonte oficial](docs/screenshots/2-resposta-rag.png)

| Home | Modo escuro |
|---|---|
| ![Página inicial](docs/screenshots/1-home.png) | ![Home no modo escuro](docs/screenshots/6-modo-escuro.png) |

| Login | Histórico do usuário | Base legal (filtro STJ) |
|---|---|---|
| ![Tela de login](docs/screenshots/3-login.png) | ![Histórico de consultas](docs/screenshots/4-historico.png) | ![Base legal filtrada por STJ](docs/screenshots/5-base-legal.png) |

## O problema

A legislação brasileira é escrita para operadores do Direito, não para o cidadão. Quem tem um produto com defeito, foi demitido, recebeu uma multa injusta ou teve o nome negativado raramente sabe **qual lei protege o seu caso, quais são os prazos e onde buscar ajuda gratuita** — e o juridiquês afasta exatamente quem mais precisa da informação.

## A solução

O DireitoAberto ataca o problema em duas camadas:

1. **Conteúdo curado** (frontend): 16 situações do dia a dia — consumidor, trabalho, trânsito, moradia, família, saúde, previdência e tributos — explicadas em passo a passo, com prazos, modelos de texto prontos, **fonte oficial destacada** (lei, artigo e link para o Planalto), glossário de juridiquês e canais gratuitos de ajuda (Defensoria Pública, Procon, consumidor.gov.br, ANS, INSS, Banco Central, Juizados Especiais). Interface com modo escuro, animações suaves, filtros por área e histórico de pesquisas.
2. **RAG jurídico** (backend): o usuário descreve o problema em linguagem natural ("*a empresa não quer trocar meu notebook defeituoso*") e o sistema:
   - normaliza a pergunta e a traduz do vocabulário do cidadão para o vocabulário da lei (sinônimos: "notebook" → "produto durável", "nome sujo" → "negativação");
   - busca no corpus de legislação (BM25) os artigos mais relevantes — ex.: CDC art. 18 e art. 26;
   - gera uma resposta cautelosa com LLM (via API, opcional), **citando apenas os artigos recuperados**, com as fontes oficiais do Planalto;
   - sem chave de API, degrada para o **modo extrativo**: devolve os artigos encontrados com orientação padrão.

## Tecnologias

| Camada | Stack |
|---|---|
| Backend | Python 3.10+, FastAPI, Pydantic |
| Recuperação | BM25 em Python puro (padrão) ou embeddings multilíngues (multilingual-e5-small/ONNX) + ChromaDB, atrás da mesma interface `Retriever` |
| Persistência | SQLAlchemy — SQLite por padrão, PostgreSQL via `DIREITO_ABERTO_DATABASE_URL` |
| Autenticação | PBKDF2 (stdlib) + tokens de sessão opacos (Bearer) |
| Documentos | pypdf (upload de nota fiscal/contrato em PDF ou TXT) |
| Geração | API de LLM (pacote `anthropic`), opcional |
| Frontend (produto) | React/Next.js 15 + TypeScript (`web/`): perguntar, login, histórico e base legal |
| Frontend (MVP) | HTML/CSS/JS estático (`frontend/`), servido pelo próprio backend |
| Testes | pytest + TestClient (httpx) — 50 testes |

## Arquitetura

```
frontend/index.html ──── busca local (offline) ─┐
        │ Enter na busca                        │ degrada graciosamente
        ▼                                       │
POST /api/perguntar                             │
        │                                       │
        ▼                                       │
Retriever (BM25 + sinônimos PT-BR)              │
        │  top-k artigos                        │
        ▼                                       │
LLM (via API) ── indisponível? ──► resposta extrativa
        │
        ▼
resposta + artigos + fontes oficiais + aviso legal
```

- `backend/data/legislacao.json` — corpus com 38 dispositivos legais (CDC, CLT, CF/88, CTB, Código Civil, CPC, Lei do Inquilinato, Lei dos Juizados Especiais e Federais, Lei do FGTS, Lei dos Planos de Saúde, Lei de Benefícios do INSS, CTN, Resolução ANAC 400 e 7 súmulas de STF/STJ/TST), cada um com texto, resumo em linguagem simples, tema, palavras-chave, fonte oficial e **bloco de vigência**.
- `backend/app/retrieval.py` — índice BM25 com filtro por área temática; a interface `Retriever.buscar()` permite trocar o motor por busca semântica (embeddings) sem alterar a API.
- `backend/app/llm.py` — camada de geração com prompt que exige linguagem cautelosa, proíbe inventar dispositivos e sempre encaminha para a Defensoria/Procon.
- `backend/app/main.py` — API FastAPI e serving do frontend.

### API pública (v1)

A API é versionada em **`/api/v1`** (os caminhos `/api/...` são aliases de compatibilidade). Documentação interativa em `/docs` (OpenAPI).

| Endpoint | Descrição |
|---|---|
| `POST /api/v1/perguntar` | Pergunta em linguagem natural (filtro opcional `tema`) → resposta + artigos + fontes |
| `POST /api/v1/perguntar-documento` | Multipart: pergunta + arquivo `.pdf`/`.txt` (nota fiscal, contrato) usado como contexto da busca |
| `GET /api/v1/artigos` | Lista o corpus; filtros `?tema=familia`, `?tribunal=STJ`, `?status=em_vacatio` e `?busca=8.078` |
| `GET /api/v1/vigencia` | Fila de monitoramento: normas já publicadas que ainda vão entrar em vigor, com dias restantes |
| `GET /api/v1/estatisticas` | Leis, artigos e jurisprudências indexados, temas, consultas realizadas (persistente), dispositivos por situação e data da última conferência de vigência |
| `POST /api/v1/auth/registrar` | Cria conta (e-mail + senha) e devolve token Bearer |
| `POST /api/v1/auth/entrar` | Login → token Bearer |
| `GET /api/v1/historico` | Consultas do usuário autenticado (as perguntas feitas com token ficam registradas) |
| `GET /api/v1/saude` | Health check |

- **Autenticação é opcional**: sem token, tudo funciona anonimamente; com `Authorization: Bearer <token>`, as consultas entram no histórico do usuário.
- **Retriever semântico**: `pip install chromadb` e `DIREITO_ABERTO_RETRIEVER=semantico`. Usa o **multilingual-e5-small** (ONNX, ~130 MB baixados do Hugging Face na 1ª execução, sem PyTorch), com prefixos assimétricos `query:`/`passage:` e vetores L2-normalizados. No benchmark interno de 21 casos: **e5 19/21 no top-1** vs BM25 18/21 vs MiniLM padrão do Chroma 13/21 — e o e5 acerta parafrases sem nenhuma palavra do corpus ("a companhia aérea me deixou na mão" → Resolução ANAC 400). `DIREITO_ABERTO_EMBEDDING=padrao` força o embedding nativo do Chroma; sem dependências ou sem rede, o fallback é o BM25.
- **Banco**: SQLite em `backend/data/direitoaberto.db` por padrão; para PostgreSQL, `DIREITO_ABERTO_DATABASE_URL=postgresql+psycopg://usuario:senha@host/db`.

### Ingestão do Planalto (semiautomatizada)

```bash
python scripts/ingerir_planalto.py \
  --url https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm \
  --lei "Código de Defesa do Consumidor — Lei nº 8.078/1990" \
  --tema consumidor --artigos 18 26 49 > novos_artigos.json
```

### Controle de vigência

O maior risco de um RAG jurídico não é não achar o artigo — é achar o artigo **errado no tempo**: citar regra revogada como se valesse, ou regra futura antes da hora. Cada dispositivo do corpus carrega um bloco próprio (o rótulo vale para o *dispositivo*, não para a lei inteira: o Código Civil está em vigor, mas o art. 1.790 é inconstitucional):

```json
"vigencia": {
  "status": "em_vacatio",            // vigente · em_vacatio · revogada
  "entra_em_vigor_em": "2026-12-15",
  "alterada_por": ["EC 141/2026"],
  "nota": "Promulgada em 16/10/2026. A regra de 42 horas vale 60 dias após a publicação…",
  "conferida_em": "2026-10-16"
}
```

A informação atravessa o sistema inteiro: entra no contexto do LLM (com regra explícita no prompt de nunca apresentar norma futura como vigente), aparece no modo extrativo, vira badge na resposta e na base legal, e alimenta o endpoint `/api/v1/vigencia`. Hoje a base tem duas normas publicadas e ainda sem efeito — a **EC 141/2026** (fim da escala 6x1: 42h em 15/12/2026, 40h em 14 meses) e o **Decreto 13.135/2026** (novo SAC, a partir de 02/11/2026).

### Benchmark de armadilha temporal

Um RAG jurídico erra de dois jeitos: não achando o dispositivo, ou achando **a redação errada no tempo**. O segundo é mais perigoso, porque a resposta sai fluente e confiante. Este benchmark mede exatamente isso.

**Dataset** (`data/benchmark_temporal.json`): 24 dispositivos cuja redação mudou depois de 10/04/2006 — data em que o texto do *Livro do Cidadão* (AGU/MJ), publicação oficial e gratuita do governo, parou. Cada caso traz a pergunta do cidadão, o que vale hoje e o que aquela fonte responderia.

**Experimento** — três índices:

| Índice | O que contém | O que mede |
|---|---|---|
| limpo | o corpus atual | cobertura: temos a redação vigente? |
| contaminado | corpus + os 24 textos de 2006, **sem marca de obsolescência** | o dano de indexar uma fonte envelhecida |
| mitigado | os mesmos textos, agora com `vigencia.status: revogada` | se o rótulo de vigência basta para neutralizar o dano |

```bash
python3 scripts/benchmark_temporal.py --casos          # BM25
python3 scripts/benchmark_temporal.py --retriever semantico --json resultado.json
```

**Resultado (top-3, corpus de 38 dispositivos):**

| Métrica | BM25 | Semântico (e5) |
|---|---|---|
| dispositivo vigente no corpus | 4/24 (16,7%) | 4/24 (16,7%) |
| recuperado quando existe | 4/4 (100%) | 4/4 (100%) |
| texto de 2006 recuperado | **24/24 (100%)** | **23/24 (95,8%)** |
| texto de 2006 **acima** do vigente | **3/4 (75%)** | **2/4 (50%)** |
| resposta final cita o texto de 2006 | **24/24 (100%)** | **23/24 (95,8%)** |
| …com aviso de revogação, após rotular | **24/24 (100%)** | **23/23 (100%)** |

**Leitura.** Recuperação não resolve validade temporal. O texto de 2006 foi recuperado em praticamente todos os casos e venceu a redação vigente na maioria das perguntas em que as duas competiam — a fonte velha é *melhor escrita* para a pergunta do cidadão, porque foi feita exatamente para ele. Trocar BM25 por embeddings multilíngues melhora pouco (100% → 95,8% de contaminação; 75% → 50% de inversão) e não muda o quadro: **nenhum avanço no motor de busca resolve o problema, porque ele não é de semântica — é de metadado**. O que resolve é o rótulo: com `status: revogada`, o distrator continua sendo recuperado, mas toda resposta passa a trazer o aviso (100% nos dois motores). Daí a decisão de arquitetura do projeto — **a vigência é um campo do corpus, não um detalhe do conteúdo**.

A cobertura de 16,7% é um achado honesto e não um defeito escondido: ela mede o tamanho da lacuna do corpus e se conecta diretamente à lista de leis faltantes do dossiê de fontes (ECA, Lei 6.015, CTB em detalhe, LINDB). Conforme o corpus cresce, o número sobe — e o benchmark é a régua.

*Nota metodológica:* os distratores recebem as mesmas palavras-chave curadas que o corpus dá aos seus dispositivos. Sem isso seriam penalizados de graça pelo peso que o BM25 atribui às palavras-chave, e o resultado seria otimista demais; o benchmark adota o pior caso. Os textos em `obsoleto` são paráfrases da redação antiga conforme o dossiê, não transcrições literais.

### Ingestão de jurisprudência (STF/STJ/TST)

```bash
# a partir da URL do portal (quando ele permitir robôs)…
python scripts/ingerir_jurisprudencia.py --tribunal stf --numeros 25

# …ou de um HTML salvo do navegador (contorna o WAF dos portais)
python scripts/ingerir_jurisprudencia.py --tribunal stj \
  --arquivo sumulas-stj.html --numeros 297 385 --tema consumidor > novas_sumulas.json
```

O parser reconhece os três formatos de cabeçalho ("Súmula Vinculante Nº 25", "Súmula N. 479", "SUM-443") e gera entradas já com `tipo`, `tribunal` e ids na convenção do corpus (`stf-sv25`, `stj-sumula479`…). Como os portais dos tribunais ficam atrás de proteção anti-robô, o modo `--arquivo` é o caminho garantido.

Em ambos os scripts, os esqueletos saem com `"revisado": false` e resumo marcado como TODO. **A revisão humana é parte do fluxo por desenho**: ninguém publica dispositivo sem escrever o resumo em linguagem simples e conferir a vigência — essa é a camada de revisão jurídica do projeto.

## Como rodar

```bash
# 1. API (obrigatória)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# http://localhost:8000  -> frontend estático (MVP) integrado
# http://localhost:8000/docs -> documentação OpenAPI

# 2. Frontend React/Next.js (opcional, em outro terminal)
cd web
npm install
npm run dev
# http://localhost:3000 -> perguntar, login, histórico e base legal
# (o Next proxia /api/* para o FastAPI; para outra origem: API_URL=https://... npm run build)
```

Com a variável `ANTHROPIC_API_KEY` configurada, as respostas passam a ser geradas por LLM; sem chave, o sistema responde no modo extrativo. Para desligar o LLM explicitamente: `export DIREITO_ABERTO_USAR_LLM=0`.

```bash
# testes
cd backend && python -m pytest
```

Exemplo de uso da API:

```bash
curl -s localhost:8000/api/perguntar \
  -H 'Content-Type: application/json' \
  -d '{"pergunta": "A empresa não quer trocar meu notebook defeituoso"}'
```

## Deploy (link público em ~5 minutos)

O repositório já traz `render.yaml` (API) e `web/vercel.json` (frontend). Os cliques:

**1. Backend no Render** (gratuito)
1. [dashboard.render.com](https://dashboard.render.com) → **New → Blueprint** → selecione este repositório.
2. O blueprint cria o serviço `direitoaberto-api` **e** um PostgreSQL gratuito já conectado (`DIREITO_ABERTO_DATABASE_URL`).
3. Ao final, copie a URL do serviço (ex.: `https://direitoaberto-api.onrender.com`).
4. Opcional: defina `ANTHROPIC_API_KEY` no painel para respostas geradas por LLM — sem ela, o modo extrativo responde normalmente.

**2. Frontend na Vercel** (gratuito)
1. [vercel.com/new](https://vercel.com/new) → importe este repositório.
2. **Root Directory**: `web` (o framework Next.js é detectado sozinho).
3. Em *Environment Variables*, adicione `API_URL` = URL do Render (passo 1.3).
4. Deploy → o site sai em `https://<projeto>.vercel.app`.

Avisos do plano gratuito: o serviço do Render hiberna após inatividade (a primeira requisição demora ~1 min) e o PostgreSQL free expira em 30 dias — sem ele o app cai no SQLite, que é efêmero no free tier (o histórico zera a cada redeploy).

## Limitações (leia antes de usar)

- **Não é aconselhamento jurídico.** O sistema informa a regra geral; detalhes do caso concreto mudam a resposta. Toda resposta encaminha para a Defensoria Pública (gratuita), Procon ou advogado.
- O corpus é **curado e pequeno** (38 dispositivos legais): cobre consumidor, trabalho, trânsito, moradia, família, saúde, previdência, tributos e acesso à Justiça, e nada além disso.
- A vigência é **conferida manualmente**, não monitorada em tempo real: cada dispositivo carrega a data da última conferência (`vigencia.conferida_em`) e o `GET /api/v1/vigencia` mostra o que está prestes a mudar. Uma norma alterada entre duas conferências continuaria sendo respondida com a redação antiga — por isso a data aparece junto da resposta.
- A busca é **lexical** (BM25 + sinônimos), não semântica — perguntas muito distantes do vocabulário indexado podem não encontrar nada (o sistema diz isso em vez de inventar).
- Os textos legais foram consolidados manualmente a partir do Planalto e podem não refletir alterações legislativas posteriores; cada artigo traz o link para a fonte oficial.
- Sem jurisprudência por enquanto (ver roadmap).

## Roadmap

- ✅ MVP estático com conteúdo curado
- ✅ RAG (BM25 + sinônimos PT-BR) com camada de LLM e fallback extrativo
- ✅ Revisão jurídica do conteúdo (JEC 40/20 salários mínimos, frete no arrependimento)
- ✅ 16 situações em 8 áreas (família, saúde, previdência, tributos…)
- ✅ Fonte oficial (lei + artigo + link do Planalto) em cada situação e resposta
- ✅ Filtros por área, busca por lei/artigo e histórico de pesquisas
- ✅ Estatísticas da base (`/api/estatisticas` + página no frontend)
- ✅ Modo escuro, animações e design responsivo
- ✅ Embeddings (busca semântica atrás da mesma interface `Retriever`)
- ✅ ChromaDB como índice vetorial (opt-in via `DIREITO_ABERTO_RETRIEVER=semantico`)
- ✅ PostgreSQL-ready (SQLAlchemy; SQLite por padrão, PostgreSQL via variável de ambiente)
- ✅ Ingestão semiautomatizada do Planalto (`scripts/ingerir_planalto.py` + revisão humana)
- ✅ Jurisprudência STF (Súmula Vinculante 25 — curadoria inicial)
- ✅ Jurisprudência STJ (Súmulas 297, 385, 302 e 479 — curadoria inicial)
- ✅ Jurisprudência TST (Súmulas 338 e 443 — curadoria inicial)
- ✅ Login (registro/entrada com token Bearer)
- ✅ Histórico por usuário (`/api/v1/historico`)
- ✅ API pública documentada e versionada (`/api/v1` + OpenAPI em `/docs`)
- ✅ Upload de documentos (nota fiscal, contrato) com extração de contexto (PDF/TXT)
- ✅ Embeddings multilíngues de qualidade (multilingual-e5-small em ONNX; 19/21 no top-1 do benchmark interno, contra 13/21 do MiniLM padrão)
- ✅ Ingestão de jurisprudência STF/STJ/TST (`scripts/ingerir_jurisprudencia.py`, por URL ou HTML salvo — os portais bloqueiam robôs)
- ✅ Controle de vigência por dispositivo (status, data de entrada em vigor, norma alteradora e data de conferência) exposto na API, no LLM e nos dois frontends
- ✅ Fila de monitoramento de normas em vacatio legis (`/api/v1/vigencia`)
- ⬜ Migrações de banco (Alembic) e deploy com PostgreSQL gerenciado
- ✅ Frontend em React/Next.js (`web/`: perguntar, login, histórico e base legal, com modo escuro)
- ✅ Benchmark de armadilha temporal (24 casos, três índices; mede cobertura, contaminação por fonte desatualizada e eficácia do rótulo de vigência)
- ⬜ Valores dinâmicos (tetos dos Juizados calculados a partir do salário mínimo vigente, em vez de fixos no conteúdo)
- ⬜ Camada de revisão jurídica contínua com profissional (o fluxo `revisado: false` já existe)

### A visão de longo prazo

Integrar **STF, STJ, TST e Planalto num único mecanismo de busca cidadã**: o usuário descreve o caso em linguagem comum e recebe a lei vigente, a jurisprudência dominante e o caminho prático — com fonte oficial em cada afirmação. É o ponto em que o projeto deixa de ser um protótipo educacional e vira uma LegalTech de acesso à Justiça.

## Tags sugeridas para o repositório

`python` · `fastapi` · `artificial-intelligence` · `natural-language-processing` · `rag` · `legal-tech` · `brazilian-law` · `education`

## Licença

Distribuído sob a licença [MIT](LICENSE) — © 2026 Roberto Chiocca.

---

**DireitoAberto** — *a lei em código aberto.* Este projeto oferece informação jurídica geral e não substitui a orientação de um advogado ou da Defensoria Pública.
