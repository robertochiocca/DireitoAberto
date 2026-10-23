# Prontidão comercial — análise e hipóteses

> Rodada 9.0, P5. **Tudo o que fala de mercado, cliente, preço ou demanda neste documento é hipótese**:
> nada foi validado com clientes, nenhum número de mercado foi pesquisado, e nenhuma cobrança, conta
> externa, contrato ou implantação foi feita. As afirmações sobre regras profissionais e regulatórias são
> pontos a confirmar com advogado, não parecer jurídico.

## O que o produto é hoje (fato, com evidência no repositório)

| Capacidade | Estado | Evidência |
|---|---|---|
| Busca em 79 dispositivos (34 normas monitoradas, súmulas, uma resolução) com resposta extrativa | funciona | `docs/avaliacao/` |
| Separação entre texto oficial (141 trechos conferidos com a página oficial) e explicação | funciona | `docs/legal-data-sources.md` |
| Versão certa para a data da pergunta, com incerteza declarada | funciona no benchmark do projeto | temporal v2 |
| Abstenção, ressalvas e encaminhamento a profissional por regra | funciona, com números otimistas | `docs/avaliacao/README.md` |
| Leitor de processos (PDF/TXT com texto) | funciona em documentos fictícios; **não validado em processos reais**; sem OCR | `docs/leitor-de-processos.md` |
| Monitor de 34 páginas do Planalto, com revisão humana | agendado nos dias úteis desde 23/10/2026; resultado vem como artefato para revisão | `docs/monitor-legislativo.md` |
| Contas, exportação e exclusão de dados, trilha de auditoria | funciona | `docs/security-audit.md` |
| Geração por LLM | existe no código; **qualidade não medida** (sem chave) | — |

## Por que ainda não é um produto vendável

1. **Nenhuma revisão jurídica humana.** Corpus, explicações, regras de política e gabaritos foram
   escritos e conferidos pelo projeto, sem profissional do Direito. Há 28 revisões de conteúdo pendentes.
2. **Cobertura pequena.** 79 dispositivos cobrem temas comuns, mas não a variedade de perguntas reais;
   a abstenção protege, e por isso o produto responde "não sei" com frequência fora desses temas.
3. **Leitor sem validação real.** Medido em 32 documentos fictícios; processos digitalizados (imagem)
   não são lidos.
4. **Operação incompleta.** O monitor está agendado, mas ninguém está designado para revisar: 16 versões
   de releitura e as 34 linhas de base esperam revisão humana; sem rotina de backup verificada; produção
   não auditada.
5. **Governança de dados incompleta.** Controlador, encarregado, bases legais e termos de uso não
   definidos; política de privacidade é minuta técnica.
6. **Compreensão e utilidade não medidas com pessoas.**

## Restrições a confirmar com advogado (hipóteses de risco)

- **Atividade privativa da advocacia.** O Estatuto da Advocacia (Lei 8.906/1994, art. 1º) reserva à
  advocacia a consultoria e a assessoria jurídicas. Hipótese de trabalho: informação jurídica geral,
  com fonte e sem análise do caso concreto, fica fora disso; resposta personalizada sobre o que a pessoa
  deve fazer, não. O produto já recusa prever resultado e encaminha o caso concreto
  (`recomendar_profissional`), mas a fronteira precisa de parecer, inclusive sobre o leitor de processos.
- **Publicidade e captação.** Qualquer encaminhamento a advogados ou escritórios (indicação, parceria,
  anúncio) toca regras da OAB sobre publicidade e captação de clientela. Não fazer sem parecer.
- **LGPD.** Dados de saúde, violência doméstica e processos são sensíveis ou de terceiros. Tratar com
  base legal definida, encarregado nomeado e relatório de impacto antes de qualquer oferta pública.
- **Relação de consumo.** Oferta paga ao cidadão traz o CDC (informação clara, vício do serviço). A
  linguagem "não substitui advogado nem a Defensoria" já está no produto e precisaria entrar nos termos.
- **Compras públicas.** Venda a órgão público segue a Lei 14.133/2021 (licitação ou hipóteses de
  contratação direta), com exigências de segurança e LGPD do próprio órgão.

## Hipóteses de modelo (nenhuma testada)

| Hipótese | Para quem | O que já sustenta | O que falta | Principal risco |
|---|---|---|---|---|
| H1. Ferramenta de triagem e orientação para Defensorias e núcleos de prática jurídica | atendimento inicial | proveniência, abstenção, encaminhamento, leitor sem envio a terceiros | piloto com equipe real; cobertura por área de atuação; revisão jurídica do corpus da área | o atendente confiar demais; dados de assistidos |
| H2. Base jurídica com proveniência e monitor, por API, para *legaltechs* e redações | equipes técnicas | trechos com hash, versão e histórico; monitor com eventos tipados | cobertura muito maior; SLA; DOU; termos de licença do conteúdo | o valor está na cobertura, que ainda é pequena |
| H3. Orientação gratuita ao cidadão, financiada por fomento ou parceria institucional | público em geral | o que já existe, sem cobrança | parceiro, governança, operação contínua, revisão jurídica | custo de revisão humana contínua sem receita |
| H4. Leitor de processos para quem é parte (entender o próprio processo) | cidadão com processo | leitor com natureza de cada item e citações conferidas | validação em processos reais anonimizados, OCR, parecer sobre a fronteira com consultoria | erro numa decisão ou prazo com consequência real |

O custo dominante, em todas, é **revisão humana qualificada** (do corpus, das mudanças do monitor, do
feedback). Hospedagem e busca custam pouco; o custo do LLM por consulta não foi medido.

## Como validar antes de investir (experimentos sugeridos)

1. **Entrevistas** (H1/H3): 5 a 10 conversas com equipes de Defensoria, NPJ e organizações de apoio
   jurídico: quais perguntas chegam, o que custa tempo, o que elas jamais delegariam a um sistema.
2. **Teste de compreensão** com pessoas (todas): a pessoa entende a diferença entre texto oficial e
   explicação? Entende "não verificado"? Toma alguma decisão errada a partir da resposta?
3. **Piloto fechado** (H1): uma área (consumidor ou família), corpus revisado por advogado da área,
   sem dados reais no início, com métricas definidas antes (taxa de abstenção aceitável, erros
   encontrados na revisão, tempo poupado).
4. **Leitor com processos anonimizados** (H4): só com base legal e anonimização conferida; medir com
   gabarito escrito por profissional, não pelo projeto.
5. **Custo de revisão** (todas): medir horas por mudança do monitor e por feedback procedente durante o
   piloto.

## Critérios mínimos antes de qualquer oferta pública

- Parecer jurídico sobre a fronteira com a advocacia e sobre o leitor.
- Revisão por profissional de todo o corpus oferecido; 0 revisões pendentes na área oferecida.
- Controlador, encarregado, política de privacidade e termos de uso aprovados.
- Monitor agendado, com responsável pela revisão e prazo definido; backup testado.
- Teste com usuários feito e problemas graves corrigidos.
- Avaliação com conjunto separado (não visto no desenvolvimento) para busca, temporal e política.
