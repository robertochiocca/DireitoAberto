"""Monitor legislativo como fluxo operacional (ciclo P3 da rodada 9.0), sem rede.

Cobre o que a auditoria de 22/10/2026 confirmou e o código antigo errava: anotação de efeito jurídico
aceita como editorial; revogação total engolida como coleta suspeita; rótulo de artigo riscado
atribuído ao artigo anterior; retorno a um texto antigo ignorado; decisão fora de ordem que voltava o
ponteiro no tempo; registro gravado 0600; escritas concorrentes perdidas; código de saída sempre 0.
"""

import importlib.util
import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from app.monitor import alertas, coleta, eventos
from app.monitor.artigos import dividir, tachados
from app.monitor.comparar import classificar, comparar
from app.monitor.impacto import afetados_pela_fonte, ato_citado, indice_de_dependencias
from app.monitor.registro import DecisaoInvalida, Registro, RegistroAlteradoPorOutroProcesso, RegistroOcupado
from app.monitor.servico import verificar
from app.monitor.sinais import fonte_desatualizada

BACKEND = Path(__file__).resolve().parents[1]
URL_CDC = "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"
FONTE = {"id": "cdc", "nome": "CDC (página sintética)", "url": URL_CDC, "orgao_emissor": "teste"}
ARTIGOS = [f"Art. {i}º Texto do artigo {i} sobre a proteção do consumidor nas relações de consumo." for i in range(1, 11)]
REVOGADO = "(Revogado pela Lei nº 15.000, de 2026)"


def pagina(*artigos: str, cabecalho: str = "", titulo: str = "LEI Nº 8.078, DE 11 DE SETEMBRO DE 1990.") -> bytes:
    corpo = "".join(f"<p>{a}</p>" for a in artigos)
    return (f"<html><head><meta charset='utf-8'></head><body><p>{titulo}</p>{cabecalho}{corpo}"
            "<p>Brasília, 11 de setembro de 1990.</p><p>Este texto não substitui o publicado no DOU de 12.9.1990</p>"
            "</body></html>").encode()


@pytest.fixture
def registro(tmp_path, monkeypatch):
    (tmp_path / "fontes.json").write_text(json.dumps({"fontes": [FONTE]}), encoding="utf-8")
    monkeypatch.setenv("DIREITO_ABERTO_MONITOR_DIR", str(tmp_path))
    return Registro(tmp_path)


def _verificar(registro, html: bytes, **extra) -> dict:
    r = verificar(FONTE, registro, baixar=lambda _url: html, **extra)
    registro.salvar()
    return r


def _tipos(registro, versao: str) -> dict[str, str]:
    return {m["artigo"]: m["tipo"] for m in registro.versao(versao)["mudancas"]}


# ---------------------------------------------------------------- 1. anotações com efeito jurídico
@pytest.mark.parametrize("anotacao, tipo, risco", [
    ("(Declarado inconstitucional pela ADI nº 1.234)", "anotacao_de_controle_constitucional", "alto"),
    ("(Suspensa a eficácia pela ADI 9.999)", "anotacao_de_controle_constitucional", "alto"),
    ("(Vide ADI nº 4424)", "anotacao_de_controle_constitucional", "alto"),
    ("(Vigência)", "anotacao_de_vigencia", "medio"),
    ("(Produção de efeitos)", "anotacao_de_vigencia", "medio"),
    ("(Promulgação partes vetadas)", "anotacao_de_vigencia", "medio"),
    ("(Vide Lei nº 15.100, de 2026)", "remissao_a_norma_nova", "medio"),
    ("(Vide Medida Provisória nº 1.400, de 2026)", "remissao_a_norma_nova", "medio"),
    # Só navegação continua de baixo risco: decreto regulamenta, não muda lei.
    ("(Vide Decreto nº 1, de 2021)", "anotacao_editorial", "baixo"),
    ("(Regulamento)", "anotacao_editorial", "baixo"),
])
def test_anotacao_com_efeito_juridico_nao_e_editorial(anotacao, tipo, risco):
    m = classificar("4", "Art. 4º Vigora na publicação.", f"Art. 4º Vigora na publicação. {anotacao}")
    assert (m.tipo, m.risco) == (tipo, risco)
    assert m.anotacoes_novas == [anotacao]


def test_anotacao_de_vigencia_vai_para_revisao(registro):
    _verificar(registro, pagina(*ARTIGOS))
    alterado = [*ARTIGOS[:3], ARTIGOS[3] + " (Declarado inconstitucional pela ADI nº 1.234)", *ARTIGOS[4:]]
    r = _verificar(registro, pagina(*alterado))
    assert r["estado"] == "pendente_revisao"  # antes: aceita automaticamente como "editorial"
    assert [e["tipo"] for e in r["eventos"]] == ["controle_constitucionalidade"]


# ---------------------------------------------------------------- 2 e 14. revogação total e artigo riscado
def _comparar_paginas(antes: bytes, depois: bytes) -> dict:
    """Compara como o serviço compara: com os artigos que a página nova mostra riscados."""
    novos = dividir(coleta.texto_vigente(depois))
    riscados = tachados(novos, dividir(coleta.texto_com_tachado(depois)))
    return {m.artigo: m for m in comparar(dividir(coleta.texto_vigente(antes)), novos, riscados)}


def test_rotulo_riscado_e_reatribuido_ao_artigo_revogado():
    um = pagina(*ARTIGOS[:2], f"<strike>{ARTIGOS[2]}</strike> {REVOGADO}", *ARTIGOS[3:])
    assert {k: m.tipo for k, m in _comparar_paginas(pagina(*ARTIGOS), um).items()} == {"3": "indicio_revogacao"}
    # Dois seguidos: uma anotação para cada um, na ordem.
    dois = pagina(*ARTIGOS[:2], f"<strike>{ARTIGOS[2]}</strike> {REVOGADO}",
                  f"<strike>{ARTIGOS[3]}</strike> (Revogado pela Lei nº 15.001, de 2026)", *ARTIGOS[4:])
    mudancas = _comparar_paginas(pagina(*ARTIGOS), dois)
    assert set(mudancas) == {"3", "4"}
    assert mudancas["3"].normas_citadas == ["Lei nº 15.000/2026"]
    assert mudancas["4"].normas_citadas == ["Lei nº 15.001/2026"]
    # Só o art. 1º revogado: a anotação cola no preâmbulo e volta para o art. 1º — não é revogação da norma.
    primeiro = pagina(f"<strike>{ARTIGOS[0]}</strike> {REVOGADO}", *ARTIGOS[1:])
    assert {k: m.tipo for k, m in _comparar_paginas(pagina(*ARTIGOS), primeiro).items()} == {"1": "indicio_revogacao"}


def test_alteracao_no_artigo_anterior_nao_vira_revogacao():
    """Revisão de 22/10/2026: o art. 2º alterado ficava "revogado" e a alteração sumia."""
    html = pagina(ARTIGOS[0], "Art. 2º Texto novo. (Redação dada pela Lei nº 15.000, de 2026)",
                  f"<strike>{ARTIGOS[2]}</strike> {REVOGADO}", *ARTIGOS[3:])
    tipos = {k: m.tipo for k, m in _comparar_paginas(pagina(*ARTIGOS), html).items()}
    assert tipos == {"2": "indicio_alteracao_legislativa", "3": "indicio_revogacao"}
    # Dois riscados e uma só anotação: não dá para saber de quem é; o art. 2º não leva a culpa.
    html = pagina(*ARTIGOS[:2], f"<strike>{ARTIGOS[2]}</strike> {REVOGADO}", f"<strike>{ARTIGOS[3]}</strike>",
                  *ARTIGOS[4:])
    assert {k: m.tipo for k, m in _comparar_paginas(pagina(*ARTIGOS), html).items()} == {
        "3": "artigo_tachado_na_pagina", "4": "artigo_tachado_na_pagina"}


def test_artigo_que_some_sem_estar_riscado_nao_e_reatribuido():
    html = pagina(*ARTIGOS[:2], REVOGADO, *ARTIGOS[3:])  # sem prova de que o art. 3º foi riscado
    tipos = {k: m.tipo for k, m in _comparar_paginas(pagina(*ARTIGOS), html).items()}
    assert tipos["3"] == "artigo_ausente_na_pagina"  # "ausente" não é revogação


def test_artigo_so_riscado_e_indicio_de_revogacao(registro):
    _verificar(registro, pagina(*ARTIGOS))
    r = _verificar(registro, pagina(*ARTIGOS[:5], f"<strike>{ARTIGOS[5]}</strike>", *ARTIGOS[6:]))
    assert _tipos(registro, r["versao"]) == {"6": "artigo_tachado_na_pagina"}
    assert [e["tipo"] for e in r["eventos"]] == ["revogacao_parcial"]


def test_revogacao_em_massa_nao_e_coleta_suspeita(registro):
    _verificar(registro, pagina(*ARTIGOS))
    metade = pagina(*ARTIGOS[:5], *[f"<strike>{a}</strike> {REVOGADO}" for a in ARTIGOS[5:]])
    r = _verificar(registro, metade)  # antes: "coleta_suspeita", sem versão nem alerta
    assert r["resultado"] == "nova_versao" and r["estado"] == "pendente_revisao"
    assert set(_tipos(registro, r["versao"]).values()) == {"indicio_revogacao"}


def test_pagina_cortada_continua_suspeita(registro):
    _verificar(registro, pagina(*ARTIGOS))
    assert _verificar(registro, pagina(*ARTIGOS[:3]))["resultado"] == "coleta_suspeita"


@pytest.mark.parametrize("cabecalho, riscar", [
    (f"<p>{REVOGADO}</p>", True),                                  # cabeçalho e tudo riscado (Lei 8.666)
    ("<p>Vigência Revogada pela Lei nº 15.000, de 2026</p>", False),  # só o cabeçalho (CPC de 1973)
    ("", True),                                                    # tudo riscado, sem cabeçalho
])
def test_revogacao_total_vira_pendencia_de_risco_alto(registro, cabecalho, riscar):
    _verificar(registro, pagina(*ARTIGOS))
    corpo = [f"<strike>{a}</strike>" for a in ARTIGOS] if riscar else ARTIGOS
    r = _verificar(registro, pagina(*corpo, cabecalho=cabecalho))
    assert r["resultado"] == "nova_versao" and r["estado"] == "pendente_revisao"
    v = registro.versao(r["versao"])
    assert v["mudancas"][0]["artigo"] == "norma" and v["mudancas"][0]["tipo"] == "indicio_revogacao_total"
    assert [e["tipo"] for e in v["eventos"]] == ["revogacao_total"]  # não vira também "revogação parcial"
    if cabecalho:
        assert v["mudancas"][0]["normas_citadas"] == ["Lei nº 15.000/2026"]
    assert registro.versao_aceita("cdc")["estado"] == "linha_de_base"  # nada aceito sozinho


def test_primeira_captura_de_pagina_revogada_nao_vira_linha_de_base(registro):
    r = _verificar(registro, pagina(*[f"<strike>{a}</strike>" for a in ARTIGOS], cabecalho=f"<p>{REVOGADO}</p>"))
    assert r["estado"] == "pendente_revisao" and registro.versao_aceita("cdc") is None


def test_pagina_de_erro_continua_nao_sendo_revogacao(registro):
    _verificar(registro, pagina(*ARTIGOS))
    r = _verificar(registro, b"<html><body><p>Servico indisponivel</p></body></html>")
    assert r["resultado"] == "coleta_suspeita" and len(registro.versoes_da_fonte("cdc")) == 1


def test_titulo_de_outro_ato_e_coleta_suspeita(registro):
    _verificar(registro, pagina(*ARTIGOS))
    r = _verificar(registro, pagina(*ARTIGOS, titulo="LEI Nº 9.099, DE 26 DE SETEMBRO DE 1995."))
    assert r["resultado"] == "coleta_suspeita" and "título" in r["detalhe"]
    assert len(registro.versoes_da_fonte("cdc")) == 1


# ---------------------------------------------------------------- 8 e 9. retorno e decisões fora de ordem
def test_retorno_a_texto_antigo_vira_evento_pendente(registro):
    base = _verificar(registro, pagina(*ARTIGOS))["versao"]
    mp = [*ARTIGOS[:3], "Art. 4º Texto da medida provisória. (Redação dada pela Medida Provisória nº 1.400, de 2026)",
          *ARTIGOS[4:]]
    nova = _verificar(registro, pagina(*mp))["versao"]
    registro.decidir(nova, "corpus_atualizado", "Fulana", "MP conferida no DOU")
    r = _verificar(registro, pagina(*ARTIGOS))  # a MP caducou: a página volta ao texto antigo
    assert r["resultado"] == "nova_versao" and r["estado"] == "pendente_revisao"  # antes: "versao_ja_registrada"
    assert r["versao"] == f"{base}-2"
    v = registro.versao(r["versao"])
    assert v["mudancas"][0]["tipo"] == "retorno_a_versao_anterior" and v["anterior"] == nova
    assert registro.ler_snapshot("cdc", r["versao"]) == registro.ler_snapshot("cdc", base)
    # A mesma página de novo: já está na fila, não duplica.
    assert _verificar(registro, pagina(*ARTIGOS))["resultado"] == "versao_ja_registrada"
    registro.decidir(r["versao"], "corpus_atualizado", "Fulana", "MP perdeu a validade")
    assert _verificar(registro, pagina(*ARTIGOS))["resultado"] == "sem_mudanca"


def test_decisao_fora_de_ordem_nao_volta_o_ponteiro(registro):
    _verificar(registro, pagina(*ARTIGOS))
    a = _verificar(registro, pagina(*ARTIGOS[:3], f"Art. 4º Primeira mudança. {REVOGADO.replace('Revogado', 'Redação dada')}",
                                    *ARTIGOS[4:]))["versao"]
    b = _verificar(registro, pagina(*ARTIGOS[:3], "Art. 4º Segunda mudança. (Redação dada pela Lei nº 15.001, de 2026)",
                                    *ARTIGOS[4:]))["versao"]
    registro.decidir(b, "corpus_atualizado", "Fulana")
    v = registro.decidir(a, "corpus_atualizado", "Fulana")  # capturada antes de b, decidida depois
    assert v["estado"] == "superada" and registro.versao_aceita("cdc")["versao"] == b
    assert registro.dados["diario"][-1]["acao"] == "decisao:corpus_atualizado:superada"


def test_confirmacao_humana_de_versao_aceita_automaticamente(registro):
    _verificar(registro, pagina(*ARTIGOS))
    auto = _verificar(registro, pagina(ARTIGOS[0].replace("Texto", "TEXTO"), *ARTIGOS[1:]))["versao"]
    assert registro.publicavel(auto) is not None  # ninguém conferiu
    with pytest.raises(DecisaoInvalida):
        registro.decidir(auto, "rejeitada", "Fulana")  # desfazer é reverter
    registro.decidir(auto, "sem_impacto", "Fulana", "só maiúsculas")
    assert registro.publicavel(auto) is None and registro.versao(auto)["estado"] == "aceita"


def test_so_a_versao_aceita_hoje_e_decidida_por_pessoa_e_publicavel(registro):
    base = _verificar(registro, pagina(*ARTIGOS))["versao"]
    assert "não foi decidida por uma pessoa" in registro.publicavel(base)
    nova = _verificar(registro, pagina(*ARTIGOS[:3], "Art. 4º Mudou. (Redação dada pela Lei nº 15.000, de 2026)",
                                       *ARTIGOS[4:]))["versao"]
    assert "não é a aceita hoje" in registro.publicavel(nova)
    registro.decidir(nova, "corpus_atualizado", "Fulana")
    assert registro.publicavel(nova) is None
    registro.reverter("cdc", "Fulana", "teste")
    assert "não é a aceita hoje" in registro.publicavel(nova)


# ---------------------------------------------------------------- 7 e 15. concorrência e permissões
def test_gravacao_concorrente_e_recusada(registro, tmp_path):
    _verificar(registro, pagina(*ARTIGOS))
    outro = Registro(tmp_path)  # outro processo leu o mesmo arquivo
    registro.registrar_verificacao("cdc", "sem_mudanca")
    registro.salvar()
    outro.registrar_verificacao("cdc", "falha_de_coleta", "HTTP 503")
    with pytest.raises(RegistroAlteradoPorOutroProcesso):
        outro.salvar()  # antes: sobrescrevia a escrita do primeiro
    outro.recarregar()
    outro.registrar_verificacao("cdc", "falha_de_coleta", "HTTP 503")
    outro.salvar()


def test_trava_exclusiva_entre_processos(registro, tmp_path):
    fcntl = pytest.importorskip("fcntl")
    with open(tmp_path / ".registro.lock", "a+") as arquivo:  # outro processo segurando a trava
        fcntl.flock(arquivo, fcntl.LOCK_EX)
        with pytest.raises(RegistroOcupado):
            with registro.travar(espera_s=0.3):
                pass
        fcntl.flock(arquivo, fcntl.LOCK_UN)
    with registro.travar(), registro.travar():  # reentrante no mesmo objeto
        registro.salvar()


def test_registro_respeita_a_umask(registro):
    antiga = os.umask(0o022)
    try:
        _verificar(registro, pagina(*ARTIGOS))
    finally:
        os.umask(antiga)
    assert stat.S_IMODE(registro.caminho.stat().st_mode) == 0o644  # antes: 0600 (arquivo temporário)


# ---------------------------------------------------------------- 12. retentativas e endereço final
def _resposta(status: int, url: str = URL_CDC, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, content=b"<p>ok</p>", headers=headers, request=httpx.Request("GET", url))


def _get(respostas: list):
    chamadas = []

    def get(url, **_):
        chamadas.append(url)
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    return get, chamadas


def test_falha_passageira_e_repetida_com_espera_crescente():
    esperas: list[float] = []
    get, chamadas = _get([_resposta(503), httpx.ConnectTimeout("t"), _resposta(200)])
    assert coleta.baixar(URL_CDC, get=get, dormir=esperas.append) == b"<p>ok</p>"
    assert len(chamadas) == 3 and len(esperas) == 2 and esperas[0] < esperas[1]


def test_retry_after_e_respeitado():
    esperas: list[float] = []
    get, _ = _get([_resposta(429, headers={"Retry-After": "7"}), _resposta(200)])
    coleta.baixar(URL_CDC, get=get, dormir=esperas.append)
    assert esperas == [7.0]
    get, _ = _get([_resposta(503, headers={"Retry-After": "3600"})])
    with pytest.raises(coleta.FalhaDeColeta, match="próxima rodada"):
        coleta.baixar(URL_CDC, get=get, dormir=esperas.append)  # espera longa não é cumprida na rodada
    assert esperas == [7.0]
    quando = datetime(2026, 10, 22, 12, 0, 30, tzinfo=timezone.utc)
    assert coleta.espera_pedida("Thu, 22 Oct 2026 12:00:30 GMT", agora=quando - timedelta(seconds=30)) == 30.0
    assert coleta.espera_pedida("amanhã") is None


def test_bloqueio_e_pagina_inexistente_nao_sao_repetidos():
    for status in (403, 404):
        get, chamadas = _get([_resposta(status)])
        with pytest.raises(coleta.FalhaDeColeta, match=f"HTTP {status}"):
            coleta.baixar(URL_CDC, get=get, dormir=lambda _s: None)
        assert len(chamadas) == 1


def test_tres_falhas_de_rede_viram_falha_de_coleta():
    get, chamadas = _get([httpx.ConnectError("x")] * 3)
    with pytest.raises(coleta.FalhaDeColeta, match="depois de 3 tentativas"):
        coleta.baixar(URL_CDC, get=get, dormir=lambda _s: None)
    assert len(chamadas) == 3


def test_redirecionamento_para_outro_site_nao_e_a_norma():
    get, _ = _get([_resposta(200, url="https://captcha.exemplo.com/desafio")])
    with pytest.raises(coleta.FalhaDeColeta, match="outro site"):
        coleta.baixar(URL_CDC, get=get, dormir=lambda _s: None)
    get, _ = _get([_resposta(200, url=URL_CDC.replace("https://www.", "http://"))])
    assert coleta.baixar(URL_CDC, get=get, dormir=lambda _s: None)  # mesmo site, sem "www"


# ---------------------------------------------------------------- 5. simulação
def test_simulacao_calcula_tudo_e_nao_grava_nada(registro, tmp_path):
    _verificar(registro, pagina(*ARTIGOS))
    antes = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    conteudo = registro.caminho.read_bytes()
    alterado = [*ARTIGOS[:3], "Art. 4º Mudou. (Redação dada pela Lei nº 15.000, de 2026)", *ARTIGOS[4:]]
    r = verificar(FONTE, registro, baixar=lambda _u: pagina(*alterado), simular=True)
    assert r["resultado"] == "nova_versao" and r["versao_calculada"]["mudancas"][0]["tipo"] == \
        "indicio_alteracao_legislativa"
    assert "Indício de alteração legislativa" in r["relatorio_md"]
    registro.salvar()  # mesmo salvando depois, a simulação não deixou nada no objeto
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == antes
    assert json.loads(registro.caminho.read_bytes())["versoes"] == json.loads(conteudo)["versoes"]
    assert registro.dados["verificacoes"]["cdc"]["resultado"] == "linha_de_base"


# ---------------------------------------------------------------- leitura 2: tachado por estilo
def test_pagina_igual_lida_de_outro_jeito_e_releitura(registro):
    html = pagina(*ARTIGOS[:4], f"<span style='text-decoration:line-through'>{ARTIGOS[4]}</span>", *ARTIGOS[5:])
    texto_antigo = coleta.texto_vigente(html, leitura=1)  # versão aceita gravada com a leitura antiga
    import hashlib

    h = hashlib.sha256(texto_antigo.encode()).hexdigest()
    registro.registrar_versao({"fonte": "cdc", "versao": h[:16], "hash_sha256": h, "url": URL_CDC,
                               "capturada_em": "2026-10-21T00:00:00+00:00", "titulo": None, "artigos": 10,
                               "estado": "linha_de_base", "anterior": None, "mudancas": []}, texto_antigo)
    r = _verificar(registro, html)
    v = registro.versao(r["versao"])
    assert v["releitura"] is True and v["leitura"] == coleta.LEITURA and r["estado"] == "pendente_revisao"
    assert {m["tipo"] for m in v["mudancas"]} == {"tachado_por_estilo_retirado"}
    assert v["eventos"] == []  # leitura corrigida não é evento jurídico


# ---------------------------------------------------------------- 10 e 11. dependências e eventos
def test_indice_de_dependencias_usa_dispositivos_adicionais_e_norma_alteradora():
    fontes = [FONTE, {"id": "lei13146", "nome": "LBI", "url": "https://www.planalto.gov.br/l13146.htm"}]
    normas = [{"id": "lei13146", "tipo": "lei", "numero": "13.146"}]
    corpus = [
        {"id": "cdc-18", "artigo": "Art. 18", "fonte": URL_CDC, "norma": "cdc", "dispositivos": [{"artigo": "18"}]},
        {"id": "cc-3-4", "artigo": "Arts. 3º e 4º", "fonte": "https://outra", "norma": "cc",
         "dispositivos_adicionais": [{"norma": "cdc", "artigo": "6"}],
         "vigencia": {"alterada_por": ["Lei 13.146/2015 (Estatuto da Pessoa com Deficiência)", "STF, ADI 4.277"]}},
    ]
    indice = indice_de_dependencias(corpus, fontes, normas)
    assert afetados_pela_fonte(indice, "cdc", {"18"}) == ["cdc-18"]
    assert afetados_pela_fonte(indice, "cdc", {"6"}) == ["cc-3-4"]  # antes: só a URL da própria entrada
    assert afetados_pela_fonte(indice, "lei13146", {"114"}) == ["cc-3-4"]
    assert afetados_pela_fonte(indice, "cdc", {"99"}) == []
    assert afetados_pela_fonte(indice, "cdc", {"99"}, norma_inteira=True) == ["cdc-18", "cc-3-4"]
    assert ato_citado("STF, ADI 4.277") is None and ato_citado("EC 141/2026") == ("emenda constitucional", "141")


def test_eventos_juridicos_nao_se_confundem():
    def m(tipo, artigo="1", normas=()):
        return {"tipo": tipo, "artigo": artigo, "normas_citadas": list(normas)}

    assert [e["tipo"] for e in eventos.derivar([], linha_de_base=True)] == ["inicio_do_monitoramento"]
    assert eventos.derivar([m("formatacao"), m("anotacao_editorial")]) == []
    tipos = [e["tipo"] for e in eventos.derivar([
        m("indicio_alteracao_legislativa", "2", ["Lei nº 15.000/2026"]), m("indicio_inclusao", "2-A"),
        m("indicio_revogacao", "3"), m("anotacao_de_vigencia", "4"), m("anotacao_de_controle_constitucional", "5"),
        m("texto_alterado_sem_norma_indicada", "6"), m("artigo_ausente_na_pagina", "7")])]
    assert tipos == ["alteracao_redacao", "inclusao", "revogacao_parcial", "entrada_em_vigor",
                     "controle_constitucionalidade", "consolidacao_ou_republicacao", "indeterminado"]


# ---------------------------------------------------------------- 13. atualidade
def test_fonte_desatualizada(registro, monkeypatch):
    agora = datetime.now(timezone.utc)
    nunca = fonte_desatualizada("cdc")  # está em fontes.json e nunca foi conferida: a base não tem a página
    assert nunca["ultima_verificacao_com_sucesso"] is None and "nunca" in nunca["motivo"]
    _verificar(registro, pagina(*ARTIGOS))
    assert fonte_desatualizada("cdc") is None
    assert fonte_desatualizada("cdc", agora=agora + timedelta(days=40))["dias_sem_verificacao"] == 40
    registro.registrar_verificacao("cdc", "falha_de_coleta", "HTTP 503")
    registro.salvar()  # falha não renova a atualidade
    atraso = fonte_desatualizada("cdc", agora=agora + timedelta(days=31))
    assert atraso["ultimo_resultado"] == "falha_de_coleta" and atraso["limite_dias"] == 30
    monkeypatch.setenv("DIREITO_ABERTO_MONITOR_DIAS_SEM_VERIFICACAO", "60")
    assert fonte_desatualizada("cdc", agora=agora + timedelta(days=31)) is None
    assert fonte_desatualizada("inexistente") is None
    assert len(registro.dados["historico_verificacoes"]["cdc"]) == 2


def test_fonte_desatualizada_aparece_na_api_e_na_validacao(registro, monkeypatch):
    from fastapi.testclient import TestClient

    from app import validacao
    from app.main import app
    from app.retrieval import Resultado

    _verificar(registro, pagina(*ARTIGOS))
    assert TestClient(app).get("/api/v1/monitor").json()["fontes"][0]["desatualizada"] is None
    monkeypatch.setenv("DIREITO_ABERTO_MONITOR_DIAS_SEM_VERIFICACAO", "-1")  # qualquer verificação já é velha
    assert TestClient(app).get("/api/v1/monitor").json()["fontes"][0]["desatualizada"]["fonte"] == "cdc"
    artigo = Resultado(id="cdc-18", lei="CDC", artigo="Art. 18", tema="consumidor", texto="t", resumo="r",
                       fonte=URL_CDC, score=99.0, norma="cdc",
                       vigencia={"status": "vigente", "conferida_em": "2026-10-16"})
    v = validacao.avaliar([artigo], datetime(2026, 10, 19).date())
    assert v["estado"] == "fonte_desatualizada_ou_indisponivel"
    assert "sem conferência recente do monitor" in next(x for x in v["verificacoes"] if x["nome"] == "atualidade")["detalhe"]


# ---------------------------------------------------------------- 3. códigos de saída, alertas e JSON
def _cli(tmp_path, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "scripts/monitor.py", *args], cwd=BACKEND, capture_output=True, text=True,
                          env={**os.environ, "DIREITO_ABERTO_MONITOR_DIR": str(tmp_path)})


def test_codigos_de_saida_alertas_e_resumo(registro, tmp_path):
    arquivo = tmp_path / "pagina.htm"
    arquivo.write_bytes(pagina(*ARTIGOS))
    r = _cli(tmp_path, "verificar", "--fonte", "cdc", "--arquivo", str(arquivo))
    assert r.returncode == 0, r.stderr  # linha de base: nada a revisar
    arquivo.write_bytes(pagina(*ARTIGOS[:3], "Art. 4º Mudou. (Redação dada pela Lei nº 15.000, de 2026)", *ARTIGOS[4:]))
    r = _cli(tmp_path, "verificar", "--fonte", "cdc", "--arquivo", str(arquivo), "--json", "-")
    assert r.returncode == 1, r.stderr  # antes: 0, sem alerta
    resumo = json.loads(r.stdout[r.stdout.index("{"):r.stdout.rindex("}") + 1])
    assert resumo["codigo_de_saida"] == 1 and resumo["novas_versoes"][0]["eventos"][0]["tipo"] == "alteracao_redacao"
    arquivo.write_bytes(b"<html><body>Erro 500</body></html>")
    r = _cli(tmp_path, "verificar", "--fonte", "cdc", "--arquivo", str(arquivo))
    assert r.returncode == 2, r.stderr
    gravados = sorted((tmp_path / "alertas").glob("*.json"))
    assert len(gravados) == 3
    ultimo = json.loads(gravados[-1].read_text(encoding="utf-8"))
    assert ultimo["falhas"][0]["resultado"] == "coleta_suspeita" and ultimo["pendentes_na_fila"]
    # Simulação: mesmo código, nenhum alerta novo.
    r = _cli(tmp_path, "verificar", "--fonte", "cdc", "--arquivo", str(arquivo), "--simular")
    assert r.returncode == 2 and len(list((tmp_path / "alertas").glob("*.json"))) == 3


def test_alertas_tem_retencao_limitada(tmp_path, monkeypatch):
    monkeypatch.setattr(alertas, "MAX_ALERTAS", 3)
    for em in ["2026-10-22T10:00:01+00:00", "2026-10-22T10:00:02+00:00", "2026-10-22T10:00:03+00:00",
               "2026-10-22T10:00:03+00:00", "2026-10-22T10:00:04+00:00"]:
        alertas.gravar(tmp_path, {"em": em})
    # O segundo alerta do mesmo segundo ("…Z-2") é mais novo que o primeiro e fica.
    assert sorted(p.name for p in (tmp_path / "alertas").glob("*.json")) == [
        "20261022T100003Z-2.json", "20261022T100003Z.json", "20261022T100004Z.json"]


def _modulo(nome: str):
    spec = importlib.util.spec_from_file_location(f"cli_{nome}", BACKEND / "scripts" / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_erro_numa_fonte_nao_interrompe_as_outras(registro, tmp_path, monkeypatch, capsys):
    segunda = {**FONTE, "id": "cdc2"}
    (tmp_path / "fontes.json").write_text(json.dumps({"fontes": [FONTE, segunda]}), encoding="utf-8")
    cli = _modulo("monitor")
    real = cli.verificar

    def defeituoso(fonte, reg, **kw):
        if fonte["id"] == "cdc":
            raise ZeroDivisionError("defeito no parser")
        return real(fonte, reg, **kw)

    monkeypatch.setattr(cli, "verificar", defeituoso)
    monkeypatch.setattr(cli.coleta, "baixar", lambda _url: pagina(*ARTIGOS))
    monkeypatch.setattr(cli.coleta, "INTERVALO_S", 0)
    args = type("A", (), {"fonte": None, "arquivo": None, "simular": False, "json": None})()
    assert cli.cmd_verificar(args, Registro(tmp_path)) == 2
    gravado = Registro(tmp_path)
    assert gravado.dados["verificacoes"]["cdc"]["resultado"] == "erro_interno"
    assert gravado.dados["verificacoes"]["cdc2"]["resultado"] == "linha_de_base"


# ---------------------------------------------------------------- 6. publicação controlada no corpus
@pytest.fixture
def corpus_temporario(registro, tmp_path, monkeypatch):
    """Corpus, histórico e loja num diretório temporário, com duas entradas reais sem a proveniência."""
    from app.corpus.proveniencia import CAMPOS_DE_PROVENIENCIA
    from app.retrieval import DATA_PATH

    cli = _modulo("corpus")
    dados = tmp_path / "dados"
    dados.mkdir()
    reais = {a["id"]: a for a in json.loads(Path(DATA_PATH).read_text(encoding="utf-8"))["artigos"]}
    entradas = [{k: v for k, v in reais[i].items() if k not in CAMPOS_DE_PROVENIENCIA} for i in ("cdc-18", "lei9099-3")]
    (dados / "legislacao.json").write_text(json.dumps({"artigos": entradas}, ensure_ascii=False), encoding="utf-8")
    for nome, valor in {"DATA_PATH": dados / "legislacao.json", "HISTORICO": dados / "corpus_historico.json",
                        "LOJA": dados / "corpus_versoes", "TRAVA": dados / ".corpus.lock",
                        "SEM_COLETA": dados / "normas_sem_coleta.json"}.items():
        monkeypatch.setattr(cli, nome, valor)
    assert cli.main(["registrar", "--responsavel", "Teste", "--motivo", "semente"]) == 0
    return cli, dados


def _corpus_de(dados: Path) -> dict[str, dict]:
    return {a["id"]: a for a in json.loads((dados / "legislacao.json").read_text(encoding="utf-8"))["artigos"]}


ART18 = ("Art. 18. Os fornecedores de produtos de consumo duráveis ou não duráveis respondem solidariamente pelos "
         "vícios de qualidade ou quantidade que os tornem impróprios ou inadequados ao consumo a que se destinam.")


def test_publicar_exige_decisao_humana_e_registra_versao_e_regressao(registro, corpus_temporario):
    cli, dados = corpus_temporario
    artigos = [*ARTIGOS[:9], ART18]
    base = _verificar(registro, pagina(*artigos))["versao"]

    def publicar(versao):
        return cli.main(["publicar", "--fonte", "cdc", "--versao", versao, "--responsavel", "Fulana",
                         "--motivo", "conferido no DOU"])

    assert publicar(base) == 1  # linha de base: ninguém revisou
    novo18 = ART18.replace("solidariamente", "subsidiariamente") + " (Redação dada pela Lei nº 15.000, de 2026)"
    nova = _verificar(registro, pagina(*artigos[:9], novo18))["versao"]
    assert publicar(nova) == 1  # pendente
    antes = _corpus_de(dados)
    registro.decidir(nova, "corpus_atualizado", "Fulana", "art. 18 conferido no DOU")
    registro.salvar()
    assert publicar(nova) == 0

    depois = _corpus_de(dados)
    trechos = depois["cdc-18"]["trechos_oficiais"]
    assert trechos and trechos[0]["versao_fonte"] == nova and "subsidiariamente" in trechos[0]["texto"]
    assert depois["lei9099-3"] == antes["lei9099-3"]  # entrada de outra fonte não é tocada
    evento = json.loads((dados / "corpus_historico.json").read_text(encoding="utf-8"))["eventos"][-1]
    assert evento["id"] == "cdc-18" and nova in evento["motivo"] and "regressão" in evento["motivo"]
    assert f"monitor:cdc:{nova}" in evento["evidencia"]
    assert Registro(registro.base).dados["diario"][-1]["acao"] == "publicacao_no_corpus"
    assert cli.problemas_de_integridade(Registro(registro.base)) == []
    # Reverter devolve a entrada ao conteúdo de antes da publicação (e registra a reversão).
    assert cli.main(["reverter", "--id", "cdc-18", "--responsavel", "Fulana", "--motivo", "teste"]) == 0
    assert "trechos_oficiais" not in _corpus_de(dados)["cdc-18"]


def test_publicar_nao_grava_nada_se_a_regressao_falhar(registro, corpus_temporario, monkeypatch):
    cli, dados = corpus_temporario
    _verificar(registro, pagina(*ARTIGOS[:9], ART18))
    nova = _verificar(registro, pagina(*ARTIGOS[:9], ART18 + " (Redação dada pela Lei nº 15.000, de 2026)"))["versao"]
    registro.decidir(nova, "sem_impacto", "Fulana")
    registro.salvar()
    monkeypatch.setattr(cli, "rodar_regressao", lambda ids, _r: [{"pergunta": "p", "esperado": ids[0], "ok": False}])
    antes = (dados / "legislacao.json").read_bytes(), (dados / "corpus_historico.json").read_bytes()
    assert cli.main(["publicar", "--fonte", "cdc", "--versao", nova, "--responsavel", "F", "--motivo", "m"]) == 1
    assert ((dados / "legislacao.json").read_bytes(), (dados / "corpus_historico.json").read_bytes()) == antes


def test_extrair_nao_usa_linha_de_base_sem_pedido_explicito(registro, corpus_temporario, capsys):
    cli, dados = corpus_temporario
    _verificar(registro, pagina(*ARTIGOS[:9], ART18))
    assert cli.main(["extrair", "--responsavel", "F", "--motivo", "m"]) == 0
    assert "trechos_oficiais" not in _corpus_de(dados)["cdc-18"]  # fonte só com linha de base: fica de fora
    assert "--incluir-linha-de-base" in capsys.readouterr().out
    assert cli.main(["extrair", "--responsavel", "F", "--motivo", "m", "--incluir-linha-de-base"]) == 0
    assert _corpus_de(dados)["cdc-18"]["trechos_oficiais"]


# ---------------------------------------------------------------- revisão adversarial de 22/10/2026
ERRO_QUE_CITA_REVOGACAO = ("<html><body><h1>Portal da Legislação</h1><p>A página solicitada não foi encontrada.</p>"
                           "<p>Destaques: Lei nº 8.666, de 1993 — Revogada pela Lei nº 14.133, de 2021.</p>"
                           "</body></html>").encode()


def test_pagina_de_erro_que_fala_de_revogacao_nao_e_revogacao(registro, tmp_path):
    """Ausência de evidência não é evidência: a página de erro não tem artigo nenhum, nem riscado."""
    assert _verificar(registro, ERRO_QUE_CITA_REVOGACAO)["resultado"] == "coleta_suspeita"  # primeira captura
    _verificar(registro, pagina(*ARTIGOS))
    r = _verificar(registro, ERRO_QUE_CITA_REVOGACAO)
    assert r["resultado"] == "coleta_suspeita" and len(registro.versoes_da_fonte("cdc")) == 1


def test_riscados_antigos_nao_completam_pagina_cortada(registro):
    """Na CLT real, quase 200 artigos riscados de sempre "completavam" uma página cortada em 65%."""
    antigos_riscados = [f"<strike>Art. {i}º Texto revogado há muito tempo.</strike> {REVOGADO}" for i in range(11, 31)]
    _verificar(registro, pagina(*ARTIGOS, *antigos_riscados))
    assert _verificar(registro, pagina(*ARTIGOS[:3], *antigos_riscados))["resultado"] == "coleta_suspeita"


def test_revogacao_ja_aceita_nao_e_sinalizada_de_novo(registro):
    revogada = [f"<strike>{a}</strike>" for a in ARTIGOS]
    _verificar(registro, pagina(*ARTIGOS))
    v = _verificar(registro, pagina(*revogada, cabecalho=f"<p>{REVOGADO}</p>"))["versao"]
    registro.decidir(v, "corpus_atualizado", "Fulana", "revogação conferida no DOU")
    assert registro.versao(v)["pagina_indica_revogacao_total"] is True
    # Depois de aceita, uma mudança só de forma na página não é "a página passou a indicar a revogação".
    formatada = pagina(*revogada, cabecalho=f"<p>{REVOGADO.upper()}</p>")
    r = _verificar(registro, formatada)
    assert r["estado"] == "aceita" and "revogacao_total" not in [e["tipo"] for e in r["eventos"]]


def test_texto_rejeitado_que_volta_depois_de_outra_versao_aceita_vai_para_revisao(registro):
    _verificar(registro, pagina(*ARTIGOS))
    b = pagina(*ARTIGOS[:4], "Art. 5º Texto estranho de página quebrada.", *ARTIGOS[5:])
    registro.decidir(_verificar(registro, b)["versao"], "rejeitada", "Fulana", "página quebrada")
    c = pagina(*ARTIGOS[:3], "Art. 4º Mudou. (Redação dada pela Lei nº 15.000, de 2026)", *ARTIGOS[4:])
    registro.decidir(_verificar(registro, c)["versao"], "corpus_atualizado", "Fulana")
    r = _verificar(registro, b)  # antes: "versao_ja_registrada", ninguém olhava
    assert r["resultado"] == "nova_versao" and r["estado"] == "pendente_revisao"
    assert registro.versao(r["versao"])["mudancas"][0]["tipo"] == "retorno_a_versao_anterior"


def test_mudanca_real_misturada_com_releitura_nao_inventa_evento(registro):
    """A aceita foi lida com a leitura 1; a página nova traz uma mudança real e texto riscado por estilo."""
    import hashlib

    riscado = "<span style='text-decoration:line-through'>Art. 5º Redação antiga do artigo cinco.</span>"
    antes = pagina(*ARTIGOS[:4], riscado, *ARTIGOS[4:])
    texto_antigo = coleta.texto_vigente(antes, leitura=1)
    h = hashlib.sha256(texto_antigo.encode()).hexdigest()
    registro.registrar_versao({"fonte": "cdc", "versao": h[:16], "hash_sha256": h, "url": URL_CDC,
                               "capturada_em": "2026-10-21T00:00:00+00:00", "titulo": None, "artigos": 11,
                               "estado": "linha_de_base", "anterior": None, "mudancas": []}, texto_antigo)
    depois = pagina(*ARTIGOS[:4], riscado, *ARTIGOS[4:8], ARTIGOS[8] + " (Declarado inconstitucional pela ADI nº 1)",
                    ARTIGOS[9])
    r = _verificar(registro, depois)
    v = registro.versao(r["versao"])
    # Lida do jeito antigo, a redação riscada por estilo era um segundo art. 5º ("5#2"): as duas diferenças são só
    # da leitura.
    assert {m["artigo"]: m["tipo"] for m in v["mudancas"]} == {
        "9": "anotacao_de_controle_constitucional", "5": "tachado_por_estilo_retirado",
        "5#2": "tachado_por_estilo_retirado"}
    assert [e["tipo"] for e in v["eventos"]] == ["controle_constitucionalidade"]  # o art. 5º não "mudou"


def test_riscado_sem_fim_e_coleta_suspeita(registro):
    _verificar(registro, pagina(*ARTIGOS))
    quebrada = pagina(ARTIGOS[0], "<span style='text-decoration:line-through'>" + "x " * 15_000, *ARTIGOS[1:])
    r = _verificar(registro, quebrada)
    assert r["resultado"] == "coleta_suspeita" and "riscado" in r["detalhe"]


def test_bloqueio_do_portal_para_a_rodada_naquele_site(registro, tmp_path, monkeypatch):
    segunda = {**FONTE, "id": "cdc2", "url": URL_CDC.replace("l8078", "l9099")}
    (tmp_path / "fontes.json").write_text(json.dumps({"fontes": [FONTE, segunda]}), encoding="utf-8")
    cli = _modulo("monitor")
    pedidos = []

    def bloqueado(url):
        pedidos.append(url)
        raise coleta.FalhaDeColeta("HTTP 403", bloqueio=True)

    monkeypatch.setattr(cli.coleta, "baixar", bloqueado)
    monkeypatch.setattr(cli.coleta, "INTERVALO_S", 0)
    args = type("A", (), {"fonte": None, "arquivo": None, "simular": False, "json": None})()
    assert cli.cmd_verificar(args, Registro(tmp_path)) == 2
    assert pedidos == [URL_CDC]  # a segunda página do mesmo site não foi pedida
    gravado = Registro(tmp_path).dados["verificacoes"]
    assert gravado["cdc2"]["resultado"] == "falha_de_coleta" and "bloqueou" in gravado["cdc2"]["detalhe"]


def test_fonte_desconhecida_sai_com_2(registro, tmp_path):
    r = _cli(tmp_path, "verificar", "--fonte", "nao-existe", "--simular")
    assert r.returncode == 2  # 1 quer dizer "revisão pendente"


def test_extrair_nao_usa_versao_aceita_automaticamente(registro, corpus_temporario):
    cli, dados = corpus_temporario
    _verificar(registro, pagina(*ARTIGOS[:9], ART18))
    auto = _verificar(registro, pagina(*ARTIGOS[:9], ART18.replace("Os fornecedores", "OS FORNECEDORES")))
    assert auto["estado"] == "aceita"  # só maiúsculas: aceita sem pessoa
    assert cli.main(["extrair", "--responsavel", "F", "--motivo", "m"]) == 0
    assert "trechos_oficiais" not in _corpus_de(dados)["cdc-18"]
    registro.decidir(auto["versao"], "sem_impacto", "Fulana", "conferido")  # pessoa confirma
    registro.salvar()
    assert cli.main(["extrair", "--responsavel", "F", "--motivo", "m"]) == 0
    assert _corpus_de(dados)["cdc-18"]["trechos_oficiais"][0]["versao_fonte"] == auto["versao"]


@pytest.mark.parametrize("texto, titulo", [
    ("LEI Nº 9.784 , DE 29 DE JANEIRO DE 1999.", "LEI Nº 9.784 , DE 29 DE JANEIRO DE 1999"),
    ("LEI\nN\no\n5.869, DE 11 DE JANEIRO DE 1973.", "LEI N o 5.869, DE 11 DE JANEIRO DE 1973"),  # CPC de 1973
    ("CONSTITUIÇÃO DA REPÚBLICA FEDERATIVA DO BRASIL DE 1988", "CONSTITUIÇÃO DA REPÚBLICA FEDERATIVA DO BRASIL DE 1988"),
])
def test_titulos_das_paginas_reais(texto, titulo):
    """Sem título, o sinal de revogação no cabeçalho não vale: a página do CPC de 1973 deixava de ser reconhecida."""
    assert coleta.metadados(texto)["titulo"] == titulo
