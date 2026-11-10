# Tasks

Ordem de execução. Cada fatia vira um PR; a página da fatia fica em `docs/features/`.

## Fatia 1 — Newsletter de qualquer time (`docs/features/newsletter-por-time.md`)
- [ ] T1: esqueleto do projeto (`pyproject.toml`, `uv`, ruff, pytest, CI) copiando a configuração da Urubu News
- [ ] T2: catálogo `teams.toml` + `load_teams()` validado com pydantic (Flamengo, Botafogo, Palmeiras para começar)
- [ ] T3: copiar coleta, resumo, ESPN, render e envio da Urubu News, trocando constantes do Flamengo por `Team`
- [ ] T4: prompts e templates parametrizados pelo time (nome, torcida, cores, escudo)
- [ ] T5: CLI `resenha preview --team <slug>` e `resenha run --team <slug>`

## Fatia 2 — Inscrição com escolha de times
- [ ] Inscrição com um ou mais times, confirmação por e-mail, descadastro por time e geral
- [ ] `/api/subscribers?team=<slug>` e envio só para quem assina o time
- [ ] `resenha due` devolvendo edições vencidas de todos os times com inscrito ativo
- [ ] Decidir cota do LLM (ver PLAN §5)

## Fatia 3 — Pedido de time e ranking de torcidas
- [ ] Formulário "meu time não está aqui" (time + e-mail opcional para avisar quando nascer)
- [ ] Página pública de ranking: inscritos por time e por série

## Fatia 4 — Edição geral por série

## Fatia 5 — Palpites (cartola simples)

## Fatia 6 — Joguinhos "7 a 0"

## Fatia 7 — Fóruns
