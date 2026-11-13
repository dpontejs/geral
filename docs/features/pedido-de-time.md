# Pedido de time (parte 3)

- **Data:** 2026-11-11
- **Status:** implementada (aguardando PR)
- **ADRs:** —

## Objetivo

Quem chega à Geral e não acha o seu time pede a torcida dele, com e-mail opcional para saber
quando ela nascer; o portal mostra os mais pedidos. O pedido só conta votos: o time continua
nascendo à mão no `teams.toml` (PLAN, decisões de 2026-11-10), e os mais pedidos dizem qual vem
primeiro.

## Fora de escopo

- O e-mail "sua torcida nasceu" (comando que avisa quem pediu): PR seguinte, quando houver o
  primeiro time a nascer de um pedido. Aqui o e-mail só fica guardado. Como ele não é
  confirmado, o aviso será um e-mail único, dizendo que alguém pediu o time com aquele endereço e
  convidando a assinar; não inscreve ninguém.
- Redesenho do portal (outro chat): o cartão "Seu time?" só vira link, e a página nova usa os
  estilos que já existem.
- Página de ranking de torcidas: o placar do portal já ordena as torcidas por inscritos.

## Contratos

- Tabela `team_requests` (mesmo SQLite): `team_key` (nome normalizado: minúsculas, sem acento,
  sem pontuação, espaços únicos), `team_name` (como digitado), `voter` (HMAC da rede: o IPv4, ou
  o /64 do IPv6), `email` (nulo se não deu), `created_at`. Chave `(team_key, voter)`: um voto
  por rede por time, com ou sem e-mail (e-mail inventado não soma voto); pedir de novo com e-mail
  guarda o e-mail.
- `GET /pedir`: formulário (time, e-mail opcional, honeypot `website`) e os 10 mais pedidos com
  pelo menos 3 votos (nome mais digitado + votos; nunca e-mail). Abaixo de 3 votos o nome não
  aparece em público: uma pessoa só não escreve na home.
- `POST /pedir` → 200 "Pedido anotado" com a posição e os votos do time; com e-mail, avisa que
  só vai receber um e-mail quando a torcida nascer.
  - Time que já está no catálogo (slug, nome ou newsletter; apelidos não, porque vários clubes
    os dividem): não conta voto, responde "Já tem!" com link para `/t/<slug>`.
  - 400: nome com menos de 2 ou mais de 40 caracteres (após NFC), fora de letras, dígitos,
    espaço, `-`, `.`, `'`, ou sem letra do alfabeto latino (mensagem própria); e-mail inválido.
    429: mais de 10 pedidos por rede por hora.
- `GET /api/team-requests` (token da API): `[{key, name, votes, emails}]` por votos, para o dono.
- E-mail ao dono a cada voto novo (`NOTIFY_EMAIL`): o time, a posição, o top 5 e um link
  assinado para `GET /pedidos?t=…` (HMAC com o segredo do site, propósito `team-requests`, vale
  30 dias). A página lista todos os pedidos, votos, data do último e quantos esperam aviso, sem
  os endereços; sem link válido é 404, com `noindex`, `no-store` e `no-referrer`.
- Portal: o cartão "Seu time?" vira link para `/pedir` e mostra o mais pedido com 3 votos ou mais.

## Critérios de aceite (como testes)

- [x] `test_request_counts_one_vote_per_person`: dado o mesmo e-mail pedindo "Sampaio Corrêa" duas vezes, então 1 voto.
- [x] `test_request_name_variants_share_a_vote_count`: "Sampaio Corrêa", "sampaio correa" e "Sampaio  Corrêa!" somam no mesmo time, exibido como o nome mais digitado.
- [x] `test_anonymous_request_counts_once_per_ip`: sem e-mail, o mesmo IP conta 1 voto; outro IP conta outro.
- [x] `test_request_again_with_email_keeps_the_email`.
- [x] `test_request_for_a_team_already_in_the_geral_points_to_it`: "Vasco" e "Almirante News" não contam voto e linkam `/t/vasco`.
- [x] `test_request_rejects_bad_name_and_email` (400) e `test_request_honeypot_counts_nothing`.
- [x] `test_request_rate_limit_per_ip` (429).
- [x] `test_request_page_lists_top_requests_without_emails`.
- [x] `test_api_team_requests_needs_token_and_lists_emails`.
- [x] `test_portal_card_links_to_request_page_with_top_request`.

## Verificação ponta a ponta

```bash
uv run ruff check . && uv run pytest
uv run uvicorn geral.web.app:create_app --factory   # abrir /pedir, pedir, ver a lista e o cartão
```

## Riscos e dúvidas abertas

- Voto por rede é burlável (troca de rede) e conta uma vez a casa inteira; para um projeto por
  diversão, aceitável.
