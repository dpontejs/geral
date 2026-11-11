# Portal da Geral e inscrição por torcida — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline). Steps use `- [ ]`.

**Goal:** app web da Geral com portal, inscrição em várias torcidas, boas-vindas e descadastro por torcida, e o `run` enviando só para a torcida.

**Architecture:** portar `flanews.web` (commit `79c3aef` do `flamengo-news`, sem `bolao.py`) para `geral.web`, acrescentando `team` em assinaturas, edições e tokens de descadastro. O portal segue o rascunho aprovado.

**Tech Stack:** FastAPI, SQLite, Jinja2, Resend, pytest + `fastapi.testclient` + respx.

**Spec:** `docs/features/portal-inscricao.md`

## Global Constraints

- Código, nomes e logs em inglês; textos das páginas e e-mails em pt-BR.
- Sem rede nos testes (respx); `SUBSCRIBE_SECRET` obrigatório para subir o app.
- Slugs válidos só os de `geral.teams.load_teams()`.
- Paleta do portal: `#EFE4CC`, `#E6D8BA`, `#8E8B84`, `#B9B5AC`, `#1E1E1E`, `#E3B23C`, `#23221F`; Oswald + IBM Plex Sans + IBM Plex Mono; cor de cada torcida = `Team.accent`.
- Commits: conventional, sem escopo, uma linha, sem coautoria.

## Review Focus

1. E-mail com maiúsculas/espaços e torcida repetida no form → normalizados, sem duplicar linha (teste na Task 1).
2. Token `unsubscribe:vasco` usado em `POST /unsubscribe` de outra torcida → não afeta a outra (Task 3).
3. Confirmação de quem já é ativo e só adicionou torcida → boas-vindas só das torcidas novas (Task 3).
4. Torcida sem edição guardada → portal mostra "Primeira edição em breve" e `/t/{slug}` responde 404 amigável (Task 4).
5. Slug removido do catálogo com assinaturas antigas no banco → ignorado no portal e na API (Task 1: `active(team)` só aceita slug do catálogo, na Task 3).

---

### Task 1: Store e tokens por torcida

**Files:** Create `src/geral/web/__init__.py`, `src/geral/web/tokens.py` (cópia), `src/geral/web/store.py`; Test `tests/test_web_tokens.py` (cópia), `tests/test_web_store.py`.

**Interfaces — Produces** (`geral.web.store`):
- `SubscriberStore(path)`; mantém `get`, `request(email, now) -> RequestResult`, `forget_confirmation`, `confirmations_sent_since`, `purge` da Urubu.
- `add_teams(email, teams: list[str], now) -> list[str]` — insere pendentes; devolve as que eram novas (não ativas).
- `confirm(email, now) -> list[str]` — ativa conta e pendentes; devolve as torcidas ativadas agora (vazia = nada mudou).
- `teams_of(email) -> list[str]` (ativas); `leave(email, team, now)`; `leave_all(email, now)`; sair da última → `unsubscribed`.
- `active(team) -> list[str]`; `counts() -> dict[str, int]` (ativos por torcida).
- `set_latest_edition(team, subject, html, text, now)`; `latest_edition(team) -> Edition | None`; `latest_editions() -> dict[str, Edition]`.

- [ ] Testes: `test_add_teams_normalizes_email_and_ignores_repeats`, `test_confirm_returns_only_newly_activated_teams`, `test_leave_one_team_keeps_others`, `test_leaving_last_team_unsubscribes`, `test_active_lists_only_that_team`, `test_counts_per_team`, `test_latest_edition_is_kept_per_team`, mais os testes portados da Urubu (cooldown, purge, reinscrição após descadastro exige confirmação).
- [ ] Rodar: falham por import. Implementar schema da spec (`subscriptions`, `editions(team PK)`); `purge` também apaga assinaturas pendentes antigas.
- [ ] `uv run pytest tests/test_web_store.py tests/test_web_tokens.py` verde → commit `feat: keep subscriptions and latest editions per team`.

### Task 2: Mailer e boas-vindas por torcida

**Files:** Create `src/geral/web/mailer.py`, `src/geral/web/welcome.py`, `src/geral/web/templates/email/confirm.{html,txt}.j2`; Test `tests/test_web_mailer.py`, `tests/test_welcome.py`.

**Interfaces — Produces:**
- `Mailer.send_confirmation(email, confirm_url, teams: list[Team])`; `send_edition(email, team: Team, subject, html, text, unsubscribe_url)`; `send_notification(to, subject, text)`. Remetente das edições: `formataddr((team.newsletter, address))`; da confirmação: `"Geral"`.
- `add_welcome(html, text, team: Team) -> tuple[str, str]` — caixa com `team.accent`, título `f"Boas-vindas à {team.newsletter}!"`, texto com `team.name`.
- Assunto da confirmação: `"Confirme sua inscrição na Geral"`; o corpo lista as newsletters escolhidas.

- [ ] Testes (respx no Resend): `test_confirmation_lists_chosen_newsletters`, `test_edition_sender_is_the_team_newsletter`, `test_welcome_box_uses_team_name_and_accent`, mais os portados (erro do Resend vira `MailError`, `LogMailer` sem chave).
- [ ] Implementar; verde; commit `feat: send geral confirmations and per-team welcome editions`.

### Task 3: Rotas de inscrição, descadastro e API

**Files:** Create `src/geral/web/app.py`, `src/geral/web/templates/{base,message}.html.j2`; Modify `src/geral/config.py` (`SUBSCRIBE_SECRET`, `SUBSCRIBERS_API_TOKEN`, `SUBSCRIBERS_DB`, `NOTIFY_EMAIL` já existem; `PUBLIC_URL` default fica); Test `tests/test_web_app.py`.

**Interfaces — Consumes:** Tasks 1 e 2. **Produces:** `create_app(settings=None, store=None, mailer=None, now=..., teams=None) -> FastAPI` (`teams` padrão `load_teams()`); rotas da spec.

- [ ] Testes (TestClient + FakeMailer): os 11 primeiros critérios de aceite da spec, com estes nomes, mais `test_confirm_of_active_subscriber_welcomes_only_new_teams` e `test_unknown_team_in_db_is_ignored_by_api`.
- [ ] Implementar: `POST /subscribe` lê `form.getlist("team")`, filtra pelo catálogo, sem torcida válida → 400 na página inicial com erro "Escolha pelo menos uma torcida."; `confirm` envia `send_edition` por torcida ativada que tenha edição; unsubscribe com purpose `unsubscribe:<slug>` ou `unsubscribe`; a página GET oferece os dois botões quando o token é de torcida.
- [ ] Verde; commit `feat: subscribe to one or more teams and leave each one separately`.

### Task 4: Portal, página da torcida e marcas

**Files:** Create `src/geral/web/templates/{index,team}.html.j2`; Modify `src/geral/web/app.py` (`GET /`, `GET /t/{slug}`, `/static`, `/favicon.ico` → `/static/geral/icon-512.png`); Test `tests/test_web_portal.py`.

- [ ] Testes: `test_portal_lists_catalog_teams_with_last_edition_and_counts` (nome da newsletter, `/static/<slug>/icon-512.png`, assunto da última edição, contagem), `test_portal_without_edition_says_first_edition_soon`, `test_team_page_shows_latest_edition_without_personal_links` (o marcador de descadastro vira link para `/`), `test_team_page_unknown_or_empty_is_404`, `test_static_brand_files_are_served`.
- [ ] Implementar o portal com o layout do rascunho: torcidas do catálogo, ingresso com um checkbox por torcida (`name="team"`), cartões "em breve" (edição geral, 7 a 0, peça seu time), placar com `counts()`.
- [ ] Verde; conferir no navegador (`uvicorn ... --factory`); commit `feat: add the geral portal and team pages`.

### Task 5: `run` por torcida

**Files:** Modify `src/geral/send/recipients.py`, `src/geral/__main__.py`, `src/geral/render/renderer.py` + template (logo via parâmetro `logo_url`, remove `Team.brand_logo`), `src/geral/teams.py`; Test `tests/test_run_command.py`, `tests/test_recipients.py`, `tests/test_renderer.py`.

**Interfaces:** `fetch_subscribers(settings, team) ` → `GET /api/subscribers?team=<slug>`; `publish_latest_edition(settings, team, subject, html, text)` e `latest_edition(settings, team)` → `/api/teams/<slug>/latest-edition`; `render(..., logo_url: str | None = None)`; o CLI passa `f"{PUBLIC_URL}/static/{slug}/logo-email.png"` quando `src/geral/static/<slug>/logo-email.png` existe.

- [ ] Testes: `test_run_sends_only_to_that_team_and_publishes_its_edition` (respx nas duas rotas com `team=flamengo`), `test_skip_if_sent_reads_the_team_edition`, ajuste dos testes de cabeçalho para `logo_url`.
- [ ] Implementar; `uv run ruff check . && uv run ruff format --check . && uv run pytest` verde; commit `feat: send and publish each edition only for its team`.

### Fechamento

- [ ] Verificação ponta a ponta da spec (inscrever em Porco + Timbu pelo navegador, confirmar pelo link do log, sair só da Timbu, `geral run --team palmeiras` contra o app local com `DRY_RUN=false` e `RESEND_API_KEY` vazio → envio só logado).
- [ ] Marcar critérios na spec e `[x]` no TASKS; PR.
