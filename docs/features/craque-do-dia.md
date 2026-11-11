# "Craque do dia": o Wordle dos ídolos de cada torcida

- **Data:** 2026-11-11
- **Status:** proposta
- **ADRs:** —

## Objetivo

Segundo joguinho da Geral: um nome de guerra por dia (ídolo histórico ou artilheiro recente), no
formato Wordle, uma edição por torcida, incluindo o ABC, e uma geral com todas. O conteúdo é curado
à mão; é o que só uma newsletter de torcida tem.

## Fora de escopo

- Teclado na tela, dicionário de palavras válidas e letras usadas: o teclado do aparelho basta.
- Pontos no placar das torcidas, conta, jogo dentro da newsletter (pedem o banco, que é do bolão).
- Nomes de mais de uma palavra ("Juninho Pernambucano"): a resposta é sempre uma palavra só.

## Contratos

- Dados: `src/geral/games/craques/<slug>.toml`, uma lista por torcida (o slug do `teams.toml`);
  sem nome de clube no código. Cada entrada:

```toml
[[craque]]
nome = "Dinamite"            # a resposta: uma palavra, 3 a 10 letras depois de tirar acentos
completo = "Roberto Dinamite"
posicao = "Atacante"
epoca = "anos 70 a 90"
fato = "Maior artilheiro da história do clube."
```

- `geral/games/daily.py` (extraído do "Quanto foi?", sem mudar a ordem dele): `shuffled(items,
  seed)` e `number_on(day, launch)`.
- `geral/games/craque.py`: `load_lists(dir) -> dict[str, list[Craque]]` (valida as regras acima),
  `pool(lists, edition)` (geral = todas, sem repetir nome), `puzzle(pool, edition, number)`,
  `normalize(text) -> str` (maiúsculas, sem acento, só A–Z) e `judge(craque, guesses) -> Verdict`:
  por letra `certo` | `existe` | `nao` (letras repetidas contadas como no Wordle), `solved`,
  `over` (acertou ou 6 chutes), dicas (posição a partir do 3º erro, época a partir do 4º) e
  `reveal` só quando `over`. `LAUNCH = 2026-11-11`.
- Rotas (em `app.py`, sem banco), no molde do "Quanto foi?":

```python
# GET  /jogos/craque-do-dia            → 200 HTML, edição geral do dia (data de Brasília)
# GET  /jogos/craque-do-dia/{edition}  → 200 HTML; 404 para torcida sem lista
# POST /api/jogos/craque-do-dia/{edition}/{number}  → 200 Verdict
class WordGuessesIn(BaseModel):
    guesses: list[str]  # 1 a 6; cada um, normalizado, com o tamanho da resposta (senão 422)
```

- Página: quadradinhos de lâmpada com o tamanho do nome; o CSS comum dos jogos sai do template do
  "Quanto foi?" para `static/geral/jogos.css`. Compartilhar: `Craque do dia #3 · Vasco 4/6` + uma
  linha de 🟩🟨⬜ por chute + link. Portal: cartão "Craque do dia" no Intervalo.

## Critérios de aceite (como testes)

- [ ] `test_lists_follow_the_rules`: toda entrada real tem uma palavra de 3 a 10 letras, campos
      preenchidos e nenhum nome repetido na torcida.
- [ ] `test_normalize_drops_accents_and_case`: "Nenê" → "NENE".
- [ ] `test_judge_marks_letters_like_wordle`: resposta "ZICO", chute "COCO" → nao, nao, certo, certo.
- [ ] `test_judge_reveals_only_when_over` e `test_judge_gives_hints_after_misses`.
- [ ] `test_geral_mixes_all_lists` e `test_team_edition_only_has_its_list`.
- [ ] `test_api_rejects_wrong_length_or_symbols`: tamanho errado ou "Z1CO" → 422.
- [ ] `test_api_rejects_future_puzzle` e `test_unknown_edition_is_404`.
- [ ] `test_game_page_does_not_leak_the_name`: o HTML mostra o tamanho, não o nome.
- [ ] `test_quanto_foi_order_is_unchanged`: a extração do `daily.py` não muda o jogo do dia.
- [ ] `test_portal_links_the_word_game`.

## Verificação ponta a ponta

```bash
uv run pytest && uv run uvicorn geral.web.app:create_app --factory
# jogar /jogos/craque-do-dia e /jogos/craque-do-dia/abc no navegador, a 1280 e 390 px
```

## Riscos e dúvidas abertas

- Curadoria: o primeiro rascunho das listas é meu e pode errar época, posição ou fato (mais no ABC
  e no Náutico). As listas passam pela revisão do dev antes do merge.
- Cola: como no "Quanto foi?", seis chutes revelam a resposta. Aceito.
