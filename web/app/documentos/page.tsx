"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiError, getToken } from "@/lib/api";
import {
  apagarDocumento,
  dataBr,
  enviarDocumento,
  listarDocumentos,
  obterDocumento,
  obterExemplo,
  type Citacao,
  type DocumentoGuardado,
  type DocumentoLido,
} from "@/lib/leitor";
import { Citacoes, ListaItens } from "@/components/leitor/Itens";
import Perguntas from "@/components/leitor/Perguntas";
import Visualizador from "@/components/leitor/Visualizador";

const ABAS = [
  ["resumo", "Resumo"],
  ["tempo", "Linha do tempo"],
  ["partes", "Partes e peças"],
  ["decisoes", "Decisões e prazos"],
  ["perguntar", "Perguntar"],
  ["glossario", "Glossário"],
] as const;
type Aba = (typeof ABAS)[number][0];

const PDF_EXEMPLO = "/api/v1/documentos/exemplo/arquivo";

function Leitor() {
  const params = useSearchParams();
  const [logado, setLogado] = useState(false);
  const [doc, setDoc] = useState<DocumentoLido | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pagina, setPagina] = useState(1);
  const [citacao, setCitacao] = useState<Citacao | null>(null);
  const [aba, setAba] = useState<Aba>("resumo");
  const [guardados, setGuardados] = useState<DocumentoGuardado[]>([]);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const jaAbriuDaUrl = useRef(false);

  const atualizarGuardados = useCallback(() => {
    if (getToken()) listarDocumentos().then(setGuardados).catch(() => setGuardados([]));
  }, []);

  useEffect(() => {
    setLogado(Boolean(getToken()));
    atualizarGuardados();
  }, [atualizarGuardados]);

  // O endereço do PDF enviado nesta sessão é um blob local: liberar ao trocar de documento.
  useEffect(() => () => {
    if (pdfUrl?.startsWith("blob:")) URL.revokeObjectURL(pdfUrl);
  }, [pdfUrl]);

  const mostrar = useCallback((lido: DocumentoLido, url: string | null) => {
    setDoc(lido);
    setPdfUrl(url);
    setPagina(1);
    setCitacao(null);
    setAba("resumo");
    window.scrollTo({ top: 0 });
  }, []);

  const executar = useCallback(async (acao: () => Promise<void>) => {
    setCarregando(true);
    setErro(null);
    try {
      await acao();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "A API não respondeu. O backend está rodando?");
    } finally {
      setCarregando(false);
    }
  }, []);

  const abrirExemplo = useCallback(
    () => executar(async () => mostrar(await obterExemplo(), PDF_EXEMPLO)),
    [executar, mostrar],
  );
  const abrirGuardado = useCallback(
    (id: string) => executar(async () => mostrar(await obterDocumento(id), null)),
    [executar, mostrar],
  );

  // /documentos?doc=exemplo ou ?doc=<id>: abre direto.
  useEffect(() => {
    const id = params.get("doc");
    if (!id || jaAbriuDaUrl.current) return;
    jaAbriuDaUrl.current = true;
    void (id === "exemplo" ? abrirExemplo() : abrirGuardado(id));
  }, [params, abrirExemplo, abrirGuardado]);

  function enviar() {
    if (!arquivo) return;
    void executar(async () => {
      const lido = await enviarDocumento(arquivo);
      mostrar(lido, arquivo.name.toLowerCase().endsWith(".pdf") ? URL.createObjectURL(arquivo) : null);
      atualizarGuardados();
    });
  }

  function apagar(id: string) {
    if (!window.confirm("Apagar este documento e a análise? Não dá para desfazer.")) return;
    void executar(async () => {
      await apagarDocumento(id);
      if (doc?.id === id) setDoc(null);
      atualizarGuardados();
    });
  }

  const aoCitar = useCallback((c: Citacao) => {
    setPagina(c.pagina);
    setCitacao(c);
    if (window.matchMedia("(max-width: 900px)").matches)
      document.getElementById("visualizador")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  if (!doc) {
    return (
      <div className="page wrap">
        <div className="eyebrow">Ler documentos jurídicos</div>
        <h1 className="hero">
          Entenda o seu processo, <em>página por página</em>.
        </h1>
        <p className="lede">
          Envie o PDF do processo. O DireitoAberto separa o que cada parte alega, o que o juiz
          decidiu e os prazos mencionados — sempre com a página de onde tirou cada informação. O
          que não conseguir ler, ele avisa.
        </p>

        {erro && <div className="erro" style={{ marginTop: 20 }}>{erro}</div>}

        <div className="leitor-entrada">
          <div className="card">
            <h3>Ver um exemplo</h3>
            <p>
              Um processo <b>fictício</b> de Juizado Especial: a compra de um notebook que deu
              defeito. Mostra tudo o que o leitor faz, sem precisar de conta.
            </p>
            <button className="btn" onClick={() => void abrirExemplo()} disabled={carregando}>
              {carregando ? "Abrindo…" : "Abrir o exemplo"}
            </button>
          </div>

          <div className="card">
            <h3>Ler o seu processo</h3>
            <ul>
              <li>Só você acessa. O arquivo não é guardado — só o texto extraído.</li>
              <li>Apagado automaticamente em 24 horas, ou quando você quiser.</li>
              <li>Nada é enviado a serviços de inteligência artificial.</li>
              <li>Páginas digitalizadas como imagem ainda não são lidas: o leitor avisa quais.</li>
              <li>Envie só documentos seus ou que você está autorizado a usar.</li>
            </ul>
            {logado ? (
              <div className="arquivo">
                <input
                  type="file"
                  accept=".pdf,.txt,application/pdf,text/plain"
                  aria-label="Arquivo do processo (PDF)"
                  onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
                />
                <button className="btn" onClick={enviar} disabled={!arquivo || carregando}>
                  {carregando ? "Lendo…" : "Ler documento"}
                </button>
              </div>
            ) : (
              <Link href="/login" className="btn" style={{ display: "inline-block" }}>
                Entrar para enviar um documento
              </Link>
            )}
          </div>
        </div>

        {guardados.length > 0 && (
          <div className="doc-lista" style={{ marginTop: 30 }}>
            <div className="sec-head">
              <h2>Seus documentos</h2>
              <span className="lbl">apagados automaticamente no prazo indicado</span>
            </div>
            {guardados.map((g) => (
              <div className="item" key={g.id}>
                <div>
                  <div className="titulo">{g.nome}</div>
                  <div className="meta">
                    <span>{g.total_paginas} páginas</span>
                    <span>expira em {new Date(g.expira_em).toLocaleString("pt-BR")}</span>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="chip" onClick={() => void abrirGuardado(g.id)}>Abrir</button>
                  <button className="chip" onClick={() => apagar(g.id)}>Apagar</button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="disc">
          <b>Isto é informação, não é decisão sobre o seu caso.</b> O leitor mostra o que está escrito
          no documento e de onde saiu. Para agir — recorrer, cumprir um prazo, fazer um acordo —
          procure a <b>Defensoria Pública</b> (gratuita) ou um advogado.
        </div>
      </div>
    );
  }

  const a = doc.analise;
  const naoLidas = [
    ...a.documento.paginas_sem_texto,
    ...a.documento.paginas_com_falha,
    ...a.documento.paginas_nao_processadas,
  ];
  const numero = a.numeros_processo[0];

  return (
    <div className="page wrap">
      <button className="chip" onClick={() => setDoc(null)}>← outro documento</button>
      <div className="doc-head">
        <h2>{doc.nome}</h2>
        {doc.ficticio && <span className="badge warn">processo fictício</span>}
        <span className="badge brand">{doc.total_paginas} páginas</span>
        <span className={`badge ${a.documento.leitura_completa ? "brand" : "right"}`}>
          {a.documento.leitura_completa
            ? "leitura completa"
            : `leitura parcial: ${naoLidas.length} página(s) não lida(s)`}
        </span>
        {doc.expira_em && (
          <span className="badge warn">apagado em {new Date(doc.expira_em).toLocaleString("pt-BR")}</span>
        )}
        {!doc.ficticio && (
          <button className="chip" onClick={() => apagar(doc.id)}>Apagar agora</button>
        )}
      </div>

      {a.avisos.length > 0 && (
        <div className="avisos" role="note">
          <h3>Antes de ler: o que pode estar faltando</h3>
          <ul>
            {a.avisos.map((aviso) => (
              <li key={aviso}>{aviso}</li>
            ))}
          </ul>
        </div>
      )}
      {erro && <div className="erro">{erro}</div>}

      <div className="leitor-grid">
        <div>
          <div className="leitor-tabs" role="tablist" aria-label="Partes da análise">
            {ABAS.map(([chave, rotulo]) => (
              <button
                key={chave}
                role="tab"
                aria-selected={aba === chave}
                onClick={() => setAba(chave)}
              >
                {rotulo}
              </button>
            ))}
          </div>

          <div role="tabpanel">
            {aba === "resumo" && (
              <>
                <div className="secao-k">Resumo — cada frase aponta de onde saiu</div>
                <ListaItens itens={a.resumo} aoCitar={aoCitar} ativa={citacao} descricoes={a.naturezas} />
                <div className="secao-k">Próximos passos possíveis</div>
                <ListaItens itens={a.proximos_passos} aoCitar={aoCitar} descricoes={a.naturezas} />
                <div className="secao-k">Perguntas para levar à Defensoria ou a um advogado</div>
                <ol className="perguntas-adv">
                  {a.perguntas_para_advogado.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ol>
              </>
            )}

            {aba === "tempo" && (
              <>
                <div className="secao-k">Em ordem de data. Alegação é a versão de uma parte, não fato comprovado.</div>
                <ListaItens
                  itens={a.linha_do_tempo}
                  aoCitar={aoCitar}
                  ativa={citacao}
                  descricoes={a.naturezas}
                  mostrarData
                  vazio="Não localizei datas no documento."
                />
              </>
            )}

            {aba === "partes" && (
              <>
                <div className="secao-k">Processo</div>
                <div className="li">
                  {numero ? (
                    <>
                      <div className="li-texto">
                        Nº {numero.numero}{" "}
                        <span className={`badge ${numero.digito_verificador_valido ? "brand" : "right"}`}>
                          {numero.digito_verificador_valido ? "dígito verificador confere" : "dígito verificador NÃO confere"}
                        </span>
                      </div>
                      <div className="li-extra">{numero.tribunal ?? numero.segmento}</div>
                      <Citacoes citacoes={numero.citacoes} aoCitar={aoCitar} ativa={citacao} />
                    </>
                  ) : (
                    <div className="li-texto">Número do processo não localizado.</div>
                  )}
                  {Object.entries(a.identificacao).map(([campo, info]) => (
                    <div key={campo} style={{ marginTop: 8 }}>
                      <div className="li-extra">
                        <b>{info.rotulo}:</b> {info.valor}
                      </div>
                      <Citacoes citacoes={info.citacoes} aoCitar={aoCitar} ativa={citacao} />
                    </div>
                  ))}
                </div>
                <div className="secao-k">Partes</div>
                <ListaItens itens={a.partes} aoCitar={aoCitar} ativa={citacao} descricoes={a.naturezas}
                            vazio="Não identifiquei as partes." />
                <div className="secao-k">Peças, na ordem do arquivo</div>
                {a.pecas.length ? (
                  a.pecas.map((p, i) => (
                    <div className="li" key={`${p.tipo}-${i}`}>
                      <div className="li-topo">
                        <span className="li-data">{p.data ? dataBr(p.data) : "sem data"}</span>
                        <span className="badge brand">{p.rotulo}</span>
                        <span className="peca-k">
                          p. {p.pagina_inicial}
                          {p.pagina_final !== p.pagina_inicial ? `–${p.pagina_final}` : ""}
                        </span>
                      </div>
                      <Citacoes citacoes={p.citacoes} aoCitar={aoCitar} ativa={citacao} />
                    </div>
                  ))
                ) : (
                  <p className="li-extra">Não reconheci títulos de peças processuais.</p>
                )}
              </>
            )}

            {aba === "decisoes" && (
              <>
                <div className="secao-k">Decisões do juiz</div>
                <ListaItens itens={a.decisoes} aoCitar={aoCitar} ativa={citacao} descricoes={a.naturezas}
                            vazio="Não localizei decisão do juiz." />
                <div className="secao-k">Trânsito em julgado</div>
                {a.transito_em_julgado.length ? (
                  <ListaItens itens={a.transito_em_julgado} aoCitar={aoCitar} ativa={citacao} descricoes={a.naturezas} />
                ) : (
                  <p className="li-extra">
                    Não localizei certidão de trânsito em julgado: pelo que foi enviado, não dá para afirmar
                    que a decisão é definitiva.
                  </p>
                )}
                <div className="secao-k">Obrigações e determinações</div>
                <ListaItens itens={a.obrigacoes_e_determinacoes} aoCitar={aoCitar} ativa={citacao} descricoes={a.naturezas} />
                <div className="secao-k">Prazos mencionados — nenhum foi calculado</div>
                {a.prazos[0]?.ressalva && <p className="vig-nota">{a.prazos[0].ressalva}</p>}
                <ListaItens itens={a.prazos} aoCitar={aoCitar} ativa={citacao} descricoes={a.naturezas} />
                <div className="secao-k">Pedidos — pedido não é direito reconhecido</div>
                <ListaItens itens={a.pedidos} aoCitar={aoCitar} ativa={citacao} descricoes={a.naturezas} />
                <div className="secao-k">Alegações das partes</div>
                <ListaItens itens={a.alegacoes} aoCitar={aoCitar} ativa={citacao} descricoes={a.naturezas} />
                <div className="secao-k">Recursos</div>
                <ListaItens itens={a.recursos} aoCitar={aoCitar} ativa={citacao} descricoes={a.naturezas}
                            vazio="Nenhuma menção a recurso." />
              </>
            )}

            {aba === "perguntar" && (
              <Perguntas documentoId={doc.id} aoCitar={aoCitar} ativa={citacao} descricoes={a.naturezas} />
            )}

            {aba === "glossario" && (
              <>
                <div className="secao-k">Termos que aparecem neste documento</div>
                {a.glossario.map((g) => (
                  <div className="li" key={g.termo}>
                    <div className="li-texto"><b>{g.termo}</b> — {g.explicacao}</div>
                    <div className="cits">
                      {g.paginas.map((n) => (
                        <button key={n} className="cit" onClick={() => { setPagina(n); setCitacao(null); }}>
                          p. {n}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>

        <div id="visualizador" className="viewer-col">
          <Visualizador
            paginas={doc.paginas}
            pagina={pagina}
            citacao={citacao}
            aoMudarPagina={(n) => { setPagina(n); setCitacao(null); }}
            pdfUrl={pdfUrl}
          />
        </div>
      </div>

      <div className="disc">
        <b>Isto é informação, não é decisão sobre o seu caso.</b> Cada item mostra a natureza do que foi
        encontrado — alegação de uma parte, pedido, decisão do juiz, fato certificado — e a página de
        origem. Confira no documento e procure a <b>Defensoria Pública</b> (gratuita) ou um advogado
        antes de agir.
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <Leitor />
    </Suspense>
  );
}
