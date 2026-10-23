"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, excluirConta, exportarDados, getEmail, getToken, sairDeTodas, trocarSenha } from "@/lib/api";

/** Seus dados e sua conta: baixar, trocar a senha, encerrar sessões, excluir (LGPD, art. 18). */
export default function ContaPage() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [senhaAtual, setSenhaAtual] = useState("");
  const [senhaNova, setSenhaNova] = useState("");
  const [senhaExclusao, setSenhaExclusao] = useState("");

  useEffect(() => setEmail(getToken() ? getEmail() : null), []);

  async function executar(acao: () => Promise<void>, sucesso: string) {
    setErro(null);
    setMensagem(null);
    try {
      await acao();
      setMensagem(sucesso);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "A API não respondeu. Tente de novo.");
    }
  }

  if (!email) {
    return (
      <div className="page wrap">
        <div className="card card-auth" style={{ textAlign: "center" }}>
          <p style={{ marginBottom: 16 }}>Entre na sua conta para baixar ou apagar os seus dados.</p>
          <Link href="/login" className="btn" style={{ display: "inline-block" }}>
            Entrar
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="page wrap">
      <div className="sec-head">
        <h2>Sua conta</h2>
        <span className="lbl">{email}</span>
      </div>
      <div role="status" aria-live="polite">
        {mensagem && <div className="aviso-ok">{mensagem}</div>}
        {erro && <div className="erro">{erro}</div>}
      </div>

      <section className="card conta-bloco" aria-labelledby="t-dados">
        <h3 id="t-dados">Baixar meus dados</h3>
        <p>
          Um arquivo com tudo o que guardamos sobre a sua conta: e-mail, data de criação, todas as perguntas do
          histórico, os documentos que você enviou ao leitor, com a análise, e os feedbacks. Veja{" "}
          <Link href="/privacidade">como tratamos os dados</Link>.
        </p>
        <button className="btn" onClick={() => void executar(exportarDados, "Arquivo baixado.")}>
          Baixar meus dados (JSON)
        </button>
      </section>

      <section className="card conta-bloco" aria-labelledby="t-senha">
        <h3 id="t-senha">Trocar a senha</h3>
        <p>As outras sessões abertas (em outros aparelhos) são encerradas; esta continua.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void executar(async () => {
              await trocarSenha(senhaAtual, senhaNova);
              setSenhaAtual("");
              setSenhaNova("");
            }, "Senha trocada. As outras sessões foram encerradas.");
          }}
        >
          <div className="field">
            <label htmlFor="senha-atual">Senha atual</label>
            <input id="senha-atual" type="password" autoComplete="current-password" required
              value={senhaAtual} onChange={(e) => setSenhaAtual(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="senha-nova">Nova senha (mínimo 8 caracteres)</label>
            <input id="senha-nova" type="password" autoComplete="new-password" minLength={8} required
              value={senhaNova} onChange={(e) => setSenhaNova(e.target.value)} />
          </div>
          <button className="btn" type="submit">Trocar a senha</button>
        </form>
      </section>

      <section className="card conta-bloco" aria-labelledby="t-sessoes">
        <h3 id="t-sessoes">Encerrar todas as sessões</h3>
        <p>Use se perdeu um aparelho ou acha que alguém entrou na sua conta. Você também sai deste aparelho.</p>
        <button
          className="chip"
          onClick={() =>
            void executar(async () => {
              await sairDeTodas();
              router.push("/login");
            }, "Sessões encerradas.")
          }
        >
          Encerrar todas as sessões
        </button>
      </section>

      <section className="card conta-bloco perigo" aria-labelledby="t-excluir">
        <h3 id="t-excluir">Excluir a conta</h3>
        <p>
          Apaga a conta, todo o histórico, os documentos do leitor e os feedbacks. Não dá para desfazer. Fica só um registro
          técnico de que a exclusão aconteceu, sem o seu e-mail, pelo prazo de retenção da auditoria.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!window.confirm("Excluir a conta e todos os dados? Não dá para desfazer.")) return;
            void executar(async () => {
              await excluirConta(senhaExclusao);
              router.push("/");
            }, "Conta excluída.");
          }}
        >
          <div className="field">
            <label htmlFor="senha-exclusao">Confirme com a sua senha</label>
            <input id="senha-exclusao" type="password" autoComplete="current-password" required
              value={senhaExclusao} onChange={(e) => setSenhaExclusao(e.target.value)} />
          </div>
          <button className="btn btn-perigo" type="submit">Excluir minha conta</button>
        </form>
      </section>
    </div>
  );
}
