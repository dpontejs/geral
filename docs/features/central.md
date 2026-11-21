# Central: tabelas e jogos das quatro séries (parte 1 de 2)

- **Data:** 2026-11-21
- **Status:** implementada (aguardando PR)
- **ADRs:** —

## Objetivo

Uma página para o torcedor se atualizar sobre o Brasileirão sem sair da Geral: a classificação das
Séries A, B, C e D com as faixas (Libertadores, Sul-Americana, acesso, playoffs, rebaixamento), a
rodada atual com navegação pelas outras, os próximos jogos dos times da Geral e, para a série que
já acabou, o resumo dela (campeão, vice, quem subiu, quem caiu). Um bloco na página inicial e um
link no menu levam até ela.

## Fora de escopo

- Aba de notícias (feed do ge e página de leitura com "Continue lendo no ge"): parte 2, PR seguinte.
- Copa do Brasil, Libertadores, estaduais; artilharia; jogo ao vivo minuto a minuto.

## Contratos

- **Rota:** `GET /central` → HTML (`central.html.j2`), série escolhida por `?serie=a|b|c|d`
  (padrão: a primeira em andamento). Rodadas trocadas no navegador, sem nova requisição.
- **Fonte:** `load_competition` do ge (já usado pela edição geral), estendido para guardar, por
  linha da tabela, a faixa do ge (`StandingRow.band: str | None`, o nome, ex. "Libertadores") e,
  por competição, a lista ordenada de faixas e as fases com seus jogos (`Competition.phases`).
- **Retrato:** `geral.central.build_snapshot(now) -> CentralSnapshot` (Pydantic), gravado em JSON
  no caminho `CENTRAL_SNAPSHOT` (padrão `data/central.json`, ao lado do SQLite):
  - `CentralSnapshot(updated_at, series: list[SerieView], next_matches: list[TeamNextMatch])`
  - `SerieView(name, status: "points" | "knockout" | "over", phase, table, bands, rounds,
    current_round, ties, summary)`; `rounds` agrupa os jogos da fase de pontos por rodada;
    `ties` são os confrontos da fase de mata-mata atual com o agregado; `summary` só quando
    `status == "over"`.
  - `SerieSummary(champion, runner_up, promoted, relegated)`: campeão e vice pelo confronto da
    fase "Final" (agregado, depois pênaltis) ou, sem final (A e B), pelos dois primeiros da fase
    de pontos; `relegated` pelas faixas "Rebaixados"; `promoted` pelas faixas com
    "Acesso"/"Série <X>" mais os vencedores das fases com "acesso" no nome.
  - Série acabada = a última fase é a atual e todos os jogos dela estão encerrados.
  - `next_matches`: o próximo jogo de cada time listado do catálogo, por `stats_client_for`.
- **Atualização:** uma thread no app web refaz o retrato a cada 10 minutos (`CENTRAL_REFRESH=0`
  desliga, padrão nos testes); comando `geral central [--out arquivo.json]` faz o mesmo à mão.
  Série que falha mantém a versão anterior dela no retrato; a página mostra "atualizado às HH:MM".
- **Cores das faixas:** paleta da Geral pela posição da faixa na lista do ge (1ª, 2ª, 3ª…), com
  "Rebaixados" sempre em vermelho; as cores do ge não são usadas.
- **Página inicial:** bloco "Central" com o líder de cada série em andamento e o link; item
  "Central" no menu do `base.html.j2`.
- Banco: nada novo.

## Critérios de aceite (como testes)

- [x] `test_ge_standing_keeps_band_name`: dada a classificação da Série A (fixture), quando lê, então o 1º tem `band="Libertadores"` e o 20º `"Rebaixados"`.
- [x] `test_points_serie_groups_games_by_round`: dada a Série A na rodada 36, quando monta, então `current_round == 36` e cada rodada tem os seus 10 jogos.
- [x] `test_knockout_serie_has_ties_with_aggregate`: dados os playoffs da B, quando monta, então dois confrontos, ida e volta, com agregado quando houver placar.
- [x] `test_finished_serie_summary`: dada a Série C com a final decidida, quando monta, então campeão, vice, os 4 que subiram e os rebaixados.
- [x] `test_tie_decided_on_penalties`: dado agregado empatado, quando decide, então vence quem fez mais pênaltis.
- [x] `test_serie_failure_keeps_previous_version`: dado o ge fora para uma série, quando refaz, então a série segue com o retrato anterior.
- [x] `test_central_page_renders_each_status`: dado um retrato, quando abre `/central?serie=a|b|c`, então tabela com legenda, confrontos ou resumo.
- [x] `test_central_page_without_snapshot`: sem retrato ainda, quando abre, então 200 com aviso "em atualização".
- [x] `test_home_links_to_central`: quando abre `/`, então há o bloco e o item de menu da Central.

## Verificação ponta a ponta

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
uv run geral central --out data/central.json && uv run uvicorn geral.web.app:app  # abrir /central
```

Conferir com o ge do dia: líder e Z4 da A, os playoffs da B, campeão e acesso da C e da D.

## Riscos e dúvidas abertas

- Acesso nas fases de mata-mata: o ge não marca faixa; `PROMOTION_PHASES` (B: playoffs; D:
  quartas e playoffs) foi conferido contra as notícias de 2026 e precisa ser revisto a cada
  temporada. Confronto empatado sem pênaltis vai para o mandante da volta (melhor campanha).
- API do ge não documentada: se mudar, a página mostra o último retrato com a hora dele.
