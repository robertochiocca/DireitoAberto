import type { Metadata } from "next";
import { Bricolage_Grotesque, Inter, Newsreader, Space_Mono } from "next/font/google";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "DireitoAberto — letramento jurídico para o cidadão",
  description:
    "A legislação brasileira traduzida em linguagem simples, com busca por IA (RAG) e fontes oficiais.",
};

// Fontes baixadas no build e servidas pelo próprio site: o navegador de quem visita não fala com o Google
// (antes, cada visita mandava o endereço IP a fonts.googleapis.com — transferência a terceiro sem aviso).
const texto = Inter({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--fonte-texto", display: "swap" });
const titulo = Bricolage_Grotesque({ subsets: ["latin"], axes: ["opsz"], variable: "--fonte-titulo", display: "swap" });
const serifa = Newsreader({
  subsets: ["latin"], style: ["normal", "italic"], axes: ["opsz"], variable: "--fonte-serifa", display: "swap",
});
const mono = Space_Mono({ subsets: ["latin"], weight: ["400", "700"], variable: "--fonte-mono", display: "swap" });

// Aplica o tema antes da hidratação para evitar flash de tema errado.
const temaInicial = `
(function(){
  try{
    var t = localStorage.getItem("da-tema") ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", t);
  }catch(e){}
})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="pt-BR"
      suppressHydrationWarning
      className={`${texto.variable} ${titulo.variable} ${serifa.variable} ${mono.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: temaInicial }} />
      </head>
      <body>
        <Nav />
        <main>{children}</main>
        <footer>
          <div className="wrap">
            <span>
              Direito<b style={{ color: "var(--brand-ink)" }}>Aberto</b> — informação jurídica, não
              aconselhamento
            </span>
            <a href="/privacidade">Como tratamos seus dados</a>
            <span className="mono">{"// a lei em código aberto"}</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
