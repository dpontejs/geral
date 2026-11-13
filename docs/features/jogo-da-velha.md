# Jogo da velha: o jogador do cruzamento

- **Data:** 2026-11-13
- **Status:** aprovada
- **ADRs:** —

## Objetivo

Joguinho de tabuleiro 3×3: cada linha e coluna é uma categoria (clube brasileiro, Seleção Brasileira,
"jogou uma Copa", nacionalidade, posição) e cada casa vale qualquer jogador que se encaixe nas duas. Dois modos sobre a mesma base e o
mesmo juiz: **solo diário** (um tabuleiro por dia, igual para todos) e **duelo** X contra O, no mesmo
PC ou por link, ao mesmo tempo, com relógio. Sem edição por time.

## Fora de escopo

- Prêmios e títulos (Wikidata esparso); "raridade" das respostas (exigiria guardar os chutes de todos).
- Conta, ranking de duelos, partida contra o computador, edição por torcida.

## Contratos

- **Categorias** (decididas pelo dev): clubes só brasileiros (`src/geral/games/velha/clubes.toml`,
  à mão: os 20 da Série A atual e os grandes históricos fora dela); Seleção = a principal do Brasil;
  Copa = esteve em alguma Copa do Mundo, por qualquer seleção; país (para estrangeiros que jogaram
  aqui); posição. **Base**
  (`scripts/import_base.py` → `src/geral/games/velha/base.json`): todo jogador com P54 em algum
  desses clubes ou na Seleção, com `fama` (nº de Wikipédias, P-sitelinks); a carreira vem do infobox da
  Wikipédia em inglês, pelo `wikipedia.py` do "Onde jogou?" (lotes de 50), com o Wikidata de reserva.
  Seleção pelo infobox; Copa pelos elencos (Wikidata P1344 nas edições da Copa, conferido com as
  listas "FIFA World Cup squads" da Wikipédia);
  nacionalidade (P1532) e posição (P413) do Wikidata. Clube conta empréstimo, não conta base
  (como no "Onde jogou?"). `carreiras.json` (106 craques) fica como está.
- `geral/games/velha/`: `Category(kind: Literal["clube","selecao","copa","pais","posicao"], value, label)` (`selecao` e
  `copa` têm um valor só);
  `fits(base, jogador, a, b) -> bool`; `make_board(base, rng) -> Board` (3+3 categorias distintas,
  toda casa com ≥ 3 respostas, no máximo 2 posições/países); `judge_solo(base, board, chutes)`.
- Busca: `GET /api/jogos/velha/jogadores?q=` → até 10 `{id, nome, anos: "1985–2002", posicao}`,
  os mais famosos primeiro (homônimos se distinguem por anos e posição; não diz onde vale).
- **Solo:** `GET /jogos/velha[/{n}]` (jogos anteriores como nos outros). Tabuleiro do dia sorteado
  pela semente `velha:{n}` e congelado no `calendario.json` como hoje (`velha` → `geral` → lista de
  strings `"clube:Q8806|selecao:BRA|…"`, 3 linhas e 3 colunas), pelo `congelar_calendario.py` até
  amanhã. `LAUNCH` = dia do merge do PR 2. `POST /api/jogos/velha/{n}` com o histórico inteiro
  `{"chutes": [{"casa": 0-8, "jogador": QID}]}` (sem estado no servidor, como os outros) → casas
  preenchidas, acerto por chute, `over` (9 casas ou 12 chutes, certos e errados) e, no fim, as 3
  respostas mais famosas e o total por casa. Casa já preenchida não aceita chute (422); jogador já
  usado no tabuleiro = erro. Compartilhar: grade 🟩⬜.
- **Duelo no mesmo PC:** `GET /jogos/velha/duelo`; `GET /api/jogos/velha/tabuleiro` sorteia;
  `POST /api/jogos/velha/confere {linha, coluna, jogador, usados}` → `{"vale": bool}` (jogador em
  `usados` não vale). Vez, relógio e placar no navegador.
- **Duelo por link** (`web/velha_partidas.py`, tabela própria no mesmo SQLite; não toca no `store.py`):
  `velha_partidas(id PK, tabuleiro JSON, x_token, o_token NULL, vez, prazo, casas JSON, jogadas JSON,
  sem_casa INT, status, criada_em)`.
  - `POST /api/jogos/velha/partidas` → `{id, token}` (quem cria é X); `GET /jogos/velha/p/{id}`.
  - `POST …/partidas/{id}/entrar` → token de O (uma vez só; depois 409 e a página só assiste).
  - `POST …/partidas/{id}/jogada {token, vez_n, casa, jogador}`: `vez_n` é o número da vez que o
    navegador viu; repetido ou velho só devolve o estado (retentativa não joga duas vezes).
    `GET …/partidas/{id}` (estado + `agora`);
    `GET …/partidas/{id}/eventos` (SSE; o navegador cai para consulta a cada 3 s se cair).
  - Relógio no servidor: 30 s por vez; X começa, e o relógio dele corre quando O entra. Errar ou
    estourar passa a vez; o prazo vencido é aplicado em qualquer leitura ou escrita. Jogador já usado
    por qualquer um = erro. Três em linha vence; tabuleiro cheio ou 6 vezes seguidas sem casa
    conquistada (erros e estouros contam) encerram, e vence quem tem mais casas (igual = empate).
  - Erros: token errado ou fora da vez 403; casa ocupada ou partida encerrada 409; jogador
    desconhecido 422; partida inexistente ou com mais de 24 h 404 (as velhas são apagadas ao criar
    uma nova). Criação limitada por rede, com o `RateLimiter` e o `network()` dos pedidos de time.

## Critérios de aceite (como testes)

- [ ] `test_fits_crosses_club_selecao_copa_country_and_position`: dado um jogador de Vasco e Seleção, então vale em Vasco×Seleção e não em Vasco×Grêmio; um uruguaio que foi a uma Copa vale em Uruguai×Copa e não em Seleção×Copa.
- [ ] `test_make_board_gives_every_cell_three_answers`: para 200 sementes, toda casa tem ≥ 3 respostas e nenhuma categoria se repete.
- [ ] `test_daily_board_follows_the_frozen_calendar`: dado um tabuleiro congelado para o nº 3, quando a base muda, então o nº 3 continua o mesmo.
- [ ] `test_solo_judge_fills_cells_counts_misses_and_reveals_only_at_the_end`.
- [ ] `test_solo_reusing_a_player_is_a_miss`.
- [ ] `test_player_search_finds_by_name_without_accents_and_hides_where_it_fits`.
- [ ] `test_duel_creator_is_x_and_the_first_to_join_is_o_then_others_only_watch`.
- [ ] `test_duel_move_out_of_turn_or_with_the_other_token_is_403`.
- [ ] `test_duel_wrong_answer_or_timeout_passes_the_turn` (relógio do teste avança 31 s).
- [ ] `test_duel_three_in_a_row_wins_and_later_moves_are_409`.
- [ ] `test_duel_ends_after_six_turns_without_a_cell_and_most_cells_wins`.
- [ ] `test_duel_same_move_twice_counts_once` (retentativa da rede não joga duas vezes).
- [ ] `test_duel_events_stream_sends_the_new_state_after_a_move`.
- [ ] `test_import_base_builds_from_recorded_wikidata_and_wikipedia` (respx, sem rede).

## Verificação ponta a ponta

```bash
uv run python scripts/import_base.py   # base real; relatório de cobertura por clube
uv run pytest && uv run uvicorn geral.web.app:create_app --factory
# Playwright: solo até o fim; duelo com dois navegadores (X cria, O entra pelo link), uma jogada
# certa, uma errada e um estouro de tempo aparecendo no outro navegador em < 1 s.
```

## Entrega em PRs

1. Base grande, categorias, gerador e juiz (sem página). 2. Solo diário. 3. Duelo no mesmo PC.
4. Duelo por link.

## Riscos e dúvidas abertas

- Tamanho e cobertura da base: alvo de 3 a 6 mil jogadores; jogadores sem página na Wikipédia em
  inglês ficam com o Wikidata. O relatório do import diz se algum clube grande ficou ralo.
- SSE depende de um processo só (como hoje no Dockerfile) e do proxy não segurar a resposta; a
  consulta a cada 3 s cobre os dois casos.
