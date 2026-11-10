"""Camada de acesso ao banco (PostgreSQL)."""

import json
import os
import sys
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row


def registrar_log(nivel, origem, operacao, status, request_id, mensagem):
    """Emite uma linha JSON no stdout para a camada de banco."""
    evento = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "level": nivel,
        "layer": "db",
        "client": origem,
        "operation": operacao,
        "status": status,
        "request_id": request_id,
        "message": mensagem,
    }
    print(json.dumps(evento, ensure_ascii=False), file=sys.stdout, flush=True)


# Catálogo fixo de produtos (nome, categoria, preço), carregado na inicialização.
PRODUTOS_INICIAIS = [
    ("Arroz 5 kg", "Alimentos", 27.90),
    ("Feijão 1 kg", "Alimentos", 8.50),
    ("Biscoito recheado", "Alimentos", 4.50),
    ("Refrigerante 2 L", "Bebidas", 9.90),
    ("Suco de laranja 1 L", "Bebidas", 7.90),
    ("Água mineral 1,5 L", "Bebidas", 3.50),
    ("Detergente 500 ml", "Limpeza", 2.99),
    ("Sabão em pó 1 kg", "Limpeza", 14.90),
    ("Desinfetante 2 L", "Limpeza", 11.90),
    ("Sabonete", "Higiene", 2.50),
    ("Creme dental", "Higiene", 5.90),
    ("Papel higiênico 12 un", "Higiene", 19.90),
]


def obter_conexao():
    return psycopg.connect(os.environ["URL_BANCO"], row_factory=dict_row)


def inicializar_banco(usuario, nome, senha_hash, request_id="startup", origem="system"):
    """Cria as tabelas, o catálogo de produtos e o usuário inicial (idempotente)."""
    try:
        with obter_conexao() as conexao:
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS usuario (
                    id SERIAL PRIMARY KEY,
                    usuario TEXT UNIQUE NOT NULL,
                    nome TEXT NOT NULL,
                    senha_hash TEXT NOT NULL,
                    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            conexao.execute(
                """
                INSERT INTO usuario (usuario, nome, senha_hash) VALUES (%s, %s, %s)
                ON CONFLICT (usuario) DO UPDATE SET nome = EXCLUDED.nome, senha_hash = EXCLUDED.senha_hash
                """,
                (usuario, nome, senha_hash),
            )
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS produto (
                    id SERIAL PRIMARY KEY,
                    nome TEXT UNIQUE NOT NULL,
                    categoria TEXT NOT NULL,
                    preco NUMERIC(10, 2) NOT NULL CHECK (preco > 0)
                )
                """
            )
            with conexao.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO produto (nome, categoria, preco) VALUES (%s, %s, %s) ON CONFLICT (nome) DO NOTHING",
                    PRODUTOS_INICIAIS,
                )
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS venda (
                    id SERIAL PRIMARY KEY,
                    produto_id INTEGER NOT NULL REFERENCES produto (id),
                    quantidade INTEGER NOT NULL CHECK (quantidade >= 1),
                    valor_unitario NUMERIC(10, 2) NOT NULL CHECK (valor_unitario > 0),
                    valor_total NUMERIC(12, 2) GENERATED ALWAYS AS (quantidade * valor_unitario) STORED,
                    data_venda DATE NOT NULL
                )
                """
            )
    except psycopg.Error:
        registrar_log("ERROR", origem, "inicializar_banco", "error", request_id, "Falha ao inicializar o banco")
        raise
    registrar_log(
        "INFO", origem, "inicializar_banco", "success", request_id, "Banco inicializado com catálogo de produtos e usuário inicial"
    )


def buscar_usuario(usuario, request_id, origem):
    """Retorna o usuário (dict) ou None se não existir."""
    try:
        with obter_conexao() as conexao:
            linha = conexao.execute(
                "SELECT id, usuario, nome, senha_hash FROM usuario WHERE usuario = %s",
                (usuario,),
            ).fetchone()
    except psycopg.Error:
        registrar_log("ERROR", origem, "consultar_usuario", "error", request_id, "Falha ao consultar usuário")
        raise
    mensagem = "Usuário encontrado" if linha else "Usuário não encontrado"
    registrar_log("INFO", origem, "consultar_usuario", "success", request_id, mensagem)
    return linha
