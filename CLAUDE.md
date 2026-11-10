# CLAUDE.md

Regras do projeto para agentes de código. A especificação técnica está em `docs/especificacao.md`; o template de PR, em `.github/PULL_REQUEST_TEMPLATE.md`.

## Projeto

CRUD de vendas com Web e CLI sobre a mesma API REST e o mesmo banco. Equipe de 3 pessoas, issues #1–#12.

- Os arquivos de produção são **somente** `index.html`, `cli.py`, `api.py`, `db.py` e `README.md`. Nunca crie outro arquivo de produção.
- Testes, infraestrutura, dependências e configuração são permitidos, mas todo arquivo auxiliar criado ou alterado precisa estar listado e justificado na PR.
- Tudo roda via Docker Compose. Nunca exija Python, Node ou outras ferramentas instaladas no host.
- Testes: `docker compose --profile testes run --rm --build testes`, com 100% de cobertura de linhas em `api.py`, `db.py` e `cli.py`.

## Idioma

Escreva o código em **português** sempre que possível: variáveis, funções, classes, tabelas, colunas, parâmetros, subcomandos e opções da CLI, IDs e classes CSS, comentários, docstrings, mensagens ao usuário, mensagens de log e nomes de testes. Use nomes sem acento (`descricao`, `funcao`), e mantenha os acentos em textos e mensagens.

Exceções que ficam em inglês:

- Rotas e métodos exigidos pela avaliação (`/api/web/records`, `/health`, `/login`, `/token`, `/search`, `/export`, `/dashboard`).
- Os campos e valores obrigatórios dos logs: `timestamp`, `level`, `layer`, `client`, `operation`, `status`, `request_id`, `message`, além de `INFO`/`WARN`/`ERROR`, `api`/`db`, `web`/`cli` e `success`/`error`. O conteúdo de `message` fica em português.
- Palavras reservadas, APIs de bibliotecas e convenções de ferramentas (`test_*` do pytest, `main`, `app`, `Authorization: Bearer`).

## Issues

- Existem exatamente **12 issues (#1–#12)**. **Nunca crie issues novas**: isso tira pontos da equipe.
- PRs podem ser criadas sem limite. A PR principal usa `Closes #N`. A PR corretiva usa `Refs #N` e explica o motivo da correção.

## Worktrees e branches

- Use uma worktree por issue em `tmp/issue-N`, na branch `issue-N`, criada a partir do `main` do repositório principal (`pv-oliveira/trabalho-final`):
  `git worktree add tmp/issue-N -b issue-N <remote-principal>/main`
- Nos comandos abaixo, `<remote-principal>` é o remote do repositório principal: `upstream` para quem trabalha com fork, `origin` para quem não usa fork.
- Para uma PR corretiva da issue N, use a branch `issue-N-fix-K` (K = 1, 2, …) na worktree `tmp/issue-N-fix-K`.
- **Nunca apague branches**, nem localmente nem no GitHub, inclusive depois do merge. Não clique em "Delete branch" após o merge. As worktrees só podem ser removidas depois da apresentação.

## Histórico linear

- Nunca faça commit direto no `main`. Toda mudança entra por PR.
- Nunca use `git merge` nem `git pull` sem rebase. Para atualizar a branch, use `git fetch <remote-principal> && git rebase <remote-principal>/main`.
- Configuração recomendada: `git config pull.rebase true`.
- Integre no GitHub **somente** por **Rebase and merge**. É proibido usar merge commit, Squash and merge e force push no `main`.
- Force push é permitido apenas na branch `issue-N` da própria pessoa, depois de um rebase (`git push --force-with-lease`).

## PRs

- Use sempre o template `.github/PULL_REQUEST_TEMPLATE.md`, com todas as seções preenchidas.
- O título deve seguir o formato `#N — <título da issue>`.
- O autor da PR principal é o responsável pela issue.
- Faça o merge somente depois da aprovação dos **2 colegas**. A aprovação do próprio autor não conta.
- Respeite os ciclos: cada integrante integra 1 PR principal por ciclo, e o próximo ciclo só começa quando os 3 tiverem integrado a sua.

## Tags e releases

Crie tags e releases **somente** após o merge de uma PR **principal**. As PRs corretivas não geram tag nem release.

- Formato SemVer: `v0.N.0`, em que N é a ordem de merge da PR principal (1 a 11). A 12ª e última PR principal gera a `v1.0.0`.
- A tag deve apontar para o commit do `main` do repositório principal resultante do merge:

```bash
SHA=$(gh api repos/pv-oliveira/trabalho-final/commits/main -q .sha)
gh release create vX.Y.Z -R pv-oliveira/trabalho-final --target "$SHA" \
  --title "vX.Y.Z — #N <título>" \
  --notes "Funcionalidade: <resumo>
Issue: #N
PR: #P"
```

Antes de criar a release, confira que `$SHA` é o último commit da PR integrada. O `gh release create` cria a tag no servidor, nesse commit. Confira também que nenhuma outra PR foi integrada nesse intervalo.
