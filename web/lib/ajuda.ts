// Canais de ajuda e o caminho de resolução. Mesmo conteúdo do frontend
// estático (frontend/dados.js e a faixa "do problema à solução" da home);
// ao revisar um, revise o outro.

export type Canal = { nome: string; oQueFaz: string; custo: string };

export const CANAIS: Canal[] = [
  {
    nome: "Defensoria Pública",
    oQueFaz:
      "Orienta e representa quem não pode pagar advogado. Atende família, moradia, consumidor e mais.",
    custo: "GRATUITO",
  },
  {
    nome: "Procon",
    oQueFaz: "Órgão de defesa do consumidor da sua cidade/estado. Media conflitos com empresas.",
    custo: "GRATUITO",
  },
  {
    nome: "consumidor.gov.br",
    oQueFaz:
      "Plataforma oficial para reclamar de empresas cadastradas. Resposta em até 10 dias.",
    custo: "GRATUITO",
  },
  {
    nome: "Juizado Especial Cível",
    oQueFaz:
      "As “pequenas causas”: até 40 salários mínimos. Até 20, você pode entrar sem advogado; acima disso, o advogado é obrigatório (Lei 9.099/95).",
    custo: "GRATUITO ATÉ CERTO VALOR",
  },
  {
    nome: "Sindicato da categoria",
    oQueFaz:
      "Orienta sobre direitos trabalhistas e pode ajudar na homologação e em ações.",
    custo: "GRATUITO P/ FILIADOS",
  },
  {
    nome: "Justiça do Trabalho",
    oQueFaz:
      "Onde correm as ações trabalhistas. A Defensoria e advogados trabalhistas atuam nela.",
    custo: "—",
  },
  {
    nome: "ANS — 0800 701 9656",
    oQueFaz:
      "Agência que regula os planos de saúde. A reclamação (NIP) costuma destravar negativas em poucos dias.",
    custo: "GRATUITO",
  },
  {
    nome: "Meu INSS / Central 135",
    oQueFaz:
      "App, site e telefone oficiais do INSS: pedidos, recursos, extratos (CNIS) e agendamentos.",
    custo: "GRATUITO",
  },
  {
    nome: "Banco Central",
    oQueFaz:
      "Canal oficial de reclamação contra bancos e instituições de pagamento (bcb.gov.br).",
    custo: "GRATUITO",
  },
];

export type Degrau = { titulo: string; texto: string; acao: string; href: string };

// Do mais simples e barato ao mais formal. No web não há modelos prontos de
// notificação (eles estão nas situações do frontend estático), então o
// degrau 2 aponta para a base legal: achar o artigo que embasa o pedido.
export const DEGRAUS: Degrau[] = [
  {
    titulo: "Entenda o seu direito",
    texto:
      "Descreva o problema em palavras simples e veja o que a lei garante — e os prazos. Alguns vencem em poucos dias.",
    acao: "Perguntar",
    href: "/",
  },
  {
    titulo: "Tente resolver direto",
    texto:
      "Procure a empresa, o empregador ou o órgão por escrito, citando o artigo de lei. Guarde o protocolo.",
    acao: "Achar o artigo",
    href: "/base-legal",
  },
  {
    titulo: "Reclame no canal oficial",
    texto:
      "Procon, consumidor.gov.br, ANS, Banco Central ou a ouvidoria do órgão. Costuma destravar sem processo.",
    acao: "Ver os canais",
    href: "#canais",
  },
  {
    titulo: "Leve à Justiça, sem pagar",
    texto:
      "Juizado Especial (até 20 salários mínimos, sem advogado) ou Defensoria Pública, para quem não pode pagar.",
    acao: "Defensoria e Juizado",
    href: "#canais",
  },
];
