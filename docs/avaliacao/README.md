# Avaliação jurídica do DireitoAberto

> O relatório numérico completo é gerado pelo código: [relatorio.md](relatorio.md) e
> [resultados.json](resultados.json) (`cd backend && python scripts/avaliar.py --gravar`). Este texto
> explica **o que cada conjunto mede, o que não mede** e o que mudou na rodada 9.0. Os conjuntos foram
> escritos pelo próprio projeto: as medidas mostram onde o sistema acerta e erra **nesses casos**, não
> que ele está correto juridicamente em geral.

## Como rodar e o portão de regressão

```bash
cd backend
python scripts/avaliar.py              # mede e imprime
python scripts/avaliar.py --comparar   # sai com 1 se alguma métrica piorou em relação a resultados.json (roda no CI)
python scripts/avaliar.py --gravar     # regrava a linha de base (explique no commit o que piorou de propósito)
python scripts/avaliar.py --varrer     # refaz a validação cruzada do corte da busca
python -m app.leitor.avaliacao         # só o conjunto adversarial do leitor
```

O portão (`app/avaliacao.py`, listas `MAIOR_MELHOR` e `MENOR_MELHOR`) cobre busca, abstenção, leitor,
conjunto adversarial do leitor, benchmark temporal v2, política de resposta e integridade da
proveniência. Nenhuma métrica isolada decide: a escolha do corte da busca, por exemplo, tinha critério
fixado antes (artigo do gabarito em 100% das respostas e ≥ 95% dos relevantes julgados) e só depois se
olhou a precisão.

## Conjuntos versionados

| Conjunto | Arquivo | O que mede | Tamanho |
|---|---|---|---|
| Busca | `data/avaliacao/` e casos de `app/benchmark.py`/`app/comparacao.py` | o dispositivo certo aparece? quantos irrelevantes vêm junto? (relevância julgada pelo projeto) | 86 perguntas (11 calibração, 75 validação) |
| Abstenção | idem | a base reconhece o que não tem? | 26 fora do escopo, 86 dentro |
| Temporal v1 | `data/benchmark_temporal.json` | armadilhas de redação antiga × vigente | 24 casos |
| **Temporal v2** | `data/avaliacao/temporal_v2.json` (versão 2) | a versão certa para a data da pergunta; intenção (atual, histórica, mudança, revogação, fundamento); data de referência; pedido de esclarecimento | 48 perguntas de versão (24 × atual/histórica) + 20 escritas à mão sobre o corpus real |
| **Política de resposta** | `app/avaliacao.py` (`avaliar_politica`) | o modo escolhido (responder, ressalva, esclarecer, não verificado, profissional) | 26 fora, 86 dentro, 3 fora com documento anexado |
| Leitor (exemplar) | `data/exemplos/processo-ficticio.*` | itens por natureza, citações conferidas, afirmações proibidas, perguntas | 1 processo fictício |
| **Leitor (adversarial)** | `data/exemplos/adversariais/` | falhas conhecidas do leitor (ver [leitor-de-processos.md](../leitor-de-processos.md)) | 31 documentos fictícios, 182 verificações |
| Fidelidade | `scripts/monitor.py fidelidade` | o `texto` do corpus × o texto oficial vigente | 71 dispositivos conferíveis |
| **Proveniência** | `scripts/corpus.py verificar` | selos, histórico e cada trecho oficial refeito a partir do snapshot | 79 entradas, 141 trechos |

## Antes e depois da rodada 9.0

"Antes" é a linha de base versionada de 19/10/2026 (commit `ccbb302`) ou, nos conjuntos novos, a mesma
régua aplicada ao código anterior.

| Medida | Antes | Depois | Observação |
|---|---|---|---|
| Precisão das respostas (só relevante) | 46,5% | 57,6% | validação cruzada agrupada: 61,4% fora da amostra |
| Precisão (relevante ou tangencial) | 69,8% | 77,9% | |
| Artigos por resposta | 2,88 | 2,59 | |
| Artigo do gabarito no top-3 | 100% | 100% | |
| Relevantes julgados mantidos | 98,1% | 96,3% | perda aceita pelo critério fixado antes |
| Temporal v2 — versão certa primeiro (pergunta atual) | 60,9% | 100% | 23 casos com as duas versões |
| Temporal v2 — versão certa primeiro (pergunta histórica, 10/04/2006) | 52,2% | 95,7% | 100% contando incerteza declarada |
| Temporal v2 — intenção e data de referência (20 perguntas) | — | 100% / 100% | |
| Fora do escopo protegidas (abstenção ou ressalva) | 16/26 (só abstenção; as outras 10 recebiam resposta sem ressalva) | 23/26 (16 abstenções + 7 ressalvas) | 3 ainda recebem resposta sem ressalva |
| Dentro do escopo com ressalva indevida | — | 5/86 | mais as 3 abstenções indevidas que já existiam |
| Fora do escopo com documento anexado | — | 3/3 abstenções | o documento não "puxa" a resposta para a base |
| Leitor adversarial (17 do ciclo + 14 da revisão independente) | 29/104 e 25/78 verificações; 0/31 documentos | 182/182, 31/31 | gabarito escrito pelo projeto; ver limites |
| Trechos oficiais no corpus | 0 | 141 (68 de 79 entradas) | todos refeitos e conferidos no CI |
| Problemas de integridade da proveniência | — | 0 | |
| Busca, mediana / p95 | 0,114 / 0,207 ms | 0,131 / 0,230 ms | |

A fidelidade passou de 46 para 71 dispositivos conferíveis porque 25 fontes passaram a ser
monitoradas; a contagem de "divergentes" subiu de 15 para 25 por isso, não por piora do texto. Os
divergentes são identificados pela natureza do texto e nunca citados como lei
([legal-data-sources.md](../legal-data-sources.md#o-que-a-proveniência-não-resolve)).

## Verificação depois da geração e política de resposta

- **Verificador** (`app/verificador.py`), determinístico: citação entre aspas tem de estar, como está,
  num trecho oficial; artigo, súmula e lei citados têm de estar entre os recuperados; número com unidade
  (prazo, percentual, valor) tem de aparecer no contexto; promessa de resultado ("com certeza", "você
  vai ganhar") é problema. Texto gerado que falha não é entregue: a API usa a resposta extrativa e diz
  por quê. A confiança que o modelo declara não entra em nenhuma regra.
- **Política** (`app/politica.py`): cinco modos decididos por regras sobre a busca, a validação e o
  verificador. Pergunta sobre o caso concreto ("devo processar?", "vou ganhar?", "quanto vou receber?")
  vai para `recomendar_profissional`: a resposta dá a regra geral e não prevê resultado nem calcula
  valor.

## Limites (o que estes números não dizem)

- **Conjuntos escritos pelo projeto.** Perguntas, julgamentos de relevância e gabaritos são do próprio
  projeto, sem revisão de profissional do Direito.
- **As regras de política foram ajustadas olhando os mesmos conjuntos em que são medidas:** os números
  da política são otimistas. Falta um conjunto separado, nunca visto, para a política e para o temporal
  v2.
- **Texto gerado por LLM não foi medido:** não há chave de API neste ambiente. O verificador foi testado
  com textos escritos para os testes.
- **Leitor:** o conjunto adversarial reproduz falhas que a auditoria e a revisão encontraram. 182/182 mostra que elas
  foram corrigidas, não que o leitor funciona em processos reais (nenhum processo real ou anonimizado foi
  usado; não há OCR).
- **Compreensão por pessoas não foi medida:** clareza, utilidade e risco de mal-entendido exigem teste
  com usuários.
- A data de referência dos testes é fixa (19/10/2026): os resultados de vigência valem para essa data.
