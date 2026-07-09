import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "DireitoAberto — letramento jurídico para o cidadão",
  description:
    "A legislação brasileira traduzida em linguagem simples, com busca por IA (RAG) e fontes oficiais.",
};

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
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: temaInicial }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Inter:wght@400;500;600;700&family=Space+Mono:wght@400;700&display=swap"
          rel="stylesheet"
        />
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
            <span className="mono">{"// a lei em código aberto"}</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
