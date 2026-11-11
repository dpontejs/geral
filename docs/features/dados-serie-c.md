# Jogos e tabela das Séries C, D e estaduais pelo ge (parte 2b.1)

- **Data:** 2026-11-11
- **Status:** proposta
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

- [ ] `test_ge_tables_require_ge_id`: dado `ge_tables` sem `ge_id`, quando carrega, então erro.
- [ ] `test_ge_fixtures_from_points_groups_and_knockout`: dadas as fases do Potiguar (respx), quando busca os jogos, então vêm os do ABC dos três formatos, com `league="ge:Potiguar"`.
- [ ] `test_ge_reads_tuuid_from_page_each_run`: dado o HTML da página, quando busca, então a API é chamada com o `tUUID` dela.
- [ ] `test_ge_last_match_has_score_and_competition`: dado um jogo encerrado na janela, quando busca o último jogo, então vem o placar, o nome do campeonato e `is_home`.
- [ ] `test_ge_next_match` e `test_ge_unplayed_match_is_pre_without_time_valid`.
- [ ] `test_ge_standings_our_group_only` e `test_ge_knockout_has_no_standings`.
- [ ] `test_ge_page_down_raises_unavailable_on_fixtures` e `..._other_methods_degrade` (None/[]).
- [ ] `test_combined_fixtures_merge_espn_and_ge` e `test_combined_unavailable_when_one_source_fails`.
- [ ] `test_combined_last_match_is_the_most_recent_of_both` e `test_combined_preview_routes_by_league`.
- [ ] `test_stats_client_for_team_without_ge_tables_is_espn`.
- [ ] `test_due_all_plans_ge_matches`: dado um jogo do Potiguar amanhã, quando roda `due --all`, então sai o pré-jogo do ABC.

## Verificação ponta a ponta

```bash
uv run ruff check . && uv run pytest
uv run geral stats --team abc --date 2026-03-22     # final do Potiguar 2026: 1x1 com o América-RN
uv run geral preview --team abc --edition post --date 2026-03-22 --out out/abc.html
```

## Riscos e dúvidas abertas

- API não documentada: se mudar, o ABC volta a só ter notícias (os demais não são afetados).
- ~20 a 40 chamadas ao ge por execução do `due` (a cada 10 min); cache só dentro da execução.
