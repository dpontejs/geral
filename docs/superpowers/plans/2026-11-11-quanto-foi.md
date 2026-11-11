# "Quanto foi?" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Daily "guess the score" game of a historic Série A match, general edition plus one per fanbase.

**Architecture:** Pure game logic in `geral/games/quanto_foi.py` (load, pool, daily puzzle, judge) over a compact CSV committed in the repo; FastAPI routes in `app.py` render the page and judge guesses statelessly; the page is Jinja + a small vanilla JS that keeps streaks in `localStorage`.

**Tech Stack:** Python 3.12, FastAPI, Jinja, pytest, vanilla JS.

**Spec:** `docs/features/quanto-foi.md`

## Global Constraints

- No database, no change to `src/geral/web/store.py`, the bolão or the Urubu migration.
- Tests never hit the network; the import script is the only code that downloads.
- Code/logs in English; page copy in pt-BR. Commits: `tipo: descrição`, one line, no trailers.
- Editions: `geral`, `vasco`, `palmeiras`, `flamengo`, `nautico` (dataset name `Nautico`). ABC → 404.
- 6 guesses max; goals 0–20; day = Brasília date (`BRASILIA` from `app.py`).

## Review Focus

- More than 6 guesses, negative or >20 goals, empty list → 422 (Task 4 test).
- A match with no coaches recorded (2003–2013): the coach hint is skipped, not "None × None" (Task 3 test).
- Day boundary: at 01:00 UTC it is still the previous day in Brasília (Task 4 test).
- Puzzle numbers before 1 or after today → 404, so nobody peeks tomorrow (Task 4 test).
- Same score guessed twice still counts as a try (Task 3 test).

---

### Task 1: Match data and import

**Files:**
- Create: `src/geral/games/__init__.py`, `src/geral/games/quanto_foi.py`, `scripts/import_brasileirao.py`, `tests/fixtures/brasileirao/full.csv`, `tests/fixtures/brasileirao/gols.csv`, `tests/test_quanto_foi.py`
- Create (generated): `src/geral/games/data/brasileirao.csv`

**Interfaces:**
- Produces: `Match` (frozen dataclass: `id: int, day: date, round: int, home: str, away: str, home_goals: int, away_goals: int, stadium: str, home_coach: str, away_coach: str, home_scorers: tuple[str, ...], away_scorers: tuple[str, ...]`); `convert(full_csv: str, goals_csv: str) -> str` (source CSVs → compact CSV text); `load_matches(path: Path = DATA) -> list[Match]`.

- [ ] Fixture: ~12 rows copied from the real `campeonato-brasileiro-full.csv` (same header) covering Vasco, Palmeiras, Flamengo, Nautico, a 2003 match without coaches, a 2014+ match with goals in `gols.csv` (including an own goal).
- [ ] Test `test_convert_keeps_scores_and_attaches_scorers`: `load_matches` on the output of `convert(fixture)` returns the fixture's matches with ints, `date`, and scorers per side; own goal listed as `"<name> (contra)"` on the side that benefited.
- [ ] Run → FAIL (module missing). Implement `convert` and `load_matches` (csv module; semicolon-join scorers). Run → PASS.
- [ ] `scripts/import_brasileirao.py`: download both CSVs with httpx from `raw.githubusercontent.com/adaoduque/Brasileirao_Dataset/master/`, write `convert(...)` to `DATA`. Run it once; commit the data file.
- [ ] Commit: `feat: import brasileirao matches for the quanto foi game`

### Task 2: Pool and daily puzzle

**Interfaces:**
- Consumes: `Match`, `load_matches`.
- Produces: `EDITIONS: dict[str, str | None]`, `BIG_12: frozenset[str]` (dataset names), `LAUNCH = date(2026, 11, 12)`, `pool(matches, edition) -> list[Match]`, `Puzzle(number: int, match: Match)`, `puzzle(matches, edition, day: date) -> Puzzle`, `puzzle_number(day) -> int`, `by_number(matches, edition, number) -> Puzzle`.

- [ ] Tests: `test_puzzle_is_the_same_for_everyone_on_a_day`, `test_puzzle_does_not_repeat_until_the_pool_ends` (len(pool) consecutive days → all distinct ids), `test_team_pool_only_has_the_team_matches`, `test_geral_pool_keeps_only_memorable_matches` (a 1x0 between small teams is out; 4x4 in).
- [ ] Run → FAIL. Implement: order = pool sorted by id, shuffled with `random.Random(f"quanto-foi:{edition}")`; index `(number - 1) % len(pool)`. Run → PASS.
- [ ] Commit: `feat: pick the daily quanto foi match per edition`

### Task 3: Judge

**Interfaces:**
- Produces: `Side(status: Literal["certo","perto","longe"], hint: Literal["mais","menos",""])`, `Verdict` (pydantic: `rows: list[tuple[Side, Side]]`, `solved: bool`, `over: bool`, `hints: list[str]`, `reveal: Reveal | None`), `Reveal(home, away, home_goals, away_goals, stadium, day, home_scorers, away_scorers)`, `judge(match, guesses: list[tuple[int, int]]) -> Verdict`.

- [ ] Tests: `test_judge_marks_exact_close_and_far_per_side` (answer 3x1, guess 2x1 → (perto, mais), (certo, "")), `test_judge_reveals_only_when_over`, `test_judge_gives_hints_after_misses` (3 misses → `"Técnicos: A × B"`; 4 → `"Venceu: <time>"` or `"Deu empate"`), `test_judge_skips_coach_hint_when_unknown`, `test_repeated_guess_counts_as_a_try`.
- [ ] Run → FAIL. Implement. Run → PASS. Commit: `feat: judge quanto foi guesses`

### Task 4: Routes, page and portal card

**Files:** Modify `src/geral/web/app.py`, `src/geral/web/templates/index.html.j2`; Create `src/geral/web/templates/quanto_foi.html.j2`, `src/geral/static/geral/quanto-foi.js`, `tests/test_web_quanto_foi.py`.

**Interfaces:** Consumes Tasks 1–3. `create_app(..., matches: list[Match] | None = None)` (tests pass the fixture).

- [ ] Tests: `test_game_page_shows_the_match_without_the_score`, `test_team_edition_page`, `test_unknown_or_abc_edition_is_404`, `test_api_judges_guesses`, `test_api_rejects_future_or_zero_puzzle`, `test_api_rejects_bad_guesses` (7 guesses, -1, 21, empty → 422), `test_day_follows_brasilia_time`, `test_portal_links_the_game` (`href="/jogos/quanto-foi"`, no "7 a 0").
- [ ] Run → FAIL. Implement routes (`GET /jogos/quanto-foi`, `GET /jogos/quanto-foi/{edition}`, `POST /api/jogos/quanto-foi/{edition}/{number}` with `GuessesIn`), page (lamp board with the two names, date, round, stadium; two number inputs; rows of colored lamps; hints; reveal; share button with the spec's text; streak), JS (POSTs all guesses so far, renders `Verdict`, stores `{number, guesses}` and streak per edition in `localStorage` with try/catch). Run → PASS.
- [ ] Manual: run the app, play geral and vasco on desktop and 390 px. Commit: `feat: play quanto foi on the portal`
