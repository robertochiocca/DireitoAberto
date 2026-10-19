"use client";

import { ROTULO_NATUREZA, dataBr, type Citacao, type Item, type Natureza } from "@/lib/leitor";

export type AoCitar = (c: Citacao) => void;

export function Selo({ natureza, descricoes }: { natureza: Natureza; descricoes?: Record<string, string> }) {
  return (
    <span className={`selo selo-${natureza}`} title={descricoes?.[natureza]}>
      {ROTULO_NATUREZA[natureza] ?? natureza}
    </span>
  );
}

/** Botões "p. 9 · fls. 30": levam o visualizador à página e destacam o trecho. */
export function Citacoes({
  citacoes,
  aoCitar,
  ativa,
}: {
  citacoes: Citacao[];
  aoCitar: AoCitar;
  ativa?: Citacao | null;
}) {
  if (!citacoes.length) return null;
  const vistas = new Set<string>();
  // Duas citações na mesma página levariam o mesmo rótulo; o começo do trecho as distingue.
  const porPagina = new Map<number, number>();
  citacoes.forEach((c) => porPagina.set(c.pagina, (porPagina.get(c.pagina) ?? 0) + 1));
  return (
    <div className="cits">
      {citacoes.map((c) => {
        const chave = `${c.pagina}|${c.trecho}`;
        if (vistas.has(chave)) return null;
        vistas.add(chave);
        const pressionada = ativa?.pagina === c.pagina && ativa?.trecho === c.trecho;
        return (
          <button
            key={chave}
            className={`cit ${c.verificada ? "" : "nao-verificada"}`}
            aria-pressed={pressionada}
            aria-label={`Ver o trecho na página ${c.pagina}${c.folha ? `, folha ${c.folha}` : ""}`}
            title={c.verificada ? "Trecho conferido na página" : "Trecho NÃO encontrado na página"}
            onClick={() => aoCitar(c)}
          >
            p. {c.pagina}
            {c.folha ? ` · fls. ${c.folha}` : ""}
            {(porPagina.get(c.pagina) ?? 0) > 1 ? ` · “${c.trecho.slice(0, 18).trim()}…”` : ""}
            {c.verificada ? "" : " ⚠"}
          </button>
        );
      })}
    </div>
  );
}

export function ListaItens({
  itens,
  aoCitar,
  ativa,
  descricoes,
  vazio,
  mostrarData,
}: {
  itens: Item[];
  aoCitar: AoCitar;
  ativa?: Citacao | null;
  descricoes?: Record<string, string>;
  vazio?: string;
  mostrarData?: boolean;
}) {
  if (!itens.length) return <p className="li-extra">{vazio ?? "Nada localizado no documento."}</p>;
  return (
    <div>
      {itens.map((it, i) => (
        <div className="li" key={`${i}-${it.texto.slice(0, 40)}`}>
          <div className="li-topo">
            {mostrarData && it.data && <span className="li-data">{dataBr(it.data)}</span>}
            <Selo natureza={it.natureza} descricoes={descricoes} />
            {it.peca && <span className="peca-k">{it.peca}</span>}
            {it.resultado && <span className="badge brand">{it.resultado}</span>}
            {it.tipo_de_prazo && <span className="badge warn">{it.tipo_de_prazo}</span>}
          </div>
          <div className="li-texto">{mostrarData && it.evento ? it.evento : it.texto}</div>
          {it.secao && <div className="li-extra">Seção: {it.secao}</div>}
          <Citacoes citacoes={it.citacoes} aoCitar={aoCitar} ativa={ativa} />
        </div>
      ))}
    </div>
  );
}
