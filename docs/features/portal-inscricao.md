# Portal da Geral e inscrição por torcida (parte 2.1)

- **Data:** 2026-11-10
- **Status:** implementada (aguardando PR)
- **ADRs:** `docs/adr/0001-geral-assume-a-urubu-news.md` (a Urubu entra depois, na parte 2a)

## Objetivo

A Geral ganha o app web: o portal do rascunho aprovado
(https://claude.ai/artifact/4TwD5bpDS9NBmFoN6onH5b), onde a pessoa escolhe uma ou mais torcidas
com um e-mail só, confirma, recebe na hora a última edição de cada torcida escolhida e sai de uma
torcida ou de todas com um clique. O envio de cada torcida vai só para quem assina aquela torcida.

## Fora de escopo

- Agenda automática de todas as torcidas, disparo pela VPS e deploy (parte 2.2).
- Urubu News, bolão e migração de inscritos (parte 2a). Pedido de time (parte 3): o cartão
  "Peça seu time" aparece como "em breve", assim como a edição geral e os joguinhos.

## Contratos

App FastAPI em `geral.web` (`uvicorn geral.web.app:create_app --factory`), portado da Urubu News.

```
GET  /                       portal: torcidas do catálogo (mascote, cor, última edição), ingresso, placar
POST /subscribe              form: email, team (repetido, slugs do catálogo), website (honeypot)
GET  /confirm?token=         ativa o e-mail e as torcidas pendentes; boas-vindas por torcida nova
GET  /t/{slug}               última edição da torcida, para ler no site (sem links pessoais)
GET  /unsubscribe?token=     página: "sair da Timbu News" ou "sair de todas"
POST /unsubscribe?token=     token de torcida: sai só dela (one-click RFC 8058); token geral: de todas
GET  /api/subscribers?team=  Bearer -> [{"email", "unsubscribe_url"}] dos ativos naquela torcida
GET|PUT /api/teams/{slug}/latest-edition   Bearer; o run publica após cada envio real
GET  /static/{slug}/...      marcas; o run usa {PUBLIC_URL}/static/{slug}/logo-email.png no cabeçalho
GET  /health, /version.json
```

- Banco (SQLite, `SUBSCRIBERS_DB`): `subscribers` como na Urubu (conta e confirmação);
  `subscriptions(email, team, status pending|active, created_at, activated_at, PK(email, team))`;
  `editions(team PK, subject, html, text, published_at)`.
- Tokens HMAC como na Urubu: `confirm` (7 dias), `unsubscribe` (todas) e `unsubscribe:<slug>`.
- Quem já é ativo e marca torcidas novas recebe outra confirmação: ninguém inclui torcidas no
  e-mail de outra pessoa. Sem enumeração: `/subscribe` responde sempre "Confira seu e-mail".
- Sair da última torcida ativa marca o e-mail como `unsubscribed`.
- Anti-abuso da Urubu mantido: honeypot, 5 por IP por hora, teto diário, reenvio após 10 min.
- `geral run --team <slug>` lê `/api/subscribers?team=` e publica em
  `/api/teams/<slug>/latest-edition`; `--skip-if-sent` e os tópicos já publicados também por torcida.

## Critérios de aceite (como testes)

- [x] `test_subscribe_with_two_teams_creates_pending_subscriptions_and_sends_one_confirmation`
- [x] `test_subscribe_rejects_no_team_or_unknown_team` (400, nada gravado nem enviado)
- [x] `test_subscribe_same_page_for_active_email` e `test_honeypot_and_rate_limit` (portados)
- [x] `test_confirm_activates_teams_and_welcomes_with_each_latest_edition` (uma boas-vindas por torcida com edição; sem edição, nada)
- [x] `test_confirm_twice_does_not_welcome_again`
- [x] `test_active_subscriber_adding_a_team_needs_confirmation` (a torcida nova fica pendente até o clique)
- [x] `test_team_unsubscribe_leaves_the_other_teams` e `test_last_team_out_unsubscribes_the_email`
- [x] `test_unsubscribe_get_does_not_unsubscribe` e `test_one_click_post_unsubscribes_from_that_team`
- [x] `test_team_token_cannot_unsubscribe_another_team`
- [x] `test_api_subscribers_lists_only_active_in_that_team_and_requires_token`
- [x] `test_latest_edition_is_kept_per_team`
- [x] `test_portal_lists_catalog_teams_with_last_edition_and_counts`
- [x] `test_team_page_shows_latest_edition_without_personal_links`
- [x] `test_run_sends_only_to_that_team_and_publishes_its_edition`

## Verificação ponta a ponta

```bash
uv run pytest
SUBSCRIBE_SECRET=dev SUBSCRIBERS_API_TOKEN=dev uv run uvicorn geral.web.app:create_app --factory
# navegador: inscrever com Porco + Timbu (o link de confirmação sai no log, sem RESEND_API_KEY),
# confirmar, sair só da Timbu; PUBLIC_URL=http://localhost:8000 uv run geral run --team palmeiras
```

## Riscos e dúvidas abertas

- Domínio da Geral (`geral.diegoponte.dev`?): decide-se no deploy (parte 2.2).
