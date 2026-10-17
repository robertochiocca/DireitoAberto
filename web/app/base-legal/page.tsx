"use client";

import { useEffect, useState } from "react";
import {
  estatisticas,
  filaDeVigencia,
  listarArtigos,
  rotuloVigencia,
  type Artigo,
  type ItemFilaVigencia,
} from "@/lib/api";

const TRIBUNAIS = ["STF", "STJ", "TST"];
const SITUACOES = [
  { valor: "", rotulo: "Qualquer situação" },
  { valor: "vigente", rotulo: "Em vigor hoje" },
  { valor: "em_vacatio", rotulo: "Ainda não em vigor" },
  { valor: "revogada", rotulo: "Revogado" },
  { valor: "inconstitucional", rotulo: "Inconstitucional" },
];

export default function BaseLegalPage() {
  const [artigos, setArtigos] = useState<Artigo[] | null>(null);
  const [temas, setTemas] = useState<string[]>([]);
  const [tema, setTema] = useState("");
  const [tribunal, setTribunal] = useState("");
  const [status, setStatus] = useState("");
  const [busca, setBusca] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [fila, setFila] = useState<ItemFilaVigencia[]>([]);

  useEffect(() => {
    estatisticas()
      .then((e) => setTemas(e.temas))
      .catch(() => {});
    filaDeVigencia(540)
      .then((f) => setFila(f.entram_em_vigor))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      listarArtigos({ tema, tribunal, status, busca })
        .then((r) => {
          setArtigos(r.artigos);
          setErro(null);
        })
        .catch(() => setErro("A API não respondeu. Backend está rodando?"));
    }, 250); // debounce da busca digitada
    return () => clearTimeout(timer);
  }, [tema, tribunal, status, busca]);

  return (
    <div className="page wrap">
      <div className="sec-head">
        <h2>Base legal indexada</h2>
        <span className="lbl">{artigos ? `${artigos.length} dispositivo(s)` : "carregando…"}</span>
      </div>

      {fila.length > 0 && (
        <div className="vig-fila">
          <h3>⚠ Mudanças já publicadas que ainda vão entrar em vigor</h3>
          <p>
            Estas regras foram aprovadas, mas só passam a valer nas datas abaixo. Até lá,
            continua valendo a regra anterior.
          </p>
          <ul>
            {fila.map((i) => (
              <li key={i.id}>
                <span className="quando">
                  {new Date(`${i.entra_em_vigor_em}T00:00:00`).toLocaleDateString("pt-BR")} (em{" "}
                  {i.dias_restantes} dias)
                </span>{" "}
                — {i.lei}: {i.resumo}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="filtros">
        <select value={tema} onChange={(e) => setTema(e.target.value)} aria-label="Filtrar por área">
          <option value="">Todas as áreas</option>
          {temas.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select
          value={tribunal}
          onChange={(e) => setTribunal(e.target.value)}
          aria-label="Filtrar jurisprudência por tribunal"
        >
          <option value="">Leis + jurisprudência</option>
          {TRIBUNAIS.map((t) => (
            <option key={t} value={t}>
              Jurisprudência {t}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label="Filtrar por situação de vigência"
        >
          {SITUACOES.map((s) => (
            <option key={s.valor} value={s.valor}>
              {s.rotulo}
            </option>
          ))}
        </select>
        <input
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar por lei ou artigo (ex.: 8.078, art. 18)"
          aria-label="Buscar por lei ou artigo"
          style={{ flex: 1, minWidth: 220 }}
        />
      </div>

      {erro && <div className="erro">{erro}</div>}
      {artigos && artigos.length === 0 && <p className="empty">Nenhum dispositivo com esses filtros.</p>}

      {artigos?.map((a) => (
        <div className="item" key={a.id}>
          <div className="titulo">
            {a.lei} — {a.artigo}
          </div>
          <div className="meta">
            <span className="badge warn">{a.tema}</span>
            {a.tipo === "jurisprudencia" && <span className="badge right">{a.tribunal}</span>}
            {(() => {
              const vig = rotuloVigencia(a.vigencia);
              return vig ? <span className={`vig vig-${vig.tom}`}>⚠ {vig.texto}</span> : null;
            })()}
          </div>
          <div className="resumo">{a.resumo}</div>
          {a.vigencia?.nota && <div className="vig-nota">{a.vigencia.nota}</div>}
          <div style={{ marginTop: 8 }}>
            <a
              href={a.fonte}
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontSize: 13, fontWeight: 600, color: "var(--brand-ink)" }}
            >
              fonte oficial ↗
            </a>
          </div>
        </div>
      ))}
    </div>
  );
}
