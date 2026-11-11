# A Urubu News entra na Geral (parte 2a)

- **Data:** 2026-11-11
- **Status:** PRs 1 e 2 entregues (geral #8); virada pronta (`infra` #28 + PR da virada)
- **ADRs:** `docs/adr/0001-geral-assume-a-urubu-news.md`

## Objetivo

A Urubu News passa a ser a torcida `flamengo` da Geral, com o mesmo nome, logo, cor e bolão, e
sem que os leitores percebam a troca: os links dos e-mails já enviados (descadastro, one-click,
palpite, ranking, logo) seguem funcionando, os inscritos e o ranking da temporada vêm junto, e
ninguém recebe edição em dobro. O bolão passa a valer para todas as torcidas.

## Fora de escopo

- Placar da Geral somando pontos do bolão (só inscritos, como hoje); joguinhos e design (outro chat).
- Apagar o código ou os dados da Urubu (`flamengo-news` fica intacto, é o caminho de volta).

## Entrega em 3 PRs, nesta ordem

1. **Bolão por torcida** (portado de `flanews.web.bolao` + cartela/quadro da newsletter).
   - Tabelas com `team`: `bolao_matches(team, match_id, opponent, home, kickoff, our_goals, their_goals, PK(team, match_id))`,
     `bolao_bets(email, team, match_id, our_goals, their_goals, updated_at, PK(email, team, match_id))`,
     `bolao_players(email PK, nickname UNIQUE NOCASE)` (apelido único na Geral toda).
   - Token `bet` (por e-mail, sem expirar) vale para qualquer torcida; só palpita quem assina a torcida.
   - `GET|POST /palpite?t=&c=<slug>&m=&p=` (GET só pergunta), `GET /bolao/<slug>?t=` (ranking da
     temporada); API `PUT /api/teams/<slug>/bolao/matches/{id}`, `GET .../summary?ours=&theirs=`,
     `PUT .../result`; `/api/subscribers?team=` ganha `bet_token`.
   - Newsletter: cartela 4×4 no pré-jogo, quadro no pós-jogo (quem cravou, top 5, Rei do Maracanã,
     Pé-frio), como na Urubu; prévia e `DRY_RUN` nunca gravam.
2. **Flamengo no catálogo e compatibilidade com a Urubu.**
   - `teams.toml`: `flamengo` (Urubu News, `#A51C24`, outras modalidades, Carioca/Supercopa/Mundial)
     com `listed = false` até a virada (fora do portal, da inscrição e do `due --all`).
   - Marcas da Urubu em `static/flamengo/`; `/static/logo-email.png`, `/static/icon-512.png` e
     `/static/og-image.png` servem as da Urubu (e-mails antigos).
   - `LEGACY_SUBSCRIBE_SECRET` (o da Urubu): token `unsubscribe` antigo sai da `flamengo`;
     `bet` antigo palpita na `flamengo`; `/palpite` sem `c` e `/bolao` sem torcida = `flamengo`.
   - Host `urubunews.*`/`flamengo.*`: `/` redireciona para `https://geral.diegoponte.dev/`.
   - `geral import-urubu <urubu.db>`: idempotente; ativos → `subscribers` + assinatura `flamengo`
     (mantém `confirmed_at`), última edição → `editions[flamengo]`, bolão → `team = flamengo`.
3. **Virada** (`infra` #28 + este PR, numa janela sem edição da Urubu vencida). Roteiro:
   1. **Importar** (a Urubu ainda no ar): copiar o SQLite dela para o volume da Geral e importar.
      ```bash
      ssh -i ~/.ssh/hetzner_vps deploy@<vps> 'set -e
        U=/opt/stacks/flamengo-news/compose.yml; G=/opt/stacks/geral/compose.yml
        docker compose -f $U cp flamengo-news:/data/subscribers.db /tmp/urubu.db
        docker compose -f $G cp /tmp/urubu.db geral:/data/urubu-import.db
        docker compose -f $G exec -T geral python -m geral import-legacy /data/urubu-import.db --team flamengo'
      ```
   2. **Trocar o tráfego:** merge do `infra` #28 e `make configure` (Caddy aponta `urubunews.*` e
      `flamengo.*` para a Geral, `.env` ganha `LEGACY_*`, o gatilho da Urubu para).
   3. **Desligar o cron da Urubu:** `gh workflow disable newsletter.yml -R dpontejs/flamengo-news`.
   4. **Importar de novo** (idempotente): o mesmo comando do passo 1 pega quem entrou ou palpitou
      no meio do caminho.
   5. **Mostrar a Urubu:** merge deste PR (`listed = true`); o auto-deploy leva ~2 min.
   6. **Conferir:** `make smoke`; abrir um link de descadastro e um de palpite de um e-mail antigo da
      Urubu (GET só pergunta); `geral due --all` na VPS lista o `flamengo` quando houver edição
      vencida; envio em `DRY_RUN` da `flamengo` pelo Actions mostra os inscritos migrados.
   - **Volta:** reverter `infra` #28 + `make configure`, `gh workflow enable` na Urubu e reverter
     este PR. Os dados da Urubu não são tocados (o import só lê).

## Critérios de aceite (como testes)

- [x] Bolão: os 16 testes da Urubu portados com `team` (`test_bet_get_does_not_record`, `test_points_exact_5_diff_3_outcome_2_miss_0`, `test_result_summary_is_idempotent`, ...) e mais:
  `test_bet_requires_following_that_team`, `test_same_match_two_teams_have_separate_bolaos` (Vasco x Palmeiras), `test_nickname_is_unique_across_teams`.
- [ ] `test_unlisted_team_is_hidden_from_portal_signup_and_due_all`
- [ ] `test_legacy_unsubscribe_token_leaves_flamengo_only`, `test_legacy_one_click_post`
- [ ] `test_legacy_bet_link_without_team_bets_on_flamengo`
- [ ] `test_legacy_static_paths_serve_the_urubu_brand`, `test_legacy_host_root_redirects_to_geral`
- [ ] `test_import_urubu_brings_active_subscribers_edition_and_bolao`, `test_import_urubu_twice_changes_nothing`, `test_import_skips_pending_and_unsubscribed`

## Verificação ponta a ponta

Antes da virada, numa cópia do SQLite da Urubu: `geral import-urubu` + app local, abrir um link de
descadastro e um de palpite gerados com o segredo antigo. Depois: `make smoke`, um envio em
`DRY_RUN` da `flamengo` pelo Actions com os inscritos migrados e `journalctl -u geral-trigger`.

## Riscos e dúvidas abertas

- Janela da virada: entre desligar o gatilho da Urubu e ligar a `flamengo` na Geral não pode haver
  edição vencida; escolher um horário longe de jogo.
- E-mails da Urubu pendentes de confirmação (link de 7 dias) não migram: a pessoa se inscreve de novo.
