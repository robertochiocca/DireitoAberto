# Avaliação do DireitoAberto

> Gerado por `scripts/avaliar.py` em 2026-10-19T22:16:05+00:00 (commit `ccbb302`, corpus `4940100685a4e361`). Os números abaixo são os do arquivo `resultados.json` ao lado.

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
| Precisão da resposta da API — só relevante | 52.3% | 45.7% | 46.5% |
| Precisão da resposta da API — relevante ou tangencial | 79.5% | 68.3% | 69.8% |
| Artigos por resposta da API | 2.91 | 2.88 | 2.88 |

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
| obrigacoes_e_determinacoes | 6 | 6 | 8 |
| prazos | 5 | 5 | 5 |
| linha_do_tempo | 10 | 10 | 13 |

Citações conferidas na página: 79/79. Afirmações proibidas pelo gabarito: 0. Perguntas com o comportamento esperado: 13/13.

## Fidelidade do corpus ao texto oficial vigente

46 de 79 dispositivos conferidos (fontes monitoradas): condensado 21, divergente 15, literal 8, quase_literal 2.

## Latência (informativa, depende da máquina)

Busca: mediana 0.114 ms, p95 0.207 ms. Custo de LLM: zero no modo extrativo (padrão); com LLM, não medido (sem chave).

## Limites

- Gabaritos, julgamentos de relevância e o conjunto fora do escopo foram feitos pelo projeto, sem revisão de profissional do Direito.
- O leitor foi medido num processo fictício escrito pelo próprio projeto, não em processos reais.
- Não há medida da qualidade do texto gerado por LLM (sem chave de API neste ambiente).
- Compreensão pelo usuário não foi medida: exige teste com pessoas.
