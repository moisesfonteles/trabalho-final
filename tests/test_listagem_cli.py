"""Testes da listagem paginada, ordenação e exclusão pela CLI (issue #9): rotas /api/cli/*, banco e cli.py."""

import io

import psycopg
import pytest

import api
import cli
import db
from conftest import SENHA_TESTE, USUARIO_TESTE, eventos_do_log


def _falhar_no_banco(*_args):
    raise psycopg.OperationalError("banco fora do ar")


def _conexao_quebrada():
    raise psycopg.OperationalError("banco fora do ar")


def _id_produto(nome):
    with db.obter_conexao() as conexao:
        return conexao.execute("SELECT id FROM produto WHERE nome = %s", (nome,)).fetchone()["id"]


def _inserir_venda(produto, quantidade, valor_unitario, data_venda):
    with db.obter_conexao() as conexao:
        return conexao.execute(
            "INSERT INTO venda (produto_id, quantidade, valor_unitario, data_venda) VALUES (%s, %s, %s, %s) RETURNING id",
            (_id_produto(produto), quantidade, valor_unitario, data_venda),
        ).fetchone()["id"]


def _da_requisicao(capsys, resposta):
    request_id = resposta.headers["X-Request-ID"]
    return [e for e in eventos_do_log(capsys) if e["request_id"] == request_id]


@pytest.fixture(autouse=True)
def vendas_limpas():
    """Cada teste começa sem vendas, para os totais e a paginação serem previsíveis."""
    with db.obter_conexao() as conexao:
        conexao.execute("TRUNCATE venda RESTART IDENTITY")


@pytest.fixture
def token_cli(cliente_http):
    resposta = cliente_http.post("/api/cli/token", json={"usuario": USUARIO_TESTE, "senha": SENHA_TESTE})
    return resposta.get_json()["token"]


@pytest.fixture
def cabecalho_cli(token_cli):
    return {"Authorization": f"Bearer {token_cli}"}


@pytest.fixture
def sete_vendas():
    """7 vendas com datas, quantidades e totais distintos. Retorna os ids na ordem de inserção."""
    dados = [
        ("Arroz 5 kg", 2, "27.90", "2026-10-01"),  # 55.80
        ("Sabonete", 10, "2.50", "2026-10-05"),  # 25.00
        ("Refrigerante 2 L", 1, "9.90", "2026-10-03"),  # 9.90
        ("Detergente 500 ml", 4, "2.99", "2026-10-07"),  # 11.96
        ("Feijão 1 kg", 3, "8.50", "2026-10-02"),  # 25.50
        ("Creme dental", 6, "5.90", "2026-10-06"),  # 35.40
        ("Suco de laranja 1 L", 5, "3.50", "2026-10-04"),  # 17.50
    ]
    return [_inserir_venda(*venda) for venda in dados]


# --- API: autenticação ----------------------------------------------------------------------------


@pytest.mark.parametrize("metodo, rota", [("get", "/api/cli/records"), ("delete", "/api/cli/records/1")])
@pytest.mark.parametrize("cabecalho", [None, "Bearer invalido", "Basic abc"])
def test_rotas_exigem_token_da_cli(cliente_http, metodo, rota, cabecalho, capsys):
    cabecalhos = {"Authorization": cabecalho} if cabecalho else {}
    capsys.readouterr()
    resposta = getattr(cliente_http, metodo)(rota, headers=cabecalhos)
    assert resposta.status_code == 401
    assert all(e["layer"] == "api" and e["client"] == "cli" for e in eventos_do_log(capsys))


@pytest.mark.parametrize("metodo, rota", [("get", "/api/cli/records"), ("delete", "/api/cli/records/1")])
def test_token_da_web_nao_vale_nas_rotas_da_cli(cliente_http, token, metodo, rota):
    resposta = getattr(cliente_http, metodo)(rota, headers={"Authorization": f"Bearer {token}"})
    assert resposta.status_code == 401


# --- API: listagem --------------------------------------------------------------------------------


def test_listar_padrao_dez_por_pagina_mais_recentes_primeiro(cliente_http, cabecalho_cli, sete_vendas):
    corpo = cliente_http.get("/api/cli/records", headers=cabecalho_cli).get_json()
    assert {k: corpo[k] for k in ("pagina", "itens_por_pagina", "total", "total_paginas", "ordenar", "direcao")} == {
        "pagina": 1,
        "itens_por_pagina": 10,
        "total": 7,
        "total_paginas": 1,
        "ordenar": "data_venda",
        "direcao": "desc",
    }
    assert [v["data_venda"] for v in corpo["vendas"]][:3] == ["2026-10-07", "2026-10-06", "2026-10-05"]
    assert corpo["vendas"][0] == {
        "id": sete_vendas[3],
        "produto_id": _id_produto("Detergente 500 ml"),
        "produto_nome": "Detergente 500 ml",
        "categoria": "Limpeza",
        "quantidade": 4,
        "valor_unitario": "2.99",
        "valor_total": "11.96",
        "data_venda": "2026-10-07",
    }


def test_listar_sem_vendas(cliente_http, cabecalho_cli):
    corpo = cliente_http.get("/api/cli/records", headers=cabecalho_cli).get_json()
    assert corpo["vendas"] == [] and corpo["total"] == 0 and corpo["total_paginas"] == 1


def test_pagina_e_tamanho_configuraveis(cliente_http, cabecalho_cli, sete_vendas):
    ids = []
    for pagina in (1, 2, 3):
        corpo = cliente_http.get(
            f"/api/cli/records?pagina={pagina}&tamanho=3&ordenar=id&direcao=asc", headers=cabecalho_cli
        ).get_json()
        assert corpo["itens_por_pagina"] == 3 and corpo["total_paginas"] == 3
        ids += [v["id"] for v in corpo["vendas"]]
    # 3 + 3 + 1, sem repetir nem pular nenhuma venda
    assert ids == sorted(sete_vendas)


def test_pagina_alem_do_fim_vem_vazia(cliente_http, cabecalho_cli, sete_vendas):
    corpo = cliente_http.get("/api/cli/records?pagina=5&tamanho=3", headers=cabecalho_cli).get_json()
    assert corpo["vendas"] == [] and corpo["total"] == 7 and corpo["total_paginas"] == 3


@pytest.mark.parametrize(
    "ordenar, direcao, campo, esperado",
    [
        ("valor_total", "asc", "valor_total", ["9.90", "11.96", "17.50", "25.00", "25.50", "35.40", "55.80"]),
        ("quantidade", "desc", "quantidade", [10, 6, 5, 4, 3, 2, 1]),
        ("data_venda", "asc", "data_venda", [f"2026-10-0{d}" for d in range(1, 8)]),
        ("categoria", "asc", "categoria", ["Alimentos", "Alimentos", "Bebidas", "Bebidas", "Higiene", "Higiene", "Limpeza"]),
    ],
)
def test_ordenacao_por_campo_e_direcao(cliente_http, cabecalho_cli, sete_vendas, ordenar, direcao, campo, esperado):
    corpo = cliente_http.get(f"/api/cli/records?ordenar={ordenar}&direcao={direcao}", headers=cabecalho_cli).get_json()
    assert corpo["ordenar"] == ordenar and corpo["direcao"] == direcao
    assert [v[campo] for v in corpo["vendas"]] == esperado


def test_empate_e_desfeito_pelo_id(cliente_http, cabecalho_cli):
    ids = [_inserir_venda("Sabonete", 1, "2.50", "2026-10-01") for _ in range(3)]
    corpo = cliente_http.get("/api/cli/records?ordenar=data_venda&direcao=asc", headers=cabecalho_cli).get_json()
    assert [v["id"] for v in corpo["vendas"]] == ids


@pytest.mark.parametrize(
    "consulta, campos",
    [
        ("pagina=0", {"pagina"}),
        ("pagina=abc", {"pagina"}),
        ("pagina=" + "9" * 5000, {"pagina"}),  # não pode virar 500 no int()
        ("tamanho=0", {"tamanho"}),
        ("tamanho=101", {"tamanho"}),
        ("tamanho=-5", {"tamanho"}),
        ("ordenar=senha_hash", {"ordenar"}),
        ("direcao=cima", {"direcao"}),
        ("pagina=0&tamanho=500", {"pagina", "tamanho"}),
    ],
)
def test_parametros_invalidos_400_sem_chegar_ao_banco(cliente_http, cabecalho_cli, monkeypatch, capsys, consulta, campos):
    monkeypatch.setattr(db, "listar_vendas_cli", _falhar_no_banco)
    capsys.readouterr()
    resposta = cliente_http.get(f"/api/cli/records?{consulta}", headers=cabecalho_cli)
    assert resposta.status_code == 400
    corpo = resposta.get_json()
    assert corpo["erro"] == "Parâmetros inválidos." and set(corpo["campos"]) == campos
    eventos = _da_requisicao(capsys, resposta)
    assert [(e["layer"], e["level"], e["client"]) for e in eventos] == [("api", "WARN", "cli")]


def test_listagem_correlaciona_logs_api_e_banco(cliente_http, cabecalho_cli, sete_vendas, capsys):
    capsys.readouterr()
    resposta = cliente_http.get("/api/cli/records", headers=cabecalho_cli)
    assert {(e["layer"], e["operation"], e["status"], e["client"]) for e in _da_requisicao(capsys, resposta)} == {
        ("api", "listar_vendas", "success", "cli"),
        ("db", "listar_vendas", "success", "cli"),
    }


def test_listagem_erro_no_banco(cliente_http, cabecalho_cli, monkeypatch, capsys):
    monkeypatch.setattr(db, "listar_vendas_cli", _falhar_no_banco)
    capsys.readouterr()
    resposta = cliente_http.get("/api/cli/records", headers=cabecalho_cli)
    assert resposta.status_code == 500 and resposta.get_json() == {"erro": "Erro interno"}
    evento = eventos_do_log(capsys)[-1]
    assert (evento["level"], evento["client"], evento["operation"]) == ("ERROR", "cli", "listar_vendas")


# --- API: exclusão --------------------------------------------------------------------------------


def test_excluir_remove_e_some_da_web(cliente_http, cabecalho_cli, token, sete_vendas, capsys):
    alvo = sete_vendas[0]
    capsys.readouterr()
    resposta = cliente_http.delete(f"/api/cli/records/{alvo}", headers=cabecalho_cli)
    assert resposta.status_code == 200 and resposta.get_json() == {"id": alvo, "mensagem": "Venda excluída."}
    assert {(e["layer"], e["operation"], e["status"], e["client"]) for e in _da_requisicao(capsys, resposta)} == {
        ("api", "excluir_venda", "success", "cli"),
        ("db", "excluir_venda", "success", "cli"),
    }
    # A exclusão feita pela CLI aparece na Web: a venda não existe mais e o total diminui.
    web = {"Authorization": f"Bearer {token}"}
    assert cliente_http.get(f"/api/web/records/{alvo}", headers=web).status_code == 404
    assert cliente_http.get("/api/web/records", headers=web).get_json()["total"] == 6


def test_excluir_inexistente_404_com_logs(cliente_http, cabecalho_cli, capsys):
    capsys.readouterr()
    resposta = cliente_http.delete("/api/cli/records/999", headers=cabecalho_cli)
    assert resposta.status_code == 404 and resposta.get_json() == {"erro": "Venda não encontrada."}
    assert {(e["layer"], e["level"]) for e in _da_requisicao(capsys, resposta)} == {("api", "WARN"), ("db", "WARN")}


@pytest.mark.parametrize("id_venda", ["-1", "0", "abc", "1.5", "１"])
def test_excluir_id_invalido_400_sem_consultar_o_banco(cliente_http, cabecalho_cli, monkeypatch, id_venda):
    monkeypatch.setattr(db, "excluir_venda_cli", _falhar_no_banco)
    resposta = cliente_http.delete(f"/api/cli/records/{id_venda}", headers=cabecalho_cli)
    assert resposta.status_code == 400 and resposta.get_json() == {"erro": "Número da venda inválido."}


def test_excluir_erro_no_banco(cliente_http, cabecalho_cli, monkeypatch):
    monkeypatch.setattr(db, "excluir_venda_cli", _falhar_no_banco)
    resposta = cliente_http.delete("/api/cli/records/1", headers=cabecalho_cli)
    assert resposta.status_code == 500 and resposta.get_json() == {"erro": "Erro interno"}


# --- banco ----------------------------------------------------------------------------------------


def test_db_listar_vendas_cli_retorna_pagina_e_total(sete_vendas, capsys):
    linhas, total = db.listar_vendas_cli(2, 3, "id", "asc", "req-lista")
    assert total == 7 and [linha["id"] for linha in linhas] == sorted(sete_vendas)[3:6]
    evento = eventos_do_log(capsys)[-1]
    assert (evento["layer"], evento["client"], evento["operation"], evento["request_id"]) == (
        "db",
        "cli",
        "listar_vendas",
        "req-lista",
    )


@pytest.mark.parametrize(
    "funcao, argumentos, operacao",
    [
        (db.listar_vendas_cli, (1, 10, "id", "asc", "req-erro"), "listar_vendas"),
        (db.excluir_venda_cli, (1, "req-erro"), "excluir_venda"),
    ],
)
def test_db_erro_registra_log_cli(monkeypatch, capsys, funcao, argumentos, operacao):
    monkeypatch.setattr(db, "obter_conexao", _conexao_quebrada)
    with pytest.raises(psycopg.OperationalError):
        funcao(*argumentos)
    evento = eventos_do_log(capsys)[-1]
    assert (evento["layer"], evento["level"], evento["client"], evento["operation"]) == ("db", "ERROR", "cli", operacao)


def test_db_excluir_venda_cli(sete_vendas):
    assert db.excluir_venda_cli(sete_vendas[0], "req-x") is True
    assert db.excluir_venda_cli(sete_vendas[0], "req-y") is False


# --- comandos da CLI (contra a API num servidor HTTP real) ----------------------------------------


def _saida(capsys):
    """Saída e erro da CLI, sem as linhas de log da API (que roda no mesmo processo durante o teste)."""
    capturado = capsys.readouterr()
    sem_log = lambda texto: [linha for linha in texto.splitlines() if not linha.startswith("{")]  # noqa: E731
    return sem_log(capturado.out), "\n".join(sem_log(capturado.err))


@pytest.fixture
def com_token(servidor_api, token_cli, monkeypatch):
    monkeypatch.setenv("TOKEN_CLI", token_cli)


def test_listar_mostra_a_tabela_e_o_rodape(com_token, sete_vendas, capsys):
    assert cli.main(["listar", "--tamanho", "3", "--ordenar", "valor_total", "--direcao", "asc"]) == cli.SAIDA_SUCESSO
    saida, _ = _saida(capsys)
    assert saida[0].split() == ["Nº", "Data", "Produto", "Categoria", "Qtd.", "Valor", "total"]
    assert "03/10/2026" in saida[1] and "Refrigerante 2 L" in saida[1] and saida[1].endswith("R$ 9,90")
    assert len(saida) == 5  # cabeçalho + 3 vendas + rodapé
    assert saida[-1] == "Página 1 de 3 · 7 vendas · 3 por página · ordenado por valor_total (crescente)"


def test_listar_segunda_pagina(com_token, sete_vendas, capsys):
    assert cli.main(["listar", "--pagina", "2", "--tamanho", "5", "--ordenar", "id"]) == cli.SAIDA_SUCESSO
    saida, _ = _saida(capsys)
    # ordenado por id decrescente (padrão desc): a 2ª página tem os 2 menores ids
    assert [linha.split()[0] for linha in saida[1:-1]] == [str(i) for i in sorted(sete_vendas)[1::-1]]
    assert saida[-1] == "Página 2 de 2 · 7 vendas · 5 por página · ordenado por id (decrescente)"


def test_listar_sem_vendas(com_token, capsys):
    assert cli.main(["listar"]) == cli.SAIDA_SUCESSO
    assert _saida(capsys)[0] == [
        "Nenhuma venda cadastrada.",
        "Página 1 de 1 · 0 vendas · 10 por página · ordenado por data_venda (decrescente)",
    ]


def test_listar_pagina_que_nao_existe(com_token, sete_vendas, capsys):
    assert cli.main(["listar", "--pagina", "9", "--tamanho", "5"]) == cli.SAIDA_SUCESSO
    assert _saida(capsys)[0] == ["A página 9 não existe: há 2 páginas."]


def test_listar_uma_venda_no_singular(com_token, capsys):
    _inserir_venda("Sabonete", 1, "2.50", "2026-10-01")
    cli.main(["listar", "--pagina", "2"])
    assert _saida(capsys)[0] == ["A página 2 não existe: há 1 página."]
    cli.main(["listar"])
    assert "· 1 venda ·" in _saida(capsys)[0][-1]


def test_listar_parametros_invalidos_mostra_a_opcao(com_token, capsys):
    assert cli.main(["listar", "--pagina", "0", "--tamanho", "500"]) == cli.SAIDA_ERRO
    erro = _saida(capsys)[1].splitlines()
    assert erro[0] == "Erro: Parâmetros inválidos. (HTTP 400)"
    assert "  --pagina: A página deve ser um número inteiro entre 1 e 100000." in erro
    assert "  --tamanho: O tamanho da página deve ser um número inteiro entre 1 e 100." in erro


@pytest.mark.parametrize("argv", [["listar", "--ordenar", "preco"], ["listar", "--direcao", "cima"]])
def test_listar_escolha_invalida_e_erro_de_uso(servidor_api, capsys, argv):
    with pytest.raises(SystemExit) as saida:
        cli.main(argv)
    assert saida.value.code == 2
    erro = capsys.readouterr().err
    assert "Erro: argumento" in erro and "escolha inválida" in erro


@pytest.mark.parametrize("resposta", ["s\n", "sim\n", " S \n"])
def test_excluir_com_confirmacao(com_token, sete_vendas, monkeypatch, capsys, resposta):
    monkeypatch.setattr("sys.stdin", io.StringIO(resposta))
    assert cli.main(["excluir", str(sete_vendas[0])]) == cli.SAIDA_SUCESSO
    saida, erro = _saida(capsys)
    assert f"Excluir a venda nº {sete_vendas[0]}?" in erro
    assert saida == [f"Venda nº {sete_vendas[0]} excluída."]
    assert db.excluir_venda_cli(sete_vendas[0], "req-conferencia") is False  # já não existe


@pytest.mark.parametrize("resposta", ["n\n", "\n", "talvez\n"])
def test_excluir_sem_confirmar_nao_exclui(com_token, sete_vendas, monkeypatch, capsys, resposta):
    monkeypatch.setattr("sys.stdin", io.StringIO(resposta))
    assert cli.main(["excluir", str(sete_vendas[0])]) == cli.SAIDA_ERRO
    assert "Exclusão cancelada; nenhuma venda foi excluída." in _saida(capsys)[1]
    assert db.excluir_venda_cli(sete_vendas[0], "req-conferencia") is True  # ainda existia


def test_excluir_sem_terminal_cancela(com_token, sete_vendas, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))  # EOF, como no `docker compose run -T` sem --sim
    assert cli.main(["excluir", str(sete_vendas[0])]) == cli.SAIDA_ERRO
    assert "Cancelado." in _saida(capsys)[1]


@pytest.mark.parametrize("opcao", ["--sim", "-s"])
def test_excluir_com_sim_nao_pergunta(com_token, sete_vendas, monkeypatch, capsys, opcao):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert cli.main(["excluir", str(sete_vendas[1]), opcao]) == cli.SAIDA_SUCESSO
    saida, erro = _saida(capsys)
    assert saida == [f"Venda nº {sete_vendas[1]} excluída."] and "[s/N]" not in erro


def test_excluir_inexistente(com_token, capsys):
    assert cli.main(["excluir", "999", "--sim"]) == cli.SAIDA_ERRO
    assert _saida(capsys)[1] == "Erro: Venda não encontrada. (HTTP 404)"


def test_excluir_id_invalido_nao_troca_a_rota(com_token, sete_vendas, capsys):
    # "1/../2" vai codificado na URL (%2F): não vira outra rota de exclusão e nenhuma venda é excluída.
    assert cli.main(["excluir", "1/../2", "--sim"]) == cli.SAIDA_ERRO
    assert "(HTTP 404)" in _saida(capsys)[1]
    with db.obter_conexao() as conexao:
        assert conexao.execute("SELECT COUNT(*) AS n FROM venda").fetchone()["n"] == 7


def test_excluir_sem_token_avisa_antes_de_perguntar(servidor_api, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("s\n"))
    assert cli.main(["excluir", "1"]) == cli.SAIDA_NAO_AUTENTICADO
    erro = _saida(capsys)[1]
    assert "comando protegido" in erro and "[s/N]" not in erro


@pytest.mark.parametrize("argv", [["listar"], ["excluir", "1", "--sim"]])
def test_comandos_com_token_invalido_saem_com_codigo_3(servidor_api, monkeypatch, capsys, argv):
    monkeypatch.setenv("TOKEN_CLI", "token-falso")
    assert cli.main(argv) == cli.SAIDA_NAO_AUTENTICADO
    assert "HTTP 401" in _saida(capsys)[1]


def test_ajuda_lista_listar_e_excluir(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    saida = capsys.readouterr().out
    assert "listar" in saida and "excluir" in saida


def test_colunas_de_ordenacao_da_cli_iguais_as_da_api():
    assert set(cli.COLUNAS_ORDENACAO) == set(db.COLUNAS_ORDENACAO_CLI)
    assert api.TAMANHO_MAXIMO_CLI == 100  # citado na ajuda de --tamanho
