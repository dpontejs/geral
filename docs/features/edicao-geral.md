# Edição geral por série (parte 4)

- **Data:** 2026-11-11
- **Status:** 4a entregue (PR #27); 4b implementada (aguardando PR)
- **ADRs:** —

## Objetivo

O futebol brasileiro da semana numa edição só, toda segunda: para cada série (A, B, C, D), os
resultados da semana, o recorte da tabela e as principais notícias, com uma abertura e um resumo
por série escritos pelo Gemini. É a newsletter da própria Geral, para quem gosta de futebol
brasileiro, e não de uma torcida.

## Fora de escopo

- 4b (PR seguinte): inscrição "Edição geral" no portal, edição guardada, `due --all` e o envio
  toda segunda aos inscritos. Aqui ela vai só para `NEWSLETTER_RECIPIENTS` (e respeita `DRY_RUN`).
- Estaduais e recorte por região (o cartão do portal cita estaduais: ficam para depois).
- Autores dos gols e estatísticas por jogo: a edição mostra placares.

## Contratos

- Fonte única: a API de tabelas do ge, pela página de cada série
  (`ge.globo.com/futebol/brasileirao-serie-{a,b,c,d}/`), e o feed de notícias dessa página.
  `geral.stats.ge_tables.load_competition(client, name, page_url, tz, team_id=None)` sai do
  `GETablesClient` (sem mudança de comportamento para os times) e serve às duas.
- `geral.general.SERIES`: nome → página da série. `collect_week(start, end) -> list[SerieWeek]`:
  - `SerieWeek(name, results, table, phase, news)`: jogos encerrados na janela (por data), a
    tabela da fase atual de pontos sem grupos cortada em G4 e Z4 (`table_top`, `table_bottom`),
    o nome da fase atual quando é mata-mata ou grupos, e até 8 notícias do feed na janela.
  - Série sem jogo encerrado e sem notícia na janela fica de fora (C e D no fim do ano).
  - Série que falha ao carregar fica de fora com aviso no log; todas falhando = erro.
- Janela: da segunda anterior às 8h até a segunda da edição às 8h (fuso de Brasília).
- Gemini (`prompts/geral.md`, pt-BR), uma chamada: `GeneralSummary(headline, intro, series:
  [{name, summary, picks: [ids das notícias]}])`, no máximo 3 notícias por série. Falha do
  Gemini: a edição sai com resultados e tabelas, sem os textos.
- Render: `render_general(edition) -> (html, text)`, com a marca da Geral (`/static/geral/`).
  Assunto: `Geral — Edição geral — DD/MM/AAAA: <manchete>`.
- CLI: `geral edicao-geral [--date AAAA-MM-DD] [--out arquivo.html] [--send]`: sem `--send`,
  só gera a prévia; com `--send`, envia para `NEWSLETTER_RECIPIENTS`.
- Banco: nada novo.

### 4b — inscrição e envio toda segunda

- No portal, `geral` é mais uma entrada do catálogo web (`geral.general.GENERAL_EDITION`, montada
  no código, fora do `teams.toml`): inscrição (opção "Edição geral" no ingresso), confirmação,
  descadastro só dela, `/t/geral`, `/api/subscribers?team=geral`, edição guardada e boas-vindas
  com texto próprio. Fica fora do placar, da lista de torcidas, dos joguinhos e do "Já tem!".
- `geral due --all`: com inscrito na edição geral, a linha `geral<TAB>news<TAB>AAAA-MM-DD<TAB>
  Edição geral — DD/MM/AAAA` das 8h às 11h da segunda, se a edição da semana ainda não saiu.
  O gatilho da VPS (`infra`) não muda.
- `geral edicao-geral --send`: destinatários pela API (`team=geral`) mais a lista fixa, link de
  descadastro de cada um, e publica a edição no portal depois do envio real. `--skip-if-sent`
  não refaz a edição da semana; sem inscritos, para antes de coletar.
- Workflow `newsletter.yml`: `team=geral` roda `edicao-geral --send` (com `--date` e
  `--skip-if-sent` quando vierem).
- `geral edicao-geral --publish-only` (workflow com `publish_only`): publica a edição no portal
  (`/t/geral`, cartão do Intervalo e boas-vindas de quem se inscreve) sem enviar. Serve para a
  primeira edição: sem ela, quem se inscreve antes da primeira segunda não recebe nada.

## Critérios de aceite (como testes)

- [x] `test_load_competition_matches_the_team_client`: o carregador solto devolve os mesmos jogos.
- [x] `test_collect_week_results_in_the_window_only` (respx, Série D de 2026 gravada).
- [x] `test_collect_week_table_cut_to_top_and_bottom` e `test_collect_week_knockout_shows_the_phase`.
- [x] `test_collect_week_skips_series_without_games_or_news` e `..._one_series_failing_is_skipped`.
- [x] `test_general_summary_prompt_lists_results_tables_and_numbered_news`.
- [x] `test_build_general_keeps_results_when_the_llm_fails`.
- [x] `test_render_general_has_each_series_results_table_and_picked_news`.
- [x] `test_edicao_geral_preview_writes_html_without_sending` e `test_edicao_geral_send_uses_recipients`.

## Verificação ponta a ponta

```bash
uv run ruff check . && uv run pytest
uv run geral edicao-geral --date 2026-11-09 --out out/geral.html   # abrir no navegador
```

## Riscos e dúvidas abertas

- ~4 páginas + fases + rodadas do ge + até 12 páginas de feed por série: cerca de 1 minuto, uma vez por semana.
- Tabela de corte: `cut_table` mostra a tabela inteira até 10 times (a página fala em G4/Z4 a partir daí).
