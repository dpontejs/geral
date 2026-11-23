# Revisão das edições antes do envio

- **Data:** 2026-11-16
- **Status:** aprovada
- **ADRs:** —

## Objetivo

O dono vê cada edição de torcida antes de ela sair e pode segurá-la ou tirar tópicos; se não mexer,
ela sai sozinha no horário. Notícias e pós-jogo passam a sair às 13:00 (montadas às 08:00, manhã
livre para revisar); o pré-jogo é montado 6 h antes do jogo e sai 4 h antes. Prepara o terreno das
seções especiais (projeto B), em que a revisão é a última rede de segurança das histórias.

## Fora de escopo

- Editar o texto de um tópico (só segurar a edição ou tirar tópicos).
- Edição geral e edição especial dos joguinhos: seguem o fluxo atual (PR seguinte, se fizer falta).
- Seções especiais e acervo histórico (projeto B, página própria).

## Contratos

- **Agenda** (`geral.schedule`): `Slot` ganha `build_at`; `send_at` passa a ser a hora do envio.
  Notícias e pós-jogo: `build_at` 08:00, `send_at` 13:00. Pré-jogo: `build_at = max(início − 6 h,
  08:00 do dia)`, `send_at = build_at + 2 h`; jogo antes das 11:00: montado às 18:00 da véspera,
  sai às 20:00. Jogos em dias seguidos: regra atual (o pré-jogo só entra se sair depois do pós-jogo
  anterior), com os horários novos. *(decisão do construtor)*
- **`geral due --all`**: `slug<TAB>kind<TAB>AAAA-MM-DD<TAB>label<TAB>stage`, `stage` ∈
  `build|send|all` (`all` para a edição geral). Coluna no fim: o gatilho antigo segue lendo as 4
  primeiras; o `infra` sobe antes da Geral. `AAAA-MM-DD` é o dia do `send_at` nas duas etapas.
- **`geral run --stage build|send|all`** (padrão `all` = comportamento atual, para disparo manual).
  `build`: tudo até o render; grava o rascunho no site (`Newsletter` em JSON) e não envia. Roda
  uma vez por slot: já existe rascunho, não faz nada (reserva e janela de 3 h não chamam o Gemini de
  novo nem apagam o que o dono tirou). *(decisão do construtor)*
  `send`: lê o rascunho, descarta os tópicos tirados, monta e envia como hoje. Com tópico tirado,
  a manchete (assunto) e a abertura são reescritas sobre os que ficaram (1 chamada ao Gemini; sem
  ele, a manchete é o primeiro tópico que ficou).
  A gravação do bolão (`_bolao`) e o `--note` passam para o `send`: só vale o que saiu de fato.
  *(decisão do construtor)*
  Sem rascunho (a montagem falhou): `send` faz `all`, a edição sai sem revisão e o relatório diz
  isso. Rascunho segurado: não envia e o relatório diz "segurada na revisão".
- **Segurar = pausar**: o dono solta quando quiser; `due --all` lista `send` para todo rascunho
  solto e não enviado cujo `send_at` passou, sem o limite de 3 h, e ele sai em até 10 min. Nunca
  solto, não sai; a edição seguinte cobre o período desde o último envio real (a janela de notícias
  ancora no último envio, não no `send_at` do rascunho parado).
- **Workflow `newsletter.yml`**: input `stage` (padrão `all`); o cron de reserva usa o `stage`
  vencido. **Repo `infra`** (papel `geral_trigger`, fora deste repo, entra no PR 1): repassa a coluna `stage`; estado `slug|label|stage`.
- **Banco**: tabela `drafts(id, team, label, kind, newsletter_json, build_at, send_at, held,
  removed_topics, sent_at)`, única por `(team, label)`.
- **API (token `GERAL_API_TOKEN`)**: `PUT /api/teams/{team}/drafts/{kind}/{day}` → 204 (`DraftIn`;
  409 se já existe); `GET …/drafts/{kind}/{day}` → `DraftOut` (newsletter, `held`,
  `removed_topics`) ou 404; `POST …/drafts/{kind}/{day}/sent` → 204. (`day` = AAAA-MM-DD: o
  rótulo tem barras e não cabe no caminho.)
- **Revisão (link assinado, `REVIEW_PURPOSE`, vale 7 dias, enviado a `NOTIFY_EMAIL`)**:
  `GET /revisao?t=` lista os rascunhos não enviados com a prévia (mesmo render do e-mail);
  `POST /revisao/{id}/segurar`, `/soltar`, `/topicos/{n}/tirar`, `/topicos/{n}/voltar` → 303 para
  `/revisao`. Rascunho já enviado: 409 "já saiu"; segurado e com `send_at` vencido, tudo segue
  permitido.
- **Publicar agora** (2026-11-23): `POST /revisao/{id}/publicar` → 303; solta o rascunho (mesmas
  recusas 409 do `soltar`) e marca `send_now`: `due --all` lista a linha `release` na próxima
  verificação, mesmo antes do `send_at`. Sem clicar, segue saindo no horário. Segurar depois desfaz.
- **Aviso ao dono**: ao gravar o rascunho, um e-mail "Revisar: <newsletter> — <label>, sai às HH:MM"
  com o link. Um por rascunho.

## Critérios de aceite (como testes)

- [x] `test_news_and_post_build_at_8_send_at_13`, `test_pre_game_builds_6h_before_sends_4h_before`,
  `test_early_kickoff_pre_game_builds_18h_sends_20h_day_before`
- [x] `test_due_all_prints_build_then_send_for_the_same_slot`
- [x] `test_run_build_saves_draft_and_sends_nothing`
- [x] `test_run_send_drops_removed_topics_and_rewrites_the_opening`
- [x] `test_run_send_without_draft_builds_and_sends`; `test_run_send_held_draft_sends_nothing`
- [x] `test_send_twice_sends_once` (o rascunho marcado como enviado e o `--skip-if-sent` atual)
- [x] `test_review_page_rejects_token_of_other_purpose` e `test_review_page_rejects_expired_token`
- [x] `test_remove_topic_after_sent_is_409`
- [x] `test_released_draft_after_send_at_is_due_for_send` e `test_next_window_starts_at_last_real_send`
- [x] `test_run_build_twice_keeps_first_draft`
- [x] `test_publish_now_sends_at_the_next_check`, `test_draft_published_before_send_at_is_due_for_send`,
  `test_hold_after_publish_now_cancels_it`

## Verificação ponta a ponta

```bash
gh workflow run newsletter.yml -R dpontejs/geral -f team=abc -f edition=news -f stage=build -f dry_run=false
# e-mail de revisão chega; na página, tirar um tópico
gh workflow run newsletter.yml -R dpontejs/geral -f team=abc -f edition=news -f stage=send -f dry_run=true
# a prévia do Actions (out/) vem sem o tópico tirado
```

## Riscos e dúvidas abertas

- O pós-jogo às 13:00 chega bem depois do jogo: aceito pelo dono; aviso no quadro "Novidades".
- Corte em PRs: (1) agenda + etapas + rascunho na API + `infra`; (2) página de revisão, e-mail,
  soltar depois do horário e janela ancorada no último envio real. Sem o (2), o (1) já roda no
  horário novo, mas sem revisão.
