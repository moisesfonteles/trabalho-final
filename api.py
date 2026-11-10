"""API REST (Flask) consumida pela Web e, futuramente, pela CLI."""

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from functools import wraps

import psycopg
from flask import Flask, g, jsonify, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import db

VALIDADE_TOKEN_WEB = 8 * 60 * 60  # 8 horas

app = Flask(__name__)
logging.getLogger("werkzeug").disabled = True  # mantém o stdout só com logs JSON


def registrar_log(nivel, origem, operacao, status, mensagem):
    """Emite uma linha JSON no stdout para a camada de API."""
    evento = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "level": nivel,
        "layer": "api",
        "client": origem,
        "operation": operacao,
        "status": status,
        "request_id": g.request_id,
        "message": mensagem,
    }
    print(json.dumps(evento, ensure_ascii=False), file=sys.stdout, flush=True)


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


@app.get("/api/web/health")
def web_saude():
    registrar_log("INFO", "web", "health", "success", "Healthcheck OK")
    return jsonify(status="ok"), 200


@app.post("/api/web/login")
def web_login():
    dados = request.get_json(silent=True) or {}
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

    if registro is None or not check_password_hash(registro["senha_hash"], senha):
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


def main():
    inicializar()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORTA_API", "8000")))


if __name__ == "__main__":  # pragma: no cover
    main()
