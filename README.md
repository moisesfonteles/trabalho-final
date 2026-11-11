# trabalho-final

CRUD de vendas de produtos com **Web + CLI** sobre a mesma API REST e o mesmo banco.
Tudo roda via **Docker Compose** — no host basta Docker, Docker Compose, navegador e terminal.

Especificação do projeto: [`docs/especificacao.md`](docs/especificacao.md).

## Stack

| Camada | Tecnologia | Arquivo |
|---|---|---|
| Web | HTML + CSS + JavaScript puro, servido por nginx | `index.html` |
| API | Python 3.12 + Flask | `api.py` |
| Banco | PostgreSQL 16 (driver psycopg 3) | `db.py` |
| Testes | pytest + pytest-cov | `tests/` |

## #1 — Estrutura Web

### Iniciar

```bash
docker compose up --build
```

Sobe três serviços:

- `db` — PostgreSQL (dados persistidos no volume `dados-banco`);
- `api` — Flask servido pelo gunicorn na porta interna 8000, sem root e sem as dependências de teste; na inicialização cria as tabelas (`usuario`, `produto`, `venda`), carrega o catálogo de produtos e o usuário inicial;
- `web` — nginx em <http://localhost:8080>, servindo `index.html` e encaminhando `/api/*` para a API.

Para parar: `docker compose down` (adicione `-v` para apagar os dados).

### Configuração e usuário inicial

As variáveis são lidas do ambiente ou de um arquivo `.env` na raiz (veja `.env.example`). Sem `.env`, valem os padrões de desenvolvimento do `docker-compose.yml`:

| Variável | Padrão | Uso |
|---|---|---|
| `ADMIN_USUARIO` | `admin` | Login do usuário inicial |
| `ADMIN_NOME` | `Administrador` | Nome exibido após o login |
| `ADMIN_SENHA` | `admin123` | Senha do usuário inicial (somente para desenvolvimento) |
| `CHAVE_SECRETA` | valor de desenvolvimento | Assina os tokens de sessão Web |
| `SENHA_BANCO` | `app` | Senha do PostgreSQL |
| `PORTA_WEB` | `8080` | Porta da Web no host |

```bash
cp .env.example .env   # edite os valores antes de subir
```

A senha **nunca é armazenada em texto puro**: na inicialização a API gera um hash (scrypt, via `werkzeug.security`) e grava apenas o hash na tabela `usuario`. Se `ADMIN_SENHA` ou `ADMIN_NOME` mudarem, os valores do usuário `ADMIN_USUARIO` são atualizados no próximo start. Se o próprio `ADMIN_USUARIO` mudar, um novo usuário é criado e o anterior **continua ativo** (não há edição nem remoção de usuários); para descartá-lo, recrie o banco com `docker compose down -v`. Senhas e tokens não são registrados em log.

### Login

1. Abra <http://localhost:8080>.
2. Entre com `ADMIN_USUARIO` / `ADMIN_SENHA`.
3. A página inicial mostra o nome do usuário logado (`ADMIN_NOME`) e o indicador de status da API (healthcheck). "Sair" encerra a sessão no navegador.

O token Web é assinado e expira em 8 horas; fica no `sessionStorage` e é enviado como `Authorization: Bearer <token>`.

### Endpoints desta issue

| Método | Rota | Autenticação | Resposta |
|---|---|---|---|
| GET | `/api/web/health` | pública | `200 {"status":"ok"}` |
| POST | `/api/web/login` | — | `200 {"token","usuario","nome"}`; `400` sem campos; `401` credenciais inválidas |
| GET | `/api/web/sessao` | Bearer | `200 {"usuario","nome"}`; `401` sem token ou token inválido |

Pelo terminal:

```bash
curl -i http://localhost:8080/api/web/health
curl -i -X POST http://localhost:8080/api/web/login \
  -H 'Content-Type: application/json' -d '{"usuario":"admin","senha":"admin123"}'
```

## #2 — Cadastro e edição de registros na Web

Cada registro é uma **venda** (tabela `venda`) de um produto do catálogo fixo (tabela `produto`).

### Campos e validação

Todos os campos são obrigatórios e validados duas vezes: no navegador, antes do envio, e na API, que é quem decide.

| Campo | No formulário | Regra |
|---|---|---|
| `produto_id` | Produto (lista agrupada por categoria) | Inteiro de um produto existente no catálogo |
| `quantidade` | Quantidade | Inteiro de 1 a 10000 |
| `valor_unitario` | Valor unitário (R$) | Maior que 0, até 100000.00, com no máximo 2 casas decimais. Ao escolher o produto, o formulário sugere o preço do catálogo, que pode ser alterado (ex.: desconto) |
| `data_venda` | Data da venda | Data válida no formato `AAAA-MM-DD`, que não pode ser futura. O formulário sugere a data de hoje |

O `valor_total` (`quantidade × valor_unitario`) é calculado pelo banco e exibido no formulário enquanto os campos são preenchidos. Os limites de quantidade e valor mantêm o total dentro da coluna `NUMERIC(12,2)`.

### Cadastrar e editar pela Web

1. Faça login em <http://localhost:8080>.
2. **Cadastrar:** no cartão "Nova venda", escolha o produto, preencha quantidade, valor e data e clique em **Cadastrar venda**. A mensagem de sucesso mostra o número da venda criada.
3. **Editar:** informe o número da venda em **Editar venda nº** e clique em **Carregar**. O formulário passa a "Editar venda nº X". Altere os campos e clique em **Salvar alterações**, ou em **Cancelar edição** para voltar ao cadastro.

Erros de validação aparecem abaixo de cada campo, tanto os do navegador quanto os devolvidos pela API. Se a sessão expirar, a página volta para o login.

As vendas ficam no volume `dados-banco` e continuam lá depois de `docker compose down` / `up`. Só `docker compose down -v` apaga os dados.

### Endpoints desta issue

Todos exigem `Authorization: Bearer <token>`. Sem token ou com token inválido, respondem `401`.

| Método | Rota | Resposta |
|---|---|---|
| GET | `/api/web/produtos` | `200 {"produtos": [{"id","nome","categoria","preco"}]}` |
| GET | `/api/web/records/{id}` | `200` venda; `404` se não existir. Usado para carregar a venda na edição |
| POST | `/api/web/records` | `201` venda criada; `400` corpo que não é objeto JSON; `422` campos inválidos |
| PUT | `/api/web/records/{id}` | `200` venda atualizada; `400`; `404` se não existir; `422` campos inválidos |

A venda é devolvida como `{"id","produto_id","produto_nome","categoria","quantidade","valor_unitario","valor_total","data_venda"}`, com valores em texto (`"25.50"`) para não perder precisão. O `PUT` substitui todos os campos, então o corpo precisa ter os quatro. No `422`, o campo `campos` traz a mensagem de cada campo inválido, inclusive `produto_id` quando o produto não existe:

```json
{"erro": "Dados inválidos.", "campos": {"quantidade": "A quantidade deve ser um número inteiro entre 1 e 10000."}}
```

Pelo terminal:

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/api/web/login -H 'Content-Type: application/json' \
  -d '{"usuario":"admin","senha":"admin123"}' | sed 's/.*"token": *"\([^"]*\)".*/\1/')
curl -s http://localhost:8080/api/web/produtos -H "Authorization: Bearer $TOKEN"
curl -i -X POST http://localhost:8080/api/web/records -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"produto_id":1,"quantidade":3,"valor_unitario":"25.50","data_venda":"2026-10-15"}'
curl -i -X PUT http://localhost:8080/api/web/records/1 -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"produto_id":1,"quantidade":5,"valor_unitario":"25.50","data_venda":"2026-10-15"}'
```

### Logs

Cada operação registra uma linha na camada `api` e outra na camada `db`, com `client: "web"` e o mesmo `request_id`. Os valores de `operation` são `listar_produtos`, `consultar_venda`, `criar_venda` e `editar_venda`. Venda inexistente e produto inexistente geram `WARN` com `status: "error"` nas duas camadas. Dados inválidos são recusados antes de chegar ao banco, então geram `WARN` só na camada `api`. Falhas no banco geram `ERROR`.

## Logs

Cada evento é uma linha JSON no stdout, com `timestamp`, `level`, `layer` (`api`/`db`), `client` (`web`/`cli`), `operation`, `status`, `request_id` e `message`. API e banco compartilham o mesmo `request_id` dentro de uma requisição (também devolvido no header `X-Request-ID`). A inicialização do banco usa `client: "sistema"` e `request_id: "inicializacao"`. Erros não previstos na API viram `500 {"erro": "Erro interno"}` com log `ERROR`.

```bash
docker compose logs -f api                           # acompanhar
docker compose logs api | grep '"request_id": "req-…"'  # correlacionar uma operação
```

## Testes e cobertura

```bash
docker compose --profile testes run --rm --build testes
```

Sobe um PostgreSQL descartável (`db-testes`, em memória) e roda o pytest exigindo **100% de cobertura de linhas** em `api.py` e `db.py` (`--cov-fail-under=100`). Para limpar: `docker compose --profile testes down`.
