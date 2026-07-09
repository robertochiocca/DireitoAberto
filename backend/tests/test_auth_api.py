from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

USUARIO = {"email": "cidadao@example.com", "senha": "senha-super-secreta"}


def _token():
    resp = client.post("/api/v1/auth/registrar", json=USUARIO)
    if resp.status_code == 409:  # já registrado por outro teste
        resp = client.post("/api/v1/auth/entrar", json=USUARIO)
    return resp.json()["token"]


def test_registrar_e_entrar():
    token = _token()
    assert token
    resp = client.post("/api/v1/auth/entrar", json=USUARIO)
    assert resp.status_code == 200
    assert resp.json()["tipo"] == "bearer"


def test_registro_duplicado_retorna_409():
    _token()
    resp = client.post("/api/v1/auth/registrar", json=USUARIO)
    assert resp.status_code == 409


def test_senha_errada_retorna_401():
    _token()
    resp = client.post(
        "/api/v1/auth/entrar", json={"email": USUARIO["email"], "senha": "senha-errada-123"}
    )
    assert resp.status_code == 401


def test_historico_exige_token():
    assert client.get("/api/v1/historico").status_code == 401
    resp = client.get("/api/v1/historico", headers={"Authorization": "Bearer token-invalido"})
    assert resp.status_code == 401


def test_consulta_autenticada_entra_no_historico():
    token = _token()
    headers = {"Authorization": f"Bearer {token}"}
    pergunta = "Fui demitido sem justa causa e não recebi as verbas"
    resp = client.post("/api/v1/perguntar", json={"pergunta": pergunta}, headers=headers)
    assert resp.status_code == 200

    historico = client.get("/api/v1/historico", headers=headers).json()
    assert historico, "histórico não deveria estar vazio"
    assert historico[0]["pergunta"] == pergunta
    assert historico[0]["artigos_ids"], "consulta deveria registrar os artigos encontrados"


def test_consulta_anonima_nao_vaza_para_historico_de_usuario():
    token = _token()
    headers = {"Authorization": f"Bearer {token}"}
    antes = len(client.get("/api/v1/historico", headers=headers).json())
    client.post("/api/v1/perguntar", json={"pergunta": "multa de trânsito injusta"})  # sem token
    depois = len(client.get("/api/v1/historico", headers=headers).json())
    assert depois == antes
