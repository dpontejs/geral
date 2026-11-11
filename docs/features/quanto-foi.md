# "Quanto foi?": adivinhe o placar de um jogo histórico

- **Data:** 2026-11-11
- **Status:** proposta
- **ADRs:** —
- **Pesquisa:** relatório "Joguinhos de futebol para a Geral" (fora do repo); o "7 a 0" virou nome de
  outro jogo (draft e Copa simulada, 7a0.com.br), por isso o cartão do portal muda de nome.

## Objetivo

Primeiro joguinho da Geral: um jogo da Série A por dia, o mesmo para todo mundo; o torcedor chuta o
placar em até 6 tentativas e compartilha o resultado sem spoiler. Começa geral e já nasce com uma
edição por torcida (o diferencial), usando dados gratuitos do Brasileirão 2003–2024.

## Fora de escopo

- ABC (sem Série A no dataset; depende do RSSSF) e Séries B/C/estaduais.
- Jogo dentro da newsletter, pontos no placar das torcidas, conta ou login: tudo isso pede o banco
  (`store.py`), que fica com o bolão.
- Wordle do artilheiro e os outros formatos do relatório.

## Contratos

- Dados: `src/geral/games/data/brasileirao.csv` (uma linha por jogo: `id,date,round,home,away,
  home_goals,away_goals,stadium,home_coach,away_coach,home_scorers,away_scorers`), gerado por
  `scripts/import_brasileirao.py` a partir do dataset `adaoduque/Brasileirao_Dataset` (GitHub, sem
  licença declarada; crédito na página). Os testes usam um CSV pequeno em `tests/fixtures/`.
- `geral/games/quanto_foi.py`:
  - `load_matches(path) -> list[Match]`; `EDITIONS = {"geral": None, "vasco": "Vasco",
    "palmeiras": "Palmeiras", "flamengo": "Flamengo", "nautico": "Nautico"}` (slug → nome no dataset).
  - `pool(matches, edition)`: geral = jogos marcantes (clássico entre os 12 grandes, 4+ gols ou
    diferença de 3+); torcida = jogos do time com 3+ gols ou contra um grande.
  - `puzzle(pool, edition, day) -> Puzzle(number, match)`: `number` = dias desde `LAUNCH` + 1;
    a ordem é uma permutação fixa do pool por edição (sem repetir até esgotar).
  - `judge(match, guesses) -> Verdict`: por chute e por lado, `certo` | `perto` (1 gol) | `longe`, e
    `mais` | `menos`; `solved`, `over` (acertou ou 6 chutes), dicas (técnicos a partir do 3º erro,
    vencedor a partir do 4º) e `reveal` (placar, estádio, autores dos gols) só quando `over`.
- Rotas (em `app.py`, sem banco):

```python
# GET  /jogos/quanto-foi            → 200 HTML, edição geral do dia (data de Brasília)
# GET  /jogos/quanto-foi/{edition}  → 200 HTML; 404 para edição sem pool (abc, desconhecida)
# POST /api/jogos/quanto-foi/{edition}/{number}  → 200 Verdict
class GuessesIn(BaseModel):
    guesses: list[tuple[int, int]]  # 1 a 6 chutes, gols de 0 a 20
```

- Erros: 404 edição desconhecida ou `number` futuro/menor que 1; 422 chutes fora do formato.
- Página: SVG/HTML no visual do placar (lâmpadas), JS pequeno sem dependências; sequência e
  histórico no `localStorage` por edição. Texto de compartilhar:
  `Quanto foi? #12 · Vasco 3/6` + uma linha de 🟩🟨⬜ por chute + link.
- Portal: o cartão "7 a 0" do Intervalo vira "Quanto foi?" com link para o jogo.

## Critérios de aceite (como testes)

- [ ] `test_puzzle_is_the_same_for_everyone_on_a_day`: dada a mesma edição e data, o jogo é o mesmo.
- [ ] `test_puzzle_does_not_repeat_until_the_pool_ends`: dias seguidos percorrem o pool sem repetir.
- [ ] `test_team_pool_only_has_the_team_matches`: a edição do Vasco só sorteia jogos do Vasco.
- [ ] `test_judge_marks_exact_close_and_far_per_side`: 2x1 contra 3x1 → mandante perto/mais, visitante certo.
- [ ] `test_judge_reveals_only_when_over`: sem acertar e com menos de 6 chutes, sem `reveal`.
- [ ] `test_judge_gives_hints_after_misses`: técnicos após 3 erros, vencedor após 4.
- [ ] `test_api_rejects_future_puzzle`: `number` de amanhã → 404 (não dá para espiar).
- [ ] `test_game_page_does_not_leak_the_score`: o HTML do dia não contém o placar.
- [ ] `test_unknown_or_abc_edition_is_404`.
- [ ] `test_portal_links_the_game`: o cartão do Intervalo aponta para `/jogos/quanto-foi`.

## Verificação ponta a ponta

```bash
uv run python scripts/import_brasileirao.py && uv run pytest
uv run uvicorn geral.web.app:create_app --factory  # jogar /jogos/quanto-foi e /jogos/quanto-foi/vasco
```

## Riscos e dúvidas abertas

- Dataset sem licença declarada: crédito visível; trocar de fonte se o autor pedir.
- Dados param em 2024; jogos de 2025–26 entram quando houver fonte.
- Cola: o chute vai ao servidor, mas o `Verdict` final revela o placar; quem quiser trapacear
  consegue. Aceito: é um joguinho, sem prêmio.
