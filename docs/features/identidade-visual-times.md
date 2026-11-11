# Identidade visual das newsletters por time

- **Data:** 2026-11-10
- **Status:** proposta (código pronto; faltam as imagens)
- **ADRs:** —

## Objetivo

Cada newsletter do hub tem marca própria, como a Urubu News: um mascote, uma paleta e três imagens.
Nada de escudo, listras ou símbolos oficiais do clube no cabeçalho, para não parecer canal oficial.
O escudo continua só no placar, como dado da partida.

## Fora de escopo

- Identidade do hub (nome, logo, página): depende da escolha do nome (ver `docs/PLAN.md`).
- Servir as imagens: o portal da Geral serve `/static/<slug>/` (parte 2.1). O `run` usa
  `{PUBLIC_URL}/static/<slug>/logo-email.png` só quando `PUBLIC_URL` é https; senão o cabeçalho
  mostra o nome em texto.

## Contratos

- `teams.toml`: `accent` (cor da marca). A logo vai como `render(..., logo_url=...)`.
- Arquivos por time, no mesmo formato da Urubu News, em `static/<slug>/`:
  - `logo-email.png`: 640×255, exibida a 320×127, mascote + nome, sobre fundo papel `#F4EFE6`;
  - `icon-512.png`: só o mascote num círculo, transparente fora dele (favicon, avatar);
  - `og-image.png`: 1200×630, prévia de link (WhatsApp, LinkedIn).
- **A paleta do mascote é a do clube**, e só ela: as cores da camisa (Vasco e ABC preto e branco,
  Palmeiras verde e branco, Náutico vermelho e branco) mais o contorno `#1C1C1C`. Nada de cor
  extra (dourado, latão, azul), nem a cor de detalhe de um símbolo que não usamos (o vermelho da
  cruz do Vasco). O torcedor tem que reconhecer o time pela cor antes de ler o nome.
- Base comum a todas: papel `#F4EFE6`, tinta `#1C1C1C`, cinza `#6B6B6B` (no "NEWS" dos times em que
  o branco sumiria sobre o papel); cada time só troca o mascote e as cores do clube.

| Newsletter | Mascote | Destaque | Apoio | Por quê |
|---|---|---|---|---|
| Almirante News (Vasco) | velho navegador português do século XVI: barba branca cheia, gorro de navegador, gola alta, luneta | preto `#141414` | branco `#FFFFFF` | o Vasco é o "Almirante"; alvinegro, sem o vermelho da cruz |
| Porco News (Palmeiras) | porco bravo, presas à mostra, faixa na testa | verde `#006437` | branco `#FFFFFF` | apelido assumido pela torcida; alviverde |
| Elefante News (ABC) | elefante investindo, tromba erguida, presas | preto `#141414` | branco `#FFFFFF` | mascote do ABC; alvinegro |
| Timbu News (Náutico) | timbu (gambá-de-orelha-branca) de cara fechada | vermelho `#C60000` | branco `#FFFFFF` | mascote e apelido do Náutico; alvirrubro |

## Como gerar

Só o **ícone** sai do Nano Banana. A logo do e-mail e a og-image são montadas por código a
partir dele (`scripts/make_brand.py`, fonte Oswald), porque o Nano Banana redesenha o mascote
mesmo com a imagem de referência, e já colocou símbolos do clube (cruz, faixa) na logo.
O script recorta o círculo (o "fundo transparente" do Nano Banana é um quadriculado desenhado),
monta as três imagens e reduz a paleta. `--circle` recorta exatamente no círculo (mascote que
cabe nele); sem a opção, o recorte segue o desenho (o elefante do ABC sai do círculo). Originais
do Nano Banana em `brand_src/` (fora do git):

```bash
python scripts/make_brand.py brand_src/vasco.jpg src/geral/static/vasco Almirante News "#141414" "#6B6B6B" Vasco --circle
python scripts/make_brand.py brand_src/palmeiras.jpg src/geral/static/palmeiras Porco News "#006437" "#1C1C1C" Palmeiras --circle
python scripts/make_brand.py brand_src/abc.jpg src/geral/static/abc Elefante News "#141414" "#6B6B6B" ABC
python scripts/make_brand.py brand_src/nautico.jpg src/geral/static/nautico Timbu News "#C60000" "#1C1C1C" Náutico --circle
```

## Prompts (Nano Banana)

Mesmo estilo da Urubu News. Só o ícone; o resto sai do script.

**Ícone** (trocar `<MASCOTE>` e `<CORES>`):

> Sports team mascot logo, esports style: <MASCOTE>, angry determined face, three-quarter view,
> bold flat vector shapes, thick dark outline, no gradients, no text, centered inside a solid
> circle, transparent background outside the circle, readable at 32 px, only these colors:
> <CORES>, #1C1C1C and #F4EFE6. No club crest, no shield, no stripes, no real club symbols.

**Logo do e-mail**:

> Horizontal wordmark logo, 640x255, background #F4EFE6: on the left the mascot icon from the
> reference image; on the right the text "<NOME>" in a heavy condensed sans-serif (like Oswald
> Bold), uppercase, color #1C1C1C with "<PALAVRA DE DESTAQUE>" in <COR DESTAQUE>. Flat, no
> gradients, no shadow, generous margins.

**og-image**: a logo do e-mail centralizada em 1200×630 sobre `#F4EFE6`, com a frase
"Notícias do <time>, antes e depois de cada jogo" em `#6B6B6B` embaixo.

Valores por time:

| Newsletter | `<MASCOTE>` | `<CORES>` | Destaque no nome |
|---|---|---|---|
| Almirante News | a stern old 16th-century Portuguese navigator with a full white beard, a dark navigator's cap, a high white collar and a dark spyglass | #141414, #FFFFFF | "ALMIRANTE" em #141414, "NEWS" em #6B6B6B |
| Porco News | a fierce wild boar-style pig with small tusks and a headband | #006437, #FFFFFF | "PORCO" em #006437 |
| Elefante News | a charging elephant with raised trunk and tusks | #141414, #FFFFFF | "ELEFANTE" em #141414, "NEWS" em #6B6B6B |
| Timbu News | a white-eared opossum (Brazilian "timbu") with a grumpy tough face | #C60000, #FFFFFF | "TIMBU" em #C60000 |

## Critérios de aceite (como testes)

- [x] `test_render_header_uses_the_brand_logo_not_the_crest`: com `logo_url`, o cabeçalho tem a logo e nenhum escudo.
- [x] `test_render_header_without_logo_shows_the_name_only`: sem `logo_url`, só o nome em texto.
- [x] `test_render_uses_team_name_and_colors`: nome e cor de destaque do time no e-mail.

## Verificação ponta a ponta

```bash
uv run geral preview --team nautico --edition post --date 2026-11-08 --open
```

## Riscos e dúvidas abertas

- "Porco" e "Timbu" são apelidos de torcida; "Almirante" e "Elefante" também. Vale uma busca no
  INPI antes de investir na marca, como anotado para a Urubu News.
- As imagens dependem do portal da Geral no ar; com imagens bloqueadas, aparece o `alt`.
