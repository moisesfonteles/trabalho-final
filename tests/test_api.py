import json

import psycopg
from werkzeug.security import check_password_hash

import api
import db
from conftest import NOME_TESTE, SENHA_TESTE, USUARIO_TESTE


def _eventos(capsys):
    return [json.loads(linha) for linha in capsys.readouterr().out.strip().splitlines()]


def test_saude_e_publica(cliente_http, capsys):
    resposta = cliente_http.get("/api/web/health")
    assert resposta.status_code == 200
    assert resposta.get_json() == {"status": "ok"}
    assert resposta.headers["X-Request-ID"].startswith("req-")
    evento = _eventos(capsys)[-1]
    assert evento["layer"] == "api" and evento["operation"] == "health"


def test_login_sucesso_correlaciona_logs_api_e_banco(cliente_http, capsys):
    capsys.readouterr()
    resposta = cliente_http.post("/api/web/login", json={"usuario": USUARIO_TESTE, "senha": SENHA_TESTE})
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["usuario"] == USUARIO_TESTE and corpo["nome"] == NOME_TESTE and corpo["token"]

    eventos = _eventos(capsys)
    request_id = resposta.headers["X-Request-ID"]
    camadas = {e["layer"] for e in eventos if e["request_id"] == request_id}
    assert camadas == {"api", "db"}
    bruto = json.dumps(eventos)
    assert SENHA_TESTE not in bruto and corpo["token"] not in bruto


def test_login_senha_errada(cliente_http):
    resposta = cliente_http.post("/api/web/login", json={"usuario": USUARIO_TESTE, "senha": "errada"})
    assert resposta.status_code == 401


def test_login_usuario_inexistente(cliente_http):
    resposta = cliente_http.post("/api/web/login", json={"usuario": "ninguem", "senha": "x"})
    assert resposta.status_code == 401


def test_login_campos_ausentes(cliente_http):
    assert cliente_http.post("/api/web/login", json={"usuario": USUARIO_TESTE}).status_code == 400
    assert cliente_http.post("/api/web/login", data="não é json").status_code == 400
    assert cliente_http.post("/api/web/login", json={"usuario": 1, "senha": 2}).status_code == 400
    for corpo in ([1], "x", 5, None):
        assert cliente_http.post("/api/web/login", json=corpo).status_code == 400


def test_login_usuario_inexistente_tambem_verifica_hash(cliente_http, monkeypatch):
    verificados = []
    original = api.check_password_hash

    def espiar(senha_hash, senha):
        verificados.append(senha_hash)
        return original(senha_hash, senha)

    monkeypatch.setattr(api, "check_password_hash", espiar)
    resposta = cliente_http.post("/api/web/login", json={"usuario": "ninguem", "senha": "x"})
    assert resposta.status_code == 401
    assert verificados == [api.HASH_FICTICIO]


def test_erro_inesperado_responde_json_e_registra_log(cliente_http, monkeypatch, capsys):
    def falhar(*_args):
        raise KeyError("URL_BANCO")

    monkeypatch.setattr(db, "buscar_usuario", falhar)
    capsys.readouterr()
    resposta = cliente_http.post("/api/web/login", json={"usuario": USUARIO_TESTE, "senha": SENHA_TESTE})
    assert resposta.status_code == 500
    assert resposta.get_json() == {"erro": "Erro interno"}
    evento = _eventos(capsys)[-1]
    assert evento["level"] == "ERROR" and evento["layer"] == "api" and evento["operation"] == "web_login"


def test_rota_inexistente_mantem_404(cliente_http):
    assert cliente_http.get("/api/web/nao-existe").status_code == 404


def test_login_erro_no_banco(cliente_http, monkeypatch):
    def falhar(*_args):
        raise psycopg.OperationalError("fora do ar")

    monkeypatch.setattr(db, "buscar_usuario", falhar)
    resposta = cliente_http.post("/api/web/login", json={"usuario": USUARIO_TESTE, "senha": SENHA_TESTE})
    assert resposta.status_code == 500


def test_sessao_com_token_valido(cliente_http, token):
    resposta = cliente_http.get("/api/web/sessao", headers={"Authorization": f"Bearer {token}"})
    assert resposta.status_code == 200
    assert resposta.get_json() == {"usuario": USUARIO_TESTE, "nome": NOME_TESTE}


def test_sessao_sem_token(cliente_http):
    assert cliente_http.get("/api/web/sessao").status_code == 401


def test_sessao_com_token_invalido(cliente_http):
    resposta = cliente_http.get("/api/web/sessao", headers={"Authorization": "Bearer invalido"})
    assert resposta.status_code == 401


def test_inicializar_cria_usuario_inicial(monkeypatch):
    monkeypatch.setenv("ADMIN_USUARIO", "admin-inicial")
    monkeypatch.setenv("ADMIN_NOME", "Admin Inicial")
    monkeypatch.setenv("ADMIN_SENHA", "segredo")
    api.inicializar()
    with api.app.test_request_context():
        registro = db.buscar_usuario("admin-inicial", "req-inicial", "web")
    assert registro["nome"] == "Admin Inicial"
    assert registro["senha_hash"] != "segredo"
    assert check_password_hash(registro["senha_hash"], "segredo")


def test_criar_app_inicializa_e_devolve_app(monkeypatch):
    chamadas = []
    monkeypatch.setattr(api, "inicializar", lambda: chamadas.append("inicializar"))
    assert api.criar_app() is api.app
    assert chamadas == ["inicializar"]
