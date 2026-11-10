"""API REST (Flask) consumida pela Web e, futuramente, pela CLI."""

import os
import uuid
from functools import wraps

import psycopg
from flask import Flask, g, jsonify, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

import db

VALIDADE_TOKEN_WEB = 8 * 60 * 60  # 8 horas

# Hash usado quando o usuário não existe, para o login levar o mesmo tempo nos dois casos
# e não revelar quais usuários estão cadastrados.
HASH_FICTICIO = generate_password_hash("senha-ficticia")

app = Flask(__name__)


def registrar_log(nivel, origem, operacao, status, mensagem):
    """Registra um evento da camada de API com o request_id da requisição atual."""
    db.registrar_log(nivel, origem, operacao, status, g.request_id, mensagem, camada="api")


def serializador_web():
    return URLSafeTimedSerializer(os.environ["CHAVE_SECRETA"], salt="sessao-web")


@app.before_request
def atribuir_request_id():
    g.request_id = f"req-{uuid.uuid4().hex[:12]}"


@app.after_request
def expor_request_id(resposta):
    resposta.headers["X-Request-ID"] = g.request_id
    return resposta


def exigir_autenticacao_web(operacao):
    """Exige `Authorization: Bearer <token>` válido emitido por /api/web/login."""

    def decorador(rota):
        @wraps(rota)
        def envoltorio(*args, **kwargs):
            cabecalho = request.headers.get("Authorization", "")
            if not cabecalho.startswith("Bearer "):
                registrar_log("WARN", "web", operacao, "error", "Requisição sem token")
                return jsonify(erro="Não autenticado"), 401
            try:
                conteudo = serializador_web().loads(cabecalho[7:], max_age=VALIDADE_TOKEN_WEB)
            except BadSignature:
                registrar_log("WARN", "web", operacao, "error", "Token inválido ou expirado")
                return jsonify(erro="Não autenticado"), 401
            g.usuario = conteudo["usuario"]
            g.nome = conteudo["nome"]
            return rota(*args, **kwargs)

        return envoltorio

    return decorador


@app.errorhandler(Exception)
def tratar_erro_inesperado(erro):
    """Responde erros não previstos com JSON e log, em vez da página HTML padrão."""
    if isinstance(erro, HTTPException):
        return erro
    registrar_log("ERROR", "web", request.endpoint or "desconhecida", "error", "Erro inesperado na API")
    return jsonify(erro="Erro interno"), 500


@app.get("/api/web/health")
def web_saude():
    registrar_log("INFO", "web", "health", "success", "Healthcheck OK")
    return jsonify(status="ok"), 200


@app.post("/api/web/login")
def web_login():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        dados = {}
    usuario = dados.get("usuario")
    senha = dados.get("senha")
    if not isinstance(usuario, str) or not isinstance(senha, str) or not usuario or not senha:
        registrar_log("WARN", "web", "login", "error", "Usuário e senha são obrigatórios")
        return jsonify(erro="Usuário e senha são obrigatórios"), 400

    try:
        registro = db.buscar_usuario(usuario, g.request_id, "web")
    except psycopg.Error:
        registrar_log("ERROR", "web", "login", "error", "Falha ao acessar o banco")
        return jsonify(erro="Erro interno"), 500

    senha_valida = check_password_hash(registro["senha_hash"] if registro else HASH_FICTICIO, senha)
    if registro is None or not senha_valida:
        registrar_log("WARN", "web", "login", "error", "Credenciais inválidas")
        return jsonify(erro="Usuário ou senha inválidos"), 401

    token = serializador_web().dumps({"usuario": registro["usuario"], "nome": registro["nome"]})
    registrar_log("INFO", "web", "login", "success", "Login realizado")
    return jsonify(token=token, usuario=registro["usuario"], nome=registro["nome"]), 200


@app.get("/api/web/sessao")
@exigir_autenticacao_web("sessao")
def web_sessao():
    registrar_log("INFO", "web", "sessao", "success", "Sessão válida")
    return jsonify(usuario=g.usuario, nome=g.nome), 200


def inicializar():
    """Cria as tabelas e o usuário inicial a partir das variáveis de ambiente."""
    senha_hash = generate_password_hash(os.environ["ADMIN_SENHA"])
    db.inicializar_banco(os.environ["ADMIN_USUARIO"], os.environ["ADMIN_NOME"], senha_hash)


def criar_app():
    """Ponto de entrada do gunicorn (`api:criar_app()`): inicializa o banco e devolve a aplicação."""
    inicializar()
    return app
