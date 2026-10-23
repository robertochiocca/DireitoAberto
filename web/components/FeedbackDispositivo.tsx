"use client";

import { useId, useState } from "react";
import { ApiError, CATEGORIAS_FEEDBACK, enviarFeedback, type CategoriaFeedback } from "@/lib/api";

/**
 * "Informar um problema" num dispositivo citado. O feedback vai para triagem humana e não muda a resposta nem a
 * base sozinho (backend/app/feedback.py); o texto pede para não escrever dado pessoal, e o servidor mascara
 * CPF, e-mail, telefone e número de processo de qualquer forma.
 */
export default function FeedbackDispositivo({ dispositivoId }: { dispositivoId: string }) {
  const id = useId();
  const [categoria, setCategoria] = useState<CategoriaFeedback>("texto_nao_confere");
  const [comentario, setComentario] = useState("");
  const [estado, setEstado] = useState<"livre" | "enviando" | "enviado">("livre");
  const [mensagem, setMensagem] = useState<string | null>(null);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setEstado("enviando");
    setMensagem(null);
    try {
      const r = await enviarFeedback(dispositivoId, categoria, comentario);
      setEstado("enviado");
      setMensagem(r.aviso);
    } catch (err) {
      setEstado("livre");
      setMensagem(err instanceof ApiError ? err.message : "A API não respondeu. Tente de novo.");
    }
  }

  return (
    <details className="feedback">
      <summary>Informar um problema neste dispositivo</summary>
      {estado === "enviado" ? null : (
        <form onSubmit={enviar}>
          <div className="field">
            <label htmlFor={`${id}-categoria`}>O que está errado?</label>
            <select id={`${id}-categoria`} value={categoria}
              onChange={(e) => setCategoria(e.target.value as CategoriaFeedback)}>
              {Object.entries(CATEGORIAS_FEEDBACK).map(([valor, rotulo]) => (
                <option key={valor} value={valor}>{rotulo}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${id}-comentario`}>Detalhes (opcional)</label>
            <textarea id={`${id}-comentario`} maxLength={600} rows={3} value={comentario}
              aria-describedby={`${id}-dica`} onChange={(e) => setComentario(e.target.value)} />
            <small id={`${id}-dica`}>
              Não escreva nome, CPF, número de processo ou outro dado pessoal. Uma pessoa vai conferir; o retorno
              não muda a resposta na hora.
            </small>
          </div>
          <button className="chip" type="submit" disabled={estado === "enviando"}>
            {estado === "enviando" ? "Enviando…" : "Enviar"}
          </button>
        </form>
      )}
      <div role="status" aria-live="polite">
        {mensagem && <p className={estado === "enviado" ? "aviso-ok" : "erro"}>{mensagem}</p>}
      </div>
    </details>
  );
}
