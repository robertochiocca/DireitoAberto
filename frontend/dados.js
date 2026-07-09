/* ============================================================
   DADOS do DireitoAberto — situações, canais de ajuda,
   códigos e glossário. Editar aqui não exige tocar no layout.
   ============================================================ */

const PROBLEMS = [
  {
    id:"defeito",
    tag:"CONSUMIDOR",
    title:"Comprei um produto com defeito e a loja não quer resolver",
    short:"Você tem direito a conserto, troca ou dinheiro de volta — e a lei dá um prazo pra loja resolver.",
    lawShort:"CDC · Lei 8.078/1990",
    plain:"A loja ou o fabricante têm 30 dias para consertar o defeito. Passou o prazo e não resolveu? Aí quem escolhe é você: trocar por outro, receber o dinheiro de volta ou ficar com o produto pagando menos.",
    law:{art:"Código de Defesa do Consumidor · art. 18 e art. 26", txt:"Se o vício não for sanado em 30 dias, o consumidor pode exigir a troca, a devolução da quantia paga ou o abatimento proporcional do preço."},
    steps:[
      "Reclame por escrito (e-mail, chat, WhatsApp) e <b>guarde o número de protocolo</b>. Provar que você reclamou é metade do caminho.",
      "Dê o prazo de <b>30 dias</b> para o conserto. Marque a data no calendário.",
      "Não resolveu? Registre no <b>consumidor.gov.br</b> ou no <b>Procon</b> da sua cidade.",
      "Persistiu? <b>Juizado Especial Cível</b> — recebe causas de até <b>40 salários mínimos</b>; até <b>20</b>, você pode entrar <b>sem advogado</b> (Lei 9.099/95, arts. 3º e 9º)."
    ],
    deadline:"Prazo pra reclamar: <b>30 dias</b> (produtos não duráveis, como alimentos) ou <b>90 dias</b> (duráveis, como eletrônicos), a contar da entrega ou de quando o defeito apareceu.",
    template:"“Venho registrar reclamação sobre o produto [modelo/nota fiscal nº], que apresentou o defeito [descrever]. Solicito o conserto no prazo legal de 30 dias, nos termos do art. 18 do CDC. Protocolo anterior: [nº]. Aguardo retorno por escrito.”",
    fonte:{lei:"Lei nº 8.078/1990 (CDC)", art:"Arts. 18 e 26", url:"https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"},
    help:["procon","consumidorgov","juizado"]
  },
  {
    id:"demissao",
    tag:"TRABALHO",
    title:"Fui demitido. Quais são os meus direitos?",
    short:"Demissão sem justa causa gera um pacote de verbas: aviso, férias, 13º, FGTS + multa e seguro-desemprego.",
    lawShort:"CLT · Decreto-Lei 5.452/1943",
    plain:"Se você foi demitido sem justa causa, a empresa deve pagar: saldo de salário, aviso prévio, férias vencidas e proporcionais + 1/3, 13º proporcional, liberar o saque do FGTS com multa de 40% e entregar as guias do seguro-desemprego.",
    law:{art:"Consolidação das Leis do Trabalho + Constituição, art. 7º", txt:"O trabalhador dispensado sem justa causa tem direito ao aviso prévio, às verbas rescisórias proporcionais e à indenização de 40% sobre o FGTS."},
    steps:[
      "Confira o <b>termo de rescisão</b>: cada verba deve estar discriminada. Some você mesmo.",
      "O pagamento deve sair em até <b>10 dias corridos</b> após o fim do contrato.",
      "Confira se o <b>FGTS</b> foi liberado e a multa de 40% depositada.",
      "Dê entrada no <b>seguro-desemprego</b> com as guias (app ou site Gov.br / SINE).",
      "Algo faltou? <b>Sindicato</b> da categoria ou <b>Justiça do Trabalho</b> (a Defensoria e advogados trabalhistas orientam)."
    ],
    deadline:"Você tem até <b>2 anos</b> após a saída para cobrar verbas na Justiça — e nesse processo pode cobrar os últimos <b>5 anos</b> trabalhados.",
    template:"“Solicito a segunda via do termo de rescisão e o extrato do FGTS para conferência das verbas rescisórias referentes ao contrato encerrado em [data]. Verifiquei possível divergência em [verba].”",
    fonte:{lei:"CLT (DL 5.452/1943) e CF/88", art:"CLT, art. 477 · CF, art. 7º", url:"https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm"},
    help:["defensoria","sindicato","justicatrabalho"]
  },
  {
    id:"multa",
    tag:"TRÂNSITO",
    title:"Recebi uma multa de trânsito que acho injusta",
    short:"Dá pra se defender — em dois momentos e sem advogado. O segredo é o prazo na notificação.",
    lawShort:"CTB · Lei 9.503/1997",
    plain:"Você pode se defender em duas etapas: primeiro a defesa da autuação (quando chega a notificação), depois o recurso à JARI e, se preciso, ao CETRAN. Tudo tem prazo — que vem impresso na própria notificação.",
    law:{art:"Código de Trânsito Brasileiro · art. 281 e seguintes", txt:"O autuado tem direito de apresentar defesa da autuação e, mantida a penalidade, recorrer às juntas administrativas antes do vencimento indicado na notificação."},
    steps:[
      "Leia a notificação e ache <b>a data limite</b> e o <b>órgão autuador</b> (Detran, prefeitura, PRF…).",
      "Junte provas: fotos, comprovantes, testemunhas, sinalização irregular.",
      "Protocole a <b>defesa prévia</b> no órgão que autuou, dentro do prazo.",
      "Mantida a multa, entre com <b>recurso à JARI</b>; se negado, ao <b>CETRAN</b>.",
      "Fique de olho na <b>pontuação da CNH</b> — o recurso suspende os efeitos até o julgamento."
    ],
    deadline:"Não existe prazo único: <b>cada notificação traz a sua data</b>. Perder o prazo é o erro mais comum — anote assim que a multa chegar.",
    template:"“Apresento defesa da autuação nº [código], lavrada em [data], por entender que [motivo objetivo: sinalização, identificação do condutor, erro de local]. Anexo [provas]. Requeiro o cancelamento nos termos do CTB.”",
    fonte:{lei:"Lei nº 9.503/1997 (CTB)", art:"Arts. 281 a 288", url:"https://www.planalto.gov.br/ccivil_03/leis/l9503compilado.htm"},
    help:["defensoria","juizado"]
  },
  {
    id:"negativado",
    tag:"CONSUMIDOR",
    title:"Meu nome foi negativado por uma dívida que não reconheço",
    short:"Cobrança indevida tem regra: você tem que ser avisado antes e, se pagou o que não devia, recebe em dobro.",
    lawShort:"CDC · Lei 8.078/1990",
    plain:"Antes de negativar seu nome, a empresa é obrigada a te avisar por escrito. E se você foi cobrado por algo que já pagou ou que não deve, tem direito a receber de volta o dobro do valor, com correção.",
    law:{art:"Código de Defesa do Consumidor · art. 42 e art. 43", txt:"O consumidor cobrado em quantia indevida tem direito à repetição do dobro do que pagou em excesso, e deve ser comunicado por escrito antes da inscrição em cadastros de inadimplentes."},
    steps:[
      "Consulte gratuitamente <b>Serasa</b> e <b>SPC</b> para ver quem negativou e por qual valor.",
      "Peça à empresa o <b>detalhamento da dívida</b> por escrito.",
      "Não reconhece? Envie <b>contestação formal</b> pedindo a retirada do nome.",
      "Sem solução, registre no <b>Procon</b> e leve ao <b>Juizado Especial</b> — negativação indevida pode gerar dano moral."
    ],
    deadline:"Uma dívida não fica negativada pra sempre: após <b>5 anos</b>, o nome deve sair dos cadastros — mesmo que a dívida ainda exista.",
    template:"“Constatei a inscrição do meu nome referente ao débito [nº/origem], que não reconheço. Solicito, no prazo de 10 dias, o detalhamento e a baixa da negativação, sob pena das medidas cabíveis (art. 42 e 43 do CDC).”",
    fonte:{lei:"Lei nº 8.078/1990 (CDC)", art:"Arts. 42 e 43", url:"https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"},
    help:["procon","juizado","defensoria"]
  },
  {
    id:"aluguel",
    tag:"MORADIA",
    title:"O dono quer me despejar ou aumentar o aluguel fora de hora",
    short:"Reajuste é uma vez por ano, pelo índice do contrato. Despejo segue rito e prazos — não é da noite pro dia.",
    lawShort:"Lei do Inquilinato · 8.245/1991",
    plain:"O aluguel só pode ser reajustado uma vez por ano, pelo índice previsto no contrato (IGP-M, IPCA…). E o despejo tem regras e prazos: o locador precisa de motivo válido ou de notificação com antecedência, conforme o tipo de contrato.",
    law:{art:"Lei do Inquilinato (Lei 8.245/1991)", txt:"A locação de imóvel urbano residencial tem lei própria, que define reajuste anual, prazos de desocupação e as hipóteses de retomada do imóvel pelo proprietário."},
    steps:[
      "Releia o contrato: <b>índice de reajuste</b>, prazo e regras de rescisão.",
      "Reajuste só <b>uma vez a cada 12 meses</b> — cobrança fora disso é indevida.",
      "Recebeu aviso de despejo? Veja o <b>motivo</b> e o <b>prazo</b> concedido.",
      "Situação apertada? A <b>Defensoria Pública</b> atende gratuitamente casos de moradia."
    ],
    deadline:"Notificação para desocupação costuma dar <b>30 dias</b> em contratos sem prazo — mas depende do caso. Não desocupe por telefone: exija por escrito.",
    template:"“Recebi a comunicação de [reajuste/desocupação]. Solicito o fundamento contratual e legal e o prazo aplicável, conforme a Lei 8.245/1991, antes de qualquer providência.”",
    fonte:{lei:"Lei nº 8.245/1991 (Inquilinato)", art:"Arts. 18, 19 e 46", url:"https://www.planalto.gov.br/ccivil_03/leis/l8245.htm"},
    help:["defensoria","juizado"],
    note:"<b>Detalhe importante de letramento:</b> a locação residencial urbana <u>não</u> é regida diretamente pelo Código Civil, e sim pela Lei do Inquilinato (8.245/1991). O Código Civil entra só de forma subsidiária. Saber qual lei rege o seu caso já evita metade dos erros."
  },
  {
    id:"arrependimento",
    tag:"CONSUMIDOR",
    title:"Comprei pela internet e me arrependi",
    short:"Compra fora da loja física? Você tem 7 dias para desistir e receber tudo de volta — sem precisar explicar por quê.",
    lawShort:"CDC · Lei 8.078/1990",
    plain:"Quando você compra pela internet, telefone ou catálogo — ou seja, sem ver o produto pessoalmente —, tem 7 dias corridos para desistir. Basta avisar dentro do prazo e a loja devolve os valores pagos, atualizados.",
    law:{art:"Código de Defesa do Consumidor · art. 49", txt:"O consumidor pode desistir do contrato em 7 dias sempre que a contratação ocorrer fora do estabelecimento comercial, com devolução dos valores pagos, monetariamente atualizados."},
    steps:[
      "Confira a <b>data de recebimento</b>: o prazo de 7 dias conta a partir dela.",
      "Comunique a desistência <b>por escrito</b> dentro do prazo e guarde o protocolo.",
      "Devolva o produto conforme orientado. <b>Em regra, o custo da devolução não deve recair sobre você</b> — mas há discussão na jurisprudência em casos específicos; guarde todos os comprovantes.",
      "O reembolso inclui os <b>valores pagos, inclusive o frete da compra</b>. Não recebeu? Procon ou consumidor.gov.br."
    ],
    deadline:"São <b>7 dias corridos</b> (incluindo fins de semana) a partir do recebimento. É o chamado <b>direito de arrependimento</b> — vale só para compras fora da loja física.",
    template:"“Manifesto, dentro do prazo de 7 dias do art. 49 do CDC, a desistência da compra [pedido nº], recebida em [data]. Solicito instruções para devolução e o reembolso integral, incluindo o frete.”",
    fonte:{lei:"Lei nº 8.078/1990 (CDC)", art:"Art. 49", url:"https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"},
    help:["consumidorgov","procon"]
  },
  {
    id:"pensao",
    tag:"FAMÍLIA",
    title:"Preciso pedir, revisar ou cobrar pensão alimentícia",
    short:"Não existe percentual fixo em lei: o valor equilibra a necessidade de quem recebe e a possibilidade de quem paga.",
    lawShort:"Código Civil · arts. 1.694–1.695",
    plain:"A pensão é fixada caso a caso, no equilíbrio entre a necessidade do filho (ou de quem recebe) e a possibilidade de quem paga — o famoso '30%' é costume, não lei. Pensão atrasada pode ser cobrada na Justiça, inclusive com prisão do devedor pelas 3 últimas parcelas.",
    law:{art:"Código Civil · arts. 1.694 e 1.695 + CPC · art. 528", txt:"Os alimentos são fixados na proporção das necessidades de quem pede e dos recursos de quem paga. O não pagamento das 3 últimas parcelas autoriza a prisão civil de 1 a 3 meses."},
    steps:[
      "Reúna documentos: certidão de nascimento, comprovantes de <b>gastos da criança</b> e, se tiver, da <b>renda de quem vai pagar</b>.",
      "Procure a <b>Defensoria Pública</b> (gratuita) — dá para pedir fixação, revisão (aumento/redução) ou execução da pensão.",
      "Se a pensão atrasou, a execução pode pedir <b>desconto em folha</b>, penhora ou <b>prisão</b> (3 últimas parcelas).",
      "Acordos feitos fora da Justiça valem, mas <b>homologados</b> ficam muito mais fáceis de cobrar depois."
    ],
    deadline:"A cobrança pelo rito da prisão vale para as <b>3 últimas parcelas</b> vencidas + as que vencerem durante o processo. Parcelas mais antigas seguem pelo rito da penhora.",
    template:"“Solicito orientação para [fixar/revisar/executar] pensão alimentícia em favor de [nome], nascido em [data]. Renda do alimentante: [se souber]. Despesas mensais comprovadas: [valor]. Situação atual: [descrever].”",
    fonte:{lei:"Lei nº 10.406/2002 (Código Civil)", art:"Arts. 1.694 e 1.695", url:"https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm"},
    help:["defensoria"]
  },
  {
    id:"divorcio",
    tag:"FAMÍLIA",
    title:"Quero me divorciar. Como funciona?",
    short:"Divórcio não exige prazo, motivo nem separação prévia. Com consenso e sem filhos menores, sai até em cartório.",
    lawShort:"CF/88 · art. 226, § 6º",
    plain:"Desde 2010, o divórcio é um direito direto: não precisa de prazo mínimo de casamento, de separação prévia nem de justificativa. Se o casal está de acordo e não há filhos menores ou incapazes (nem gravidez), pode ser feito por escritura em cartório, com advogado ou defensor público.",
    law:{art:"Constituição Federal · art. 226, § 6º + CPC · art. 733", txt:"O casamento civil pode ser dissolvido pelo divórcio. O divórcio consensual pode ser lavrado por escritura pública quando não houver nascituro ou filhos incapazes."},
    steps:[
      "Verifique o cenário: <b>consensual ou litigioso</b>? Há <b>filhos menores</b>? Há <b>bens</b> a partilhar?",
      "Consensual, sem filhos menores/incapazes: <b>cartório</b>, com advogado ou defensor — costuma ser rápido.",
      "Com filhos menores ou sem acordo: o divórcio é <b>judicial</b> — a Defensoria atende quem não pode pagar advogado.",
      "Guarda, pensão e partilha <b>podem ser resolvidas depois</b> — o divórcio em si não pode ser negado."
    ],
    deadline:"Não há prazo mínimo nem carência. A partilha de bens pode ser feita <b>junto ou depois</b> do divórcio.",
    template:"“Solicito orientação para divórcio [consensual/litigioso]. Casamento em [data], regime de bens [tipo]. Filhos: [nomes e idades ou 'não há']. Bens a partilhar: [descrever ou 'não há'].”",
    fonte:{lei:"Constituição Federal de 1988", art:"Art. 226, § 6º", url:"https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm"},
    help:["defensoria"]
  },
  {
    id:"guarda",
    tag:"FAMÍLIA",
    title:"Como fica a guarda dos filhos depois da separação?",
    short:"A regra legal é a guarda compartilhada — mesmo sem acordo entre os pais. Guarda, convivência e pensão são coisas diferentes.",
    lawShort:"Código Civil · arts. 1.583–1.584",
    plain:"Desde 2014, a guarda compartilhada é a regra, mesmo quando os pais não se entendem — desde que ambos estejam aptos. Compartilhar a guarda não significa dividir o tempo meio a meio, e não elimina a pensão: guarda, convivência e alimentos são questões independentes.",
    law:{art:"Código Civil · arts. 1.583 e 1.584, § 2º", txt:"Quando não houver acordo entre a mãe e o pai, estando ambos aptos a exercer o poder familiar, será aplicada a guarda compartilhada."},
    steps:[
      "Tente um <b>acordo por escrito</b> sobre rotina, escola, saúde e convivência — a Justiça homologa acordos razoáveis.",
      "Sem acordo, qualquer um dos pais pode pedir a <b>regulamentação judicial</b> da guarda e da convivência.",
      "Guarda compartilhada <b>não zera a pensão</b>: quem tem mais renda ou menos tempo com o filho normalmente contribui mais.",
      "Impedir contato do filho com o outro genitor pode caracterizar <b>alienação parental</b> — evite e documente se sofrer isso."
    ],
    deadline:"Não há prazo para pedir a regulamentação — mas quanto antes houver regra clara (mesmo provisória), menos conflito e mais proteção para a criança.",
    template:"“Solicito orientação para regulamentar a guarda e a convivência de [nome da criança], [idade]. Situação atual: [com quem mora, rotina]. Proposta: [descrever]. Há acordo parcial sobre: [itens].”",
    fonte:{lei:"Lei nº 10.406/2002 (Código Civil)", art:"Arts. 1.583 e 1.584", url:"https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm"},
    help:["defensoria"]
  },
  {
    id:"planosaude",
    tag:"SAÚDE",
    title:"O plano de saúde negou meu exame, cirurgia ou internação",
    short:"Urgência e emergência têm cobertura obrigatória. Exija a negativa por escrito — ela é a sua principal prova.",
    lawShort:"Lei 9.656/1998 · art. 35-C",
    plain:"Atendimentos de urgência (acidentes) e emergência (risco de vida) têm cobertura obrigatória por lei. Para o resto, a ANS fixa prazos máximos de atendimento e obriga o plano a entregar a negativa por escrito quando você pedir — e é com ela que Procon, ANS e Justiça agem rápido.",
    law:{art:"Lei dos Planos de Saúde · art. 35-C", txt:"É obrigatória a cobertura do atendimento nos casos de emergência (risco imediato de vida) e de urgência (acidentes pessoais ou complicações no processo gestacional)."},
    steps:[
      "Peça a <b>negativa por escrito</b>, com o motivo — o plano é obrigado a fornecer.",
      "Registre reclamação na <b>ANS</b> (0800 701 9656 ou ans.gov.br) — a NIP costuma resolver em dias.",
      "Guarde <b>pedido médico, laudos e protocolos</b>: são a base de qualquer medida.",
      "Caso urgente negado? A Justiça concede <b>liminares</b> com frequência — Defensoria ou advogado; Juizado Especial para causas menores."
    ],
    deadline:"Prazos máximos da ANS (RN 566/2022): consultas básicas em <b>7 dias</b>, exames simples em <b>3 dias</b>, cirurgias eletivas em <b>21 dias</b> — estourou, reclame na ANS.",
    template:"“Solicito, por escrito, a justificativa da negativa de cobertura do procedimento [nome], prescrito pelo(a) Dr(a). [nome/CRM] em [data], protocolo [nº], nos termos da regulamentação da ANS. Aguardo resposta em 24 horas dada a natureza do caso.”",
    fonte:{lei:"Lei nº 9.656/1998 (Planos de Saúde)", art:"Art. 35-C", url:"https://www.planalto.gov.br/ccivil_03/leis/l9656compilado.htm"},
    help:["ans","procon","defensoria"]
  },
  {
    id:"inss",
    tag:"PREVIDÊNCIA",
    title:"O INSS negou meu benefício (aposentadoria, auxílio, BPC)",
    short:"Negativa não é o fim: cabe recurso gratuito em 30 dias, sem advogado — e depois ação no Juizado Federal.",
    lawShort:"Lei 8.213/1991 · art. 126",
    plain:"Se o INSS indeferiu seu benefício, você pode recorrer ao Conselho de Recursos (CRPS) em 30 dias, de graça e sem advogado — pelo Meu INSS ou pela Central 135. Se o recurso não resolver, ações de até 60 salários mínimos correm no Juizado Especial Federal, onde também dá para entrar sem advogado.",
    law:{art:"Lei 8.213/1991 · art. 126 + Lei 10.259/2001 · art. 3º", txt:"Das decisões do INSS cabe recurso ao CRPS. Causas federais de até 60 salários mínimos competem ao Juizado Especial Federal."},
    steps:[
      "Leia a <b>carta de indeferimento</b> no Meu INSS: o motivo da negativa define a estratégia.",
      "Junte o que faltou: <b>laudos médicos, vínculos, CNIS, documentos rurais</b> — a maioria das negativas é por documento.",
      "Entre com <b>recurso ao CRPS em até 30 dias</b> (Meu INSS → 'Agendamentos/Solicitações' → 'Recurso').",
      "Recurso negado ou demorado? <b>Juizado Especial Federal</b> (até 60 salários mínimos, sem advogado em 1º grau) — a Defensoria Pública da União também atende."
    ],
    deadline:"Recurso administrativo: <b>30 dias</b> da ciência da negativa. Na via judicial, benefícios geram parcelas atrasadas de até <b>5 anos</b>.",
    template:"“Apresento recurso contra o indeferimento do benefício [tipo/NB nº], decidido em [data]. Razões: [motivo pelo qual a decisão está errada]. Anexo os documentos: [lista]. Requeiro a reforma da decisão.”",
    fonte:{lei:"Lei nº 8.213/1991", art:"Art. 126", url:"https://www.planalto.gov.br/ccivil_03/leis/l8213cons.htm"},
    help:["meuinss","defensoria"]
  },
  {
    id:"pix",
    tag:"CONSUMIDOR",
    title:"Caí num golpe do PIX. Dá pra recuperar o dinheiro?",
    short:"Agir rápido é tudo: o MED pode bloquear o valor na conta do golpista. E o banco responde por falhas de segurança.",
    lawShort:"Súmula 479/STJ · Resolução BCB 103/2021",
    plain:"Comunique o banco imediatamente: o Mecanismo Especial de Devolução (MED) permite bloquear o dinheiro na conta de destino e devolvê-lo. Além disso, quando o golpe envolve falha de segurança do banco (conta invadida, fraude interna), a instituição responde pelos prejuízos, segundo o STJ.",
    law:{art:"Súmula 479 do STJ + Resolução BCB 103/2021 (MED)", txt:"As instituições financeiras respondem objetivamente pelos danos gerados por fortuito interno relativo a fraudes praticadas por terceiros em operações bancárias."},
    steps:[
      "<b>Ligue para o banco AGORA</b> (canal oficial) e peça o acionamento do <b>MED</b> — quanto antes, maior a chance de bloquear o valor.",
      "Registre <b>boletim de ocorrência</b> (dá para fazer online) — ele é exigido no processo de devolução.",
      "Formalize a contestação <b>por escrito no app/SAC</b> do banco e guarde os protocolos.",
      "Sem solução? Reclame no <b>Banco Central</b> (bcb.gov.br → Registrar reclamação) e no <b>consumidor.gov.br</b>; para reaver valores, <b>Juizado Especial</b>."
    ],
    deadline:"O MED pode ser acionado em até <b>80 dias</b> da transação, mas a chance real de recuperar cai a cada hora — trate como emergência.",
    template:"“Comunico transação sob fraude (golpe) via Pix em [data/hora], no valor de R$ [valor], para a chave [chave]. Solicito o acionamento imediato do Mecanismo Especial de Devolução (Resolução BCB 103/2021), o bloqueio cautelar dos valores e apuração. B.O. nº [número]. Protocolo: [nº].”",
    fonte:{lei:"Súmula 479 do STJ", art:"c/ Resolução BCB nº 103/2021", url:"https://www.stj.jus.br/docs_internet/revista/eletronica/stj-revista-sumulas-2017_44_capSumulas479-483.pdf"},
    help:["bcb","consumidorgov","juizado"]
  },
  {
    id:"voo",
    tag:"CONSUMIDOR",
    title:"Meu voo atrasou, foi cancelado ou fiquei sem embarcar",
    short:"A partir de 1h de espera a companhia já te deve assistência. Acima de 4h (ou cancelado), você escolhe a solução.",
    lawShort:"Resolução ANAC 400/2016",
    plain:"A assistência é escalonada: 1 hora de espera dá direito a comunicação (internet/telefone); 2 horas, alimentação; 4 horas, acomodação ou hospedagem com transporte. Cancelou ou atrasou mais de 4 horas? Você escolhe: outro voo, reembolso integral ou outro meio de transporte. Danos maiores (compromissos perdidos) podem gerar indenização pelo CDC.",
    law:{art:"Resolução ANAC 400/2016 · arts. 20 a 27", txt:"Em atrasos e cancelamentos, o transportador deve oferecer assistência material escalonada e, acima de 4 horas, reacomodação, reembolso integral ou execução por outra modalidade, à escolha do passageiro."},
    steps:[
      "No aeroporto, peça <b>por escrito o motivo</b> do atraso/cancelamento e <b>guarde cartão de embarque</b> e comprovantes.",
      "Cobre a <b>assistência escalonada</b>: 1h comunicação, 2h alimentação, 4h hospedagem + transporte.",
      "Acima de 4h ou cancelamento: escolha entre <b>reacomodação, reembolso integral ou outro transporte</b> — a escolha é sua, não da companhia.",
      "Guarde <b>notas de despesas</b> (comida, hotel, transporte). Sem acordo: <b>consumidor.gov.br</b>, ANAC e <b>Juizado Especial</b> (inclusive nos aeroportos maiores)."
    ],
    deadline:"O reembolso, quando escolhido, deve ser processado em até <b>7 dias</b>. Ação por danos: até <b>5 anos</b> (CDC) para voos domésticos.",
    template:"“Solicito, nos termos da Resolução ANAC 400/2016, [assistência material/reacomodação/reembolso integral] referente ao voo [nº], de [origem-destino], em [data], [atrasado/cancelado]. Despesas já suportadas: R$ [valor], conforme comprovantes anexos.”",
    fonte:{lei:"Resolução ANAC nº 400/2016", art:"Arts. 20 a 27", url:"https://www.anac.gov.br/assuntos/legislacao/legislacao-1/resolucoes/resolucoes-2016/resolucao-no-400-13-07-2016"},
    help:["consumidorgov","procon","juizado"]
  },
  {
    id:"condominio",
    tag:"MORADIA",
    title:"Briga com o condomínio: multa, cobrança ou barulho de vizinho",
    short:"Atraso na cota tem teto de multa (2%). Multa por infração tem rito. E barulho fora de hora pode ser exigido de cessar.",
    lawShort:"Código Civil · arts. 1.336, 1.337 e 1.277",
    plain:"Cota atrasada gera no máximo 2% de multa + juros — acima disso é ilegal. Multa por infração de regra interna precisa respeitar a convenção e o direito de defesa. E o sossego é protegido por lei: barulho reiterado fora de hora pode ser combatido do síndico até a Justiça.",
    law:{art:"Código Civil · arts. 1.336, 1.337 e 1.277", txt:"O condômino em atraso paga juros e multa de até 2% sobre o débito. O descumprimento reiterado de deveres pode gerar multa por deliberação; o vizinho pode exigir que cessem interferências prejudiciais ao sossego."},
    steps:[
      "Confira a <b>convenção e o regimento interno</b>: multa e procedimento precisam estar previstos lá.",
      "Multa de atraso acima de <b>2%</b>? Conteste por escrito com o síndico/administradora — o teto é legal.",
      "Recebeu multa por infração? Exija <b>notificação prévia e direito de defesa</b> antes da cobrança.",
      "Barulho: registre datas/horários, converse, acione o síndico por escrito; persistindo, <b>Juizado Especial</b> (obrigação de não fazer + danos)."
    ],
    deadline:"A cobrança de cotas condominiais prescreve em <b>5 anos</b>. Guarde atas, notificações e comprovantes — condomínio é prova documental.",
    template:"“Solicito ao síndico/administradora [revisão da multa aplicada em (data) / providências quanto ao barulho da unidade (nº), ocorrido em (datas/horários)], nos termos dos arts. 1.336/1.277 do Código Civil e da convenção condominial. Aguardo resposta por escrito em 10 dias.”",
    fonte:{lei:"Lei nº 10.406/2002 (Código Civil)", art:"Arts. 1.336, 1.337 e 1.277", url:"https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm"},
    help:["defensoria","juizado"]
  },
  {
    id:"iptu",
    tag:"TRIBUTOS",
    title:"Recebi cobrança de IPTU que considero errada ou muito antiga",
    short:"Erro de valor venal se contesta na prefeitura, sem processo. E cobrança de IPTU com mais de 5 anos pode estar prescrita.",
    lawShort:"CTN · arts. 34 e 174",
    plain:"O IPTU é lançado pela prefeitura com base no valor venal do imóvel — se a metragem, o uso ou o valor estiverem errados, cabe impugnação administrativa direto na prefeitura. E a cobrança prescreve em 5 anos: dívidas mais antigas que isso, sem execução em curso, podem não ser mais exigíveis.",
    law:{art:"Código Tributário Nacional · arts. 34 e 174", txt:"Contribuinte do IPTU é o proprietário ou possuidor do imóvel. A ação de cobrança do crédito tributário prescreve em cinco anos da constituição definitiva."},
    steps:[
      "Confira o <b>carnê/lançamento</b>: metragem, uso (residencial/comercial) e valor venal batem com a realidade?",
      "Erro encontrado? Protocole <b>impugnação administrativa</b> na prefeitura (muitas aceitam online), dentro do prazo do carnê.",
      "Cobrança de anos antigos? Verifique a <b>prescrição de 5 anos</b> — peça a certidão da dívida e as datas.",
      "Execução fiscal já ajuizada? Procure a <b>Defensoria</b> ou advogado — existem defesas (exceção de pré-executividade, embargos)."
    ],
    deadline:"Impugnação: no prazo indicado no próprio carnê/notificação. Prescrição da cobrança: <b>5 anos</b> — mas ela pode ser interrompida por execução fiscal; verifique caso a caso.",
    template:"“Impugno o lançamento do IPTU [exercício], inscrição [nº], por [erro de metragem/uso/valor venal divergente]. Valor lançado: R$ [x]; valor correto estimado: R$ [y]. Anexo [documentos]. Requeiro a revisão do lançamento.”",
    fonte:{lei:"Lei nº 5.172/1966 (CTN)", art:"Arts. 34 e 174", url:"https://www.planalto.gov.br/ccivil_03/leis/l5172compilado.htm"},
    help:["defensoria","juizado"]
  },
  {
    id:"heranca",
    tag:"FAMÍLIA",
    title:"Um familiar faleceu. Como funciona a herança e o inventário?",
    short:"A herança se transmite no momento da morte, mas é o inventário que organiza tudo — e ele tem prazo para começar.",
    lawShort:"Código Civil · arts. 1.784, 1.845–1.846",
    plain:"Com o falecimento, os bens passam automaticamente aos herdeiros — mas para vender, transferir ou sacar é preciso o inventário. Metade dos bens é reservada por lei aos herdeiros necessários (filhos, pais, cônjuge). Havendo consenso entre herdeiros maiores e capazes, e sem testamento, o inventário pode ser feito em cartório.",
    law:{art:"Código Civil · arts. 1.784, 1.845 e 1.846 + CPC · art. 611", txt:"Aberta a sucessão, a herança transmite-se desde logo aos herdeiros. Aos herdeiros necessários pertence, de pleno direito, a metade dos bens (legítima). O inventário deve ser instaurado em até 2 meses."},
    steps:[
      "Reúna: <b>certidão de óbito</b>, documentos dos herdeiros, do casamento e <b>dos bens</b> (matrículas, extratos, veículos).",
      "Todos maiores, capazes e de acordo, sem testamento? <b>Inventário extrajudicial em cartório</b> — mais rápido e barato (precisa de advogado ou defensor).",
      "Há menores, testamento ou conflito? O inventário é <b>judicial</b> — a Defensoria atende quem não pode pagar.",
      "Atenção ao <b>prazo de 2 meses</b> para abrir o inventário: muitos estados cobram multa no ITCMD pelo atraso.",
      "Dívidas do falecido são pagas <b>pelo espólio</b> — os herdeiros não respondem além do que herdarem."
    ],
    deadline:"Abertura do inventário: <b>2 meses</b> do falecimento (CPC, art. 611) — o atraso costuma gerar multa no imposto estadual (ITCMD).",
    template:"“Solicito orientação para inventário dos bens de [nome], falecido(a) em [data]. Herdeiros: [lista e idades]. Testamento: [sim/não]. Bens conhecidos: [imóveis, contas, veículos]. Há consenso entre os herdeiros: [sim/não].”",
    fonte:{lei:"Lei nº 10.406/2002 (Código Civil)", art:"Arts. 1.784, 1.845 e 1.846", url:"https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm"},
    help:["defensoria"]
  }
];

const HELP = {
  defensoria:{nm:"Defensoria Pública",tp:"Orienta e representa quem não pode pagar advogado. Atende família, moradia, consumidor e mais.",free:"GRATUITO"},
  procon:{nm:"Procon",tp:"Órgão de defesa do consumidor da sua cidade/estado. Media conflitos com empresas.",free:"GRATUITO"},
  consumidorgov:{nm:"consumidor.gov.br",tp:"Plataforma oficial para reclamar de empresas cadastradas. Resposta em até 10 dias.",free:"GRATUITO"},
  juizado:{nm:"Juizado Especial Cível",tp:"As “pequenas causas”: até 40 salários mínimos. Até 20, você pode entrar sem advogado; acima disso, o advogado é obrigatório (Lei 9.099/95).",free:"GRATUITO ATÉ CERTO VALOR"},
  sindicato:{nm:"Sindicato da categoria",tp:"Orienta sobre direitos trabalhistas e pode ajudar na homologação e em ações.",free:"GRATUITO P/ FILIADOS"},
  justicatrabalho:{nm:"Justiça do Trabalho",tp:"Onde correm as ações trabalhistas. A Defensoria e advogados trabalhistas atuam nela.",free:"—"},
  ans:{nm:"ANS — 0800 701 9656",tp:"Agência que regula os planos de saúde. A reclamação (NIP) costuma destravar negativas em poucos dias.",free:"GRATUITO"},
  meuinss:{nm:"Meu INSS / Central 135",tp:"App, site e telefone oficiais do INSS: pedidos, recursos, extratos (CNIS) e agendamentos.",free:"GRATUITO"},
  bcb:{nm:"Banco Central",tp:"Canal oficial de reclamação contra bancos e instituições de pagamento (bcb.gov.br).",free:"GRATUITO"}
};

const CODES = [
  {cat:"No seu dia a dia", items:[
    {name:"Código Civil", num:"Lei 10.406 · 2002", status:"vig", desc:"O código das relações entre pessoas: contratos, propriedade, casamento, herança e indenizações."},
    {name:"Código de Defesa do Consumidor", num:"Lei 8.078 · 1990", status:"vig", desc:"Seus direitos ao comprar e contratar: garantia, troca, cobrança, publicidade."},
    {name:"Consolidação das Leis do Trabalho", num:"DL 5.452 · 1943", status:"vig", desc:"Direitos de quem trabalha com carteira assinada: jornada, férias, rescisão, FGTS."},
    {name:"Código de Trânsito Brasileiro", num:"Lei 9.503 · 1997", status:"vig", desc:"Regras de trânsito, infrações, CNH e como recorrer de multas."},
    {name:"Código Penal", num:"DL 2.848 · 1940", status:"vig", desc:"Define o que é crime e qual a pena. Base do Direito Penal brasileiro."},
    {name:"Código Tributário Nacional", num:"Lei 5.172 · 1966", status:"vig", desc:"Regras gerais dos impostos e taxas: como se cobra, prazos e prescrição."}
  ]},
  {cat:"Como corre na Justiça", items:[
    {name:"Código de Processo Civil", num:"Lei 13.105 · 2015", status:"vig", desc:"O CPC atual. Define como anda um processo civil: prazos, provas, recursos, execução."},
    {name:"Código de Processo Penal", num:"DL 3.689 · 1941", status:"vig", desc:"Como funcionam a investigação e o processo criminal, e os direitos do acusado."},
    {name:"Código de Processo Civil (1973)", num:"Lei 5.869 · 1973", status:"rev", desc:"Revogado. Foi substituído pelo CPC de 2015 — hoje só tem valor histórico."}
  ]},
  {cat:"Áreas específicas", items:[
    {name:"Código Eleitoral", num:"Lei 4.737 · 1965", status:"vig", desc:"Regras das eleições, alistamento, voto e crimes eleitorais (muito alterado desde então)."},
    {name:"Código Florestal", num:"Lei 12.651 · 2012", status:"vig", desc:"Proteção da vegetação: áreas de preservação (APP), reserva legal, uso do solo rural."},
    {name:"Código de Mineração", num:"DL 227 · 1967", status:"vig", desc:"Regras para pesquisar e explorar recursos minerais no país."},
    {name:"Código Brasileiro de Aeronáutica", num:"Lei 7.565 · 1986", status:"vig", desc:"Aviação civil e base dos direitos do passageiro aéreo (junto com as resoluções da ANAC)."},
    {name:"Código de Águas", num:"Decreto 24.643 · 1934", status:"par", desc:"Parcialmente em vigor. Uso e aproveitamento dos recursos hídricos."},
    {name:"Código Brasileiro de Telecomunicações", num:"Lei 4.117 · 1962", status:"par", desc:"Parcialmente em vigor. Muito substituído pela Lei Geral de Telecomunicações (1997)."},
    {name:"Código Comercial", num:"Lei 556 · 1850", status:"par", desc:"Só a parte de comércio marítimo continua valendo; o resto foi absorvido pelo Código Civil de 2002."}
  ]},
  {cat:"Justiça Militar", items:[
    {name:"Código Penal Militar", num:"DL 1.001 · 1969", status:"vig", desc:"Define os crimes militares e suas penas."},
    {name:"Código de Processo Penal Militar", num:"DL 1.002 · 1969", status:"vig", desc:"Como corre o processo penal na Justiça Militar."}
  ]}
];

const GLOSSARY = [
  {t:"Petição inicial", d:"O documento que abre um processo. É onde você conta o problema e diz o que quer da Justiça."},
  {t:"Autor e réu", d:"O autor é quem entra com a ação; o réu é quem é processado. Em muitos casos, o mesmo cidadão pode ser um ou outro."},
  {t:"Prescrição", d:"O prazo depois do qual não dá mais para cobrar uma dívida ou processar alguém. Passou o prazo, perdeu-se o direito de exigir na Justiça."},
  {t:"Verbas rescisórias", d:"O conjunto de valores que a empresa paga quando o contrato de trabalho termina (aviso, férias, 13º, saldo…)."},
  {t:"Vício do produto", d:"Um defeito que faz o produto funcionar mal ou não servir para o que deveria. É o que aciona a garantia legal."},
  {t:"Liminar", d:"Uma decisão rápida do juiz, no começo do processo, para proteger alguém antes do julgamento final."},
  {t:"Juizado Especial", d:"A Justiça das “pequenas causas”: recebe causas de até 40 salários mínimos. Mais rápida e informal — até 20 salários mínimos, sem precisar de advogado."},
  {t:"Notificação extrajudicial", d:"Um aviso formal, por escrito, enviado antes de ir à Justiça. Serve para provar que você comunicou a outra parte."},
  {t:"Danos morais", d:"Indenização pelo sofrimento, humilhação ou constrangimento causado por alguém — separada do prejuízo em dinheiro."},
  {t:"Trânsito em julgado", d:"O momento em que a decisão não admite mais recurso. Dali em diante, ela é definitiva."},
  {t:"Alimentos (pensão)", d:"O nome técnico da pensão: valor pago para o sustento de filho, ex-cônjuge ou parente que precise."},
  {t:"Herdeiro necessário", d:"Filhos, pais e cônjuge: por lei, metade da herança (a 'legítima') é deles e não pode ser dada a outra pessoa."},
  {t:"Espólio", d:"O conjunto de bens e dívidas deixado por quem faleceu, enquanto o inventário não termina."},
  {t:"Valor venal", d:"O valor que a prefeitura atribui ao seu imóvel para calcular o IPTU — pode ser contestado se estiver errado."},
  {t:"Liquidação / Execução", d:"A fase em que a decisão vira dinheiro: calcula-se o valor (liquidação) e cobra-se de verdade (execução)."}
];
