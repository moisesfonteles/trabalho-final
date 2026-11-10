<!--
Título da PR: "#N — <título da issue>" (principal) ou "Refs #N — <motivo>" (corretiva).
Branch: issue-N (principal) ou issue-N-fix-<k> (corretiva). Rebase and merge apenas.
-->

## Tipo

- [ ] **Principal** — entrega a issue e conta no ciclo
- [ ] **Corretiva** — corrige algo já integrado, não conta no ciclo e não gera tag/release

## Issue

<!-- Principal: "Closes #N". Corretiva: "Refs #N". Nunca criar issue nova. -->
Closes #

**Ciclo:** <!-- 1, 2, 3 ou 4 (só PR principal) -->

**Motivo da correção:** <!-- só PR corretiva: o que estava errado e por quê -->

## Descrição

<!-- O que a PR entrega e como atende cada critério de aceite da issue. -->

- [ ] Critério de aceite 1 —
- [ ] Critério de aceite 2 —

## Arquivos alterados

### Produção

| Arquivo | Alteração |
|---|---|
| `index.html` / `cli.py` | |
| `api.py` | |
| `db.py` | |
| `README.md` | Seção "#N — ..." |

### Auxiliares (testes, infraestrutura, dependências, configuração)

<!-- Todo arquivo auxiliar criado ou alterado precisa estar listado e justificado. -->

| Arquivo | Criado/alterado | Justificativa |
|---|---|---|
| | | |

## Endpoints

| Método | Rota | Autenticação | Descrição |
|---|---|---|---|
| | `/api/web/...` ou `/api/cli/...` | | |

<!-- A CLI usa rotas /api/cli/* próprias e nunca acessa o banco diretamente. -->

## Logs

<!-- Operações registradas, camadas (api/db), valores de `operation` e como o request_id é correlacionado. -->

## Autenticação

<!-- Quais rotas exigem login/token, o comportamento 401 e como segredos são protegidos. Escreva "Não se aplica" se for o caso. -->

## Como verificar (via Docker Compose)

```bash
docker compose up --build -d
# comandos para reproduzir a funcionalidade
```

## Testes e cobertura

```bash
# comando exato executado
docker compose --profile testes run --rm --build testes
```

- [ ] Todos os testes passam dentro do contêiner
- [ ] **100% de cobertura de linhas** em `api.py`, `db.py` (e `cli.py`, quando existir)

<!-- Saída resumida (TOTAL ... 100%) -->

```text
```

## Verificação funcional

<!-- O que foi testado manualmente na Web/CLI e o resultado. -->

## Checklist

- [ ] Branch rebaseada sobre o `main` atual do repositório principal (sem merge commits)
- [ ] PR aberta do fork para o `main` do repositório principal
- [ ] README atualizado com a seção desta issue
- [ ] Nenhum arquivo de produção além de `index.html`, `cli.py`, `api.py`, `db.py`, `README.md`
- [ ] Nenhuma senha, token ou segredo commitado ou registrado em log
- [ ] Aprovação dos 2 colegas antes do merge
- [ ] Após o merge (PR principal): tag `vX.Y.Z` e release no commit resultante do `main`
