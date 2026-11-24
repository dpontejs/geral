# 7a0 do clube

- **Data:** 2026-11-23
- **Status:** aprovada
- **ADRs:** —

## Objetivo

O torcedor monta o time dos sonhos do seu clube só com quem vestiu a camisa e tenta a campanha
perfeita: **7 jogos, 7 vitórias, 0 derrota**. Inspirado no 7a0/Sete a Zero
(`docs/pesquisa/joguinhos-de-carreira.md`), que só tem seleções em Copas. O diferencial da Geral:
ABC, Náutico e CSA têm o seu, com os rivais do Nordeste e o clássico local na final.

## Fora de escopo

- Desafio diário (mesmo sorteio para todos) e ranking: depois. O sorteio já sai de uma semente.
- Clubes sem edição. Mudar `velha/clubes.toml` (mudaria o sorteio diário da velha).
- Nota dada à mão para todo jogador (só os ídolos têm nota manual).

## Como joga

1. Abre `/jogos/7a0/{edicao}`, escolhe o modo (**Clássico**: estrelas à vista, 3 trocas;
   **Almanaque**: estrelas escondidas, 1 troca) e o esquema (4-3-3, 4-4-2, 4-2-3-1, 3-5-2, 5-3-2).
2. 11 rodadas: o dado sorteia uma **década do clube** ("ABC · anos 70") e mostra quem jogou nele
   nela; o torcedor põe um jogador numa vaga livre. Uma troca sorteia outra década. Quem entra não
   sai, só troca de vaga. Décadas com menos de 8 jogadores no clube se juntam às seguintes
   numa **época** ("ABC · anos 60 a 80"), decidido pelo dev em 2026-11-23.
3. Campanha, jogada partida a partida: os jogos 1–6 em ordem crescente de força; o 7º é sempre o
   clássico, com **bônus de clássico** que o deixa ao menos tão forte quanto o 6º. Perdeu, caiu.
4. Empate vai à disputa de pênaltis (5 + alternadas): o torcedor bate as cobranças do seu time no
   minijogo da Carreira (`penalti.js`); o motor faz o goleiro e as cobranças do adversário. Botão
   "deixar o motor bater" (essa cobrança ou o resto da disputa).
5. Cada jogo acende no placar de lâmpadas os gols com minuto e autor ("34' Alberi"); botão
   "simular o resto". No fim, card com os 11, a década de cada um, a campanha e as marcas.

## Dados (`src/geral/games/setea0/`)

- **Elencos** (`setea0.json`, gerado por `scripts/import_setea0.py`): para cada edição, os
  jogadores da categoria "Futebolistas do <clube>" da Wikipédia pt, com anos no clube, posição e
  fama (nº de Wikipédias, pela Wikidata). ABC e Náutico reaproveitam `carreiras_pt.json`.
  Novos: CSA (149), Flamengo (765), Vasco (677), Palmeiras (719); a lista passa por revisão humana.
- **Força** (1–99, estrelas = faixas): fórmula de fama **relativa ao clube** + anos no clube +
  Seleção; `idolos.toml` fixa a nota dos ídolos (semeado de `craques/*.toml` e `carreira/lendas.toml`;
  ABC, Náutico e CSA precisam de lista nova de 15–20, revisada pelo dev).
- **Adversários** (`chaves.toml`): Nordeste (ABC, Náutico, CSA) contra os 6 mais fortes do grupo
  Ceará, Fortaleza, Vitória, Bahia, Santa Cruz, Sport, ABC, Náutico, CSA, tirando o próprio e o
  rival da final (o Náutico pega o ABC ou o CSA no lugar do Sport); grandes contra Corinthians, Santos,
  São Paulo, Grêmio, Internacional, Cruzeiro, Atlético-MG. Final: ABC×América-RN, CSA×CRB,
  Náutico×Sport, Flamengo×Vasco, Vasco×Flamengo, Palmeiras×Corinthians. Cada adversário é o
  "de todos os tempos": 11 por fama no esquema 4-4-2, da base da velha; América-RN e CRB vêm da
  Wikipédia pt pelo mesmo script.

- **Publicação por clube:** `chaves.toml` tem `publicado` por edição; o PR de dados mergeia com
  cada clube desligado até o dev revisar a lista e os ídolos dele. O motor anda com dados de teste.
- **Marcas** (`marcas.toml`, conteúdo revisado pelo dev no PR do motor): ~8, entre elas
  `sete-a-zero` (vencer **um jogo** por 7 a 0, rara), campanha invicta, artilheiro da campanha
  (≥ 7 gols), campeão nos pênaltis, virada na final.

## Contratos

```python
# motor puro e determinístico (setea0/motor.py)
# tipos em setea0/modelos.py; toda função do motor recebe também `dados: Dados`
class Jogador(BaseModel): id: str; nome: str; posicoes: list[Posicao]; passagens: list[tuple[int, int]]; forca: int
def oferta(edicao, semente, rodada, troca) -> Rodada   # década + jogadores
def jogo(edicao, semente, esquema, escalacao: list[Escolha], cobrancas: list[list[Cobranca]],
         n: int) -> Partida | PedidoDePenalti   # reprocessa do 1º ao n-ésimo, sem estado
class Cobranca(BaseModel): resultado: Literal["gol", "defesa", "fora", "trave", "motor"]
# POST /api/jogos/7a0/{edicao}/oferta {semente?, rodada, trocas}  → Rodada
# POST /api/jogos/7a0/{edicao}/jogo {semente, modo, esquema, escalacao, cobrancas, n}
#      → Partida (+ codigo e campanha quando é o 7º jogo ou a eliminação) | PedidoDePenalti
#      (a disputa pede a próxima cobrança do torcedor; o cliente repete a chamada com ela)
# GET  /jogos/7a0/c/{codigo}  → card da campanha guardada
```

- Banco: `setea0_guardado(codigo PK, campanha JSON zlib, criado_em)`, como `carreira_guardada`;
  `codigo` = 10 caracteres base64url do hash da entrada. O link nunca reprocessa: lê o guardado.
- Erros: 404 edição sem 7a0 ou código desconhecido; 422 escalação inválida (jogador fora da
  oferta da rodada, repetido, mais trocas que o modo).

## Critérios de aceite (como testes)

- [ ] `test_mesma_entrada_mesma_campanha`: semente + escalação iguais → campanha idêntica.
- [ ] `test_oferta_so_tem_jogadores_do_clube_na_decada`.
- [ ] `test_decadas_ralas_viram_epoca` (< 8 jogadores se juntam às seguintes).
- [ ] `test_escalacao_trapaceada_da_422`: jogador fora da oferta, repetido ou troca a mais.
- [ ] `test_fora_de_posicao_perde_forca`.
- [ ] `test_final_e_o_classico_e_ao_menos_tao_forte_quanto_o_6o` e
  `test_jogos_1_a_6_em_ordem_crescente`.
- [ ] `test_calibragem` (1000 campanhas numa passada, por clube): time por escolha gulosa fecha
  7 a 0 em 10–30%; time aleatório em < 3%; ABC e Flamengo com taxas a ±50% uma da outra.
- [ ] `test_empate_pede_cobranca_do_torcedor`: o motor devolve `PedidoDePenalti` até a disputa
  se decidir; o adversário cobra sozinho.
- [ ] `test_motor_bate_os_penaltis`: `motor` dá o mesmo resultado em toda chamada (determinístico).
- [ ] `test_placar_7_a_0_vira_marca_rara`.
- [ ] `test_link_abre_apos_mudar_os_dados`: guarda, troca `setea0.json`, o card segue igual.

## Verificação ponta a ponta

`uv run pytest -n auto` e, no servidor local, jogar uma campanha do ABC e uma do Flamengo no
celular e no computador, abrir o link do card numa aba anônima; fotos ao dev antes de commitar o visual.

## Riscos e dúvidas abertas

- Categorias grandes da Wikipédia pt trazem muita gente obscura; a revisão de ~2.300 nomes é o
  gargalo. Mitigação: o script sugere cortes (sem anos, sem posição, < 1 temporada).
- Posição vem do infobox pt ("Lateral" existe lá, ao contrário da Wikidata): conferir na amostra.
