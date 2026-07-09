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
| Recuperação | BM25 implementado em Python puro (normalização PT-BR, stopwords, expansão de sinônimos) |
| Geração | API de LLM (pacote `anthropic`), opcional |
| Frontend | HTML/CSS/JS estático (sem build), integrado à API quando servido pelo backend |
| Testes | pytest + TestClient (httpx) |

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

### Endpoints

| Endpoint | Descrição |
|---|---|
| `POST /api/perguntar` | Pergunta em linguagem natural (aceita filtro opcional `tema`) → resposta + artigos + fontes |
| `GET /api/artigos` | Lista o corpus; filtros `?tema=familia` e `?busca=8.078` (por lei ou artigo) |
| `GET /api/estatisticas` | Leis e artigos indexados, áreas temáticas, consultas realizadas e data de atualização da base |
| `GET /api/saude` | Health check |

## Como rodar

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# abra http://localhost:8000  (frontend integrado)
# docs da API: http://localhost:8000/docs
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
- ⬜ Embeddings (busca semântica atrás da mesma interface `Retriever`)
- ⬜ ChromaDB (ou FAISS) como índice vetorial
- ⬜ PostgreSQL (corpus, histórico e telemetria persistentes)
- ⬜ Ingestão automatizada do Planalto/LexML
- ⬜ Jurisprudência STF
- ⬜ Jurisprudência STJ
- ⬜ Jurisprudência TST
- ⬜ Login
- ⬜ Histórico por usuário
- ⬜ API pública documentada e versionada
- ⬜ Upload de documentos (nota fiscal, contrato) com extração de contexto
- ⬜ Frontend em React/Next.js
- ⬜ Camada de revisão jurídica contínua (validação por profissional)

### A visão de longo prazo

Integrar **STF, STJ, TST e Planalto num único mecanismo de busca cidadã**: o usuário descreve o caso em linguagem comum e recebe a lei vigente, a jurisprudência dominante e o caminho prático — com fonte oficial em cada afirmação. É o ponto em que o projeto deixa de ser um protótipo educacional e vira uma LegalTech de acesso à Justiça.

## Tags sugeridas para o repositório

`python` · `fastapi` · `artificial-intelligence` · `natural-language-processing` · `rag` · `legal-tech` · `brazilian-law` · `education`

---

**DireitoAberto** — *a lei em código aberto.* Este projeto oferece informação jurídica geral e não substitui a orientação de um advogado ou da Defensoria Pública.
