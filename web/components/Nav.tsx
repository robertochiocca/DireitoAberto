"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { encerrarSessao, getEmail } from "@/lib/api";

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [tema, setTema] = useState("light");

  useEffect(() => {
    const atualizar = () => setEmail(getEmail());
    atualizar();
    window.addEventListener("da-auth", atualizar);
    setTema(document.documentElement.getAttribute("data-theme") || "light");
    return () => window.removeEventListener("da-auth", atualizar);
  }, []);

  function alternarTema() {
    const novo = tema === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", novo);
    localStorage.setItem("da-tema", novo);
    setTema(novo);
  }

  function sair() {
    encerrarSessao();
    router.push("/");
  }

  const ativo = (rota: string) => (pathname === rota ? "on" : "");

  return (
    <header className="bar">
      <div className="wrap bar-in">
        <Link href="/" className="logo" aria-label="DireitoAberto — início">
          <div className="logo-mark" />
          <b>
            Direito<span>Aberto</span>
          </b>
        </Link>
        <nav className="bar-nav">
          <Link href="/" className={ativo("/")}>Perguntar</Link>
          <Link href="/base-legal" className={ativo("/base-legal")}>Base legal</Link>
          <Link href="/historico" className={ativo("/historico")}>Histórico</Link>
          {email ? (
            <>
              <span className="user-chip" title={email}>{email}</span>
              <button className="linklike" onClick={sair}>Sair</button>
            </>
          ) : (
            <Link href="/login" className={ativo("/login")}>Entrar</Link>
          )}
          <button
            className="theme-btn"
            onClick={alternarTema}
            title="Alternar tema"
            aria-label="Alternar tema claro/escuro"
          >
            {tema === "dark" ? "☀️" : "🌙"}
          </button>
        </nav>
      </div>
    </header>
  );
}
