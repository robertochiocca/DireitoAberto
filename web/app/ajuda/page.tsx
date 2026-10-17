import type { Metadata } from "next";
import Degraus from "@/components/Degraus";
import { CANAIS } from "@/lib/ajuda";

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

      <Degraus nivel={3} />

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
