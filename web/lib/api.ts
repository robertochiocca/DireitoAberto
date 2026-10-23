/** Cliente da API do DireitoAberto (/api/v1, proxiada pelo Next via rewrites). */

export type Vigencia = {
  /** nao_verificada: sem conferência registrada — nunca tratar como em vigor. */
  status: "vigente" | "em_vacatio" | "revogada" | "redacao_anterior" | "inconstitucional" | "nao_verificada";
  vigente_ate?: string | null;
  entra_em_vigor_em: string | null;
  alterada_por: string[];
  nota: string | null;
  conferida_em: string | null;
  /** Presente quando a data de início chegou mas o registro na base ainda não foi revisado. */
  status_registrado?: string | null;
  vigente_desde?: string | null;
};

/** Pendência de revisão: a informação sobre o dispositivo está sendo conferida. */
export type Revisao = {
  estado: "pendente";
  motivo: string;
  evidencia: string[];
  aberta_em: string | null;
};

/** Transcrição de um dispositivo da página oficial (texto consolidado), com proveniência. */
export type TrechoOficial = {
  dispositivo: string;
  tipo: "consolidado" | "literal";
  texto: string;
  contexto?: string | null;
  fonte: string;
  versao_fonte: string;
  coletado_em: string;
  hash_sha256: string;
  alertas?: string[];
};

/** O que é o texto curado da base: só "consolidado" e "literal" são transcrição. */
export type NaturezaTexto =
  | "consolidado"
  | "literal"
  | "resumo_explicativo"
  | "interpretacao_juridica"
  | "nao_conferido";

export type Artigo = {
  id: string;
  lei: string;
  artigo: string;
  tema: string;
  texto?: string;
  texto_natureza?: NaturezaTexto;
  texto_natureza_rotulo?: string;
  trechos_oficiais?: TrechoOficial[];
  lacunas?: string[];
  resumo: string;
  fonte: string;
  score?: number;
  tipo?: string;
  tribunal?: string | null;
  vigencia?: Vigencia;
  revisao?: Revisao | null;
};

export type ItemFilaVigencia = {
  id: string;
  lei: string;
  artigo: string;
  tema: string;
  resumo: string;
  entra_em_vigor_em: string;
  dias_restantes: number;
  nota: string | null;
  fonte: string;
};

export type Validacao = {
  estado:
    | "fonte_e_versao_verificadas"
    | "evidencia_suficiente"
    | "fonte_localizada"
    | "revisao_humana_recomendada"
    | "conflito_de_fontes"
    | "fonte_desatualizada_ou_indisponivel"
    | "evidencia_insuficiente";
  rotulo: string;
  verificacoes: { nome: string; ok: boolean | null; detalhe: string }[];
  aviso: string;
};

/** O que a API fez com a evidência que tem (backend/app/politica.py). */
export type Politica = {
  modo:
    | "responder"
    | "responder_com_ressalvas"
    | "pedir_esclarecimento"
    | "nao_verificado"
    | "recomendar_profissional";
  rotulo: string;
  motivos: string[];
  proximos_passos: string;
};

/** Data a que a resposta se refere e o que a base sabe sobre ela (backend/app/temporal.py). */
export type Temporal = {
  intencao: "atual" | "historica" | "mudanca" | "revogacao" | "fundamento";
  data_referencia: string;
  data_explicita: boolean;
  so_ano: boolean;
  expressao: string | null;
  pede_esclarecimento: boolean;
  motivo: string | null;
  avisos: string[];
};

export type Resposta = {
  resposta: string;
  artigos: Artigo[];
  gerado_por_llm: boolean;
  validacao: Validacao;
  temporal?: Temporal | null;
  politica?: Politica | null;
  /** Problemas do texto gerado por IA; quando há algum, a resposta mostrada é a extrativa. */
  verificacao_do_texto?: { tipo: string; detalhe: string }[];
  aviso: string;
};

export type ConsultaHistorico = {
  id: number;
  pergunta: string;
  tema: string | null;
  artigos_ids: string[];
  gerado_por_llm: boolean;
  criado_em: string;
};

export type Estatisticas = {
  leis_indexadas: number;
  artigos_indexados: number;
  jurisprudencias_indexadas: number;
  temas: string[];
  consultas_realizadas: number;
  base_atualizada_em: string | null;
  dispositivos_em_revisao: number;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

const TOKEN_KEY = "da_token";
const EMAIL_KEY = "da_email";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getEmail(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(EMAIL_KEY);
}

export function salvarSessao(token: string, email: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(EMAIL_KEY, email);
  window.dispatchEvent(new Event("da-auth"));
}

/** Revoga o token no servidor e apaga a sessão local (mesmo se a API não responder). */
export async function encerrarSessao() {
  const token = getToken();
  if (token) {
    await fetch("/api/v1/auth/sair", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {
      /* sem rede: o token expira sozinho no servidor */
    });
  }
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
  window.dispatchEvent(new Event("da-auth"));
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  // Só JSON leva Content-Type explícito; FormData (upload) define o próprio, com o boundary.
  if (!headers.has("Content-Type") && typeof init.body === "string")
    headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetch(`/api/v1${path}`, { ...init, headers });
  if (!resp.ok) {
    let detail = `Erro ${resp.status}`;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(resp.status, detail);
  }
  return resp.status === 204 ? (undefined as T) : resp.json();
}

export const perguntar = (pergunta: string, tema?: string | null) =>
  api<Resposta>("/perguntar", {
    method: "POST",
    body: JSON.stringify({ pergunta, tema: tema || null }),
  });

export const entrar = (email: string, senha: string) =>
  api<{ token: string }>("/auth/entrar", {
    method: "POST",
    body: JSON.stringify({ email, senha }),
  });

export const registrar = (email: string, senha: string) =>
  api<{ token: string }>("/auth/registrar", {
    method: "POST",
    body: JSON.stringify({ email, senha }),
  });

export const historico = (limite = 20, deslocamento = 0) =>
  api<ConsultaHistorico[]>(`/historico?limite=${limite}&deslocamento=${deslocamento}`);

export const saude = () => api<{ status: string; artigos_no_corpus: number; llm_ativo: boolean }>("/saude");

/** Baixa tudo o que a base guarda sobre a conta (LGPD, art. 18) como arquivo JSON. */
export async function exportarDados() {
  const resp = await fetch("/api/v1/conta/exportar", { headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
  if (!resp.ok) throw new ApiError(resp.status, `Erro ${resp.status}`);
  const url = URL.createObjectURL(await resp.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: "direitoaberto-meus-dados.json" });
  a.click();
  URL.revokeObjectURL(url);
}

export const trocarSenha = (senhaAtual: string, senhaNova: string) =>
  api<void>("/conta/senha", {
    method: "POST",
    body: JSON.stringify({ senha_atual: senhaAtual, senha_nova: senhaNova }),
  });

/** Encerra todas as sessões da conta (inclusive esta) e apaga a sessão local. */
export async function sairDeTodas() {
  await api<void>("/auth/sair-de-todas", { method: "POST" });
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
  window.dispatchEvent(new Event("da-auth"));
}

/** Apaga a conta, o histórico e os documentos (pede a senha de novo). */
export async function excluirConta(senha: string) {
  await api<void>("/conta/excluir", { method: "POST", body: JSON.stringify({ senha }) });
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
  window.dispatchEvent(new Event("da-auth"));
}

export const apagarHistorico = () => api<void>("/historico", { method: "DELETE" });

/** Categorias de feedback (as mesmas de backend/app/feedback.py). */
export const CATEGORIAS_FEEDBACK = {
  texto_nao_confere: "O texto mostrado não confere com a lei",
  norma_revogada_ou_alterada: "A norma foi revogada ou alterada",
  dispositivo_nao_se_aplica: "O dispositivo não tem a ver com a pergunta",
  explicacao_confusa: "A explicação está confusa, incompleta ou errada",
  outro: "Outro problema",
} as const;
export type CategoriaFeedback = keyof typeof CATEGORIAS_FEEDBACK;

/** Aponta um problema num dispositivo. Vai para triagem humana; não muda a base sozinho. */
export const enviarFeedback = (dispositivoId: string, categoria: CategoriaFeedback, comentario: string) =>
  api<{ id: number; estado: string; aviso: string }>("/feedback", {
    method: "POST",
    body: JSON.stringify({ dispositivo_id: dispositivoId, categoria, comentario: comentario.trim() || null }),
  });

export const listarArtigos = (filtros: {
  tema?: string;
  tribunal?: string;
  status?: string;
  busca?: string;
}) => {
  const params = new URLSearchParams();
  if (filtros.tema) params.set("tema", filtros.tema);
  if (filtros.tribunal) params.set("tribunal", filtros.tribunal);
  if (filtros.status) params.set("status", filtros.status);
  if (filtros.busca) params.set("busca", filtros.busca);
  const qs = params.toString();
  return api<{ total: number; artigos: Artigo[] }>(`/artigos${qs ? `?${qs}` : ""}`);
};

export const filaDeVigencia = (dias = 180) =>
  api<{
    hoje: string;
    janela_dias: number;
    entram_em_vigor: ItemFilaVigencia[];
    marcadas_como_futuras_mas_ja_vigentes: ItemFilaVigencia[];
  }>(`/vigencia?dias=${dias}`);

/** Rótulo curto da situação do dispositivo, para exibir ao lado do artigo. */
export function rotuloVigencia(v?: Vigencia): { texto: string; tom: string } | null {
  if (v?.status === "vigente" && v.status_registrado === "em_vacatio" && v.vigente_desde) {
    const desde = new Date(`${v.vigente_desde}T00:00:00`).toLocaleDateString("pt-BR");
    return { texto: `em vigor desde ${desde}`, tom: "vacatio" };
  }
  if (!v || v.status === "nao_verificada")
    return { texto: "situação de vigência não verificada", tom: "revogada" };
  if (v.status === "vigente") return null;
  if (v.status === "revogada") return { texto: "revogado", tom: "revogada" };
  if (v.status === "redacao_anterior") return { texto: "redação anterior — não vale hoje", tom: "revogada" };
  if (v.status === "inconstitucional")
    return { texto: "declarado inconstitucional", tom: "revogada" };
  const data = v.entra_em_vigor_em
    ? new Date(`${v.entra_em_vigor_em}T00:00:00`).toLocaleDateString("pt-BR")
    : null;
  return { texto: data ? `em vigor a partir de ${data}` : "ainda não está em vigor", tom: "vacatio" };
}

export const estatisticas = () => api<Estatisticas>("/estatisticas");
