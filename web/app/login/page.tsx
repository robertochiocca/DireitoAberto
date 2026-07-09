"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, entrar, registrar, salvarSessao } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [modo, setModo] = useState<"entrar" | "registrar">("entrar");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function submeter(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      const { token } =
        modo === "entrar" ? await entrar(email, senha) : await registrar(email, senha);
      salvarSessao(token, email);
      router.push("/historico");
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "A API não respondeu. Backend está rodando?");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="page wrap">
      <div className="card card-auth">
        <div className="tabs" role="tablist">
          <button
            role="tab"
            aria-selected={modo === "entrar"}
            className={modo === "entrar" ? "on" : ""}
            onClick={() => setModo("entrar")}
          >
            Entrar
          </button>
          <button
            role="tab"
            aria-selected={modo === "registrar"}
            className={modo === "registrar" ? "on" : ""}
            onClick={() => setModo("registrar")}
          >
            Criar conta
          </button>
        </div>

        {erro && <div className="erro">{erro}</div>}

        <form onSubmit={submeter}>
          <div className="field">
            <label htmlFor="email">E-mail</label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="senha">Senha {modo === "registrar" && "(mínimo 8 caracteres)"}</label>
            <input
              id="senha"
              type="password"
              required
              minLength={8}
              autoComplete={modo === "entrar" ? "current-password" : "new-password"}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
            />
          </div>
          <button className="btn" style={{ width: "100%" }} disabled={enviando}>
            {enviando ? "Aguarde…" : modo === "entrar" ? "Entrar" : "Criar conta"}
          </button>
        </form>

        <p style={{ marginTop: 18, fontSize: 13, color: "var(--ink-2)" }}>
          A conta serve apenas para guardar o seu histórico de consultas. Perguntar não exige
          login.
        </p>
      </div>
    </div>
  );
}
