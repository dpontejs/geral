# Identidade visual da Geral (o hub)

- **Data:** 2026-11-10
- **Status:** periquito no lugar do geraldino (2026-11-11)
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
  | papel de jornal antigo | `#EFE4CC` | fundo da página e do e-mail, penas claras do periquito |
  | amarelo de ingresso | `#E3B23C` | só detalhes: radinho, selos, "edição geral" |
  | tinta | `#1E1E1E` | contorno e texto |

- Mascote: o **periquito** (2026-11-11, no lugar do geraldino): um periquito torcedor comemorando o gol
  na frente do estádio redondo, de radinho de pilha e ingresso na mão, em concreto e papel de jornal
  (sem verde, para não virar o mascote do Palmeiras). O geraldino segue na história do "Por que
  Geral?", como o torcedor do Maracanã antigo.
- Tipografia: condensada de pôster esportivo antigo (Oswald na logo, como as newsletters).
- Arquivos em `src/geral/static/geral/`: `icon-512.png`, `logo-email.png`, `og-image.png`, gerados
  por `scripts/make_brand.py` a partir do ícone do Nano Banana (`brand_src/geral-periquito.png`).

## Prompt do ícone (Nano Banana Pro, `gemini-3-pro-image` pela chave do Gemini)

> Retro 1970s Brazilian newspaper illustration style mascot logo: a cheerful, cheeky little parakeet
> (periquito) fan in the old concrete stadium terraces, wings raised celebrating a goal, holding a
> small transistor radio, tiny paper ticket tucked under one wing. Behind it, the curved concrete
> roof edge and terraces of a huge old round stadium. Bold flat vector shapes, thick #1E1E1E outline,
> no gradients, no textures, no text. Everything fits completely inside a solid #8E8B84 circle with a
> thin #EFE4CC ring; nothing crosses the circle edge. Plain white background outside the circle.
> Readable at 32 px. Colors: circle background #8E8B84; terraces and roof #B9B5AC; the parakeet's
> feathers in #EFE4CC and #B9B5AC with #1E1E1E markings; the radio is the only #E3B23C element. No
> green, no other colors. No club crest, no club colors, no flags, no stadium logo. Square image.

Gerado pela API (`google-genai`, `models.generate_content(model="gemini-3-pro-image", ...,
response_modalities=["IMAGE"])`); o original fica em `brand_src/geral-periquito.png`.

## Critérios de aceite

- O ícone lê bem a 32 px (favicon) e não lembra nenhum clube.
- A logo do e-mail "GERAL" e a og-image saem do script, com a paleta acima.

## Riscos e dúvidas abertas

- Selo "edição geral" e as torcidas na página inicial: definir com a página do hub.
