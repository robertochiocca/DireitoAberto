# Leitor de processos

> Estado: **concluído — backend (ciclo 2) e interface `/documentos` no Next.js (ciclo 3)**. Funciona
> sem modelo de linguagem e sem enviar nada a terceiros.

## Interface (`web/app/documentos`)

- Entrada com o exemplo fictício (sem conta) e o envio de PDF (com conta), com os compromissos de
  privacidade escritos na tela; lista dos documentos guardados, com validade e botão de apagar.
- Abas: Resumo (com próximos passos e perguntas para a Defensoria), Linha do tempo, Partes e peças,
  Decisões e prazos, Perguntar, Glossário. Cada item tem o selo da natureza e os botões de citação
  "p. 9 · fls. 30"; duas citações na mesma página mostram o começo do trecho para se distinguirem.
- Visualizador ao lado (fixo no desktop, abaixo no celular): o texto extraído da página com o trecho
  citado destacado, navegação entre páginas, aviso explícito em página não lida e, quando o PDF está
  disponível, o original (o arquivo enviado na sessão vira um endereço `blob:` local — nunca volta do
  servidor; o do exemplo vem de `/documentos/exemplo/arquivo`, a única rota que aceita iframe da
  própria origem).
- Verificado num navegador real (Playwright, Chromium): fluxo completo de conta → envio pelo proxy do
  Next → análise → PDF original → pergunta → exclusão, sem erro de console; 1360 px, 960 px e 390 px,
  claro e escuro, sem rolagem horizontal no celular. Esse roteiro ainda não está automatizado na CI.

## O que ele faz

Recebe um processo em PDF (ou TXT) e devolve, com a página de cada informação:

| Saída | Como é obtida |
|---|---|
| Número do processo, com conferência do dígito verificador | padrão CNJ (Res. 65/2008), módulo 97 |
| Classe, assunto, juízo | linhas "Classe: …", "Assunto: …" da capa |
| Partes e papéis | linhas "Autora: …", "Ré: …" e "em face de …" na petição inicial |
| Peças (petição, decisão, certidão, termo de audiência, contestação, sentença…) | títulos das peças |
| Linha do tempo | datas de peças (linha "Cidade, dd de mês de aaaa") e de fatos narrados, certificados ou designados |
| Alegações, pedidos, decisões, obrigações e determinações, prazos, recursos | frases de cada peça, classificadas pela natureza da peça |
| Trânsito em julgado | só se houver **certidão** dizendo isso |
| Folhas citadas e não enviadas | "fls. N" citadas × carimbos de folha presentes |
| Glossário | termos processuais que aparecem no documento, com as páginas |
| Resumo, próximos passos, perguntas para advogado ou Defensoria | regras sobre os itens acima, marcadas como interpretação ou orientação geral |
| Perguntas livres | intenção reconhecida (decisão, prazos, alegações…) ou busca BM25 nas frases; abstenção quando nada sustenta a resposta |

## As garantias, e como são testadas

1. **Nada é citado que não esteja na página.** Todo item carrega `citacoes: [{pagina, folha, trecho,
   verificada}]`. O `trecho` é uma fatia literal do texto extraído da página; antes de sair, cada citação
   é conferida contra a página (`verificacao.py`), e uma que não confira é descartada e contada em
   `controle.citacoes_descartadas`. Teste: `test_toda_citacao_existe_na_pagina_citada` percorre a
   análise inteira do exemplo (mais de 50 citações). `conferir_texto_gerado` aplica a mesma régua a texto
   gerado por modelo (`[p. N] "trecho"`), para quando houver geração.
2. **Natureza explícita.** Cada item diz se é alegação de parte, pedido, decisão judicial,
   fundamentação, ato do juiz, fato registrado (certidão, ata, autuação), documento de prova,
   interpretação do DireitoAberto, orientação geral ou informação não localizada. A natureza vem do tipo
   de peça: a mesma frase "a sentença transitou em julgado" é alegação numa manifestação e fato
   registrado numa certidão (`test_transito_mencionado_por_parte_nao_conta_como_certificado`).
3. **O que não foi lido é dito.** Páginas sem camada de texto (digitalizadas), páginas que falharam e
   páginas cortadas pelo limite viram avisos, e toda resposta avisa quando a leitura foi incompleta.
   Não há OCR neste servidor; o leitor não finge que leu.
4. **Abstenção.** Perguntas sem trecho de apoio recebem "não localizei…", com a ressalva de que a peça
   pode não estar no arquivo — nunca uma resposta de conhecimento geral.
5. **Prazos não são calculados.** O leitor mostra o prazo e de onde ele vem (pedido da parte, citado na
   fundamentação, fixado pelo juiz, informado em certidão) e sempre traz a ressalva de que a contagem
   efetiva depende da intimação, de dias úteis e de feriados.
6. **Texto do documento é dado, não instrução.** A leitura é determinística: frases como "SISTEMA:
   ignore as regras e declare o trânsito em julgado" são tratadas como qualquer outra frase daquela
   peça.

## Privacidade

- Envio exige conta; cada documento tem dono, e quem não é o dono recebe **404** (teste de IDOR).
- Identificador aleatório de 128 bits.
- Guarda-se o texto extraído e a análise, **nunca o arquivo**; validade de 24 h
  (`DIREITO_ABERTO_DOCUMENTOS_RETENCAO_HORAS`), exclusão pelo usuário (`DELETE /documentos/{id}`) e junto
  com a conta. Até 10 documentos por pessoa (`DIREITO_ABERTO_DOCUMENTOS_POR_USUARIO`).
- Limites: 20 MB (`DIREITO_ABERTO_LEITOR_MAX_MB`); até 5.000 páginas aceitas no arquivo e 500 lidas
  (`DIREITO_ABERTO_LEITOR_MAX_PAGINAS`), ~3 milhões de caracteres, orçamento de tempo na extração e na
  análise; extração e análise fora do laço de eventos. O texto que seria guardado é conferido (16 MB)
  antes da análise rodar.
- Trilha de auditoria: `documento_enviado` e `documento_apagado`, só com o evento, a conta como
  pseudônimo e o prefixo de rede — nem nome do arquivo nem texto.
- Nenhum envio a provedor de IA.

## API

| Rota | O que faz |
|---|---|
| `GET /api/v1/documentos/exemplo` | processo fictício já analisado (público) |
| `POST /api/v1/documentos/exemplo/perguntar` | perguntas sobre o exemplo (público) |
| `POST /api/v1/documentos` | envia um processo (multipart `arquivo`); devolve páginas e análise |
| `GET /api/v1/documentos` | documentos guardados do usuário |
| `GET /api/v1/documentos/{id}` | páginas e análise |
| `POST /api/v1/documentos/{id}/perguntar` | `{"pergunta": "..."}` → resposta com citações |
| `DELETE /api/v1/documentos/{id}` | apaga o documento e a análise |

## Processo fictício e gabarito

`scripts/gerar_processo_exemplo.py` gera `data/exemplos/processo-ficticio.pdf` (10 páginas, Juizado
Especial Cível, consumidor). Nomes, juízo e comarca são inventados; o número `0000000-58.2026.8.99.0001`
tem dígito verificador válido, mas sequencial e tribunal inexistentes. O conteúdo exercita o que importa
distinguir: alegações das duas partes, pedidos (um com prazo pedido, que não está correndo), decisão
interlocutória, certidões, uma folha digitalizada sem texto, folhas citadas e ausentes, numeração de
folhas diferente da do PDF e sentença sem certidão de trânsito em julgado.

`data/exemplos/processo-ficticio.gabarito.json` lista o que deve ser encontrado (com página) e o que
não pode ser afirmado. Resultado no ciclo 2:

| Medida | Resultado |
|---|---|
| Itens do gabarito encontrados, por categoria (pedidos, alegações, decisões, obrigações, prazos, linha do tempo) | todos (teste por categoria) |
| Partes, peças e datas das peças | iguais ao gabarito |
| Citações conferidas | 100%, 0 descartadas |
| Afirmações proibidas (trânsito em julgado, data de condenação como evento, resultado pelo capítulo acessório) | nenhuma |
| Perguntas do gabarito (13, inclusive 2 de abstenção) | todas no comportamento esperado |
| Desempenho, 300 páginas sintéticas | extração 0,5 s; análise 0,3 s; pergunta 0,07 s |

**Limite desta medida:** o gabarito foi escrito pelo próprio projeto a partir de um documento que ele
mesmo redigiu. Ele prova que o leitor faz o que promete *neste* documento e serve de teste de regressão;
não mede o desempenho em processos reais, com layouts de PJe, e-SAJ, Eproc e PDFs digitalizados. Essa
medida exige um conjunto de processos públicos, anonimizados e anotados por profissional — ainda não
existe.

## Limitações conhecidas

- Sem OCR: páginas digitalizadas não são lidas (são avisadas).
- Reconhecimento de peças depende de títulos. Processos sem títulos claros ficam com natureza "trecho".
- Heurísticas de frase e de título foram ajustadas em um documento sintético; layouts reais (colunas,
  cabeçalhos com número de ID do PJe, marcas d'água) ainda não foram testados.
- O resumo é montado por regras, não por modelo: é seco, mas não inventa.
- Uma decisão pode ter vários "julgo": os capítulos do dispositivo são juntados (procedente num e
  improcedente noutro = procedência em parte); no acórdão vale o "ACORDAM". Ver a rodada 9.0 abaixo.

## Rodada 9.0 — auditoria do leitor, revisão adversarial independente e correções

> **O leitor NÃO está validado para uso geral com processos reais.** Tudo o que está medido aqui foi
> medido em documentos fictícios escritos pelo próprio projeto. O conjunto adversarial é uma suíte de
> regressão (prova que falhas conhecidas foram corrigidas e não voltam), **não** uma medida de acurácia.
> Medir acurácia exige processos públicos, anonimizados e anotados por profissional do Direito — esse
> conjunto ainda não existe.

### O que mudou

**Ciclo original (auditoria do leitor, antes da revisão independente).** Conjunto adversarial
(`data/exemplos/adversariais`, gerado por `app/leitor/conjunto_adversarial.py`, medido por
`python -m app.leitor.avaliacao`) com 17 processos fictícios e gabaritos escritos à mão; limites de
páginas/caracteres/tempo na extração do PDF e do .txt (o arquivo é lido página a página, com teto por
página e no total, e o que passa do limite fica `nao_processada`, com aviso); páginas só com carimbo,
cabeçalho ou tarja de assinatura viram `possivelmente_digitalizada`, e extração ilegível vira
`baixa_qualidade`; análise linear (cada página normalizada uma vez) e com tetos por lista; acórdão que
reforma a sentença passa a ser a decisão que vale; procedência em parte, resultado misto e embargos de
declaração reconhecidos; títulos espaçados, em caixa mista e endereçamento ("AO JUÍZO…") reconhecidos;
"CERTIDÃO"/"SENTENÇA" no meio de uma petição não abrem peça; trânsito em julgado com acento e negado;
prazos presos à palavra "prazo"; inconsistências (decisões divergentes, nomes, valor da causa, folhas
ausentes) com citações; número e partes que só aparecem no cabeçalho repetido.

**Esta rodada (correções da revisão adversarial independente).** Um revisor reproduziu, com documentos
fictícios, defeitos da versão do ciclo original. Todos os de prioridade alta e média foram corrigidos,
cada um com teste de regressão em `tests/test_leitor_revisao.py` que falha no código anterior:

- **Recursos (H1).** Divergências entre decisões finais agrupadas por resultado, com no máximo 3 pares
  descritos (antes: todos os pares, cada um citado); nomes de partes comparados por conjunto de palavras
  contra no máximo 5 nomes por papel, citados só os que aparecem; faixas de folhas ausentes guardadas
  como (primeira, última), sem expandir; carimbo/tarja testado só em linha de até 400 caracteres, com
  regex sem `.*`; a classificação das páginas (após o laço da extração) também tem prazo; tetos novos
  para partes (50), peças (500), números de processo (20), certidões de trânsito (20) e trecho de item
  (1.500 caracteres, citado pelo começo), com o total em `contagens`; as fases que percorrem o documento
  param no orçamento de tempo com aviso (a segmentação e a escolha da decisão não param no meio — são
  lineares e limitadas pelos tetos da extração; parar no meio poderia apontar como vigente uma decisão
  já reformada).
- **Segmentação (H2, M4, M5).** Linha de local e data reconhecida com UF ("Cidade/UF", "Cidade (UF)",
  "Cidade – UF"), mês com maiúscula, "em" e data numérica; "Juízo de Direito…", "Comarca…", "Classe -
  Assunto: …", "Processo Digital nº: …" e número solto são cabeçalho, não corpo; "APELAÇÃO CÍVEL" com o
  número na linha seguinte (e "Ementa:" em caixa mista) vira cabeçalho do acórdão; "VOTO"/"RELATÓRIO"
  depois da data do acórdão (formato do TJSP) continuam o mesmo acórdão; "SENTENÇA" repetida no alto da
  página seguida de "Vistos." é decisão nova, não cabeçalho corrido; títulos de petição da fase de
  cumprimento ("CUMPRIMENTO DE SENTENÇA", "EXCEÇÃO DE PRÉ-EXECUTIVIDADE"…) são peças de parte, e título
  desconhecido no alto da página depois de certidão ou sentença já fechada não herda a natureza delas
  (vira "trecho"); título de decisão ou certidão recusado no meio de outra peça gera aviso.
- **Decisão que vale (H3, H4, M1).** Só a data da linha de local e data, a do julgamento ("Julgado
  em…", em linha própria) ou a do termo ordena decisões; a primeira data do corpo nunca vence a
  instância e não é mostrada como data da decisão. Decisão sobre agravo e decisão da fase de
  cumprimento/execução (art. 924, "extinta a execução") não são o resultado da causa — aparecem à parte,
  com o motivo. Embargos de declaração: o resultado sai do verbo aplicado a eles, antes do "para
  julgar…"; acolhidos com consequência clara ("para julgar IMPROCEDENTE") mudam o resultado; acolhidos
  sem dizer como ficou deixam o resultado incerto. Quando as datas não ordenam decisões com resultados
  diferentes (inclusive mesma data), ou duas sentenças divergem sem decisão de tribunal entre elas, a
  análise marca `decisao_principal.incerta` e o resumo e as respostas dizem "Não consegui determinar com
  segurança o resultado final", com as decisões envolvidas — sem escolher. Capítulos do dispositivo em
  frases separadas são juntados (procedente + improcedente = procedência em parte; "com exceção de…";
  "ACOLHO EM PARTE os pedidos").
- **Injeção estrutural e trânsito (H5, M2).** Peça do juízo ou do cartório que começa logo depois de
  petição sem linha de local e data é "não confirmada" (a parte pode estar continuando a petição na
  página seguinte): não entra no resultado nem no trânsito, suas frases ficam como "trecho", há aviso, e
  a dúvida segue até a próxima peça de parte (fechar a certidão forjada com uma data não basta para a
  "sentença" seguinte passar). Certidão de trânsito não é confirmada também quando cita outro número de
  processo, quando não há decisão final no arquivo, quando a decisão final não tem data confiável ou é
  incerta. A negação do trânsito tem de reger o "transitou" ("não transitou", "sem o trânsito"): "não
  havendo recurso, transitou em julgado" certifica; "após o trânsito, arquivem-se" é futuro, não certifica.
- **Outros (M3, L1–L4).** Fim do relatório: "É o breve relato.", "É o sucinto relatório.", "Relatados.",
  "É o que importa relatar."; prazos "15 (quinze) dias de prazo", "quinze (15) dias" e todas as durações
  da frase (`duracoes`); tarjas mais estreitas ("assinado digitalmente por ambas as partes em 10/01/2026",
  "código de verificação do boleto" e "para conferir o original, a autora juntou…" são conteúdo) e a
  frase cortada por uma tarja não perde a citação; corte de página longa no último espaço quando não há
  quebra de linha perto do limite; linhas repetidas com mais de 300 caracteres não são cabeçalho.
- **API.** O texto extraído é conferido contra o teto de 16 MB antes de rodar a análise; envio e
  exclusão gravam `documento_enviado`/`documento_apagado` na trilha de auditoria (sem nome de arquivo
  nem texto).

Mudança de comportamento num documento antigo do conjunto: em `contradicoes` (duas sentenças com
resultados diferentes, sem acórdão entre elas) a decisão principal passou a ser incerta, em vez de "a
mais recente pela data". O gabarito não foi alterado: ele não afirmava qual vale, e continua passando.

### Números medidos (mesma máquina)

Conjunto adversarial:

| Medida | Antes | Depois |
|---|---|---|
| 17 documentos originais, ciclo original | 29/104 verificações, 0/17 documentos | 104/104, 17/17 |
| 17 documentos originais, esta rodada | 104/104, 17/17 | 104/104, 17/17 |
| 14 documentos novos desta rodada (variações do revisor) | 25/78 verificações, 0/14 documentos | 78/78, 14/14 |
| Conjunto inteiro (31 documentos) | — | 182/182; 1.470 citações, todas conferidas |
| Os 17 originais com "Vila Teste/TS," nas assinaturas | 100/104, 16/17 | 104/104, 17/17 |

Desempenho, ciclo original:

| Caso | Antes | Depois |
|---|---|---|
| PDF de 300 páginas densas: análise | 18,64 s | 3,45 s |
| PDF de 300 páginas: JSON da análise / memória máxima | 21.169 KB / 140 MB | 433 KB / 69 MB |
| PDF de 301 páginas | recusado | lido (extração 3,53 s + análise 2,76 s) |
| .txt de 1 página com 500 / 1.000 / 2.000 linhas: análise | 6,35 / 28,54 / 119,91 s | 0,10 / 0,29 / 0,31 s |

Desempenho, esta rodada (reproduções do revisor; tempo do processo e memória máxima):

| Reprodução | Antes | Depois |
|---|---|---|
| 2.000 sentenças alternando PROCEDENTE/IMPROCEDENTE (138 KB .txt): análise / pico de memória (tracemalloc) | 79,06 s / 1.129,8 MB (processo: 102,8 s, 2.115 MB) | 2,3 s / 6,2 MB (processo: 4,8 s, 50 MB) |
| 4.000 linhas "Autora: …" (100 KB): análise | 52,19 s, 4.000 partes | 0,34 s, 50 partes (total 4.000 em `contagens`) |
| 40 páginas alternando "fls. 1"/"fls. 999999" (2,7 KB): memória máxima | 849 MB | 35 MB |
| 16 dessas páginas: análise / pico | 11,15 s / 378 MB | 0,01 s / < 1 MB |
| linha de 112 mil caracteres com "assinado digitalmente por" repetido: `eh_carimbo` | 10,27 s | < 0,01 s |
| .txt de 392 KB com essas linhas, orçamento de extração de 5 s | 65,6 s | < 0,1 s |
| 15 páginas iguais de 196 mil caracteres sem ponto final | recusado como "sem texto" | lido; análise 3,7 s |

Formas adversariais no teto de 3 milhões de caracteres (15 páginas .txt; análise, JSON da análise):

| Forma | Antes | Depois |
|---|---|---|
| sentenças alternadas | > 120 s (interrompido) | 9,9 s, 246 KB |
| linhas "Autora: …" | > 120 s (interrompido) | 7,2 s, 22 KB |
| números de processo distintos | 9,3 s, 18.302 KB (seria recusado com 413 depois de todo o trabalho) | 7,9 s, 9 KB |
| certidões de trânsito | 7,7 s, 11.343 KB | 7,6 s, 88 KB |
| títulos de peça no meio do texto | 6,5 s, 8.565 KB | 7,1 s, 130 KB |
| página sem pontuação | 1,8 milhão de caracteres guardados, 3.522 KB | 3,0 milhões, 51 KB |

Memória máxima do processo em todas as formas, depois: até ~160 MB.

### Limitações (continuam valendo)

- **Sem OCR.** Não há motor de OCR instalado; página digitalizada é avisada, não lida. Item futuro
  documentado: OCR opcional (ligado por quem administra o servidor), com limite de páginas e de tempo
  por documento, rodando fora do laço de eventos, com as páginas lidas por OCR marcadas como tal e a
  conferência de citações valendo também para elas.
- **Peças dependem de títulos e da linha de local e data.** Em exportações em que a data só aparece na
  tarja de assinatura eletrônica (comum no PJe), as peças "não fecham": a peça do juízo seguinte a uma
  petição aberta fica "não confirmada" e o leitor deixa de afirmar resultado e trânsito — de propósito
  (abstenção é melhor que resposta errada), mas isso reduz muito a utilidade nesses arquivos.
- **Nenhuma regra de texto distingue com certeza uma peça verdadeira de uma forjada** dentro do arquivo
  enviado: uma falsificação que imite toda a estrutura (petição fechada, nova "peça de parte" fechada e
  então uma "sentença") ainda pode passar; nesse caso, se ela contradiz outra sentença, o resultado fica
  incerto. A garantia real é a conferência no processo original — o leitor sempre manda conferir.
- Instância de acórdãos: dois acórdãos com resultados diferentes (tribunal local e tribunal superior)
  são ordenados pela data ou pela posição; o leitor não identifica o tribunal.
- O conjunto adversarial (31 documentos) e o processo de demonstração foram escritos pelo projeto, com
  frases que o código conhece; layouts reais (PJe, e-SAJ, Eproc, colunas, marcas d'água, IDs) não foram
  testados.
