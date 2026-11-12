# "Onde jogou?": acerte os clubes da carreira do jogador do dia

- **Data:** 2026-11-11
- **Status:** aprovada
- **ADRs:** —

## Objetivo

Terceiro joguinho da Geral, o primeiro de carreira: aparece um jogador principal (ídolo das
torcidas ou craque brasileiro) e uma fileira de espaços com os anos de cada passagem; o torcedor
digita clubes e cada acerto acende as passagens daquele clube. Três erros ou desistir encerram.
Na edição de uma torcida, as passagens por aquele clube já vêm acesas e não contam no placar.
O arquivo de carreiras também vai servir ao "Quem é?" (próximo PR).

## Fora de escopo

- O "Quem é?" (mesmos dados, mecânica inversa) e estatísticas de jogos e gols.
- Seleções e categorias de base: só clubes profissionais.
- Pontos no placar das torcidas, conta, jogo dentro da newsletter.

## Contratos

- `src/geral/games/jogadores.toml`: a lista curada (`nome` como a torcida chama, `wikidata`).
  `scripts/find_wikidata.py` ajuda a montar; a revisão é humana.
- Fonte das carreiras (desde 12/11/2026): o quadro de carreira da Wikipédia em inglês
  (`Infobox football biography`, campos `yearsN`/`clubsN`, empréstimos incluídos), lido por
  `geral/games/wikipedia.py`; cada clube é um link cuja página dá o id do Wikidata, então nomes,
  apelidos e `clubes.toml` seguem iguais. O Wikidata ficou para posição, nome e país dos clubes e
  para quem não tem quadro na Wikipédia. Motivo: o Wikidata atrasa transferências (Cano ainda no
  Vasco, Vegetti no Colón); o Transfermarkt foi descartado (sem API, termos proíbem raspagem).
  Créditos nas páginas: Wikipédia (CC BY-SA) e Wikidata.
- Calendário congelado (`src/geral/games/calendario.json`, `geral/games/calendario.py`): as
  respostas já jogadas (e a de amanhã) de cada jogo e edição, por id do Wikidata. A importação
  congela antes de gravar dados novos (`scripts/congelar_calendario.py`), então uma atualização
  não troca o jogo do dia nem os números antigos; só os números seguintes seguem a ordem nova.
- `scripts/import_carreiras.py`: consultas SPARQL ao Wikidata em blocos (com pausa e `Retry-After`;
  a resposta bruta fica em `~/.cache/geral/`, e `--cache` refaz o arquivo sem consultar de novo)
  e `convert(rows) -> dict` puro, que tira seleções e base, descarta passagens sem ano de início,
  junta passagens seguidas no mesmo clube e escreve `src/geral/games/carreiras.json`:
  `{"clubes": {qid: {"nome", "apelidos"}}, "jogadores": [{"wikidata", "nome", "posicao",
  "clubes": [{"clube", "inicio", "fim"}]}]}`. `src/geral/games/clubes.toml` corrige nomes curtos
  ("Vasco", "PSV") e apelidos, e `ignorar = true` tira o que não é clube (o país Brasil, time B);
  prevalece sobre o Wikidata.
- `geral/games/onde_jogou.py`: `load(path)`, `resolve(data, texto) -> qid | None` (sem acento e
  maiúscula, por nome e apelidos), `pool(data, edition, catalog)` (geral = jogadores com 3+ clubes;
  torcida = quem passou pelo clube cujo `nome` é o `name` do time no `teams.toml`),
  `judge(jogador, palpites, desistiu) -> Verdict` (`slots` com anos e o clube só se acertado ou no
  fim, `achados`, `total` de clubes distintos, `erros`, `over` com tudo achado, 3 erros ou
  desistência). `LAUNCH = 2026-11-11`; ordem diária de `daily.py`.
- Rotas, no molde do Craque do dia:

```python
# GET  /jogos/onde-jogou[/{edition}]  → 200 HTML (jogador, posição, anos; lista de clubes p/ completar)
# POST /api/jogos/onde-jogou/{edition}/{number}  → 200 Verdict
class ClubGuessesIn(BaseModel):
    palpites: list[str]  # até 40, cada um até 60 caracteres
    desistiu: bool = False


# 422 se um palpite não é clube conhecido (não conta como erro); 404 edição ou número inválido
```

- Compartilhar: `Onde jogou? #4 · Geral 9/13` + 🟩 por clube achado e ⬛ por clube que faltou + link.

## Critérios de aceite (como testes)

- [x] `test_convert_drops_national_and_youth_teams`, `test_convert_merges_back_to_back_stints`,
      `test_convert_drops_stints_without_a_start_year`.
- [x] `test_resolve_accepts_short_names_and_accents`: "vasco", "Vasco da Gama" → o mesmo clube.
- [x] `test_judge_lights_every_stint_of_a_found_club`.
- [x] `test_judge_ends_after_three_wrong_clubs_or_giving_up_and_reveals`.
- [x] `test_judge_ignores_a_repeated_guess`.
- [x] `test_team_edition_has_only_players_who_played_there`.
- [x] `test_team_edition_gives_the_team_stints_without_scoring_them`.
- [x] `test_api_rejects_unknown_club_without_counting_it`, `test_api_rejects_future_puzzle`.
- [x] `test_game_page_does_not_leak_the_clubs`: a página mostra os anos, não os clubes do dia.
- [x] `test_real_careers_are_sane`: todo jogador real tem 2+ clubes, anos crescentes, clubes conhecidos.

## Verificação ponta a ponta

```bash
uv run python scripts/import_carreiras.py && uv run pytest
uv run uvicorn geral.web.app:create_app --factory  # jogar /jogos/onde-jogou e /jogos/onde-jogou/vasco
```

## Riscos e dúvidas abertas

- As fontes têm erros (o Romário aparecia com um "Ajax" sem data no Wikidata). O arquivo gerado
  passa por revisão antes do merge; correção vai na fonte ou em `clubes.toml`.
- Empréstimos curtos contam como clube: o torcedor pode achar injusto. Ajustável depois.
