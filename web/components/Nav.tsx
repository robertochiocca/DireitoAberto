"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { encerrarSessao, getEmail } from "@/lib/api";

// Acima desta largura a navegação cabe numa linha; abaixo, vira o botão Menu.
// Precisa bater com o @media de globals.css.
const LARGURA_DESKTOP = "(min-width: 960px)";

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [tema, setTema] = useState("light");
  const [aberto, setAberto] = useState(false);
  const menuBtn = useRef<HTMLButtonElement>(null);
  const primeiroItem = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    const atualizar = () => setEmail(getEmail());
    atualizar();
    window.addEventListener("da-auth", atualizar);
    setTema(document.documentElement.getAttribute("data-theme") || "light");
    return () => window.removeEventListener("da-auth", atualizar);
  }, []);

  const fecharMenu = useCallback((devolverFoco: boolean) => {
    setAberto(false);
    if (devolverFoco) menuBtn.current?.focus();
  }, []);

  // Trocar de página (inclusive pelo "voltar" do navegador) fecha o painel.
  useEffect(() => setAberto(false), [pathname]);

  // Enquanto o painel está aberto: trava a rolagem, foca o primeiro item,
  // Esc fecha devolvendo o foco ao botão, e alargar a janela até o layout de
  // uma linha o faz deixar de existir.
  useEffect(() => {
    if (!aberto) return;
    const html = document.documentElement;
    html.classList.add("menu-aberto");
    primeiroItem.current?.focus({ preventScroll: true });
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === "Escape") fecharMenu(true);
    };
    const desktop = matchMedia(LARGURA_DESKTOP);
    const aoAlargar = (e: MediaQueryListEvent) => {
      if (e.matches) fecharMenu(false);
    };
    document.addEventListener("keydown", aoTeclar);
    desktop.addEventListener("change", aoAlargar);
    return () => {
      html.classList.remove("menu-aberto");
      document.removeEventListener("keydown", aoTeclar);
      desktop.removeEventListener("change", aoAlargar);
    };
  }, [aberto, fecharMenu]);

  function alternarTema() {
    const novo = tema === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", novo);
    localStorage.setItem("da-tema", novo);
    setTema(novo);
  }

  async function sair() {
    setAberto(false);
    await encerrarSessao();
    router.push("/");
  }

  const ativo = (rota: string) => (pathname === rota ? "on" : "");
  // Link para a página atual não muda o pathname: fecha o painel no clique.
  const fechar = () => setAberto(false);

  return (
    <>
      <header className="bar">
        <div className="wrap bar-in">
          <Link href="/" className="logo" aria-label="DireitoAberto — início">
            <div className="logo-mark" />
            <b>
              Direito<span>Aberto</span>
            </b>
          </Link>

          <nav className="bar-nav" aria-label="Seções">
            <Link href="/" className={ativo("/")}>Perguntar</Link>
            <Link href="/documentos" className={ativo("/documentos")}>Ler documento</Link>
            <Link href="/base-legal" className={ativo("/base-legal")}>Base legal</Link>
            <Link href="/historico" className={ativo("/historico")}>Histórico</Link>
            <Link href="/ajuda" className={`nav-cta ${ativo("/ajuda")}`}>
              <span className="cta-dot" />
              Ajuda gratuita
            </Link>
          </nav>

          <div className="bar-tools">
            {email ? (
              <>
                <span className="user-chip" title={email}>{email}</span>
                <button className="linklike conta" onClick={sair}>Sair</button>
              </>
            ) : (
              <Link href="/login" className={`linklike conta ${ativo("/login")}`}>Entrar</Link>
            )}
            <button
              className="theme-btn"
              onClick={alternarTema}
              title="Alternar tema"
              aria-label="Alternar tema claro/escuro"
            >
              {tema === "dark" ? "☀️" : "🌙"}
            </button>
            <button
              ref={menuBtn}
              className="menu-btn"
              aria-label="Menu"
              aria-expanded={aberto}
              aria-controls="menu"
              onClick={() => (aberto ? fecharMenu(true) : setAberto(true))}
            >
              <span className="burger" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              <span className="menu-lbl">Menu</span>
            </button>
          </div>
        </div>

        {/* Menu compacto (tablet e celular): mesmas seções, em ordem de
            importância. Primeiro os dois caminhos que resolvem — perguntar e
            a ajuda gratuita —, depois a consulta e a conta. */}
        <div className="menu" id="menu" hidden={!aberto}>
          <div className="wrap menu-in">
            <div className="menu-k">Comece por aqui</div>
            <Link ref={primeiroItem} href="/" className="mi mi-primary" onClick={fechar}>
              <span className="mi-t">Tenho um problema</span>
              <span className="mi-d">Pergunte em palavras simples e veja a lei</span>
              <span className="mi-go" aria-hidden="true">→</span>
            </Link>
            <Link href="/ajuda" className="mi mi-help" onClick={fechar}>
              <span className="mi-t">Ajuda gratuita</span>
              <span className="mi-d">Defensoria, Procon, Juizado — de graça</span>
              <span className="mi-go" aria-hidden="true">→</span>
            </Link>

            <div className="menu-k">Para consultar</div>
            <div className="mi-list">
              <Link href="/documentos" className={`mi-row ${ativo("/documentos")}`} onClick={fechar}>
                <b>Ler documento</b>
                <span>Entenda um processo, página por página</span>
              </Link>
              <Link href="/base-legal" className={`mi-row ${ativo("/base-legal")}`} onClick={fechar}>
                <b>Base legal</b>
                <span>Leis, súmulas e o que vale hoje</span>
              </Link>
              <Link href="/historico" className={`mi-row ${ativo("/historico")}`} onClick={fechar}>
                <b>Histórico</b>
                <span>Suas perguntas anteriores</span>
              </Link>
            </div>

            <div className="menu-k">Sua conta</div>
            <div className="mi-list">
              {email ? (
                <button className="mi-row" onClick={sair}>
                  <b>Sair</b>
                  <span className="mi-email">{email}</span>
                </button>
              ) : (
                <Link href="/login" className={`mi-row ${ativo("/login")}`} onClick={fechar}>
                  <b>Entrar</b>
                  <span>Para guardar o seu histórico</span>
                </Link>
              )}
            </div>
          </div>
        </div>
      </header>
      {aberto && <div className="menu-veil" onClick={() => fecharMenu(false)} />}
    </>
  );
}
