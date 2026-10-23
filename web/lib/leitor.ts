/** Cliente do leitor de processos (/api/v1/documentos). */
import { api } from "@/lib/api";

export type Citacao = {
  pagina: number;
  folha: string | null;
  trecho: string;
  verificada: boolean;
};

export type Natureza =
  | "alegacao"
  | "pedido"
  | "decisao_judicial"
  | "fundamento_judicial"
  | "ato_judicial"
  | "fato_registrado"
  | "documento_de_prova"
  | "ato_processual"
  | "trecho"
  | "interpretacao"
  | "nao_localizado"
  | "orientacao_geral"
  | "inconsistencia";

export type Item = {
  texto: string;
  natureza: Natureza;
  peca?: string | null;
  citacoes: Citacao[];
  // campos específicos de cada lista
  data?: string;
  evento?: string;
  papel?: string;
  nome?: string;
  resultado?: string | null;
  instancia?: string;
  tipo_de_prazo?: string;
  duracao?: string;
  ressalva?: string;
  secao?: string | null;
};

export type Peca = {
  tipo: string;
  rotulo: string;
  origem: string;
  pagina_inicial: number;
  pagina_final: number;
  data: string | null;
  citacoes: Citacao[];
};

export type Analise = {
  documento: {
    nome: string;
    total_paginas: number;
    paginas_lidas: number[];
    paginas_sem_texto: number[];
    paginas_com_falha: number[];
    paginas_nao_processadas: number[];
    leitura_completa: boolean;
    folhas: Record<string, string>;
  };
  avisos: string[];
  numeros_processo: {
    numero: string;
    digito_verificador_valido: boolean;
    segmento: string | null;
    tribunal: string | null;
    citacoes: Citacao[];
  }[];
  identificacao: Record<string, { rotulo: string; valor: string; citacoes: Citacao[] }>;
  partes: Item[];
  pecas: Peca[];
  linha_do_tempo: Item[];
  alegacoes: Item[];
  pedidos: Item[];
  decisoes: Item[];
  obrigacoes_e_determinacoes: Item[];
  prazos: Item[];
  recursos: Item[];
  transito_em_julgado: Item[];
  folhas_citadas_nao_enviadas: { folha: string; citacoes: Citacao[] }[];
  glossario: { termo: string; explicacao: string; paginas: number[] }[];
  naturezas: Record<Natureza, string>;
  pendencias: Item[];
  resumo: Item[];
  proximos_passos: Item[];
  perguntas_para_advogado: string[];
  // Rodada 9.0 (backend/app/leitor/analise.py). A página mostra o mesmo conteúdo pelo resumo, avisos e
  // pendências; os campos ficam tipados para quem usar a API direto.
  decisao_principal?: { incerta?: boolean; [campo: string]: unknown } | null;
  decisoes_nao_usadas?: Item[];
  inconsistencias?: Item[];
  transito_nao_confirmado?: Item[];
  contagens?: Record<string, number>;
};

export type PaginaDoc = { numero: number; folha: string | null; estado: string; texto: string };

export type DocumentoLido = {
  id: string;
  nome: string;
  total_paginas: number;
  ficticio?: boolean;
  criado_em?: string;
  expira_em?: string;
  paginas: PaginaDoc[];
  analise: Analise;
};

export type DocumentoGuardado = {
  id: string;
  nome: string;
  total_paginas: number;
  criado_em: string;
  expira_em: string;
};

export type RespostaLeitor = {
  pergunta: string;
  intencao: string;
  resposta: string;
  itens: Item[];
  abstencao: boolean;
  avisos: string[];
  aviso_geral: string;
  glossario?: { termo: string; explicacao: string }[];
  perguntas?: string[];
};

export const obterExemplo = () => api<DocumentoLido>("/documentos/exemplo");

export const listarDocumentos = () => api<DocumentoGuardado[]>("/documentos");

export const obterDocumento = (id: string) => api<DocumentoLido>(`/documentos/${encodeURIComponent(id)}`);

export const apagarDocumento = (id: string) =>
  api<void>(`/documentos/${encodeURIComponent(id)}`, { method: "DELETE" });

export function enviarDocumento(arquivo: File) {
  const corpo = new FormData();
  corpo.append("arquivo", arquivo);
  return api<DocumentoLido>("/documentos", { method: "POST", body: corpo });
}

export function perguntarAoDocumento(id: string, pergunta: string) {
  const rota = id === "exemplo" ? "/documentos/exemplo/perguntar" : `/documentos/${encodeURIComponent(id)}/perguntar`;
  return api<RespostaLeitor>(rota, { method: "POST", body: JSON.stringify({ pergunta }) });
}

/** Rótulo curto da natureza, para o selo ao lado de cada item. */
export const ROTULO_NATUREZA: Record<Natureza, string> = {
  alegacao: "alegação de parte",
  pedido: "pedido",
  decisao_judicial: "decisão judicial",
  fundamento_judicial: "fundamentação",
  ato_judicial: "ato do juiz",
  fato_registrado: "fato registrado",
  documento_de_prova: "prova",
  ato_processual: "peça do processo",
  trecho: "trecho",
  interpretacao: "interpretação",
  nao_localizado: "não localizado",
  orientacao_geral: "orientação geral",
  inconsistencia: "inconsistência",
};

export function dataBr(iso?: string | null) {
  if (!iso) return "";
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${ano}`;
}
