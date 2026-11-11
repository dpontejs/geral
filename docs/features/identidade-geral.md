# Identidade visual da Geral (o hub)

- **Data:** 2026-11-10
- **Status:** proposta
- **ADRs:** —

## Objetivo

A marca do hub evoca a nostalgia do Maracanã antigo: a Geral de concreto, gente em pé, radinho de
pilha no ouvido, ingresso de papel, placar manual. É a casa de todas as torcidas, então não usa a
cor de nenhum clube; as torcidas (Almirante, Porco, Elefante, Timbu...) aparecem dentro dela com os
seus mascotes.

## Fora de escopo

- A página do hub em si (fatia 2): aqui só a marca e as imagens.
- Logos, escudos ou o nome oficial do estádio como marca; "Maracanã" é inspiração, não símbolo.

## Contratos

- Paleta neutra, de foto de jornal antigo (o verde de pôster foi descartado: lembrava o Palmeiras):

  | Papel | Cor | Uso |
  |---|---|---|
  | concreto | `#8E8B84` | destaque principal, fundo do ícone |
  | concreto claro | `#B9B5AC` | arquibancada, traços secundários |
  | papel de jornal antigo | `#EFE4CC` | fundo da página e do e-mail, camisa do geraldino |
  | pele desbotada | `#C99A73` | só a pele do geraldino |
  | amarelo de ingresso | `#E3B23C` | só detalhes: radinho, selos, "edição geral" |
  | tinta | `#1E1E1E` | contorno e texto |

- Mascote: o **geraldino**, torcedor da Geral, em pé, radinho de pilha colado no ouvido, camisa
  sem time, braço erguido no grito de gol; atrás dele, a curva da marquise de concreto.
- Tipografia: condensada de pôster esportivo antigo (Oswald na logo, como as newsletters).
- Arquivos em `src/geral/static/geral/`: `icon-512.png`, `logo-email.png`, `og-image.png`, gerados
  por `scripts/make_brand.py` a partir do ícone do Nano Banana (`brand_src/geral.jpg`).

## Prompt do ícone (Nano Banana)

> Retro 1970s Brazilian newspaper illustration style mascot logo: a "geraldino", an ordinary fan
> standing in the old concrete stadium terraces, holding a small transistor radio against his ear,
> other arm raised shouting a goal, plain shirt with no team colors, mustache, joyful and passionate
> face, three-quarter view. Behind him, the curved concrete roof edge and terraces of a huge old
> round stadium. Bold flat vector shapes, thick #1E1E1E outline, no gradients, no textures, no
> text. Everything fits completely inside a solid #8E8B84 circle with a thin #EFE4CC ring; nothing
> crosses the circle edge. Transparent background outside the circle. Readable at 32 px. Colors:
> circle background #8E8B84; terraces and roof #B9B5AC; shirt #EFE4CC; skin #C99A73; hair, mustache
> and outlines #1E1E1E; the radio is the only #E3B23C element. No green, no other colors. No club
> crest, no club colors, no flags, no stadium logo.

## Critérios de aceite

- O ícone lê bem a 32 px (favicon) e não lembra nenhum clube.
- A logo do e-mail "GERAL" e a og-image saem do script, com a paleta acima.

## Riscos e dúvidas abertas

- Selo "edição geral" e as torcidas na página inicial: definir com a página do hub.
