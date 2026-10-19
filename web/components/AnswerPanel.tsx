"use client";

import { rotuloVigencia, type Resposta, type Validacao } from "@/lib/api";

const TOM_VALIDACAO: Record<Validacao["estado"], string> = {
  fonte_e_versao_verificadas: "brand",
  evidencia_suficiente: "brand",
  fonte_localizada: "warn",
  revisao_humana_recomendada: "warn",
  conflito_de_fontes: "warn",
  fonte_desatualizada_ou_indisponivel: "right",
  evidencia_insuficiente: "right",
};

const NOME_VERIFICACAO: Record<string, string> = {
  forca_da_evidencia: "Força da evidência",
  fonte_oficial: "Fonte oficial",
  texto_conferido: "Texto conferido com a versão oficial",
  vigencia: "Vigência hoje",
  atualidade: "Conferência recente",
  revisao_pendente: "Revisão pendente",
  conflito: "Conflito entre redações",
  citacoes_do_texto_gerado: "Citações do texto gerado",
};

function PainelValidacao({ v }: { v: Validacao }) {
  return (
    <details className="validacao">
      <summary>
        <span className={`badge ${TOM_VALIDACAO[v.estado]}`}>{v.rotulo}</span>
        <span className="validacao-k">como chegamos a isso</span>
      </summary>
      <ul>
        {v.verificacoes.map((c) => (
          <li key={c.nome}>
            <span aria-hidden="true">{c.ok === true ? "✓" : c.ok === false ? "✗" : "–"}</span>{" "}
            <b>{NOME_VERIFICACAO[c.nome] ?? c.nome}:</b> {c.detalhe}
          </li>
        ))}
      </ul>
      <p>{v.aviso}</p>
    </details>
  );
}

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
      {resposta.validacao && <PainelValidacao v={resposta.validacao} />}
      <div className="ai-answer">{resposta.resposta}</div>
      {resposta.artigos.length > 0 && (
        <div className="ai-arts">
          {resposta.artigos.map((a) => {
            const vig = rotuloVigencia(a.vigencia);
            return (
              <div className="ai-art" key={a.id}>
                <div className="art">
                  § {a.lei} · {a.artigo}
                  {vig && <span className={`vig vig-${vig.tom}`}>⚠ {vig.texto}</span>}
                </div>
                <div className="txt">{a.resumo}</div>
                {a.vigencia?.nota && <div className="vig-nota">{a.vigencia.nota}</div>}
                {a.revisao?.estado === "pendente" && (
                  <div className="vig-nota">⚠ Em revisão: {a.revisao.motivo}</div>
                )}
                <a href={a.fonte} target="_blank" rel="noopener noreferrer">
                  fonte oficial ↗
                </a>
              </div>
            );
          })}
        </div>
      )}
      <div className="ai-aviso">{resposta.aviso}</div>
    </div>
  );
}
