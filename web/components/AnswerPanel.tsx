"use client";

import type { Resposta } from "@/lib/api";

export default function AnswerPanel({
  carregando,
  resposta,
  erro,
}: {
  carregando: boolean;
  resposta: Resposta | null;
  erro: string | null;
}) {
  if (carregando) {
    return (
      <div className="ai-panel" role="status">
        <div className="ai-k">
          <span className="pulse" /> Consultando a base jurídica…
        </div>
      </div>
    );
  }
  if (erro) {
    return (
      <div className="ai-panel">
        <div className="ai-k">⚠ Não consegui responder</div>
        <div className="ai-answer">{erro}</div>
      </div>
    );
  }
  if (!resposta) return null;

  return (
    <div className="ai-panel">
      <div className="ai-k">
        ⚖ Resposta da base jurídica {resposta.gerado_por_llm ? "· gerada por IA" : "· modo extrativo"}
      </div>
      <div className="ai-answer">{resposta.resposta}</div>
      {resposta.artigos.length > 0 && (
        <div className="ai-arts">
          {resposta.artigos.map((a) => (
            <div className="ai-art" key={a.id}>
              <div className="art">
                § {a.lei} · {a.artigo}
              </div>
              <div className="txt">{a.resumo}</div>
              <a href={a.fonte} target="_blank" rel="noopener noreferrer">
                fonte oficial ↗
              </a>
            </div>
          ))}
        </div>
      )}
      <div className="ai-aviso">{resposta.aviso}</div>
    </div>
  );
}
