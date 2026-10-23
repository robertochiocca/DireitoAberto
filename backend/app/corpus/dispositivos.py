"""Localiza um dispositivo (artigo, parágrafo, inciso, alínea) no texto oficial de um artigo.

O texto vem do snapshot do monitor (`monitor/artigos.dividir`): um artigo por chave, numa linha só,
sem a redação tachada. A estrutura é reconstruída pelos marcadores que a técnica legislativa fixa
(LC 95/1998, art. 10): "§ 1º" e "Parágrafo único." abrem parágrafo; "XIII -" abre inciso; "a)" abre
alínea. Marcador citado no meio do texto ("previsto no § 1º deste artigo") não abre nada: o
parágrafo de verdade começa por maiúscula, e incisos e alíneas precisam vir em ordem crescente.

As anotações da Casa Civil — "(Redação dada pela Lei nº …)", "(Incluído pela …)", "(Vide …)",
"Regulamento" — não são texto de lei. Saem do trecho e ficam guardadas à parte, como evidência das
alterações.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ------------------------------------------------------------------ referência a dispositivo


@dataclass(frozen=True)
class Ref:
    artigo: str                    # "7", "1694", "54-A" (a chave de monitor/artigos.chave)
    paragrafo: str | None = None   # "1", "2-A", "unico", "caput"
    inciso: str | None = None      # "XIII"
    alinea: str | None = None      # "a"

    def rotulo(self) -> str:
        numero = self.artigo.split("-")[0]
        letra = self.artigo[len(numero):]
        n = int(numero)
        partes = [f"art. {n:,}".replace(",", ".") + ("º" if n < 10 else "") + letra]
        if self.paragrafo == "caput":
            partes.append("caput")
        elif self.paragrafo == "unico":
            partes.append("parágrafo único")
        elif self.paragrafo:
            p = self.paragrafo.split("-")[0]
            partes.append(f"§ {p}{'º' if int(p) < 10 else ''}{self.paragrafo[len(p):]}")
        if self.inciso:
            partes.append(self.inciso)
        if self.alinea:
            partes.append(f'alínea "{self.alinea}"')
        return ", ".join(partes)

    def como_dict(self) -> dict:
        return {k: v for k, v in vars(self).items() if v is not None}


_ROMANOS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def romano(valor: str) -> int:
    total = 0
    for atual, seguinte in zip(valor, valor[1:] + " ", strict=False):
        v = _ROMANOS[atual]
        total += -v if _ROMANOS.get(seguinte, 0) > v else v
    return total


def _chave_artigo(numero: str, letra: str | None) -> str:
    return numero.replace(".", "") + (f"-{letra.upper()}" if letra else "")


_TOKEN = re.compile(
    r"(?P<faixa>(?P<ini>\d{1,4}(?:\.\d{3})?)\s*[º°o]?\s+a\s+(?P<fim>\d{1,4}(?:\.\d{3})?)\s*[º°o]?)"
    r"|(?P<pars>§§)"
    r"|(?P<par>§)"
    r"|(?P<unico>par[áa]grafo\s+[úu]nico)"
    r"|(?P<caput>\bcaput\b)"
    r"|(?P<num>\d{1,4}(?:\.\d{3})?)\s*[º°o]?(?:-(?P<letra>[A-Z]{1,2})\b)?"
    r"|(?P<romano>\b[IVXLC]+\b)(?:-(?P<rletra>[A-Z])\b)?",
    re.IGNORECASE,
)


def interpretar_rotulo(rotulo: str) -> list[Ref]:
    """Dispositivos nomeados no rótulo do corpus ("Arts. 1.583 e 1.584, § 2º" → art. 1.583; art. 1.584, § 2º).

    Rótulo que não começa por "Art." (súmula, decreto inteiro) não nomeia dispositivo: lista vazia.
    O que vem entre parênteses ("(síntese)", "(c/ Lei …)") é observação e não entra. Um artigo
    seguido só de "e § N" ("Art. 284 e § 1º") é o caput mais o parágrafo.
    """
    if not re.match(r"\s*arts?\.", rotulo, re.IGNORECASE):
        return []
    texto = re.sub(r"\([^)]*\)", " ", rotulo)
    texto = re.sub(r"^\s*arts?\.\s*", "", texto, flags=re.IGNORECASE)
    refs: list[Ref] = []
    artigo: str | None = None
    paragrafo: str | None = None
    modo = "artigo"  # o que um número solto significa agora: artigo ou parágrafo
    qualificados: set[str] = set()   # artigos com parágrafo ou inciso nomeado
    for m in _TOKEN.finditer(texto):
        anterior = texto[:m.start()].rstrip()
        if m.group("faixa"):
            ini, fim = (int(m.group(g).replace(".", "")) for g in ("ini", "fim"))
            if modo == "paragrafo" and artigo:
                refs += [Ref(artigo, str(n)) for n in range(ini, fim + 1)]
                qualificados.add(artigo)
            else:
                for n in range(ini, fim + 1):
                    refs.append(Ref(str(n)))
                artigo, paragrafo, modo = str(fim), None, "artigo"
        elif m.group("pars") or m.group("par"):
            modo = "paragrafo"
            if artigo and anterior.endswith(" e") and not anterior.endswith(", e") and artigo not in qualificados:
                # "Art. 284 e § 1º": o artigo citado sozinho antes era o caput.
                refs = [r for r in refs if r != Ref(artigo)] + [Ref(artigo, "caput")]
                qualificados.add(artigo)
        elif m.group("unico"):
            if artigo:
                refs.append(Ref(artigo, "unico"))
                qualificados.add(artigo)
                paragrafo = "unico"
        elif m.group("caput"):
            if artigo:
                refs = [r for r in refs if r != Ref(artigo)] + [Ref(artigo, "caput")]
                qualificados.add(artigo)
                paragrafo = "caput"
        elif m.group("num"):
            numero = _chave_artigo(m.group("num"), m.group("letra"))
            if modo == "paragrafo" and artigo:
                # "Art. 43, §§ 1º e 2º": o artigo citado antes da vírgula era só o recipiente.
                refs = [r for r in refs if r != Ref(artigo)] + [Ref(artigo, numero)]
                qualificados.add(artigo)
                paragrafo = numero
            else:
                artigo, paragrafo = numero, None
                refs.append(Ref(artigo))
        elif m.group("romano") and artigo:
            inciso = m.group("romano").upper() + (f"-{m.group('rletra').upper()}" if m.group("rletra") else "")
            dono = paragrafo if paragrafo not in (None, "caput") else None
            # O inciso substitui o recipiente nomeado logo antes ("§ 3º, V" é só o inciso V do § 3º).
            refs = [r for r in refs if r not in (Ref(artigo), Ref(artigo, dono))]
            refs.append(Ref(artigo, dono, inciso))
            qualificados.add(artigo)
    # Sem duplicatas, na ordem do rótulo.
    vistos: list[Ref] = []
    for r in refs:
        if r not in vistos:
            vistos.append(r)
    return vistos


# ------------------------------------------------------------------ anotações editoriais

# "(Parágrafo incluído pela …)", "(Inciso acrescentado …)": a CLT anota assim.
_PREFIXO_DE_DISPOSITIVO = r"(?:(?:Par[áa]grafo|Inciso|Al[íi]nea|Artigo|Item|Caput)\s+(?:[úu]nico\s+)?)?"
_INICIO_ANOTACAO = _PREFIXO_DE_DISPOSITIVO + r"(?:" + (
    r"Reda[çc][ãa]o\s+dada|Reda[çc][ãa]o\s+determinada|Inclu[íi]d[oa]|Acrescid[oa]|Acrescentad[oa]|"
    r"Revogad[oa]|Vide|Vig[êe]ncia|Regulamento|Regulamenta[çc][ãa]o|Produ[çc][ãa]o\s+de\s+efeito|"
    r"Renumerad[oa]|Promulga[çc][ãa]o|Execu[çc][ãa]o\s+suspensa|Suspens[oa]|Retificad[oa]|Em\s+vigor|"
    r"Mensagem\s+de\s+veto|Revigorad[oa]|Transformad[oa]|Declarad[oa]|Express[ãa]o|Convers[ãa]o|"
    r"Texto\s+compilado|Vetad[oa]\s+pel|Partes?\s+mantid|Inclus[ãa]o|Altera[çc][ãa]o|Restabelecid|"
    r"com\s+reda[çc][ãa]o"
) + r")"
# Parêntese de anotação, com até um nível de parênteses dentro ("(Vide Lei nº 1 (Vigência))"). A página às
# vezes deixa o último parêntese aberto no fim do artigo: também é anotação.
_ANOTACAO = re.compile(
    rf"\(\s*(?:{_INICIO_ANOTACAO})(?:[^()]|\([^()]*\))*(?:\)|$)", re.IGNORECASE
)
# "(Revogado pela Lei …)" ocupa o lugar do texto revogado: sem ele, sobraria "I -;" — fica no trecho.
_MARCA_DE_REVOGACAO = re.compile(rf"^\(\s*{_PREFIXO_DE_DISPOSITIVO}Revogad[oa]", re.IGNORECASE)
# A marca de revogação só fica no texto quando ocupa o lugar de um dispositivo ("I - (Revogado)", "§ 2º
# (Revogado …)", "Art. 262. (Revogado …)"). Solta depois do ponto final, ela é do artigo seguinte, cujo
# rótulo a página tachou: o art. 792 da CLT, revogado, deixava "(Revogado …)" no fim do art. 791-A.
_ROTULO_ANTES = re.compile(
    r"(?:§\s*\d+\s*[º°o]?(?:-[A-Z])?\.?|Par[áa]grafo\s+[úu]nico\.?|(?<![\w-])[IVXLC]+(?:-[A-Z])?\s*[-–—]|"
    r"(?<![\w])[a-z]\)|Art\.\s*\d[\d.]*\s*[º°o]?(?:-[A-Z])?\.?|\x00)\s*$"
)
# Título da divisão seguinte (com as anotações dele), que a divisão por artigos deixa no fim do artigo.
_CABECALHO = re.compile(
    r"\s(?:LIVRO|T[ÍI]TULO|CAP[ÍI]TULO|SE[ÇC][ÃA]O|Se[çc][ãa]o|SUBSE[ÇC][ÃA]O|Subse[çc][ãa]o)\s+"
    r"(?:[IVXLC]+(?:-[A-Z])?|[ÚU]NIC[OA]|[ÚU]nic[oa])\b"
)
_FIM_DE_DISPOSITIVO = re.compile(r"[.;:](?:\s*\((?:[^()]|\([^()]*\))*\))*\s*$")

_CORTE = "\x00"  # marca o lugar de onde saiu uma anotação
_SEP = rf"[\s{_CORTE}]"  # entre a pontuação e um rótulo solto pode ter ficado uma anotação retirada
# Rótulos de link soltos entre um dispositivo e outro ("… advogado. Produção de efeitos Parágrafo único.").
_ROTULOS_SOLTOS = r"(?:Produ[çc][ãa]o\s+de\s+efeitos?|Regulamento|Vig[êe]ncia|Mensagem\s+de\s+veto|Texto\s+compilado)"
_SOLTA = re.compile(
    rf"(?P<p>[.;:])(?P<resto>(?:{_SEP}+{_ROTULOS_SOLTOS})+)"
    rf"(?={_SEP}+(?:§|Par[áa]grafo\s+[úu]nico|[IVXLC]+\s*[-–—]|[a-z]\)|Art\.)|{_SEP}*$)"
)
@dataclass
class TextoLimpo:
    texto: str
    anotacoes: list[str] = field(default_factory=list)
    # Pedaços contíguos da página que compõem o texto: cada um está, palavra por palavra, no original.
    segmentos: list[str] = field(default_factory=list)
    # O que saiu e não é evidência sobre o dispositivo: o título da divisão seguinte (com as anotações dele) e
    # marcas de revogação órfãs (do artigo seguinte, de rótulo tachado). Não viram relação de alteração.
    descartado: list[str] = field(default_factory=list)


def normalizar(texto: str) -> str:
    """Espaços colapsados e duas quebras de diagramação da página desfeitas: o algarismo romano partido
    em duas linhas ("I" / "I - fornecer" é o inciso II) e o ordinal sobrescrito numa linha própria
    ("Art. 3" / "o" é "Art. 3o")."""
    plano = " ".join(texto.split())
    plano = re.sub(r"(?<![\w-])([IVXLC]{1,4}) ([IVXLC]{1,4})(?=\s*[-–—]\s)", r"\1\2", plano)
    return re.sub(r"((?:Art\.|§)\s*\d[\d.]*) o(?=[\s.])", r"\1o", plano)


def normalizar_pontuacao(texto: str) -> str:
    return re.sub(r"\s+([;.,:])", r"\1", normalizar(texto))


def _cortar_cabecalho(texto: str) -> tuple[str, str | None]:
    for m in _CABECALHO.finditer(texto):
        if _FIM_DE_DISPOSITIVO.search(texto[:m.start()]):
            return texto[:m.start()], " ".join(texto[m.start():].split())
    return texto, None


def limpar(texto: str) -> TextoLimpo:
    """Texto do dispositivo sem as anotações editoriais, que voltam à parte (evidência de alteração)."""
    anotacoes: list[str] = []
    descartado: list[str] = []
    texto, cabecalho = _cortar_cabecalho(texto)
    if cabecalho:
        descartado.append(cabecalho)

    def tirar(m: re.Match) -> str:
        anotacao = " ".join(m.group(0).split())
        if not _MARCA_DE_REVOGACAO.match(anotacao):
            anotacoes.append(anotacao)
            return _CORTE
        if _ROTULO_ANTES.search(m.string[:m.start()]):
            anotacoes.append(anotacao)
            return f"{_CORTE}{anotacao}{_CORTE}"
        descartado.append(f"marca de revogação sem dispositivo (do artigo seguinte?): {anotacao}")
        return _CORTE

    def soltar(m: re.Match) -> str:
        anotacoes.append(" ".join(m.group("resto").replace(_CORTE, " ").split()))
        return m.group("p") + _CORTE

    limpo = _ANOTACAO.sub(tirar, texto)
    limpo = _SOLTA.sub(soltar, limpo)
    segmentos = [s for s in (normalizar_pontuacao(p) for p in limpo.split(_CORTE)) if s.strip(" .;:,()")]
    limpo = normalizar_pontuacao(limpo.replace(_CORTE, " "))
    # A pontuação que vinha depois da anotação ("graus; (Redação dada …).") não é do texto da lei, nem o
    # parêntese que sobra aberto quando a página tacha o que vinha dentro dele.
    limpo = re.sub(r"([.;:])\.", r"\1", limpo)
    limpo = re.sub(r"\(\s+(?=\(|$)", "", limpo).strip()
    return TextoLimpo(limpo, anotacoes, segmentos, descartado)


# ------------------------------------------------------------------ estrutura do artigo

# "§ 1º O …", "§ 2º-A Os …" e o estilo da CLT, com travessão: "§ 1º - A falta …", "Parágrafo único - …".
_PARAGRAFO = re.compile(
    r"(?:(?<=\s)|^)(?:§\s*(?P<num>\d{1,3})\s*[º°o]?(?:-(?P<letra>[A-Z])\b)?\.?|(?P<unico>Parágrafo\s+único)\.?)"
    r"(?:\s*[-–—])?\s+(?=[A-ZÀ-Ú(“\"])"
)
_INCISO = re.compile(r"(?:(?<=[\s;:.)])|^)(?P<num>[IVXLC]+)(?:\s*-\s*(?P<letra>[A-Z])(?=\s*[-–—]))?\s*[-–—]\s+(?=\S)")
_ALINEA = re.compile(r"(?:(?<=[;:.)]\s)|(?<=^))(?P<letra>[a-z])\)\s+(?=\S)")


@dataclass
class _Marca:
    tipo: str      # "paragrafo" | "inciso" | "alinea"
    valor: str
    inicio: int


def _marcas(texto: str) -> list[_Marca]:
    marcas: list[_Marca] = []
    for m in _PARAGRAFO.finditer(texto):
        valor = "unico" if m.group("unico") else m.group("num") + (f"-{m.group('letra')}" if m.group("letra") else "")
        marcas.append(_Marca("paragrafo", valor, m.start()))
    for m in _INCISO.finditer(texto):
        valor = m.group("num") + (f"-{m.group('letra')}" if m.group("letra") else "")
        marcas.append(_Marca("inciso", valor, m.start()))
    for m in _ALINEA.finditer(texto):
        marcas.append(_Marca("alinea", m.group("letra"), m.start()))
    marcas.sort(key=lambda m: m.inicio)

    # Ordem crescente dentro de cada nível: inciso citado no meio do texto ("inciso XIII -") não abre
    # dispositivo. A sequência de incisos recomeça em cada parágrafo; a de alíneas, em cada inciso.
    aceitas: list[_Marca] = []
    ultimo_par, ultimo_inc, ultima_al = 0, 0, ""
    for marca in marcas:
        if marca.tipo == "paragrafo":
            n = 1 if marca.valor == "unico" else int(marca.valor.split("-")[0])
            if n < ultimo_par:
                continue
            ultimo_par, ultimo_inc, ultima_al = n, 0, ""
        elif marca.tipo == "inciso":
            n = romano(marca.valor.split("-")[0])
            if texto[max(0, marca.inicio - 12):marca.inicio].rstrip().lower().endswith(("inciso", "incisos")):
                continue  # "o disposto no inciso III - …" cita, não abre
            # A lista de incisos começa no I (ou no II, se o I saiu tachado inteiro) e não salta muito.
            if n < ultimo_inc or (not ultimo_inc and n > 2) or (ultimo_inc and n > ultimo_inc + 5):
                continue
            ultimo_inc, ultima_al = n, ""
        else:
            if marca.valor < ultima_al or (ultima_al and ord(marca.valor) > ord(ultima_al) + 3):
                continue
            if not ultima_al and marca.valor != "a":
                continue
            ultima_al = marca.valor
        aceitas.append(marca)
    return aceitas


class DispositivoNaoEncontrado(LookupError):
    pass


class DispositivoAmbiguo(LookupError):
    """O mesmo parágrafo, inciso ou alínea aparece mais de uma vez: a página deixou a redação antiga sem
    tachar ao lado da nova (acontece no Código Florestal). Escolher uma delas seria adivinhar."""


def repeticoes(texto: str) -> list[str]:
    """Dispositivos repetidos no trecho (mesmo parágrafo, ou mesmo inciso no mesmo parágrafo)."""
    vistos: set[tuple[str, str, str]] = set()
    repetidos: list[str] = []
    paragrafo, inciso = "caput", ""
    plano = normalizar(texto)
    for marca in _marcas(plano):
        if marca.tipo == "paragrafo":
            paragrafo, inciso = marca.valor, ""
            chave = ("paragrafo", "", marca.valor)
        elif marca.tipo == "inciso":
            inciso = marca.valor
            chave = ("inciso", paragrafo, marca.valor)
        else:
            chave = ("alinea", f"{paragrafo}/{inciso}", marca.valor)
        if chave in vistos:
            nome = {"paragrafo": "§ ", "inciso": "inciso ", "alinea": "alínea "}[chave[0]] + chave[2]
            repetidos.append(nome if chave[0] == "paragrafo" else f"{nome} (em {chave[1]})")
        vistos.add(chave)
    # Aqui sem o filtro de ordem de _marcas: um "Parágrafo único" depois do § 6º é justamente o sintoma.
    paragrafos = ["unico" if m.group("unico") else m.group("num") for m in _PARAGRAFO.finditer(plano)]
    if "unico" in paragrafos and any(p != "unico" for p in paragrafos):
        # Parágrafo único ao lado de §§ numerados: sobra de redação antiga (art. 11 da LAI traz o antigo
        # parágrafo único do art. 12).
        repetidos.append("parágrafo único junto de §§ numerados")
    # Duas linhas de pena no mesmo dispositivo: a pena antiga ficou sem tachado ao lado da nova
    # (art. 24-A da Lei 11.340/2006, na coleta de 21/10/2026).
    marcas = [m.inicio for m in _marcas(plano) if m.tipo == "paragrafo"]
    for ini, fim in zip([0, *marcas], [*marcas, len(plano)], strict=False):
        if len(_PENA.findall(plano[ini:fim])) > 1:
            repetidos.append("linha de pena" + (" (no caput)" if ini == 0 else ""))
    return repetidos


_PENA = re.compile(r"\bPena\s*[-–—:]")


def localizar(texto_artigo: str, ref: Ref) -> str:
    """Trecho do artigo que corresponde à referência, com os dispositivos subordinados.

    Levanta `DispositivoNaoEncontrado` quando o parágrafo, inciso ou alínea não está no texto:
    o chamador registra a lacuna em vez de adivinhar.
    """
    texto = normalizar(texto_artigo)
    if ref.paragrafo is None and ref.inciso is None:
        return texto
    marcas = _marcas(texto)
    paragrafos = [m for m in marcas if m.tipo == "paragrafo"]

    # 1) O recipiente: o caput (até o primeiro parágrafo) ou o parágrafo pedido.
    if ref.paragrafo in (None, "caput"):
        ini, fim = 0, paragrafos[0].inicio if paragrafos else len(texto)
    else:
        candidatos = [m for m in paragrafos if m.valor == ref.paragrafo]
        if len(candidatos) > 1:
            raise DispositivoAmbiguo(f"{ref.rotulo()}: o parágrafo aparece {len(candidatos)} vezes")
        alvo = candidatos[0] if candidatos else None
        if alvo is None:
            raise DispositivoNaoEncontrado(f"{ref.rotulo()}: parágrafo não encontrado")
        seguintes = [m.inicio for m in paragrafos if m.inicio > alvo.inicio]
        ini, fim = alvo.inicio, seguintes[0] if seguintes else len(texto)
    if ref.inciso is None:
        return texto[ini:fim].strip()

    # 2) O inciso dentro do recipiente.
    dentro = [m for m in marcas if ini <= m.inicio < fim]
    incisos = [m for m in dentro if m.tipo == "inciso"]
    candidatos = [m for m in incisos if m.valor == ref.inciso]
    if len(candidatos) > 1:
        raise DispositivoAmbiguo(f"{ref.rotulo()}: o inciso aparece {len(candidatos)} vezes")
    alvo = candidatos[0] if candidatos else None
    if alvo is None:
        raise DispositivoNaoEncontrado(f"{ref.rotulo()}: inciso não encontrado")
    seguintes = [m.inicio for m in incisos if m.inicio > alvo.inicio]
    ini_inc, fim_inc = alvo.inicio, seguintes[0] if seguintes else fim
    if ref.alinea is None:
        return texto[ini_inc:fim_inc].strip()

    # 3) A alínea dentro do inciso.
    alineas = [m for m in dentro if m.tipo == "alinea" and ini_inc <= m.inicio < fim_inc]
    alvo_al = next((m for m in alineas if m.valor == ref.alinea), None)
    if alvo_al is None:
        raise DispositivoNaoEncontrado(f"{ref.rotulo()}: alínea não encontrada")
    seguintes = [m.inicio for m in alineas if m.inicio > alvo_al.inicio]
    return texto[alvo_al.inicio:seguintes[0] if seguintes else fim_inc].strip()


def enunciado_do_paragrafo(texto_artigo: str, paragrafo: str) -> str:
    """O parágrafo sem os incisos ("§ 3º Em três anos:"): contexto de um inciso do parágrafo."""
    trecho = localizar(texto_artigo, Ref("0", paragrafo))
    marcas = [m for m in _marcas(trecho) if m.tipo == "inciso"]
    return trecho[: marcas[0].inicio].strip() if marcas else trecho


def enunciado_do_caput(texto_artigo: str) -> str:
    """O caput sem os incisos ("Art. 7º São direitos …:"): contexto de um inciso citado sozinho."""
    texto = normalizar(texto_artigo)
    marcas = _marcas(texto)
    fim = marcas[0].inicio if marcas else len(texto)
    return texto[:fim].strip()
