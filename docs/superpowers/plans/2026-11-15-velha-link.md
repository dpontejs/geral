# Jogo da velha — PR 4 (duelo por link) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** X creates a duel, sends the link, O joins from another device; both see every move and the
30 s clock in under a second; the server owns the clock and the rules.

**Architecture:** `web/velha_partidas.py` keeps each duel in its own table of the same SQLite (not
`store.py`): the board code, the two tokens, the moves and the current turn's deadline. The state is
always `judge_duel(base, board, moves)` from PR 3; a deadline that passed becomes `{estouro}` moves on
any read or write. Routes in `app.py`; live updates by SSE with a 3 s polling fallback.

**Tech Stack:** FastAPI (StreamingResponse for SSE), sqlite3, vanilla JS, pytest + TestClient.

**Spec:** `docs/features/jogo-da-velha.md` ("Duelo por link"). Stacked on PR 3 (#47, `feat/velha-duelo`).

## Global Constraints

- No change to `store.py`, bolão, Urubu; same SQLite file (`settings.SUBSCRIBERS_DB`), own table.
- One process (as the Dockerfile runs it): SSE and the in-memory rate limiter rely on it.
- Tokens are secrets (`secrets.token_urlsafe(16)`), never shown to the other side or in HTML.
- Same look as the same-screen duel; screenshots (two browsers) to the dev before committing the page.
- Commits `tipo: descrição`, one line, no trailers; tests never hit the network.

## Decisions

- **Table** `velha_partidas(id TEXT PK, tabuleiro TEXT, x_token TEXT, o_token TEXT NULL,
  jogadas TEXT JSON, prazo TEXT NULL, criada_em TEXT)`. The spec's `vez`, `casas`, `sem_casa`,
  `status` are derived from the moves by `judge_duel` (one source of truth, no drift). `id` =
  `secrets.token_urlsafe(6)`.
- **Clock:** `prazo` = end of the current turn (UTC). NULL until O joins; then `now + 30 s`. Before
  any read or write, `_expire(row, now)`: while not over and `now >= prazo`, append `{estouro}` and
  move `prazo` 30 s on. After a move, `prazo = now + 30 s`; over → `prazo = NULL`.
- **Move** `POST …/partidas/{id}/jogada {token, vez_n, casa, jogador}`: `vez_n` = number of moves the
  browser had seen; `vez_n != len(jogadas)` → return the state unchanged (a retry or a stale tab
  never plays twice). Token of nobody or of the side not on turn → 403; taken cell or game over →
  409; unknown player → 422; no duel or created > 24 h ago → 404. A wrong player is a normal miss
  (passes the turn), like in PR 3.
- **Join** `POST …/{id}/entrar` → `{token}` for O once; later 409 and the page only watches.
- **Create** `POST /api/jogos/velha/partidas` → `{id, token}`; at most 20 per network per hour
  (`RateLimiter` + `network()`); deletes duels older than 24 h. The page keeps tokens in
  `localStorage["velha:p:{id}"]`.
- **State** `GET …/{id}` and SSE `GET …/{id}/eventos`: `{id, tabuleiro labels, casas, jogadores,
  nomes, vez, over, vencedor, linha, jogou: len(jogadas), o_entrou, prazo, agora}`; the browser
  draws the clock from `prazo - agora` (no trust in the device clock). The stream sends the state on
  connect and whenever `(len(jogadas), o_entrou, prazo)` changes, checking every 0.5 s, and ends when
  the game is over or after 5 minutes (the browser reconnects); on error the page polls every 3 s.
- **Entry:** the duel page's start box gets two buttons: "Começar aqui" (PR 3) and "Desafiar por
  link" (creates the duel and opens `/jogos/velha/p/{id}`, where X shares the link and waits).

## Review Focus

- Two tabs of X (same token) sending the same move: it counts once (`vez_n`) (Task 2).
- A deadline that passed while nobody looked is applied as many times as turns went by (Task 1).
- O's token cannot play X's turn, and a watcher without token cannot play at all (Task 2).
- The clock does not run before O joins (Task 1).
- A duel id that does not exist, or one from yesterday, is 404 on every endpoint (Task 2).

### Task 1: duel store and server clock (`web/velha_partidas.py`)
- **Produces:** `DuelStore(path)`: `create(board_code, now) -> (id, x_token)`; `join(id, now) ->
  str | None` (O token, None if taken); `play(id, token, vez_n, move, now, judge) -> Row`;
  `get(id, now) -> Row | None` (expired turns applied and saved); `purge(now)`. `Row(id, tabuleiro,
  x_token, o_token, jogadas: list[dict], prazo: datetime | None, criada_em)`. Exceptions
  `DuelNotFound`, `NotYourTurn`, `DuelConflict` (the routes map them to 404/403/409).
- [ ] Tests (`tests/test_velha_partidas.py`, real SQLite in tmp_path, clock passed in):
      `test_creator_is_x_and_the_first_to_join_is_o_then_nobody`,
      `test_clock_starts_when_o_joins`, `test_expired_turns_become_timeouts_on_read`
      (join, +65 s → two `estouro`, `prazo` = join + 90 s), `test_same_move_twice_counts_once`,
      `test_old_duels_are_gone_after_24_hours`. Commit `feat: keep jogo da velha duels by link`.

### Task 2: routes and events (`web/app.py`)
- [ ] `tests/test_web_velha_partidas.py` (clock fixture): the spec's
      `test_duel_creator_is_x_and_the_first_to_join_is_o_then_others_only_watch`,
      `test_duel_move_out_of_turn_or_with_the_other_token_is_403`,
      `test_duel_wrong_answer_or_timeout_passes_the_turn` (clock +31 s),
      `test_duel_three_in_a_row_wins_and_later_moves_are_409`,
      `test_duel_ends_after_six_turns_without_a_cell_and_most_cells_wins`,
      `test_duel_same_move_twice_counts_once`, plus `test_unknown_or_old_duel_is_404`,
      `test_creating_duels_is_limited_per_network`, and
      `test_duel_events_stream_sends_the_new_state_after_a_move` (the generator `duel_events(…)`
      driven with a fake sleep that plays a move between ticks).
- [ ] Routes: create, page `GET /jogos/velha/p/{id}` (declared before `/jogos/velha/{edition}`),
      join, move, state, events. Commit `feat: jogo da velha duel by link routes`.

### Task 3: page and script
- [ ] `velha_partida.html.j2` + `velha-partida.js`: X sees "Mande o link" (share/copy) until O
      joins; O sees "Entrar como O"; a third person watches. Same board, score plates and search
      dialog as PR 3; my side lit; clock from the server; moves sent with `vez_n`; SSE with polling
      fallback. "Desafiar por link" on the duel start box. Playwright with two contexts: X creates,
      O joins by the link, a right move, a wrong one and a timeout show in the other browser in < 1 s.
      Screenshots → dev → commit `feat: play the jogo da velha duel by link`.

## Verification

`uv run ruff check . && uv run ruff format --check . && uv run pytest`; the two-browser Playwright
run above; fresh-context review; PR on #47.
