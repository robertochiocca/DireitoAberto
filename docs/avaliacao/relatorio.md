# Avaliação do DireitoAberto

> Gerado por `scripts/avaliar.py` em 2026-10-23T17:08:52+00:00 (commit `fe633c9`, corpus `aeea075bb14e68e1`). Os números abaixo são os do arquivo `resultados.json` ao lado.

## Busca (BM25, o motor padrão)

| Medida | Calibração | Validação | Geral |
|---|---|---|---|
| Perguntas | 11 | 75 | 86 |
| Recall@1 | 81.8% | 89.3% | 88.4% |
| Recall@3 | 100.0% | 100.0% | 100.0% |
| Recall@10 | 100.0% | 100.0% | 100.0% |
| MRR@10 | 89.4% | 94.0% | 93.4% |
| nDCG@4 (julgamento manual) | 85.7% | 89.0% | 88.6% |
| Precisão@4 — só relevante | 31.8% | 32.6% | 32.5% |
| Precisão@4 — relevante ou tangencial | 63.6% | 55.6% | 56.6% |
| Precisão da resposta da API — só relevante | 61.4% | 57.0% | 57.6% |
| Precisão da resposta da API — relevante ou tangencial | 84.1% | 77.0% | 77.9% |
| Artigos por resposta da API | 2.64 | 2.59 | 2.59 |

Por tema do dispositivo esperado:

| Tema | Perguntas | Recall@1 | Recall@3 | MRR@10 |
|---|---|---|---|---|
| acesso-justica | 9 | 66.7% | 100.0% | 83.3% |
| ambiental | 2 | 100.0% | 100.0% | 100.0% |
| civel | 8 | 87.5% | 100.0% | 91.7% |
| civil-registro | 8 | 100.0% | 100.0% | 100.0% |
| consumidor | 8 | 87.5% | 100.0% | 91.7% |
| crianca-adolescente | 5 | 100.0% | 100.0% | 100.0% |
| dados | 1 | 100.0% | 100.0% | 100.0% |
| familia | 11 | 100.0% | 100.0% | 100.0% |
| moradia | 5 | 60.0% | 100.0% | 76.7% |
| previdencia | 3 | 66.7% | 100.0% | 83.3% |
| saude | 2 | 100.0% | 100.0% | 100.0% |
| servico-publico | 3 | 66.7% | 100.0% | 83.3% |
| trabalho | 9 | 88.9% | 100.0% | 92.6% |
| transito | 11 | 100.0% | 100.0% | 100.0% |
| tributos | 1 | 100.0% | 100.0% | 100.0% |

## Abstenção (limiar de evidência 6.0)

| | Calibração | Validação |
|---|---|---|
| Fora do escopo: abstenção correta | 8/13 | 8/13 |
| Dentro do escopo: abstenção indevida | 0/11 | 3/75 |

Fora do escopo e ainda respondidas: "Como abrir uma empresa de responsabilidade limitada?"; "Estrangeiro pode comprar terra no Brasil?"; "Posso ter uma arma de fogo em casa?"; "Qual é a idade mínima para tirar carteira de motorista?"; "Qual é a multa por não votar na eleição?"; "Qual é a pena para homicídio culposo?"; "Qual é a velocidade máxima permitida numa rodovia?"; "Quanto tempo de prisão pega quem dirige sem habilitação?"; "Quem tem direito ao seguro-desemprego?"; "É crime xingar alguém nas redes sociais?".

Legítimas sem resposta (abstenção indevida): "Minhas dívidas passaram do que ganho, dá para renegociar tudo?"; "Pedi informação na prefeitura e não responderam"; "Posso alegar que não sabia da lei?".

## Vigência (benchmark de armadilha temporal, top-3)

| Medida | Resultado |
|---|---|
| Dispositivo vigente no corpus | 24/24 (100.0%) |
| Vigente recuperado (quando existe) | 24/24 (100.0%) |
| Texto de 2006 recuperado | 24/24 (100.0%) |
| Texto de 2006 acima do vigente | 10/24 (41.7%) |
| Resposta cita o texto de 2006 | 24/24 (100.0%) |
| …com aviso de revogação, após rotular | 24/24 (100.0%) |

## Leitor de processos (processo fictício × gabarito)

| Categoria | Esperados | Encontrados | Extraídos |
|---|---|---|---|
| pedidos | 5 | 5 | 5 |
| alegacoes | 7 | 7 | 10 |
| decisoes | 6 | 6 | 6 |
| obrigacoes_e_determinacoes | 6 | 6 | 9 |
| prazos | 5 | 5 | 6 |
| linha_do_tempo | 10 | 10 | 13 |

Citações conferidas na página: 100/100. Afirmações proibidas pelo gabarito: 0. Perguntas com o comportamento esperado: 13/13.

### Leitor no conjunto adversarial (documentos fictícios × gabarito)

182/182 verificações; 31/31 documentos sem falha; citações conferidas de novo na página: 1470/1470. Os documentos e os gabaritos foram escritos pelo projeto para reproduzir falhas conhecidas: a medida mostra que essas falhas foram corrigidas, **não** valida o leitor em processos reais.

- `acordao-antes-da-sentenca`: 5/5
- `acordao-estilo-tjsp`: 4/4
- `acordao-reforma-sentenca`: 10/10
- `agravo-de-instrumento-e-sentenca`: 5/5
- `apelacao-numero-na-linha-seguinte`: 6/6
- `assinaturas-variadas`: 7/7
- `cabecalho-do-juizo-na-sentenca`: 6/6
- `certidao-de-outro-processo`: 6/6
- `contradicoes`: 8/8
- `cumprimento-apos-transito`: 8/8
- `documento-longo`: 8/8
- `embargos-acolhidos-efeitos-infringentes`: 6/6
- `embargos-acolhidos-sem-resultado-claro`: 5/5
- `embargos-de-declaracao`: 4/4
- `extracao-ilegivel`: 6/6
- `injecao-estrutural`: 7/7
- `injecao-quebra-de-pagina`: 9/9
- `numero-so-no-cabecalho`: 5/5
- `pagina-digitalizada-com-carimbo`: 9/9
- `prazos`: 8/8
- `procedencia-em-parte`: 3/3
- `procedencia-mista`: 3/3
- `relatorio-breve-relato`: 4/4
- `resultados-mistos-em-frases`: 3/3
- `sentenca-em-audiencia`: 4/4
- `sentencas-sem-data-confiavel`: 5/5
- `subtitulos-em-peticao`: 7/7
- `titulos-repetidos`: 4/4
- `titulos-sem-padrao`: 7/7
- `transito-acentuado-e-negado`: 6/6
- `transito-nao-havendo-recurso`: 4/4

## Fidelidade do corpus ao texto oficial vigente

71 de 79 dispositivos conferidos (fontes monitoradas): condensado 33, divergente 25, literal 11, quase_literal 2.

## Proveniência do corpus

68 de 79 entradas com texto oficial transcrito e conferido (141 trechos, de 34 fontes monitoradas). Natureza do texto curado: consolidado 11, interpretacao_juridica 12, nao_conferido 4, resumo_explicativo 52. Com lacuna declarada: 27. Com alerta de vigência: 11. Em revisão humana: 28. Problemas de integridade (selos, trechos): 0.

## Recuperação temporal (benchmark v2)

Versões do mesmo dispositivo indexadas juntas (a redação de 2006 ligada à vigente). "Antes" é a ordem da busca; "depois", a da API com a análise temporal.

| Pergunta | Com as duas versões | Versão certa primeiro, antes | Versão certa primeiro, depois |
|---|---|---|---|
| Regra atual | 23 | 60.9% | 100.0% |
| Em 10/04/2006 | 23 | 52.2% | 95.7% (com incerteza declarada: 100.0%) |

Perguntas sobre o corpus real (20, escritas pelo projeto junto com as regras — medida otimista): intenção 100.0%, data de referência 100.0%, pedido de esclarecimento 100.0%, dispositivo aceito no topo 90.0% → 90.0%, situação de vigência 100.0%, aplicabilidade na data 100.0%.

## Política de resposta

| | Abstenção | Resposta com ressalva (ligação fraca) | Resposta |
|---|---|---|---|
| Fora do escopo (26) | 16 | 7 | 3 |
| Dentro do escopo (86) | 3 | 5 | 78 |

Fora do escopo com uma nota fiscal anexada: 3/3 abstenções. A regra da ligação fraca (só uma palavra da pergunta casa com o dispositivo) foi motivada por estas mesmas perguntas: os números são otimistas até haver um conjunto novo.

## Latência (informativa, depende da máquina)

Busca: mediana 0.122 ms, p95 0.201 ms. Custo de LLM: zero no modo extrativo (padrão); com LLM, não medido (sem chave).

## Limites

- Gabaritos, julgamentos de relevância e o conjunto fora do escopo foram feitos pelo projeto, sem revisão de profissional do Direito.
- O leitor foi medido num processo fictício escrito pelo próprio projeto, não em processos reais.
- Não há medida da qualidade do texto gerado por LLM (sem chave de API neste ambiente).
- Compreensão pelo usuário não foi medida: exige teste com pessoas.
