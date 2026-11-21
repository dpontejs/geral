# Central — tabelas e jogos: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline, regra do harness).

**Goal:** página `/central` com tabela, rodadas, confrontos e resumo das Séries A–D, mais o bloco na inicial.
**Architecture:** o `CompetitionLoader` do ge passa a guardar faixas, escudos e todas as fases; `geral.central`
monta um retrato Pydantic gravado em JSON; uma thread do app o refaz a cada 10 min; a página só lê o JSON.
**Tech Stack:** Python 3.12, httpx + respx, Pydantic, FastAPI + Jinja2, pytest.
**Spec:** `docs/features/central.md`

## Global Constraints

- Código, nomes e logs em inglês; textos da página em pt-BR. Testes sem internet (`respx`).
- Commits `tipo: frase` em pt-BR, sem escopo, sem trailer. Antes de commitar: ruff check, ruff format --check, pytest.
- Cores das faixas da paleta da Geral pela posição; "Rebaixados" sempre vermelho; nunca as cores do ge.
- Mudar o loader não pode mudar o comportamento dos times (ABC, CSA) nem da edição geral.

## Review Focus

- Série sem retrato ainda (primeiro boot) → página 200 com "em atualização" (Task 4).
- Confronto de jogo único (final da C) e de ida e volta → agregado certo nos dois (Task 2).
- Jogo sem placar ainda / adiado (sem hora) na rodada → mostra data e "a definir", sem quebrar (Task 2).
- ge fora numa série → retrato anterior dela, e só ela (Task 2).
- Celular (360 px): tabela de 20 linhas cabe sem rolagem horizontal da página (Task 4, conferido à mão).

---

### Task 1: loader do ge guarda faixas, escudos e fases

**Files:** Modify `src/geral/stats/ge_models.py`, `src/geral/stats/ge_tables.py`, `src/geral/models.py`;
Test `tests/test_ge_tables.py`; fixtures novas gravadas do ge de hoje em `tests/fixtures/ge_tables/`
(`page_seriea.html`, `seriea_fase-unica.json`, `seriea_fase-unica_r36.json`, `page_serieb.html`,
`serieb_fase-unica.json`, `serieb_playoffs.json`, `page_seriec.html`, `seriec_*.json` das três fases).

**Produces:**
- `StandingRow.band: str | None = None`, `StandingRow.crest: str | None = None`.
- `Game.phase: str | None`, `Game.round: int | None`, `Game.tie: str | None`, `Game.home_crest / away_crest: str | None` (todos default `None`).
- `@dataclass(frozen=True) class Phase: name: str; kind: Literal["points","groups","knockout"] | None; bands: list[str]; groups: list[list[StandingRow]] | None` e `Competition.phases: list[Phase]` (fases publicadas, em ordem) e `Competition.current: int | None` (índice em `phases`).

- [ ] Gravar as fixtures com um script no scratchpad (rodadas que não a 36 respondem `[]` no teste via `side_effect`).
- [ ] Testes que falham: `test_ge_standing_keeps_band_name` (A: 1º `band="Libertadores"`, 20º `"Rebaixados"`, `crest` começa com `https://`), `test_competition_keeps_every_phase` (C: 3 fases, `current == 2`, bands da 2ª `["Finalistas e Série B", "Série B"]`), `test_game_knows_round_and_tie` (A: jogos da 36 com `round == 36`; B playoffs: `tie == "Playoff de acesso 1"`).
- [ ] Implementar: `band` pelo `faixa_classificacao.cor` casado com `faixas_classificacao[].cor` da fase; `round` passado por `_rounds`; `tie` = `chave.nome`; fase de grupos sem rodada fica `round=None`.
- [ ] `uv run pytest tests/test_ge_tables.py tests/test_general_collect.py tests/test_combined_stats.py` verde.
- [ ] Commit `feat: tabela do ge guarda faixas, escudos e todas as fases`.

### Task 2: retrato da Central

**Files:** Create `src/geral/central/__init__.py`, `src/geral/central/models.py`, `src/geral/central/build.py`; Test `tests/test_central_build.py` (Competition montada à mão, sem HTTP).

**Produces (`geral.central`):**
- Modelos: `MatchView(home, away, home_crest, away_crest, home_goals, away_goals, home_penalties, away_penalties, kickoff, time_valid, status: Literal["pre","live","post"], venue)`; `TieView(name, legs: list[MatchView], home_agg: int | None, away_agg: int | None, winner: str | None)`; `SerieSummary(champion, runner_up, promoted: list[str], relegated: list[str])`; `SerieView(name, slug: Literal["a","b","c","d"], status: Literal["points","knockout","over"], phase, table: list[StandingRow], bands: list[str], rounds: dict[int, list[MatchView]], current_round: int | None, ties: list[TieView], summary: SerieSummary | None)`; `TeamNextMatch(team_slug, team_name, opponent, kickoff, competition, is_home)`; `CentralSnapshot(updated_at, series: list[SerieView], next_matches: list[TeamNextMatch])`.
- `serie_view(competition: Competition, slug, now) -> SerieView`; `decide(tie: TieView) -> str | None`; `build_snapshot(now, previous: CentralSnapshot | None, client=None) -> CentralSnapshot`; `save_snapshot(path, snap)` / `load_snapshot(path) -> CentralSnapshot | None`.
- Regras: `table` = última fase de pontos sem grupos (a B segue com a tabela final nos playoffs); `current_round` = menor rodada com jogo não encerrado, senão a última; `status="over"` quando a fase atual é a última e todos os jogos dela estão encerrados; campeão/vice pela fase "Final" ou pelos dois primeiros da tabela; `promoted` = faixas com "Acesso" ou "Série " no nome (fase de pontos ou grupos) + vencedores dos confrontos de fases com "acesso" no nome, sem repetir; `relegated` = faixa que começa com "Rebaixados".

- [ ] Testes que falham: `test_points_serie_groups_games_by_round`, `test_knockout_serie_has_ties_with_aggregate`, `test_single_leg_final_aggregate`, `test_tie_decided_on_penalties`, `test_finished_serie_summary` (C: campeão, vice, 4 subiram, rebaixados), `test_finished_league_summary_uses_table` (A/B sem final), `test_unscheduled_game_is_pre_without_time`, `test_serie_failure_keeps_previous_version` (respx: página da B 500 → `series[1]` igual ao `previous`), `test_snapshot_roundtrip_json`.
- [ ] Implementar `build.py`; `next_matches` via `stats_client_for(team, tz)` de cada time `listed`, erro de um time só o tira da lista.
- [ ] Testes verdes; commit `feat: retrato da central com tabela, rodadas, confrontos e resumo`.

### Task 3: atualização a cada 10 minutos e comando

**Files:** Modify `src/geral/config.py`, `src/geral/web/app.py`, `src/geral/__main__.py`, `tests/conftest.py`; Test `tests/test_central_refresh.py`.

**Produces:** `Settings.CENTRAL_REFRESH: int = 600` (segundos; 0 desliga; `conftest` põe 0), `Settings.CENTRAL_SNAPSHOT: str | None = None` (padrão: `central.json` ao lado de `SUBSCRIBERS_DB`); `geral.central.refresh.Refresher(path, interval, build=build_snapshot)` com `run_once()` e `start()` (thread daemon, primeira rodada na hora); `create_app` o inicia no `lifespan` quando `CENTRAL_REFRESH > 0`; CLI `geral central [--out PATH]`.

- [ ] Testes: `test_refresher_run_once_writes_snapshot` (build falso), `test_refresher_survives_build_error` (exceção vira log, arquivo antigo intacto), `test_central_command_writes_out` (CliRunner com build falso).
- [ ] Implementar; testes verdes; commit `feat: central atualizada a cada dez minutos e comando geral central`.

### Task 4: página /central, bloco na inicial e menu

**Files:** Create `src/geral/web/templates/central.html.j2`; Modify `src/geral/web/app.py`, `templates/base.html.j2`, `templates/index.html.j2`; Test `tests/test_web_central.py`.

- [ ] Testes: `test_central_page_renders_each_status` (retrato de fixture: `?serie=a` tabela + legenda "Libertadores" + rodada 36; `?serie=b` "Playoff de acesso 1"; `?serie=c` "Campeão"), `test_central_default_serie_is_first_running`, `test_central_unknown_serie_falls_back`, `test_central_page_without_snapshot` (200, "em atualização"), `test_home_links_to_central` (bloco com líder da A e `href="/central"` no menu).
- [ ] Implementar: rota lê `load_snapshot` a cada requisição (arquivo pequeno); rodadas todas no HTML, JS troca a visível com setas; faixas como filete à esquerda da posição + legenda; nomes curtos na tabela no celular.
- [ ] Rodar local com `geral central` real + uvicorn, fotos desktop e 390 px, mostrar ao dev **antes** do commit visual.
- [ ] Conferir resumo da C e da D contra as notícias (acesso da D); registrar no PR.
- [ ] Commit `feat: página da central com tabelas e jogos e chamada na inicial`; marcar a feature e abrir PR.
