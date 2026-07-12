# DireitoAberto ⚖️

**Plataforma de letramento jurídico baseada em legislação brasileira, que traduz os direitos do cidadão em linguagem simples — agora com busca aumentada por recuperação (RAG) sobre um corpus de leis.**

> *"A lei foi escrita pra você. Só faltava alguém traduzir."*

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
| Recuperação | BM25 em Python puro (padrão) ou embeddings + ChromaDB (opt-in), atrás da mesma interface `Retriever` |
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

- `backend/data/legislacao.json` — corpus com 30 dispositivos legais (CDC, CLT, CF/88, CTB, Código Civil, CPC, Lei do Inquilinato, Lei dos Juizados Especiais e Federais, Lei do FGTS, Lei dos Planos de Saúde, Lei de Benefícios do INSS, CTN, Súmula 479/STJ e Resolução ANAC 400), cada um com texto, resumo em linguagem simples, tema, palavras-chave e link para a fonte oficial.
- `backend/app/retrieval.py` — índice BM25 com filtro por área temática; a interface `Retriever.buscar()` permite trocar o motor por busca semântica (embeddings) sem alterar a API.
- `backend/app/llm.py` — camada de geração com prompt que exige linguagem cautelosa, proíbe inventar dispositivos e sempre encaminha para a Defensoria/Procon.
- `backend/app/main.py` — API FastAPI e serving do frontend.

### API pública (v1)

A API é versionada em **`/api/v1`** (os caminhos `/api/...` são aliases de compatibilidade). Documentação interativa em `/docs` (OpenAPI).

| Endpoint | Descrição |
|---|---|
| `POST /api/v1/perguntar` | Pergunta em linguagem natural (filtro opcional `tema`) → resposta + artigos + fontes |
| `POST /api/v1/perguntar-documento` | Multipart: pergunta + arquivo `.pdf`/`.txt` (nota fiscal, contrato) usado como contexto da busca |
| `GET /api/v1/artigos` | Lista o corpus; filtros `?tema=familia`, `?tribunal=STJ` e `?busca=8.078` |
| `GET /api/v1/estatisticas` | Leis, artigos e jurisprudências indexados, temas, consultas realizadas (persistente) e atualização da base |
| `POST /api/v1/auth/registrar` | Cria conta (e-mail + senha) e devolve token Bearer |
| `POST /api/v1/auth/entrar` | Login → token Bearer |
| `GET /api/v1/historico` | Consultas do usuário autenticado (as perguntas feitas com token ficam registradas) |
| `GET /api/v1/saude` | Health check |

- **Autenticação é opcional**: sem token, tudo funciona anonimamente; com `Authorization: Bearer <token>`, as consultas entram no histórico do usuário.
- **Retriever semântico (experimental)**: `pip install chromadb` e `DIREITO_ABERTO_RETRIEVER=semantico`. O embedding padrão (MiniLM/ONNX, baixado na 1ª execução) tem qualidade limitada em português — por isso o BM25 continua sendo o padrão; a interface é a mesma e a troca não afeta a API.
- **Banco**: SQLite em `backend/data/direitoaberto.db` por padrão; para PostgreSQL, `DIREITO_ABERTO_DATABASE_URL=postgresql+psycopg://usuario:senha@host/db`.

### Ingestão do Planalto (semiautomatizada)

```bash
python scripts/ingerir_planalto.py \
  --url https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm \
  --lei "Código de Defesa do Consumidor — Lei nº 8.078/1990" \
  --tema consumidor --artigos 18 26 49 > novos_artigos.json
```

O script extrai os artigos e gera esqueletos no formato do corpus com `"revisado": false` e resumo marcado como TODO. **A revisão humana é parte do fluxo por desenho**: ninguém publica dispositivo sem escrever o resumo em linguagem simples e conferir a vigência — essa é a camada de revisão jurídica do projeto.

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
- O corpus é **curado e pequeno** (30 dispositivos legais): cobre consumidor, trabalho, trânsito, moradia, família, saúde, previdência, tributos e acesso à Justiça, e nada além disso.
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
- ⬜ Embeddings multilíngues de qualidade (modelo PT-BR; o MiniLM padrão é limitado)
- ⬜ Ingestão automatizada de jurisprudência (APIs dos tribunais) — hoje a curadoria é manual
- ⬜ Migrações de banco (Alembic) e deploy com PostgreSQL gerenciado
- ✅ Frontend em React/Next.js (`web/`: perguntar, login, histórico e base legal, com modo escuro)
- ⬜ Camada de revisão jurídica contínua com profissional (o fluxo `revisado: false` já existe)

### A visão de longo prazo

Integrar **STF, STJ, TST e Planalto num único mecanismo de busca cidadã**: o usuário descreve o caso em linguagem comum e recebe a lei vigente, a jurisprudência dominante e o caminho prático — com fonte oficial em cada afirmação. É o ponto em que o projeto deixa de ser um protótipo educacional e vira uma LegalTech de acesso à Justiça.

## Tags sugeridas para o repositório

`python` · `fastapi` · `artificial-intelligence` · `natural-language-processing` · `rag` · `legal-tech` · `brazilian-law` · `education`

## Licença

Distribuído sob a licença [MIT](LICENSE) — © 2026 Roberto Chiocca.

---

**DireitoAberto** — *a lei em código aberto.* Este projeto oferece informação jurídica geral e não substitui a orientação de um advogado ou da Defensoria Pública.
