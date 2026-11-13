# Jogo da velha — PR 1 (base, categories, board, judge) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** The player base, the categories, the board generator and the solo judge of the jogo da
velha, with no page yet (PR 2 adds the solo daily page).

**Architecture:** Pure logic in `src/geral/games/velha/` (`base.py`, `board.py`, `judge.py`) over a
generated `base.json`; the download lives in `src/geral/games/velha/importacao.py` (testable with
respx) behind a thin `scripts/import_base.py`. MediaWiki/SPARQL helpers move from
`scripts/import_carreiras.py` to `src/geral/games/mediawiki.py` so both importers share them.

**Tech Stack:** Python 3.12, httpx + respx, pydantic, tomllib.

**Spec:** `docs/features/jogo-da-velha.md`

## Global Constraints

- No change to `store.py`, the bolão, the Urubu migration or `carreiras.json` (106 craques stays).
- Clubs only Brazilian; Seleção = the senior Brazil team (Q83459); Copa = any FIFA World Cup, any
  team; club counts loans, not youth (as in "Onde jogou?"). No prizes, no per-team edition.
- Tests never hit the network; `time.sleep` is patched out in importer tests.
- Commits: `tipo: descrição`, one line, no trailers. Code and logs in English, labels in pt-BR.

## Decisions (verified on Wikidata/Wikipedia on 2026-11-13)

- **Size:** ~1000 players with P54 Flamengo, ~700 Internacional, ~830 Seleção; the 30 clubs give
  well over 6000. Keep players with `fama` (sitelinks) ≥ `MIN_FAMA`: on the first real run pick the
  smallest value ≥ 2 that leaves ≤ 6000 players, write it as a constant, say it in the PR.
- **Copa:** P1344 is good for 1930–2018 (250–740 per edition) but thin for 2022 (130) and mixed
  with qualifiers for 2026. So Copa = the "{year} FIFA World Cup squads" pages of the 23 editions
  (`{{nat fs g player|…|name=[[Title|…]]}}`, links resolved to ids with `page_qids`) ∪ P1344 on
  the editions 1930–2018 only (`EDITIONS` = their 21 ids, hardcoded; qualifier items excluded).
- **Positions** (P413, a player may have several), grouped: `goleiro` Q201330 Q172964;
  `zagueiro` Q336286 Q268258; `lateral` Q90173132; `meio-campo` Q193592 Q904289 Q8025128
  Q90326494 Q18691898 Q1201458; `atacante` Q280658 Q9731197 Q3446915 Q11681748. Other ids are
  listed by the import report and added to the map by hand.
- **País:** P1532, else P27 when it has a single value; Brazil (Q155) dropped. Labels pt-BR with
  `onde_jogou.COUNTRY_NAMES`.
- **Clubs** (`velha/clubes.toml`, `[Qid] nome = "…"`; never remove an entry: frozen boards use it).
  Série A 2026: Atlético-MG Q270995, Athletico-PR Q506832, Bahia Q198032, Botafogo Q80958,
  Bragantino Q541744, Chapecoense Q2536715, Corinthians Q35933, Coritiba Q478317, Cruzeiro Q188277,
  Flamengo Q17479, Fluminense Q80987, Grêmio Q221695, Internacional Q80845, Mirassol Q2622870,
  Palmeiras Q80964, Remo Q2552872, Santos Q80955, São Paulo Q38568, Vasco Q5014111,
  Vitória Q274465. Historic: América-MG Q338285, Ceará Q1052219, Fortaleza Q188841, Goiás Q816779,
  Guarani Q1133475, Juventude Q910453, Náutico Q73971, Portuguesa Q204675, Santa Cruz Q508440,
  Sport Q219098.
- **Board code** (used by PR 2's calendar): `"clube:Q17479|selecao:BRA|copa:FIFA|pais:Q77|…"`,
  3 rows then 3 columns; cell index `casa = linha * 3 + coluna`.

## Review Focus

- A player with no position, country or years must fit nothing there and never crash (Task 3).
- Brazil U-20 or Olympic caps are not Seleção (Task 2).
- A squads link to a redirect still finds the player (Task 6, recorded redirect).
- Guess after the game is over, cell 9 or −1, unknown id → `GuessError`, never a silent pass (Task 5).
- The 12th guess that fills the 9th cell ends the game once, as a hit (Task 5).

### Task 1: share the MediaWiki helpers (`src/geral/games/mediawiki.py`)
- [ ] `test_api_waits_and_retries_on_429` (respx: 429 with `Retry-After: 1`, then 200 → returns
      the JSON; sleep patched). Move `HEADERS`, `api`, `enwiki_titles`, `wikitexts`, `page_qids`
      and a new `sparql(client, query) -> list[dict]` (the 429 loop of `fetch`/`club_info`, returns
      the bindings) out of `import_carreiras.py`, which imports them. `uv run pytest` green.
      Commit `refactor: share the wikidata and wikipedia helpers between importers`.

### Task 2: national team and squads in `wikipedia.py`
- [ ] `test_national_teams_reads_the_senior_teams_only`: infobox with `nationalteam1 = [[Brazil
      national under-20 football team|Brazil U20]]`, `nationalteam2 = {{nowrap|[[Brazil national
      football team|Brazil]]}}` → `national_teams(text) == ["Brazil national under-20 football
      team", "Brazil national football team"]`, and `SELECAO_PAGE in national_teams(...)` only by
      the second. `test_squad_players_reads_the_nat_fs_links`: two `nat fs g player` lines (one
      `[[Félix Torres (footballer, born 1997)|Félix Torres]]`) → the two page titles.
- [ ] `national_teams(wikitext) -> list[str]` (`nationalteamN` through `_club`), `SELECAO_PAGE =
      "Brazil national football team"`, `squad_players(wikitext) -> list[str]`. Commit
      `feat: read the national team and world cup squads from wikipedia`.

### Task 3: base and categories (`velha/base.py`, `velha/clubes.toml`)
- **Produces:** `Player(id, nome, anos: str, posicoes: tuple[str, ...], paises: tuple[str, ...],
  fama: int, clubes: frozenset[str], selecao: bool, copa: bool)`; `Base(players: dict[str,
  Player], clubs: dict[str, str], countries: dict[str, str])` with `players_in(cat) ->
  frozenset[str]` (cached); `load(path=BASE) -> Base`; `Category(kind: Literal["clube","selecao",
  "copa","pais","posicao"], value: str, label: str)` frozen, `.code` = `"kind:value"`;
  `category(base, code) -> Category` (`ValueError` if unknown); `fits(base, player_id, a, b) ->
  bool`; `answers(base, a, b) -> list[Player]` (fama desc, then nome). Labels: club name,
  "Seleção Brasileira", "Jogou uma Copa", country label, position ("Goleiro", "Zagueiro",
  "Lateral", "Meio-campo", "Atacante").
- [ ] `test_fits_crosses_club_selecao_copa_country_and_position` (spec values, tiny base built in
      the test), `test_player_without_position_or_country_fits_neither`,
      `test_category_rejects_unknown_codes` (`clube:Q1`, `cor:azul`). Implement. Commit
      `feat: jogo da velha categories and fit`.

### Task 4: board generator (`velha/board.py`)
- **Produces:** `Board(rows: tuple[Category, ...], cols: tuple[Category, ...])` with `.code`,
  `cell(casa) -> tuple[Category, Category]`; `parse_board(base, code) -> Board`;
  `make_board(base, rng: random.Random) -> Board`.
- [ ] `test_make_board_gives_every_cell_three_answers` (200 seeds on a synthetic base of ~300
      players from a fixed rng: ≥ 3 answers per cell, 6 distinct categories, ≤ 2 of
      `posicao`/`pais` together), `test_board_code_round_trips`, `test_make_board_is_the_same_for_the_same_seed`.
- [ ] Rejection sampling: draw 6 distinct categories from the pool (every club; selecao; copa;
      countries and positions with ≥ 10 players), weights clube 6 : selecao 1 : copa 1 : pais 1 :
      posicao 1; first 3 rows, last 3 cols; accept when the rules hold, else redraw (raise
      `RuntimeError` after 2000 tries). Commit `feat: generate jogo da velha boards`.

### Task 5: solo judge (`velha/judge.py`)
- **Produces:** `Guess(casa: int, jogador: str)`; `Answer(id, nome)`; `CellReveal(top:
  list[Answer], total: int)`; `SoloVerdict(casas: dict[int, str], acertos: list[bool], over:
  bool, revelacao: list[CellReveal] | None)` (pydantic); `GuessError(ValueError)`;
  `judge_solo(base, board, chutes: list[Guess]) -> SoloVerdict`; `MAX_GUESSES = 12`.
- [ ] `test_solo_judge_fills_cells_counts_misses_and_reveals_only_at_the_end` (`revelacao` None
      until over; then 9 cells with top 3 by fama and the total), `test_solo_reusing_a_player_is_a_miss`,
      `test_solo_twelve_guesses_end_the_game`, `test_solo_rejects_taken_cell_bad_cell_unknown_player_and_guess_after_the_end`.
      Implement. Commit `feat: judge the solo jogo da velha`.

### Task 6: importer and the real base
- **Produces:** `importacao.build_base(client, clubs: dict[str, str]) -> tuple[dict, list[str]]`
  (the `base.json` dict `{"paises": {qid: label}, "jogadores": [...]}` sorted by id, one player
  per line when written, and the report lines); `scripts/import_base.py` writes `base.json`,
  prints the report (players per club, Seleção, Copa per edition from each source, positions
  without group, players from Wikidata only).
- [ ] `test_import_base_builds_from_recorded_wikidata_and_wikipedia`: respx fixtures in
      `tests/fixtures/velha/` (SPARQL members, labels, P1344; enwiki sitelinks; wikitexts of 3
      players: one Vasco + Seleção with an infobox, one Uruguayan at Grêmio who went to a Copa only
      via a squads page whose link is a redirect, one with no infobox using Wikidata P54); asserts
      the three players' fields, `anos` (`"1985–2002"`, open end `"2019–"`), and a fama below
      `MIN_FAMA` left out.
- [ ] Implement: SPARQL members of each club and Q83459 (id, label pt-br, sitelinks, P413, P1532,
      P27, P54+dates for the fallback), careers through `parse_career`/`page_qids`, Seleção through
      `national_teams`, Copa as decided. Run for real; check the report (no big club ralo); add
      `test_real_base_boards` (50 seeds on `base.json`, every cell ≥ 3). Commit
      `feat: import the jogo da velha player base`.

## Verification

`uv run ruff check . && uv run ruff format --check . && uv run pytest`; `uv run python
scripts/import_base.py` report pasted in the PR (counts, MIN_FAMA, 3 sample boards with answers).
