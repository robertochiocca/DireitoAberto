/** Cliente da API do DireitoAberto (/api/v1, proxiada pelo Next via rewrites). */

export type Vigencia = {
  status: "vigente" | "em_vacatio" | "revogada" | "inconstitucional";
  entra_em_vigor_em: string | null;
  alterada_por: string[];
  nota: string | null;
  conferida_em: string | null;
};

export type Artigo = {
  id: string;
  lei: string;
  artigo: string;
  tema: string;
  texto?: string;
  resumo: string;
  fonte: string;
  score?: number;
  tipo?: string;
  tribunal?: string | null;
  vigencia?: Vigencia;
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

export type Resposta = {
  resposta: string;
  artigos: Artigo[];
  gerado_por_llm: boolean;
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
  base_atualizada_em: string;
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

export function encerrarSessao() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
  window.dispatchEvent(new Event("da-auth"));
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");
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
  return resp.json();
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

export const historico = () => api<ConsultaHistorico[]>("/historico");

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
  if (!v || v.status === "vigente") return null;
  if (v.status === "revogada") return { texto: "revogado", tom: "revogada" };
  if (v.status === "inconstitucional")
    return { texto: "declarado inconstitucional", tom: "revogada" };
  const data = v.entra_em_vigor_em
    ? new Date(`${v.entra_em_vigor_em}T00:00:00`).toLocaleDateString("pt-BR")
    : null;
  return { texto: data ? `em vigor a partir de ${data}` : "ainda não está em vigor", tom: "vacatio" };
}

export const estatisticas = () => api<Estatisticas>("/estatisticas");
