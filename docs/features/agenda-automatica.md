# Agenda automática por torcida (parte 2.2b)

- **Data:** 2026-11-11
- **Status:** proposta
- **ADRs:** —

## Objetivo

Cada torcida com inscrito ativo recebe pré-jogo, pós-jogo e notícias sozinha, como a Urubu News:
a VPS pergunta à Geral a cada 10 minutos o que está vencido e dispara o envio no Actions; um cron
de hora em hora no Actions é a reserva. Torcida sem inscrito não gasta Gemini.

## Fora de escopo

- Flamengo, bolão e migração da Urubu (parte 2a); edição geral por série (parte 4).
- Desligar o gatilho da Urubu: só depois que a Geral enviar a Urubu (parte 2a).

## Contratos

- `geral due --all` (no container, lê o SQLite de `SUBSCRIBERS_DB`): uma linha por torcida com
  inscrito ativo e edição vencida, `slug<TAB>kind<TAB>AAAA-MM-DD<TAB>label`; nada vencido, nada
  impresso. A agenda de cada torcida usa a última edição dela guardada no banco.
- `geral run --team <slug>` com envio real e nenhum destinatário: sai com 0 e "nada a enviar: sem
  inscritos", **antes** de coletar e chamar o Gemini. Prévia e `DRY_RUN` seguem gerando.
- Workflow `newsletter.yml` (repo `geral`): `workflow_dispatch` com `team` (obrigatório),
  `edition`, `date`, `dry_run`, `skip_if_sent`, `note`; `concurrency: newsletter-<team>`.
  `schedule` de hora em hora (minuto 23): matriz com todas as torcidas do `teams.toml`,
  `--edition auto --skip-if-sent` (sem inscrito, a regra acima evita o custo).
- Segredos do Actions (repo `geral`): `GEMINI_API_KEY`, `RESEND_API_KEY`, `NEWSLETTER_FROM`
  (`Geral <news@diegoponte.dev>`), `SUBSCRIBERS_API_TOKEN` (= `GERAL_API_TOKEN`); variável
  `PUBLIC_URL=https://geral.diegoponte.dev`.
- `infra`: papel `geral_trigger` (timer `*:0/10`, usuário `deploy`) com o script `geral-trigger`:
  lê as linhas do `due --all`, despacha cada edição uma vez (estado `slug|label`) com
  `{"team","edition","date","dry_run":"false","skip_if_sent":"true"}`. Token
  `GERAL_GITHUB_TOKEN`: fine-grained, só `dpontejs/geral`, "Actions: Read and write".

## Critérios de aceite (como testes)

- [x] `test_due_all_lists_only_teams_with_subscribers` (torcida sem inscrito não aparece)
- [x] `test_due_all_uses_each_team_latest_edition` (edição já enviada não volta)
- [x] `test_due_all_prints_nothing_when_nothing_is_due` e `test_due_all_when_espn_fails_for_a_team_the_others_go_on`
- [x] `test_run_without_recipients_does_not_build` (sem chamada ao Gemini nem coleta)
- [ ] `test_trigger_dispatches_each_team_once` e `test_trigger_same_label_two_teams_are_both_dispatched` (infra)
- [ ] `test_trigger_token_stays_out_of_argv` (infra)

## Verificação ponta a ponta

```bash
docker compose -f /opt/stacks/geral/compose.yml exec -T geral python -m geral due --all  # na VPS
gh workflow run newsletter.yml -R dpontejs/geral -f team=vasco -f edition=post -f date=2026-11-09   # dry run
journalctl -u geral-trigger -n 20
```

## Riscos e dúvidas abertas

- O token do GitHub para a VPS é criado à mão pelo dono (fine-grained, só o repo `geral`).
