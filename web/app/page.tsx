"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import AnswerPanel from "@/components/AnswerPanel";
import { ApiError, perguntar, type Resposta } from "@/lib/api";

const EXEMPLOS = [
  "Produto com defeito e a loja não troca",
  "Quanto pagar de pensão alimentícia?",
  "Caí num golpe do PIX",
  "Meu voo foi cancelado",
  "O INSS negou meu benefício",
  "Posso ser preso por dívida?",
];

function Home() {
  const searchParams = useSearchParams();
  const [pergunta, setPergunta] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [resposta, setResposta] = useState<Resposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const jaPerguntouDaUrl = useRef(false);

  const enviar = useCallback(async (texto: string) => {
    const q = texto.trim();
    if (q.length < 4) return;
    setPergunta(q);
    setCarregando(true);
    setErro(null);
    setResposta(null);
    try {
      setResposta(await perguntar(q));
    } catch (e) {
      setErro(
        e instanceof ApiError
          ? e.message
          : "A API não respondeu. Confira se o backend está rodando (uvicorn app.main:app).",
      );
    } finally {
      setCarregando(false);
    }
  }, []);

  // Suporte a /?q=... (ex.: "perguntar de novo" a partir do histórico)
  useEffect(() => {
    const q = searchParams.get("q");
    if (q && !jaPerguntouDaUrl.current) {
      jaPerguntouDaUrl.current = true;
      void enviar(q);
    }
  }, [searchParams, enviar]);

  return (
    <div className="page wrap">
      <div className="eyebrow">Letramento jurídico · para o cidadão comum</div>
      <h1 className="hero">
        A lei foi escrita pra você. Só faltava alguém <em>traduzir</em>.
      </h1>
      <p className="lede">
        Descreva o seu problema em linguagem comum. A busca encontra os artigos de lei e a
        jurisprudência que se aplicam — sempre com a fonte oficial ao lado.
      </p>

      <form
        className="ask"
        onSubmit={(e) => {
          e.preventDefault();
          void enviar(pergunta);
        }}
      >
        <input
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
          placeholder="Ex.: a empresa não quer trocar meu notebook defeituoso"
          aria-label="Descreva seu problema"
        />
        <button className="btn" disabled={carregando}>
          {carregando ? "Buscando…" : "Perguntar"}
        </button>
      </form>

      <div className="chips">
        {EXEMPLOS.map((ex) => (
          <button key={ex} className="chip" onClick={() => void enviar(ex)}>
            {ex}
          </button>
        ))}
      </div>

      <AnswerPanel carregando={carregando} resposta={resposta} erro={erro} />

      <div className="disc">
        <b>Isto é informação, não é decisão sobre o seu caso.</b> Cada situação tem detalhes que
        mudam a resposta. Para agir com segurança, procure a <b>Defensoria Pública</b> (gratuita)
        ou um advogado.
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <Home />
    </Suspense>
  );
}
