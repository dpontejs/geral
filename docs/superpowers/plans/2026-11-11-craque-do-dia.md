# "Craque do dia" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Daily Wordle of a fanbase's idols, one edition per team (ABC included) plus a mixed one.

**Architecture:** Curated TOML lists per team slug; pure logic in `geral/games/craque.py` sharing
the daily order with "Quanto foi?" through `geral/games/daily.py`; stateless judge route in
`app.py`; Jinja page + small vanilla JS, common game CSS in `static/geral/jogos.css`.

**Spec:** `docs/features/craque-do-dia.md`

## Global Constraints

- No database; no change to `store.py`, the bolão or the Urubu migration. No club names in code.
- Tests never hit the network. Commits: `tipo: descrição`, one line, no trailers.

## Review Focus

- Repeated letters (answer "PELE", guess "EEEE"): only one E per real E gets a mark (Task 2).
- Accented guesses ("Nenê") must match the plain answer (Task 2).
- A guess with spaces, digits or the wrong length → 422, never a 500 (Task 3).
- The "Quanto foi?" puzzle of a day must not change after the `daily.py` extraction (Task 1).
- A team without a list file has no edition and no tab (Task 3).

### Task 1: `daily.py` extraction
- [ ] `test_quanto_foi_order_is_unchanged` (pin today's real puzzle ids for geral/vasco before the
      change), then move `shuffled`/`number_on` into `daily.py`; quanto_foi uses them. Commit
      `refactor: share the daily puzzle order between games`.

### Task 2: lists and judge (`craque.py`, `craques/*.toml`)
- [ ] Tests from the spec (rules, normalize, judge with repeated letters, hints, reveal, pools)
      over a fixture dir `tests/fixtures/craques/`; implement; write the real lists (30–40 per
      team); `test_lists_follow_the_rules` runs on them. Commit `feat: craque do dia lists and judge`.

### Task 3: routes, page, portal card
- [ ] Web tests from the spec; routes, `craque.html.j2`, `craque.js`, `jogos.css` (moved from the
      quanto foi template), Intervalo card. Manual play at 1280/390 px. Commit
      `feat: play craque do dia on the portal`.
