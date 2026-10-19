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

| Ajuda gratuita: os quatro degraus e os canais | Menu no celular |
|---|---|
| ![Página /ajuda com o caminho de resolução em quatro degraus](docs/screenshots/7-ajuda.png) | <img src="docs/screenshots/8-menu-celular.png" alt="Menu compacto aberto no celular" width="260"> |

## O problema

A legislação brasileira é escrita para operadores do Direito, não para o cidadão. Quem tem um produto com defeito, foi demitido, recebeu uma multa injusta ou teve o nome negativado raramente sabe **qual lei protege o seu caso, quais são os prazos e onde buscar ajuda gratuita** — e o juridiquês afasta exatamente quem mais precisa da informação.

## A solução

O DireitoAberto ataca o problema em duas camadas:

1. **Conteúdo curado** (frontend): 16 situações do dia a dia — consumidor, trabalho, trânsito, moradia, família, saúde, previdência e tributos — explicadas em passo a passo, com prazos, modelos de texto prontos, **fonte oficial destacada** (lei, artigo e link para o Planalto), glossário de juridiquês e canais gratuitos de ajuda (Defensoria Pública, Procon, consumidor.gov.br, ANS, INSS, Banco Central, Juizados Especiais). A home mostra o **caminho de resolução em quatro degraus** — entender o direito, tentar resolver direto, reclamar no canal oficial, levar à Justiça sem pagar — e a navegação destaca a ajuda gratuita em todas as páginas. Interface com modo escuro, animações suaves, filtros por área e histórico de pesquisas.
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
| Frontend (produto) | React/Next.js 15 + TypeScript (`web/`): perguntar, base legal, histórico, ajuda gratuita e login |
| Frontend (MVP) | HTML/CSS/JS estático (`frontend/`), servido pelo próprio backend |
| Testes | pytest + TestClient (httpx) — 146 testes |

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

- `backend/data/legislacao.json` — corpus com 79 dispositivos legais (CF/88, Código Civil, LINDB, CDC e Decreto 7.962/2013, CLT, CTB, CPC, Lei do Inquilinato, Lei do Bem de Família, Lei dos Juizados Especiais, Federais e da Fazenda Pública, LC 80/1994 da Defensoria, Lei de Registros Públicos, ECA e ECA Digital, Maria da Penha, Estatuto da Pessoa Idosa e da Pessoa com Deficiência, LOAS/BPC, Lei do FGTS, Lei dos Planos de Saúde, Lei de Benefícios do INSS, CTN, Lei do Processo Administrativo, LAI, Lei 13.460/2017, LGPD, Código Florestal, Resolução ANAC 400 e 7 súmulas de STF/STJ/TST), cada um com texto, resumo em linguagem simples, tema, palavras-chave, fonte oficial e **bloco de vigência**.
- `backend/app/retrieval.py` — índice BM25 com filtro por área temática. Os sinônimos que traduzem o vocabulário do cidadão entram na consulta com **peso 0,6**, abaixo das palavras que ele de fato escreveu: com peso cheio, um sinônimo solto trazia lei de outro assunto ("o plano negou minha cirurgia" expandia "negou" para "negativa" e puxava a Lei de Acesso à Informação). Na API, a busca é **adaptativa**: devolve de 2 a 4 artigos, cortando os que têm menos de um terço da nota do 1º colocado (ver *Comparação de motores de busca*). A interface `Retriever.buscar()` permite trocar o motor por busca semântica (embeddings) sem alterar a API.
- `backend/app/llm.py` — camada de geração com prompt que exige linguagem cautelosa, proíbe inventar dispositivos e sempre encaminha para a Defensoria/Procon.
- `backend/app/main.py` — API FastAPI e serving do frontend.

### Navegação e caminho de resolução

Os dois frontends seguem o mesmo desenho, pensado para que a saída do problema nunca passe despercebida:

- **"Ajuda gratuita" é o único item da navegação com peso próprio**, em pílula na cor de "seu direito" e presente em todas as páginas. A seção atual é marcada por um traço sob o rótulo, não só pela cor.
- **No celular e no tablet, a navegação vira um botão Menu.** O painel lista as seções em ordem de importância — primeiro "Tenho um problema" e "Ajuda gratuita", depois o material de consulta (e a conta, no Next.js). Ele fecha com Esc (o foco volta ao botão), com toque fora, ao navegar e ao alargar a janela, e trava a rolagem da página enquanto está aberto.
- **A faixa "Do problema à solução, em quatro degraus"** ordena a resolução do mais simples ao mais formal: entender o direito → tentar resolver direto, por escrito → reclamar no canal oficial → levar à Justiça sem pagar. Cada degrau aponta para a parte do site que ajuda nele, e um aviso lembra que violência ou risco à vida não espera degrau (190 e 180).

| | Frontend estático (`frontend/`) | Next.js (`web/`) |
|---|---|---|
| Navegação numa linha | a partir de 1040px: marca, busca e seções | a partir de 960px: marca, seções e conta |
| Menu compacto | abaixo de 1040px | abaixo de 960px |
| Busca | no cabeçalho, presente em todas as views | campo da home |
| Faixa dos quatro degraus | home | home (depois da resposta) e `/ajuda` |
| Canais gratuitos | view "Ajuda gratuita" | página `/ajuda` |

No frontend estático a busca mora no cabeçalho, fora das views: trocar de view não a esconde nem tira o foco do campo. A filtragem por tecla tem *debounce* de 200 ms, e Enter pergunta à base jurídica.

No Next.js, a navegação está em `web/components/Nav.tsx`, a faixa em `web/components/Degraus.tsx` (usada pela home e pela `/ajuda`, com os links adaptados a cada página) e os canais e degraus em `web/lib/ajuda.ts`. Esse arquivo espelha o `HELP` de `frontend/dados.js` e a faixa da home do estático — **ao revisar o texto de um, revise o outro**.

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
- **Retriever semântico**: `pip install chromadb` e `DIREITO_ABERTO_RETRIEVER=semantico`. Usa o **multilingual-e5-small** (ONNX, ~130 MB baixados do Hugging Face na 1ª execução, sem PyTorch), com prefixos assimétricos `query:`/`passage:` e vetores L2-normalizados. Cada texto é vetorizado numa chamada própria: o modelo quantizado calcula a escala das ativações sobre a chamada inteira, e em lote o vetor de um documento dependia dos vizinhos — editar um verbete mudava a posição de outros na busca. No benchmark interno de 21 casos: **e5 19/21 no top-1** vs BM25 18/21 vs MiniLM padrão do Chroma 13/21 — e o e5 acerta parafrases sem nenhuma palavra do corpus ("a companhia aérea me deixou na mão" → Resolução ANAC 400). `DIREITO_ABERTO_EMBEDDING=padrao` força o embedding nativo do Chroma; sem dependências ou sem rede, o fallback é o BM25.
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
  "status": "em_vacatio",            // vigente · em_vacatio · revogada · inconstitucional
  "entra_em_vigor_em": "2026-12-15",
  "alterada_por": ["EC 141/2026"],
  "nota": "Promulgada em 16/10/2026. A regra de 42 horas vale 60 dias após a publicação…",
  "conferida_em": "2026-10-16"
}
```

A informação atravessa o sistema inteiro: entra no contexto do LLM (com regra explícita no prompt de nunca apresentar norma futura como vigente), aparece no modo extrativo, vira badge na resposta e na base legal, e alimenta o endpoint `/api/v1/vigencia`. Hoje a base tem duas normas publicadas e ainda sem efeito — a **EC 141/2026** (fim da escala 6x1: 42h em 15/12/2026, 40h em 14 meses) e o **Decreto 13.135/2026** (novo SAC, a partir de 02/11/2026) —, um dispositivo **revogado** mantido como marcador histórico (CTB art. 262, apreensão do veículo por 30 dias, extinta em 2016) e um **declarado inconstitucional** (CC art. 1.790, sucessão do companheiro, STF Tema 809).

Os quatro status não são redundantes entre si, e é por isso que `revogada` não dá conta do caso: um artigo inconstitucional continua impresso no Código, nunca foi revogado pelo Legislativo e ainda assim não deve ser aplicado. Quem lê o código em papel não tem como saber.

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

**Resultado (top-3, corpus de 79 dispositivos):**

| Métrica | BM25 | Semântico (e5) |
|---|---|---|
| dispositivo vigente no corpus | 24/24 (100%) | 24/24 (100%) |
| recuperado quando existe | 24/24 (100%) | 23/24 (95,8%) |
| texto de 2006 recuperado | **24/24 (100%)** | **20/24 (83,3%)** |
| texto de 2006 **acima** do vigente | **10/24 (41,7%)** | **6/24 (25,0%)** |
| resposta final cita o texto de 2006 | **24/24 (100%)** | **20/24 (83,3%)** |
| …com aviso de revogação, após rotular | **24/24 (100%)** | **20/20 (100%)** |

**Leitura.** Recuperação não resolve validade temporal. Com o corpus fechando os 24 casos, a redação vigente está lá e é recuperada — e **o texto de 2006 continua sendo recuperado junto em 83% a 100% das perguntas, e ainda vence a redação vigente em 25% a 42% delas**. A fonte velha é *melhor escrita* para a pergunta do cidadão, porque foi feita exatamente para ele: ela compete em pé de igualdade mesmo quando a resposta correta está indexada ao lado. Trocar BM25 por embeddings multilíngues reduz o dano (100% → 83% de contaminação; 42% → 25% de inversão) mas não muda o quadro: **nenhum avanço no motor de busca resolve o problema, porque ele não é de semântica — é de metadado**. O que resolve é o rótulo: com `status: revogada`, o distrator continua sendo recuperado, mas toda resposta passa a trazer o aviso (100% nos dois motores). Daí a decisão de arquitetura do projeto — **a vigência é um campo do corpus, não um detalhe do conteúdo**.

Ao dar peso menor aos sinônimos, a contaminação do BM25 subiu de 23/24 para 24/24: no caso "indicar o condutor", a vaga que um artigo ocupava só por sinônimo passou ao texto de 2006, que carrega as palavras-chave da própria pergunta. É o desenho de pior caso funcionando — o distrator é feito para casar com o que o cidadão escreve, e qualquer ajuste que favoreça as palavras literais o favorece também.

A cobertura saiu de 16,7% (corpus de 38) para 100% (corpus de 79) com a entrada das leis que o dossiê de fontes apontava como faltantes — ECA, Lei 6.015, CTB em detalhe, LINDB, Código Florestal e o regime sucessório do companheiro. O ganho foi medido, não presumido: o benchmark é a régua. E o resultado mais interessante é o que **não** melhorou — a inversão caiu de 75% para 42% no BM25 porque passou a ser medida sobre 24 casos em vez de 4, e a contaminação quase não se moveu. Fechar a lacuna do corpus era necessário e não foi suficiente.

*Nota metodológica:* os distratores recebem as mesmas palavras-chave curadas que o corpus dá aos seus dispositivos. Sem isso seriam penalizados de graça pelo peso que o BM25 atribui às palavras-chave, e o resultado seria otimista demais; o benchmark adota o pior caso. Os textos em `obsoleto` são paráfrases da redação antiga conforme o dossiê, não transcrições literais.

### Comparação de motores de busca: BM25 × semântico × híbrido

Toda resposta traz 4 artigos, mas a maioria das perguntas tem uns 2 realmente relevantes — as últimas vagas ficam com o que estiver mais perto, e às vezes isso é lei de outro assunto. A pergunta deste experimento: **trocar o motor de busca reduz esse ruído?**

```bash
python3 scripts/comparar_retrievers.py           # resumo (requer chromadb; baixa o modelo na 1ª vez)
python3 scripts/comparar_retrievers.py --casos   # + cada pergunta julgada, motor a motor
```

**Método.** Duas medidas, porque são duas perguntas:

- **o artigo certo aparece?** — nas 86 perguntas com gabarito (`data/casos_busca.json` mais as do benchmark temporal);
- **o que mais aparece junto?** — o ruído, que o gabarito não mede, porque só conhece um artigo certo por pergunta. Nas 86 perguntas, cada artigo que algum motor pôs no top-4 foi **julgado à mão** como relevante, tangencial ou ruído — 586 rótulos em `data/relevancia_julgada.json`. Como aproximação, conta-se também quantos resultados extras são de área diferente da do artigo esperado.

Os julgamentos seguem três regras: são feitos **sem saber qual motor trouxe cada artigo**; "tangencial" exige que o artigo faça parte do mesmo conflito que o cidadão plausivelmente vive (tirar o sobrenome do ex, num divórcio) — ser apenas da mesma área do direito conta como ruído; e paráfrases da mesma pergunta dão o mesmo rótulo ao mesmo artigo (um teste confere). As perguntas se dividem em **calibração** — as 11 usadas para escolher o corte da busca adaptativa (as do README, os atalhos da home e "onde consigo advogado gratuito?") — e **validação**, as outras 75, que medem a busca fora dessa amostra. Os rótulos foram atribuídos pelo projeto e ainda não passaram por revisão de um profissional do Direito.

O híbrido funde as duas listas por posição (*Reciprocal Rank Fusion*), sem depender da escala de nota de cada motor.

**Resultado (top-4):**

| | BM25 | BM25 adaptativo (o que a API devolve) | Semântico (e5) | Híbrido (RRF) |
|---|---|---|---|---|
| artigos por resposta (média) | 3,92 | **2,88** | 4,00 | 4,00 |
| artigo certo no top-3 | **86/86** | **86/86** | 84/86 | 85/86 |
| artigo certo em 1º lugar | 76/86 | 76/86 | 76/86 | **78/86** |
| extras de outra área (aproximação) | 53% | 45% | 45% | 46% |
| **ruído julgado — validação** (75 perguntas) | **131/293 (45%)** | **70/216 (32%)** | **140/300 (47%)** | **130/300 (43%)** |
| relevantes · tangenciais — validação | 93 · 69 | 91 · 55 | 92 · 68 | 93 · 77 |
| ruído julgado — calibração (11 perguntas) | 16/44 (36%) | 8/32 (25%) | 17/44 (39%) | 15/44 (34%) |
| tempo por busca | 0,2 ms | igual ao BM25 | 6,1 ms | — |

**Leitura.** Entre os motores com 4 vagas fixas, fora da amostra, BM25 e híbrido ficam em 45% e 43% de ruído e o semântico fica atrás, com 47%. Trocar de motor não reduz o ruído; muda **o tipo de erro**. O BM25 confunde palavras escritas iguais ("trocar o nome" puxa troca de produto; "caí" casa com a jornada que "cai") — ruído óbvio. O semântico traz o que *parece* do assunto e não é: a LGPD entre os artigos do CDC em "notebook defeituoso", a súmula de negativação em perguntas de voo, INSS e plano de saúde — ruído que engana mais. O semântico ganha onde a pergunta não usa as palavras da lei ("posso ser preso por dívida?" sai limpa, com a súmula certa em 1º), mas **perde a Defensoria Pública em "onde consigo advogado gratuito?"** — e o híbrido também. Para uma plataforma cujo propósito é encaminhar o cidadão à ajuda gratuita, é a falha que mais pesa.

**Decisão: o BM25 continua o padrão.** O ruído não é do motor, é estrutural: preencher sempre 4 vagas quando há uns 2 artigos relevantes. Trocar de motor troca o tipo de ruído e custa cobertura e implantação (modelo de ~135 MB, ChromaDB). A alavanca é o número de vagas.

**Número de artigos por resposta.** A API usa a busca adaptativa: os 2 primeiros artigos sempre entram e, depois deles, só quem tem **ao menos um terço da nota do 1º colocado** — de 2 a 4 artigos por resposta, 2,88 em média. Fora da amostra, nas 75 perguntas de validação, o ruído cai de 131 para 70 — de 45% para 32% das vagas —, o artigo certo continua em todas as 86 perguntas, e o custo são 14 tangenciais e 2 relevantes a menos (um só caso, contado duas vezes por ter duas paráfrases; ver limite 2 abaixo). Nas 11 perguntas de calibração a queda é parecida (de 36% para 25%, sem perder relevante), sinal de que o corte não ficou preso à amostra em que foi escolhido; ele **não** foi reajustado na validação, para que ela continue medindo fora da amostra. A calibração saiu da grade: com mínimo de 1 artigo já se perdiam relevantes (às vezes o 2º colocado é relevante e fraco — a súmula 297 no golpe do PIX tem 16% da nota do 1º); com mínimo de 2, qualquer corte entre 30% e 35% dá o mesmo resultado, e um terço fica nessa faixa. No semântico a regra não teria efeito — o 4º colocado tem de 91% a 99% da nota do 1º —, e o parâmetro é aceito, mas ignorado.

O que a regra não resolve: (1) ruído que pontua perto do artigo certo — em "posso ser preso por dívida?" os quatro têm notas parecidas e ficam todos; (2) o mínimo de 2 protege o 2º colocado mesmo quando ele é ruído — em "quais são os direitos sociais na Constituição?", a união estável (ruído, 30% da nota) fica em 2º e o art. 7º da CF (relevante, 25%) sai; (3) secundário útil fraco sai junto com o ruído — o art. 42 do CDC (cobrança indevida) na pergunta sobre nome negativado tem 25% da nota do 1º. Também quase não muda a armadilha temporal: com a busca adaptativa, o texto de 2006 ainda chega à resposta em 23 dos 24 casos, porque o distrator carrega as palavras da própria pergunta e não é cauda fraca — quem protege o cidadão continua sendo o rótulo de vigência.

Benchmark e comparação medem com número fixo de resultados, para continuarem comparáveis entre si; a coluna adaptativa mostra o que o cidadão de fato recebe.

Se um motor passar a devolver um artigo ainda não julgado, o script o lista para ser rotulado; um teste trava os julgamentos em sincronia com o BM25.

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
# http://localhost:3000 -> perguntar, base legal, histórico, ajuda gratuita (/ajuda) e login
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
- O corpus é **curado e pequeno** (79 dispositivos legais): cobre consumidor, trabalho, trânsito, moradia, família, cível, registros públicos, criança e adolescente, saúde, previdência e assistência, tributos, proteção de dados, serviço público, ambiental e acesso à Justiça — e nada além disso.
- A vigência é **conferida manualmente**, não monitorada em tempo real: cada dispositivo carrega a data da última conferência (`vigencia.conferida_em`) e o `GET /api/v1/vigencia` mostra o que está prestes a mudar. Uma norma alterada entre duas conferências continuaria sendo respondida com a redação antiga — por isso a data aparece junto da resposta.
- A busca é **lexical por padrão** (BM25 + sinônimos PT-BR); o índice semântico existe, mas é opt-in (`DIREITO_ABERTO_RETRIEVER=semantico`). Perguntas muito distantes do vocabulário indexado podem não encontrar nada — e o sistema diz isso em vez de inventar. No outro extremo, a busca ainda pode trazer artigo de outro assunto que casa uma palavra ambígua ("plano" de saúde × plano de pagamento). A busca adaptativa corta esse ruído quando ele é fraco, mas não quando pontua perto do artigo certo, e trocar o BM25 pela busca semântica também não resolve (ver *Comparação de motores de busca*).
- Os textos legais foram consolidados manualmente a partir do Planalto e podem não refletir alterações legislativas posteriores; cada artigo traz o link para a fonte oficial. Textos marcados como "(síntese)" condensam caput e parágrafos relevantes em vez de transcrevê-los na íntegra.
- A jurisprudência é uma **curadoria inicial de 7 súmulas** de STF, STJ e TST — não um índice de precedentes.

## Roadmap

- ✅ MVP estático com conteúdo curado
- ✅ RAG (BM25 + sinônimos PT-BR) com camada de LLM e fallback extrativo
- ✅ Revisão jurídica do conteúdo (JEC 40/20 salários mínimos, frete no arrependimento)
- ✅ 16 situações em 8 áreas (família, saúde, previdência, tributos…)
- ✅ Fonte oficial (lei + artigo + link do Planalto) em cada situação e resposta
- ✅ Filtros por área, busca por lei/artigo e histórico de pesquisas
- ✅ Estatísticas da base (`/api/estatisticas` + página "Números" no frontend)
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
- ✅ Frontend em React/Next.js (`web/`: perguntar, base legal, histórico, ajuda gratuita e login, com modo escuro)
- ✅ Navegação responsiva nos dois frontends (menu compacto no celular, "Ajuda gratuita" em destaque) e caminho de resolução em quatro degraus, com página `/ajuda` no Next.js
- ✅ Benchmark de armadilha temporal (24 casos, três índices; mede cobertura, contaminação por fonte desatualizada e eficácia do rótulo de vigência)
- ✅ Comparação BM25 × semântico × híbrido, com julgamento manual de relevância (`scripts/comparar_retrievers.py`)
- ✅ Expansão do corpus para 100% de cobertura do benchmark (38 → 79 dispositivos; fechou as lacunas que o próprio benchmark mediu)
- ⬜ Valores dinâmicos (tetos dos Juizados calculados a partir do salário mínimo vigente, em vez de fixos no conteúdo)
- ✅ Número de artigos por resposta ajustado à pergunta (2 a 4; corte em um terço da nota do 1º colocado, calibrado com os julgamentos manuais)
- ✅ Julgamentos manuais de relevância nas 86 perguntas do gabarito (586 rótulos, julgados sem saber o motor; 11 de calibração e 75 de validação)
- ⬜ Revisão dos julgamentos de relevância por profissional do Direito
- ⬜ Camada de revisão jurídica contínua com profissional (o fluxo `revisado: false` já existe)

### A visão de longo prazo

Integrar **STF, STJ, TST e Planalto num único mecanismo de busca cidadã**: o usuário descreve o caso em linguagem comum e recebe a lei vigente, a jurisprudência dominante e o caminho prático — com fonte oficial em cada afirmação. É o ponto em que o projeto deixa de ser um protótipo educacional e vira uma LegalTech de acesso à Justiça.

## Tags sugeridas para o repositório

`python` · `fastapi` · `artificial-intelligence` · `natural-language-processing` · `rag` · `legal-tech` · `brazilian-law` · `education`

## Licença

Distribuído sob a licença [MIT](LICENSE) — © 2026 Roberto Chiocca.

---

**DireitoAberto** — *a lei em código aberto.* Este projeto oferece informação jurídica geral e não substitui a orientação de um advogado ou da Defensoria Pública.
