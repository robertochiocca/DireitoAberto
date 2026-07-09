# DireitoAberto ⚖️

**Plataforma de letramento jurídico baseada em legislação brasileira, que traduz os direitos do cidadão em linguagem simples — agora com busca aumentada por recuperação (RAG) sobre um corpus de leis.**

> *"A lei foi escrita pra você. Só faltava alguém traduzir."*

## O problema

A legislação brasileira é escrita para operadores do Direito, não para o cidadão. Quem tem um produto com defeito, foi demitido, recebeu uma multa injusta ou teve o nome negativado raramente sabe **qual lei protege o seu caso, quais são os prazos e onde buscar ajuda gratuita** — e o juridiquês afasta exatamente quem mais precisa da informação.

## A solução

O DireitoAberto ataca o problema em duas camadas:

1. **Conteúdo curado** (frontend): situações do dia a dia explicadas em passo a passo, com prazos, modelos de texto prontos, glossário de juridiquês e canais gratuitos de ajuda (Defensoria Pública, Procon, consumidor.gov.br, Juizados Especiais).
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

- `backend/data/legislacao.json` — corpus com artigos do CDC, CLT, CF/88, CTB, Lei do Inquilinato, Lei dos Juizados Especiais, Lei do FGTS e Código Civil, cada um com texto, resumo em linguagem simples, palavras-chave e link para a fonte oficial.
- `backend/app/retrieval.py` — índice BM25; a interface `Retriever.buscar()` permite trocar o motor por busca semântica (embeddings) sem alterar a API.
- `backend/app/llm.py` — camada de geração com prompt que exige linguagem cautelosa, proíbe inventar dispositivos e sempre encaminha para a Defensoria/Procon.
- `backend/app/main.py` — API FastAPI (`/api/perguntar`, `/api/artigos`, `/api/saude`) e serving do frontend.

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
- O corpus é **curado e pequeno** (~18 dispositivos legais): cobre bem consumidor, trabalho, trânsito, moradia e acesso à Justiça, e nada além disso.
- A busca é **lexical** (BM25 + sinônimos), não semântica — perguntas muito distantes do vocabulário indexado podem não encontrar nada (o sistema diz isso em vez de inventar).
- Os textos legais foram consolidados manualmente a partir do Planalto e podem não refletir alterações legislativas posteriores; cada artigo traz o link para a fonte oficial.
- Sem jurisprudência por enquanto (ver roadmap).

## Roadmap

- [x] MVP estático com conteúdo curado
- [x] Backend FastAPI + RAG lexical (BM25) + camada LLM com fallback extrativo
- [x] Revisão jurídica do conteúdo (JEC 40/20 salários mínimos, frete no direito de arrependimento)
- [ ] Busca semântica com embeddings (ChromaDB ou FAISS) atrás da mesma interface `Retriever`
- [ ] PostgreSQL para corpus e histórico de perguntas
- [ ] Ampliar o corpus (ingestão automatizada do Planalto/LexML) e incluir súmulas/jurisprudência com metadados de vigência
- [ ] Upload de documentos (nota fiscal, contrato) com extração de contexto
- [ ] Frontend em React/Next.js
- [ ] Camada de revisão jurídica contínua (validação por profissional antes de publicar conteúdo curado)

## Tags sugeridas para o repositório

`python` · `fastapi` · `artificial-intelligence` · `natural-language-processing` · `rag` · `legal-tech` · `brazilian-law` · `education`

---

**DireitoAberto** — *a lei em código aberto.* Este projeto oferece informação jurídica geral e não substitui a orientação de um advogado ou da Defensoria Pública.
