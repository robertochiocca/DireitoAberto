import Link from "next/link";

export const metadata = { title: "Como tratamos seus dados — DireitoAberto" };

/**
 * Descrição técnica do tratamento de dados, escrita a partir do código (backend/app). Não é política de
 * privacidade revisada juridicamente nem declaração de conformidade com a LGPD: falta definir o controlador,
 * o encarregado e as bases legais com assessoria jurídica (docs/security-audit.md).
 */
export default function PrivacidadePage() {
  return (
    <div className="page wrap prosa">
      <div className="aviso-minuta" role="note">
        <b>Minuta técnica.</b> Este texto descreve o que o sistema faz hoje, conforme o código. Ainda não foi revisado
        juridicamente e não é uma política de privacidade nem uma declaração de conformidade com a LGPD.
      </div>
      <h2>Como o DireitoAberto trata seus dados</h2>

      <h3>Perguntas</h3>
      <ul>
        <li>
          <b>Sem conta:</b> o texto da pergunta não é guardado. Fica só um registro de que houve uma consulta e quais
          artigos foram mostrados.
        </li>
        <li>
          <b>Com conta:</b> a pergunta fica no seu histórico, que você pode apagar a qualquer momento. Por padrão, é
          apagada automaticamente depois de 365 dias.
        </li>
        <li>
          <b>Inteligência artificial:</b> quando o serviço usa um provedor de IA (Anthropic), a pergunta e os textos
          de lei encontrados são enviados a ele para escrever a resposta, e a página avisa isso antes. O texto de um
          documento só é enviado se você autorizar expressamente.
        </li>
      </ul>

      <h3>Feedback sobre um dispositivo</h3>
      <ul>
        <li>
          Guardamos o dispositivo, o tipo de problema e o comentário, se você escrever um. CPF, e-mail, telefone e
          número de processo escritos no comentário são mascarados antes de gravar. A pergunta não é copiada.
        </li>
        <li>Com conta, o feedback fica ligado a ela: sai no arquivo de dados e é apagado com a conta.</li>
        <li>
          Uma pessoa confere cada feedback. Ele não muda a resposta nem a base automaticamente. É apagado em 365
          dias (padrão).
        </li>
      </ul>

      <h3>Documentos do leitor de processos</h3>
      <ul>
        <li>Exige conta. Guardamos o texto extraído de cada página e a análise; o arquivo original não é guardado.</li>
        <li>São apagados automaticamente em 24 horas (padrão) ou quando você pede. Só você tem acesso.</li>
        <li>A análise roda no próprio servidor do DireitoAberto, sem IA externa.</li>
        <li>Processos têm dados de outras pessoas: envie só o necessário.</li>
      </ul>

      <h3>Conta e segurança</h3>
      <ul>
        <li>Guardamos o e-mail e um resumo criptográfico (hash) da senha — nunca a senha.</li>
        <li>
          Operações sensíveis (login, exclusão, exportação) ficam registradas por 180 dias, sem o seu e-mail e sem o
          conteúdo das perguntas: a conta aparece como um código e o endereço de rede, só pelo prefixo.
        </li>
        <li>As fontes do site são servidas pelo próprio DireitoAberto: o seu navegador não fala com o Google.</li>
        <li>No seu navegador ficam só o token de sessão e a preferência de tema.</li>
      </ul>

      <h3>Seus direitos</h3>
      <p>
        Em <Link href="/conta">Sua conta</Link> você baixa todos os seus dados, troca a senha, encerra sessões e
        exclui a conta. Os dados não são usados para treinar modelos de IA nem compartilhados com bases de terceiros.
      </p>

      <h3>Contato</h3>
      <p>
        <i>A definir:</i> controlador dos dados e encarregado (art. 41 da LGPD). Até lá, este serviço não deve ser
        oferecido ao público em produção.
      </p>
    </div>
  );
}
