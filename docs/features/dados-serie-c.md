# Jogos e tabela das Séries C, D e estaduais pelo ge (parte 2b.1)

- **Data:** 2026-11-11
- **Status:** implementada (aguardando PR)
- **ADRs:** —

## Objetivo

A ESPN não cobre Série C, Série D nem estaduais, e a agenda das edições vem dos jogos que ela
conhece: o ABC só recebe a edição de notícias. Com a API de tabelas do ge como segunda fonte de
jogos, o ABC passa a ter pré-jogo, pós-jogo (placar), próximo jogo, forma recente, tabela e bolão
nos jogos do Potiguar e da Série C 2027, sem mexer nos times que a ESPN já cobre.

## Fora de escopo

- Autores dos gols (página de jogo da CBF): parte 2b.2. Aqui o pós-jogo traz só o placar.
- Notícias pelo feed JSON do ge: parte 2b.3. Pernambucano (`tabela-context`): parte 2b.4.
- Escudos dos adversários: o ge só publica SVG, que o Gmail não mostra; o nosso usa o da ESPN.
- Confronto direto no pré-jogo (o ge não tem); a forma dos dois times sai dos jogos do campeonato.

## Contratos

```toml
[abc]
ge_id = 350  # equipe_id do ge (classificação/jogos)
[abc.ge_tables]  # nome na newsletter -> página do campeonato no ge
"Série C" = "https://ge.globo.com/futebol/brasileirao-serie-c/"
"Potiguar" = "https://ge.globo.com/rn/futebol/campeonato-potiguar/"
```

- `Team.ge_id: int | None` e `Team.ge_tables: dict[str, str]`; `ge_tables` sem `ge_id` é erro.
- `geral.stats.ge_tables.GETablesClient(team, client=None, tz_name=...)`: os métodos do
  `StatsClient` do pipeline mais `get_fixtures(now)`. A cada execução lê da página do campeonato o
  `tUUID` (`tUUID: "..."`) e `fases_navegacao`, e busca na API
  `https://api.globoesporte.globo.com/tabela/{tUUID}/fase/{slug}/classificacao/` das fases até a
  atual. Pontos corridos (`tipo_id` 1): jogos em `.../rodada/{n}/jogos/` para n de 1 a
  `rodada.ultima`. Grupos (`tipo_id` 3): rodadas de 1 até a primeira lista vazia. Mata-mata
  (`tipo_id` 2): jogos em `secao[].chave[].jogos`.
- Jogo do ge: `Fixture(match_id=str(id), league="ge:<nome>")`, encerrado (`post`) com placar e
  2h15 depois do início, `in` com `jogo_ja_comecou`, sem `hora_realizacao` é `time_valid=False`.
  O `match_id` serve ao bolão sem mudança no banco.
- Tabela: se o time tem `league` (ESPN), segue a da ESPN; senão, a da fase atual de pontos do
  campeonato do último jogo nosso no ge, só o nosso grupo. Mata-mata não tem tabela.
- `geral.stats.combined.stats_client_for(team, tz_name)`: só ESPN quando não há `ge_tables`;
  senão `CombinedStatsClient(espn, ge)` (último/próximo jogo pela data, forma juntando as duas,
  prévia pelo prefixo `ge:` da liga). `get_fixtures` levanta `StatsUnavailable` se qualquer
  fonte falhar inteira (calendário desconhecido não é vazio). O `pipeline`, o `stats` e o `due`
  passam a usar `stats_client_for`.
- Banco: nada novo.

## Critérios de aceite (como testes)

- [x] `test_ge_tables_require_ge_id`: dado `ge_tables` sem `ge_id`, quando carrega, então erro.
- [x] `test_ge_fixtures_from_points_groups_and_knockout`: dadas as fases do Potiguar (respx), quando busca os jogos, então vêm os do ABC dos três formatos, com `league="ge:Potiguar"`.
- [x] `test_ge_reads_tuuid_from_page_each_run`: dado o HTML da página, quando busca, então a API é chamada com o `tUUID` dela.
- [x] `test_ge_last_match_has_score_and_competition`: dado um jogo encerrado na janela, quando busca o último jogo, então vem o placar, o nome do campeonato e `is_home`.
- [x] `test_ge_next_match` e `test_ge_unplayed_match_is_pre_without_time_valid`.
- [x] `test_ge_standings_our_group_only` e `test_ge_knockout_has_no_standings`.
- [x] `test_ge_page_down_raises_unavailable_on_fixtures` e `test_ge_api_down_other_methods_degrade` (None/[]).
- [x] `test_ge_undefined_knockout_game_is_skipped`: confronto ainda sem times não derruba a agenda.
- [x] `test_combined_fixtures_merge_espn_and_ge` e `test_combined_unavailable_when_one_source_fails`.
- [x] `test_combined_last_match_is_the_most_recent_of_both` e `test_combined_preview_routes_by_league`.
- [x] `test_stats_client_for_team_without_ge_tables_is_espn`.
- [x] `test_due_fixtures_come_from_espn_and_ge`: a agenda do `due` usa `stats_client_for`.
- [x] `test_render_table_and_campaign_use_the_table_competition` e `test_build_newsletter_keeps_the_table_competition`.

## Verificação ponta a ponta

```bash
uv run ruff check . && uv run pytest
uv run geral stats --team abc        # hoje: sem jogo do ABC no ge (Série C 2026 sem ele)
```

A agenda só olha a semana passada em diante, então data antiga não resolve edição (vale também
para a ESPN). O Potiguar 2026 foi conferido chamando o `GETablesClient` com o relógio em
22/03/2026: 11 jogos, último jogo 1x1 com o América-RN, forma, prévia e confronto direto.

## Riscos e dúvidas abertas

- API não documentada: se mudar, o ABC volta a só ter notícias (os demais não são afetados).
- ~20 a 40 chamadas ao ge por execução do `due` (a cada 10 min); cache só dentro da execução.
