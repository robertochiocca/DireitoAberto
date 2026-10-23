"""Feedback controlado (app/feedback.py): entra numa fila de triagem humana e nunca muda nada sozinho."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Feedback, SessionLocal
from app.feedback import mascarar
from app.main import app
from app.retrieval import DATA_PATH
from app.seguranca import limitador

client = TestClient(app)


def _conta(email: str) -> str:
    resp = client.post("/api/v1/auth/registrar", json={"email": email, "senha": "senha-muito-segura"})
    assert resp.status_code == 201, resp.text
    return resp.json()["token"]


def _enviar(dispositivo="cdc-18", categoria="texto_nao_confere", comentario=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/v1/feedback", headers=headers,
                       json={"dispositivo_id": dispositivo, "categoria": categoria, "comentario": comentario})


def test_feedback_vai_para_a_fila_e_mascara_dado_pessoal():
    r = _enviar(comentario="Meu CPF é 123.456.789-09, processo 0001234-56.2026.8.26.0100, "
                           "e-mail maria@exemplo.com.br, telefone (11) 98765-4321. O art. 18 mudou.")
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "novo" and "não muda a resposta" in r.json()["aviso"]
    with SessionLocal() as db:
        f = db.get(Feedback, r.json()["id"])
        assert f.dispositivo_id == "cdc-18" and f.usuario_id is None
        for dado in ("123.456.789-09", "0001234-56.2026.8.26.0100", "maria@exemplo.com.br", "98765-4321"):
            assert dado not in f.comentario
        assert "O art. 18 mudou." in f.comentario


def test_mascarar_nao_apaga_numero_de_lei():
    texto = "A Lei 8.078/1990, art. 49, prazo de 7 dias; Lei nº 13.146, de 2015."
    assert mascarar(texto) == texto


def test_feedback_invalido_e_recusado():
    assert _enviar(dispositivo="nao-existe").status_code == 404
    assert _enviar(categoria="corrija_a_lei").status_code == 422
    assert _enviar(dispositivo="<script>").status_code == 422
    assert _enviar(comentario="x" * 601).status_code == 422


def test_feedback_tem_limite_por_endereco():
    limitador.resetar()
    codigos = [_enviar().status_code for _ in range(6)]
    assert codigos == [201] * 5 + [429]


def test_feedback_nao_muda_a_resposta_nem_a_base():
    """Dez relatos de "norma revogada" no mesmo dispositivo não mudam nada: viram prioridade na fila."""
    pergunta = {"pergunta": "A empresa não quer trocar meu notebook com defeito"}
    antes = client.post("/api/v1/perguntar", json=pergunta).json()
    corpus_antes = Path(DATA_PATH).read_bytes()
    for _ in range(10):
        limitador.resetar()
        assert _enviar(categoria="norma_revogada_ou_alterada").status_code == 201
    depois = client.post("/api/v1/perguntar", json=pergunta).json()
    for campo in ("resposta", "artigos", "validacao", "politica"):
        assert depois[campo] == antes[campo], campo
    assert Path(DATA_PATH).read_bytes() == corpus_antes


def test_feedback_da_conta_sai_na_exportacao_e_some_com_a_conta():
    token = _conta("feedback@example.com")
    assert _enviar(token=token, comentario="texto diferente do Planalto").status_code == 201
    dados = client.get("/api/v1/conta/exportar", headers={"Authorization": f"Bearer {token}"}).json()
    assert [f["comentario"] for f in dados["feedbacks"]] == ["texto diferente do Planalto"]
    resp = client.post("/api/v1/conta/excluir", json={"senha": "senha-muito-segura"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 204
    with SessionLocal() as db:
        assert not db.scalars(select(Feedback).where(Feedback.comentario == "texto diferente do Planalto")).all()


def test_retencao_apaga_feedback_velho(monkeypatch):
    from datetime import timedelta

    from app.db import agora
    from app.manutencao import expurgar

    with SessionLocal() as db:
        velho = Feedback(dispositivo_id="cdc-18", categoria="outro", criado_em=agora() - timedelta(days=400))
        novo = Feedback(dispositivo_id="cdc-18", categoria="outro")
        db.add_all([velho, novo])
        db.commit()
        ids = velho.id, novo.id
        assert expurgar(db)["feedbacks"] >= 1
        assert db.get(Feedback, ids[0]) is None and db.get(Feedback, ids[1]) is not None


def test_triagem_procedente_abre_revisao_registrada_no_corpus(tmp_path, monkeypatch, capsys):
    """A triagem humana é o único caminho de um feedback até o corpus — e só abre pendência de revisão."""
    import importlib.util
    import sys

    from app.corpus.proveniencia import carregar_historico, selo

    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend / "scripts"))
    corpus_cli = importlib.import_module("corpus")
    dados = tmp_path / "legislacao.json"
    entrada = {k: v for k, v in json.loads((backend / "data/legislacao.json").read_text(encoding="utf-8"))["artigos"][0].items()
               if k != "revisao"}
    dados.write_text(json.dumps({"artigos": [entrada]}, ensure_ascii=False), encoding="utf-8")
    for nome, valor in {"DATA_PATH": dados, "HISTORICO": tmp_path / "historico.json", "LOJA": tmp_path / "loja",
                        "TRAVA": tmp_path / ".corpus.lock"}.items():
        monkeypatch.setattr(corpus_cli, nome, valor)
    assert corpus_cli.main(["registrar", "--responsavel", "T", "--motivo", "semente"]) == 0

    spec = importlib.util.spec_from_file_location("feedback_cli", backend / "scripts" / "feedback.py")
    feedback_cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(feedback_cli)
    limitador.resetar()
    fid = _enviar(dispositivo=entrada["id"], categoria="texto_nao_confere").json()["id"]
    texto_antes = entrada["texto"]

    assert feedback_cli.main(["triar", "--id", str(fid), "--resultado", "improcedente", "--responsavel", "Ana",
                              "--nota", "n", "--abrir-revisao"]) == 1  # revisão só com procedente
    assert feedback_cli.main(["triar", "--id", str(fid), "--resultado", "procedente", "--responsavel", "Ana",
                              "--nota", "texto confere com a página? não: falta o § 2º", "--abrir-revisao"]) == 0
    gravada = json.loads(dados.read_text(encoding="utf-8"))["artigos"][0]
    assert gravada["revisao"]["estado"] == "pendente" and f"feedback #{fid}" in gravada["revisao"]["motivo"]
    assert gravada["texto"] == texto_antes  # o texto da lei não muda
    historico = carregar_historico(tmp_path / "historico.json")
    assert historico["eventos"][-1]["responsavel"] == "Ana" and f"feedback:{fid}" in historico["eventos"][-1]["evidencia"]
    assert historico["selos"][entrada["id"]]["selo"] == selo(gravada)
    assert feedback_cli.main(["triar", "--id", str(fid), "--resultado", "duplicado", "--responsavel", "Ana",
                              "--nota", "n"]) == 1  # já triado
