/** Cliente da API do DireitoAberto (/api/v1, proxiada pelo Next via rewrites). */

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

export const listarArtigos = (filtros: { tema?: string; tribunal?: string; busca?: string }) => {
  const params = new URLSearchParams();
  if (filtros.tema) params.set("tema", filtros.tema);
  if (filtros.tribunal) params.set("tribunal", filtros.tribunal);
  if (filtros.busca) params.set("busca", filtros.busca);
  const qs = params.toString();
  return api<{ total: number; artigos: Artigo[] }>(`/artigos${qs ? `?${qs}` : ""}`);
};

export const estatisticas = () => api<Estatisticas>("/estatisticas");
