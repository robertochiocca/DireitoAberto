"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Citacao, PaginaDoc } from "@/lib/leitor";

/** Divide o texto da página em [antes, trecho, depois], tolerando quebras de linha no trecho. */
function destacar(texto: string, trecho?: string): [string, string, string] | null {
  if (!trecho) return null;
  const palavras = trecho.trim().split(/\s+/).map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!palavras.length) return null;
  const m = new RegExp(palavras.join("\\s+")).exec(texto);
  if (!m) return null;
  return [texto.slice(0, m.index), m[0], texto.slice(m.index + m[0].length)];
}

export default function Visualizador({
  paginas,
  pagina,
  citacao,
  aoMudarPagina,
  pdfUrl,
}: {
  paginas: PaginaDoc[];
  pagina: number;
  citacao: Citacao | null;
  aoMudarPagina: (n: number) => void;
  pdfUrl?: string | null;
}) {
  const [verPdf, setVerPdf] = useState(false);
  const atual = paginas[pagina - 1];
  const trecho = citacao && citacao.pagina === pagina ? citacao.trecho : undefined;
  const partes = useMemo(() => (atual ? destacar(atual.texto, trecho) : null), [atual, trecho]);
  const caixa = useRef<HTMLDivElement>(null);
  const marca = useRef<HTMLElement>(null);

  // Centraliza o trecho destacado rolando só a caixa do texto, não a página.
  useEffect(() => {
    const c = caixa.current;
    if (!c) return;
    c.scrollTop = marca.current ? Math.max(0, marca.current.offsetTop - c.clientHeight / 3) : 0;
  }, [pagina, partes]);

  return (
    <section className="viewer" aria-label="Visualizador do documento">
      <div className="viewer-bar">
        <b aria-live="polite">
          Página {pagina} de {paginas.length}
          {atual?.folha ? ` · fls. ${atual.folha}` : ""}
        </b>
        <div className="nav">
          {pdfUrl && (
            <button onClick={() => setVerPdf((v) => !v)} aria-pressed={verPdf}>
              {verPdf ? "Texto extraído" : "PDF original"}
            </button>
          )}
          <button onClick={() => aoMudarPagina(pagina - 1)} disabled={pagina <= 1} aria-label="Página anterior">
            ←
          </button>
          <button
            onClick={() => aoMudarPagina(pagina + 1)}
            disabled={pagina >= paginas.length}
            aria-label="Próxima página"
          >
            →
          </button>
        </div>
      </div>
      {verPdf && pdfUrl ? (
        // O PDF original não aceita destaque; o texto extraído, sim.
        <iframe key={pagina} src={`${pdfUrl}#page=${pagina}`} title={`PDF, página ${pagina}`} />
      ) : !atual || atual.estado !== "lida" ? (
        <div className="viewer-vazio">
          {atual?.estado === "sem_texto"
            ? "Esta página não tem texto legível — provavelmente foi digitalizada como imagem. Ela NÃO foi lida e nada nela entra na análise."
            : "Esta página não foi lida."}
        </div>
      ) : (
        <div className="viewer-texto" tabIndex={0} ref={caixa} style={{ position: "relative" }}>
          {partes ? (
            <>
              {partes[0]}
              <mark ref={marca}>{partes[1]}</mark>
              {partes[2]}
            </>
          ) : (
            atual.texto
          )}
        </div>
      )}
    </section>
  );
}
