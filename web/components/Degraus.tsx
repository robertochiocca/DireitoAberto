"use client";

import Link from "next/link";
import { DEGRAUS } from "@/lib/ajuda";

// Faixa "do problema à solução". Aparece na home e na /ajuda; os links se
// adaptam à página: na home, "Perguntar" leva ao campo da própria página e os
// canais ficam na /ajuda; na /ajuda, os canais estão logo abaixo.
type Props = {
  naHome?: boolean;
  // Nível do título da faixa: 2 na home (abaixo do h1), 3 na /ajuda (abaixo do h2).
  nivel: 2 | 3;
};

function irParaPergunta() {
  const campo = document.getElementById("pergunta");
  if (!campo) return;
  const suave = !matchMedia("(prefers-reduced-motion: reduce)").matches;
  campo.scrollIntoView({ behavior: suave ? "smooth" : "auto", block: "center" });
  campo.focus({ preventScroll: true });
}

export default function Degraus({ naHome = false, nivel }: Props) {
  const Titulo = `h${nivel}` as "h2" | "h3";
  const TituloDegrau = `h${nivel + 1}` as "h3" | "h4";

  function acao(href: string, rotulo: string) {
    if (naHome && href === "/") {
      return (
        <button className="ps-go" onClick={irParaPergunta}>
          {rotulo} ↑
        </button>
      );
    }
    if (href.startsWith("#")) {
      return naHome ? (
        <Link className="ps-go" href={`/ajuda${href}`}>{rotulo} →</Link>
      ) : (
        <a className="ps-go" href={href}>{rotulo} ↓</a>
      );
    }
    return <Link className="ps-go" href={href}>{rotulo} →</Link>;
  }

  return (
    <section className={`path${naHome ? " path-home" : ""}`} aria-labelledby="path-h">
      <div className="path-head">
        <div className="eyebrow">Como se resolve um problema com a lei</div>
        <Titulo id="path-h" className="path-title">
          Do problema à solução, em quatro degraus
        </Titulo>
        <p>
          Na maioria dos casos, a saída começa simples e só sobe de degrau se a anterior não
          funcionar. Nenhum deles exige pagar nada.
        </p>
      </div>
      <ol className="path-steps">
        {DEGRAUS.map((d, i) => (
          <li key={d.titulo} className={i === DEGRAUS.length - 1 ? "ps-last" : undefined}>
            <span className="ps-n">{i + 1}</span>
            <TituloDegrau className="ps-title">{d.titulo}</TituloDegrau>
            <p>{d.texto}</p>
            {acao(d.href, d.acao)}
          </li>
        ))}
      </ol>
      <p className="path-urgent">
        <b>Violência ou risco à vida não espera degrau:</b> ligue <b>190</b> (Polícia) ou{" "}
        <b>180</b> (Central de Atendimento à Mulher). A medida protetiva pode ser pedida direto na
        delegacia.
      </p>
    </section>
  );
}
