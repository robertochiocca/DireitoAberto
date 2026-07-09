"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getToken, historico, type ConsultaHistorico } from "@/lib/api";

export default function HistoricoPage() {
  const [consultas, setConsultas] = useState<ConsultaHistorico[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [semSessao, setSemSessao] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      setSemSessao(true);
      return;
    }
    historico()
      .then(setConsultas)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) setSemSessao(true);
        else setErro(e instanceof ApiError ? e.message : "A API não respondeu.");
      });
  }, []);

  if (semSessao) {
    return (
      <div className="page wrap">
        <div className="card card-auth" style={{ textAlign: "center" }}>
          <p style={{ marginBottom: 16 }}>
            O histórico guarda as consultas feitas com a sua conta.
          </p>
          <Link href="/login" className="btn" style={{ display: "inline-block" }}>
            Entrar para ver o histórico
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="page wrap">
      <div className="sec-head">
        <h2>Suas consultas</h2>
        <span className="lbl">{consultas ? `${consultas.length} registro(s)` : "carregando…"}</span>
      </div>

      {erro && <div className="erro">{erro}</div>}

      {consultas && consultas.length === 0 && (
        <p className="empty">
          Nada por aqui ainda — faça uma pergunta na <Link href="/" style={{ color: "var(--brand-ink)" }}>página inicial</Link> estando logado.
        </p>
      )}

      {consultas?.map((c) => (
        <div className="item" key={c.id}>
          <div className="titulo">{c.pergunta}</div>
          <div className="meta">
            <span>{new Date(c.criado_em).toLocaleString("pt-BR")}</span>
            {c.tema && <span className="badge warn">{c.tema}</span>}
            <span className={`badge ${c.gerado_por_llm ? "brand" : "right"}`}>
              {c.gerado_por_llm ? "IA" : "extrativo"}
            </span>
            {c.artigos_ids.map((id) => (
              <span key={id} className="badge brand">
                {id}
              </span>
            ))}
          </div>
          <div style={{ marginTop: 10 }}>
            <Link
              className="chip"
              href={`/?q=${encodeURIComponent(c.pergunta)}`}
              style={{ display: "inline-block" }}
            >
              ↻ perguntar de novo
            </Link>
          </div>
        </div>
      ))}
    </div>
  );
}
