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
- Servir as imagens: entra com o site do hub (fatia 2). Até lá, `brand_logo` fica vazio e o
  cabeçalho mostra o nome em texto.

## Contratos

- `teams.toml`: `brand_logo` (URL absoluta da `logo-email.png`) e `accent` (cor da marca).
- Arquivos por time, no mesmo formato da Urubu News, em `static/<slug>/`:
  - `logo-email.png`: 640×255, exibida a 320×127, mascote + nome, sobre fundo papel `#F4EFE6`;
  - `icon-512.png`: só o mascote num círculo, transparente fora dele (favicon, avatar);
  - `og-image.png`: 1200×630, prévia de link (WhatsApp, LinkedIn).
- Base comum a todas: papel `#F4EFE6`, tinta `#1C1C1C`, cinza `#6B6B6B`; cada time só troca a cor
  de destaque e o mascote.

| Newsletter | Mascote | Destaque | Apoio | Por quê |
|---|---|---|---|---|
| Almirante News (Vasco) | almirante navegador: chapéu bicorne, luneta, barba | carvão `#141414` | vermelho `#B3122E` (só detalhe) | o Vasco é o "Almirante"; vermelho remete à cruz sem desenhá-la |
| Porco News (Palmeiras) | porco bravo, presas à mostra, faixa na testa | verde `#006437` | verde-claro `#3FA34D` | apelido assumido pela torcida |
| Elefante News (ABC) | elefante investindo, tromba erguida, presas | carvão `#141414` | cinza-elefante `#8A8F98` | mascote do ABC |
| Timbu News (Náutico) | timbu (gambá-de-orelha-branca) de cara fechada | vermelho `#C60000` | branco | mascote e apelido do Náutico |

## Prompts (Nano Banana)

Mesmo estilo da Urubu News. Gerar o ícone primeiro e reaproveitá-lo na logo e na og-image.

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
| Almirante News | a bearded old navigator admiral with a bicorne hat and a brass spyglass | #141414, #B3122E | "ALMIRANTE" em #141414, "NEWS" em #B3122E |
| Porco News | a fierce wild boar-style pig with small tusks and a headband | #006437, #3FA34D | "PORCO" em #006437 |
| Elefante News | a charging elephant with raised trunk and tusks | #141414, #8A8F98 | "ELEFANTE" em #141414, "NEWS" em #8A8F98 |
| Timbu News | a white-eared opossum (Brazilian "timbu") with a grumpy tough face | #C60000 | "TIMBU" em #C60000 |

## Critérios de aceite (como testes)

- [x] `test_render_header_uses_the_brand_logo_not_the_crest`: com `brand_logo`, o cabeçalho tem a logo e nenhum escudo.
- [x] `test_render_header_without_logo_shows_the_name_only`: sem `brand_logo`, só o nome em texto.
- [x] `test_render_uses_team_name_and_colors`: nome e cor de destaque do time no e-mail.

## Verificação ponta a ponta

```bash
uv run resenha preview --team nautico --edition post --date 2026-11-08 --open
```

## Riscos e dúvidas abertas

- "Porco" e "Timbu" são apelidos de torcida; "Almirante" e "Elefante" também. Vale uma busca no
  INPI antes de investir na marca, como anotado para a Urubu News.
- Hospedagem das imagens: até o site do hub existir, não há URL pública para `brand_logo`.
