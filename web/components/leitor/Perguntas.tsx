"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api";
import { perguntarAoDocumento, type Citacao, type RespostaLeitor } from "@/lib/leitor";
import { ListaItens, type AoCitar } from "./Itens";

const SUGESTOES = [
  "O que aconteceu neste processo?",
  "O juiz já tomou alguma decisão?",
  "O que a outra parte está alegando?",
  "Quais são as obrigações mencionadas?",
  "Explique esta decisão como se eu não entendesse Direito.",
  "Tem prazo para recorrer?",
  "Quais informações ainda preciso confirmar?",
];

export default function Perguntas({
  documentoId,
  aoCitar,
  ativa,
  descricoes,
}: {
  documentoId: string;
  aoCitar: AoCitar;
  ativa: Citacao | null;
  descricoes: Record<string, string>;
}) {
  const [pergunta, setPergunta] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [resposta, setResposta] = useState<RespostaLeitor | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar(texto: string) {
    const q = texto.trim();
    if (q.length < 3) return;
    setPergunta(q);
    setCarregando(true);
    setErro(null);
    try {
      setResposta(await perguntarAoDocumento(documentoId, q));
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "A API não respondeu.");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <div>
      <form
        className="ask"
        style={{ marginTop: 0 }}
        onSubmit={(e) => {
          e.preventDefault();
          void enviar(pergunta);
        }}
      >
        <input
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
          placeholder="Pergunte sobre este documento"
          aria-label="Pergunta sobre o documento"
          maxLength={500}
        />
        <button className="btn" disabled={carregando}>
          {carregando ? "Lendo…" : "Perguntar"}
        </button>
      </form>
      <div className="chips">
        {SUGESTOES.map((s) => (
          <button key={s} className="chip" onClick={() => void enviar(s)}>
            {s}
          </button>
        ))}
      </div>

      {erro && <div className="erro" style={{ marginTop: 14 }}>{erro}</div>}
      {resposta && (
        <div className={`ai-panel resposta-doc ${resposta.abstencao ? "abstencao" : ""}`} role="status">
          <div className="ai-k">
            {resposta.abstencao ? "⚠ Não encontrado no documento" : "⚖ Resposta com trechos do documento"}
          </div>
          <div className="ai-answer">{resposta.resposta}</div>
          {resposta.avisos.length > 0 && (
            <ul className="vig-nota" style={{ listStyle: "none" }}>
              {resposta.avisos.map((a) => (
                <li key={a}>⚠ {a}</li>
              ))}
            </ul>
          )}
          {resposta.itens.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <ListaItens itens={resposta.itens} aoCitar={aoCitar} ativa={ativa} descricoes={descricoes} mostrarData={false} />
            </div>
          )}
          {resposta.glossario && resposta.glossario.length > 0 && (
            <>
              <div className="secao-k" style={{ marginTop: 16 }}>Termos usados na decisão</div>
              {resposta.glossario.map((g) => (
                <p key={g.termo} className="li-extra">
                  <b>{g.termo}:</b> {g.explicacao}
                </p>
              ))}
            </>
          )}
          {resposta.perguntas && resposta.perguntas.length > 0 && (
            <>
              <div className="secao-k" style={{ marginTop: 16 }}>Leve estas perguntas à Defensoria ou a um advogado</div>
              <ol className="perguntas-adv">
                {resposta.perguntas.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ol>
            </>
          )}
          <div className="ai-aviso">{resposta.aviso_geral}</div>
        </div>
      )}
    </div>
  );
}
