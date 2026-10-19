"""Testes do frontend estático (`frontend/`) num navegador de verdade (opt-in).

Rodam quando o Playwright para Python e o Chromium dele estão instalados
(`pip install playwright` e `python -m playwright install chromium`). Sem
isso, são pulados — o resto da suíte não depende de navegador.

A página é aberta direto do disco: sem backend, a busca à API falha em
silêncio e o conteúdo curado de `dados.js` continua valendo.
"""

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import Error as ErroPlaywright  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

INDEX = Path(__file__).resolve().parents[2] / "frontend" / "index.html"

# Larguras em que o layout muda: desktop, tablet e celular.
LARGURAS = [1360, 768, 390]

# Maior vão aceitável entre dois trechos de texto vizinhos na mesma linha.
# Texto corrido emenda um trecho no outro (vão ~0); no defeito antigo, entre
# uma "coluna" e outra havia pelo menos o `gap` de 14 px do flex.
VAO_MAXIMO = 8

# Para cada passo de cada página de problema, agrupa os retângulos do texto
# por linha e mede o maior vão entre trechos vizinhos da mesma linha.
MEDIR_PASSOS = """() => PROBLEMS.flatMap(pr => {
  openProblem(pr.id);
  return [...document.querySelectorAll("#pdetail ol.steps li")].map((li, i) => {
    const rects = [];
    const textos = document.createTreeWalker(li, NodeFilter.SHOW_TEXT);
    for (let n; (n = textos.nextNode());) {
      if (!n.textContent.trim()) continue;
      const faixa = document.createRange();
      faixa.selectNodeContents(n);
      rects.push(...[...faixa.getClientRects()].filter(r => r.width >= 1));
    }
    rects.sort((a, b) => (a.top + a.bottom) - (b.top + b.bottom));
    const linhas = [];
    for (const r of rects) {
      const ultima = linhas[linhas.length - 1];
      if (!ultima || (r.top + r.bottom) / 2 > ultima.bottom) linhas.push({ bottom: r.bottom, trechos: [r] });
      else ultima.trechos.push(r);
    }
    let maiorVao = 0;
    for (const { trechos } of linhas) {
      trechos.sort((a, b) => a.left - b.left);
      for (let j = 1; j < trechos.length; j++)
        maiorVao = Math.max(maiorVao, trechos[j].left - trechos[j - 1].right);
    }
    return { problema: pr.id, passo: i + 1, inicio: li.textContent.slice(0, 50), maiorVao };
  });
})"""


@pytest.fixture(scope="module")
def navegador():
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except ErroPlaywright as exc:  # Playwright instalado, Chromium não
            pytest.skip(f"Chromium do Playwright indisponível: {str(exc).splitlines()[0]}")
        yield browser
        browser.close()


@pytest.mark.parametrize("largura", LARGURAS)
def test_passo_a_passo_corre_em_linha(navegador, largura):
    """Regressão: com o texto solto no `<li>` (que é flex), cada trecho e cada
    `<b>` virava uma coluna — "Ligue para o banco AGORA │ (canal oficial) e
    peça o acionamento do │ MED │ …". O texto do passo tem de correr em linha."""
    pagina = navegador.new_page(viewport={"width": largura, "height": 900})
    erros = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.goto(INDEX.as_uri())

    passos = pagina.evaluate(MEDIR_PASSOS)
    esperados = pagina.evaluate("() => PROBLEMS.reduce((n, p) => n + p.steps.length, 0)")
    pagina.close()

    assert not erros, erros
    assert esperados and len(passos) == esperados
    quebrados = [p for p in passos if p["maiorVao"] > VAO_MAXIMO]
    assert not quebrados, f"passos quebrados em colunas a {largura}px: {quebrados}"


# Texto que fecha o atributo e o elemento: no código antigo, o histórico local
# ia para o innerHTML sem escape, e "&quot;" digitado virava aspas no onclick.
CARGA_XSS = '"><img src=x onerror="window.__xss=1">&quot;);window.__xss=2;//'


def test_historico_local_nao_executa_html(navegador):
    pagina = navegador.new_page()
    dialogos = []
    pagina.on("dialog", lambda d: (dialogos.append(d.message), d.dismiss()))
    pagina.add_init_script(
        f"localStorage.setItem('da-hist', JSON.stringify([{CARGA_XSS!r}, 'golpe do pix']))"
    )
    pagina.goto(INDEX.as_uri())

    botoes = pagina.locator("#hist [data-hist]")
    assert botoes.count() == 2
    assert botoes.first.inner_text() == CARGA_XSS  # aparece como texto, literal
    assert pagina.locator("#hist img").count() == 0
    botoes.first.click()
    assert pagina.input_value("#q") == CARGA_XSS
    assert pagina.evaluate("() => window.__xss") is None
    assert not dialogos
    pagina.close()


def test_links_externos_so_aceitam_http(navegador):
    pagina = navegador.new_page()
    pagina.goto(INDEX.as_uri())
    assert pagina.evaluate("() => urlSegura('javascript:alert(1)')") == "#"
    assert pagina.evaluate("() => urlSegura('https://www.planalto.gov.br/x?a=1&b=\"2\"')") == (
        "https://www.planalto.gov.br/x?a=1&amp;b=&quot;2&quot;"
    )
    # Data sem hora não pode virar o dia anterior no fuso do Brasil.
    assert pagina.evaluate("() => dataLocal('2026-10-18').getDate()") == 18
    pagina.close()
