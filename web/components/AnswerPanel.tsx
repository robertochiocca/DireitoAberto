"use client";

import FeedbackDispositivo from "@/components/FeedbackDispositivo";
import { rotuloVigencia, type Artigo, type Resposta, type Validacao } from "@/lib/api";

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

/** Texto oficial transcrito da fonte, separado da explicação — ou o aviso de que não foi conferido. */
function TextoOficial({ artigo: a }: { artigo: Artigo }) {
  const trechos = a.trechos_oficiais ?? [];
  if (trechos.length === 0) {
    return (
      <div className="texto-oficial ausente">
        Texto oficial não conferido nesta base{a.lacunas?.length ? ` (${a.lacunas[0]})` : ""}. Confira na
        fonte oficial antes de citar.
      </div>
    );
  }
  const coletado = new Date(trechos[0].coletado_em).toLocaleDateString("pt-BR");
  return (
    <details className="texto-oficial">
      <summary>
        Texto oficial — {trechos.map((t) => t.dispositivo).join("; ")}{" "}
        <span className="meta">(transcrição do texto consolidado, coletado em {coletado})</span>
      </summary>
      {trechos.map((t) => (
        <blockquote key={t.dispositivo} cite={t.fonte}>
          {t.contexto && <p className="contexto">{t.contexto} […]</p>}
          <p>{t.texto}</p>
          {/* Não é <footer>: o estilo do rodapé do site vazaria para dentro da citação. */}
          <p className="origem">
            {t.dispositivo} · página oficial do Planalto, versão {t.versao_fonte.slice(0, 8)} · texto
            atualizado pela Casa Civil, não substitui o publicado no Diário Oficial
          </p>
        </blockquote>
      ))}
      {a.texto_natureza && a.texto_natureza !== "consolidado" && a.texto_natureza_rotulo && (
        <p className="meta">O texto da base para este dispositivo é: {a.texto_natureza_rotulo}.</p>
      )}
      {a.lacunas && a.lacunas.length > 0 && (
        <ul className="lacunas">
          {a.lacunas.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      )}
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
      {resposta.politica && resposta.politica.modo !== "responder" && (
        <div className={`politica politica-${resposta.politica.modo}`} role="note">
          <b>{resposta.politica.rotulo}.</b>
          {resposta.politica.motivos.length > 0 && (
            <ul>
              {resposta.politica.motivos.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
          <p>{resposta.politica.proximos_passos}</p>
        </div>
      )}
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
                <div className="txt">
                  <span className="rotulo-natureza">Explicação do DireitoAberto:</span> {a.resumo}
                </div>
                {a.vigencia?.nota && <div className="vig-nota">{a.vigencia.nota}</div>}
                {a.revisao?.estado === "pendente" && (
                  <div className="vig-nota">⚠ Em revisão: {a.revisao.motivo}</div>
                )}
                <TextoOficial artigo={a} />
                <a href={a.fonte} target="_blank" rel="noopener noreferrer">
                  fonte oficial ↗
                </a>
                <FeedbackDispositivo dispositivoId={a.id} />
              </div>
            );
          })}
        </div>
      )}
      <div className="ai-aviso">{resposta.aviso}</div>
    </div>
  );
}
