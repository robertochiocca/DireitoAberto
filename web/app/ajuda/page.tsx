import type { Metadata } from "next";
import Link from "next/link";
import { CANAIS, DEGRAUS } from "@/lib/ajuda";

export const metadata: Metadata = {
  title: "Ajuda gratuita — DireitoAberto",
  description: "Como se resolve um problema com a lei e onde buscar ajuda sem pagar.",
};

export default function AjudaPage() {
  return (
    <div className="page wrap">
      <div className="sec-head">
        <h2>Onde buscar ajuda</h2>
        <span className="lbl">quase tudo aqui é de graça</span>
      </div>

      <section className="path" aria-labelledby="path-h">
        <div className="path-head">
          <div className="eyebrow">Como se resolve um problema com a lei</div>
          <h3 id="path-h">Do problema à solução, em quatro degraus</h3>
          <p>
            Na maioria dos casos, a saída começa simples e só sobe de degrau se a anterior não
            funcionar. Nenhum deles exige pagar nada.
          </p>
        </div>
        <ol className="path-steps">
          {DEGRAUS.map((d, i) => {
            const ultimo = i === DEGRAUS.length - 1;
            const rotulo = `${d.acao} ${d.href.startsWith("#") ? "↓" : "→"}`;
            return (
              <li key={d.titulo} className={ultimo ? "ps-last" : undefined}>
                <span className="ps-n">{i + 1}</span>
                <h4>{d.titulo}</h4>
                <p>{d.texto}</p>
                {d.href.startsWith("#") ? (
                  <a className="ps-go" href={d.href}>{rotulo}</a>
                ) : (
                  <Link className="ps-go" href={d.href}>{rotulo}</Link>
                )}
              </li>
            );
          })}
        </ol>
        <p className="path-urgent">
          <b>Violência ou risco à vida não espera degrau:</b> ligue <b>190</b> (Polícia) ou{" "}
          <b>180</b> (Central de Atendimento à Mulher). A medida protetiva pode ser pedida direto
          na delegacia.
        </p>
      </section>

      <section className="help" id="canais" aria-labelledby="canais-h">
        <h3 id="canais-h">Você não precisa resolver sozinho.</h3>
        <p>
          O Brasil tem canais públicos e gratuitos para orientar e representar o cidadão. Comece
          por eles.
        </p>
        <div className="help-grid">
          {CANAIS.map((c) => (
            <div className="hres" key={c.nome}>
              <div className="nm">{c.nome}</div>
              <div className="tp">{c.oQueFaz}</div>
              <span className="free">{c.custo}</span>
            </div>
          ))}
        </div>
      </section>

      <div className="disc">
        <b>Isto é informação, não é decisão sobre o seu caso.</b> Cada situação tem detalhes que
        mudam a resposta. Para agir com segurança, procure a <b>Defensoria Pública</b> (gratuita)
        ou um advogado.
      </div>
    </div>
  );
}
