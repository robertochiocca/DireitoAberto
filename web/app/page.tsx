"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import AnswerPanel from "@/components/AnswerPanel";
import Degraus from "@/components/Degraus";
import Link from "next/link";
import { ApiError, perguntar, saude, type Resposta } from "@/lib/api";

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
  // Com IA ativa, a pergunta sai do servidor para o provedor: quem pergunta precisa saber antes.
  const [llmAtivo, setLlmAtivo] = useState(false);
  useEffect(() => {
    saude()
      .then((s) => setLlmAtivo(s.llm_ativo))
      .catch(() => setLlmAtivo(false));
  }, []);

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
        Descreva o seu problema em linguagem comum. A busca encontra artigos de lei e jurisprudência
        que podem ter relação com o seu caso — com a explicação separada do texto oficial e a fonte ao
        lado.
      </p>

      <form
        className="ask"
        onSubmit={(e) => {
          e.preventDefault();
          void enviar(pergunta);
        }}
      >
        <input
          id="pergunta"
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
          placeholder="Ex.: a empresa não quer trocar meu notebook defeituoso"
          aria-label="Descreva seu problema"
          aria-describedby="nota-privacidade"
        />
        <button className="btn" disabled={carregando}>
          {carregando ? "Buscando…" : "Perguntar"}
        </button>
      </form>

      <p className="nota-privacidade" id="nota-privacidade">
        {llmAtivo
          ? "Sua pergunta e os textos de lei encontrados são enviados a um provedor de inteligência artificial (Anthropic) para escrever a resposta. Não escreva nomes, CPF ou dados de saúde."
          : "Sua pergunta é respondida no próprio servidor do DireitoAberto, sem IA externa."}{" "}
        Sem conta, o texto da pergunta não é guardado. <Link href="/privacidade">Como tratamos seus dados</Link>.
      </p>

      <div className="chips">
        {EXEMPLOS.map((ex) => (
          <button key={ex} className="chip" onClick={() => void enviar(ex)}>
            {ex}
          </button>
        ))}
      </div>

      <AnswerPanel carregando={carregando} resposta={resposta} erro={erro} />

      {/* Depois da resposta, o caminho para resolver: do mais simples ao mais formal. */}
      <Degraus naHome nivel={2} />

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
