# "Quem é?": adivinhe o jogador pela carreira

- **Data:** 2026-11-11
- **Status:** aprovada
- **ADRs:** —

## Objetivo

Quarto joguinho da Geral, o inverso do "Onde jogou?": a carreira inteira do jogador do dia aparece
(clubes e anos) e o torcedor adivinha quem é, escolhendo num seletor com busca, em até 6 chutes.
Usa o mesmo `carreiras.json`; edições iguais às do "Onde jogou?", em outra ordem diária.

## Fora de escopo

- Estatísticas de jogos e gols por clube (cobertura irregular no Wikidata).
- Pontos no placar das torcidas, conta, jogo dentro da newsletter.

## Contratos

- Jogos anteriores (12/11/2026): `GET /jogos/quem-e/{edição}/{número}` abre um número já passado
  (o de hoje redireciona para a página do dia; futuro ou zero dá 404), com a data e o aviso "não
  conta na sequência"; a página do dia lista os anteriores da edição. No navegador, cada número
  antigo tem o próprio registro (`quem-e:{edição}:{número}`) e não mexe nas estatísticas; um jogo
  já jogado no próprio dia aparece como ficou. As respostas vêm do calendário congelado
  (`src/geral/games/calendario.json`).
- `onde_jogou.pool(data, edition, teams, game="onde-jogou")`: o prefixo da semente vira parâmetro
  (o "Onde jogou?" continua na mesma ordem).
- `geral/games/quem_e.py`: `pool(data, edition, teams)` (semente `quem-e`), `judge(data, jogador,
  palpites) -> Verdict` com `rows` (nome e acerto por chute), `solved`, `over` (acertou ou 6
  chutes), dicas (posição a partir do 3º erro, inicial do nome a partir do 4º) e `reveal` (nome,
  posição) só no fim. `LAUNCH = 2026-11-11`, `MAX_GUESSES = 6`.
- Rotas: `GET /jogos/quem-e[/{edition}]` (carreira com clubes e anos; lista de jogadores para o
  seletor) e `POST /api/jogos/quem-e/{edition}/{number}` com `{"palpites": [id do Wikidata]}`;
  jogador desconhecido → 422; edição ou número inválido → 404.
- Compartilhar: `Quem é? #3 · Vasco 3/6` + 🟥 por erro e 🟩 no acerto + link.

## Critérios de aceite (como testes)

- [x] `test_judge_marks_each_guess_and_reveals_only_when_over`.
- [x] `test_judge_gives_position_then_initial_after_misses`.
- [x] `test_judge_ignores_a_repeated_guess`.
- [x] `test_quem_e_order_differs_from_onde_jogou`.
- [x] `test_game_page_shows_the_career_not_the_name`.
- [x] `test_api_rejects_unknown_player`, `test_api_rejects_future_puzzle`, `test_portal_links_who_game`.

## Verificação ponta a ponta

```bash
uv run pytest && uv run uvicorn geral.web.app:create_app --factory  # jogar /jogos/quem-e
```

## Riscos e dúvidas abertas

- Com 106 jogadores, a lista do seletor é curta: quem conhece o futebol brasileiro acerta rápido.
  Dá para crescer a lista de jogadores depois.
