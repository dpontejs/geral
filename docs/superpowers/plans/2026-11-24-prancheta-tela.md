# Prancheta — a tela (fatia E) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** as páginas da Prancheta (criar sala, sala ao vivo, súmula) a partir do rascunho aprovado pelo dev, falando com a API da fatia D.

**Architecture:** o rascunho aprovado (`docs/features/prancheta-rascunho.html`, no worktree `~/geral-prancheta-visual`, ainda não commitado) vira template + JS + CSS no padrão dos outros joguinhos: `prancheta.html.j2` estende `base.html.j2`, `static/geral/prancheta.js` (máquina de estados que só desenha o que o `estado`/eventos mandam), estilos em `static/geral/prancheta.css`. As rotas de página ficam num router próprio que recebe o objeto da fatia D.

**Tech Stack:** Jinja2, JS puro (EventSource, Pointer Events, canvas), CSS; pytest para as rotas; Playwright para fotos e ponta a ponta.

**Spec:** `docs/features/prancheta.md` (Regras, Contratos › Traço, Rotas, Eventos). Rascunho: o arquivo acima, **aprovado como está** (inclusive as linhas do campo apagadas no quadro).

## Global Constraints

- Visual = o do rascunho. Não inventar cor, enfeite ou tela nova; o que mudar por necessidade técnica, dizer no PR. Identidade e gosto do dev: `docs/features/identidade-geral.md`.
- Traço: coordenadas inteiras 0–1000 **nos dois eixos** do quadro 4:3; pedaços de ≤ 64 pontos, enviados a cada ~50 ms enquanto desenha; espessuras e cores do rascunho; cor 0 = apagador.
- Relógio: `prazo − (agora_do_servidor − Date.now() no recebimento)`; nada de relógio só local.
- Reconexão: o `EventSource` reconecta sozinho; ao receber `estado`, a tela se redesenha inteira a partir dele (inclusive `tracos`). Token em `localStorage` por sala (`prancheta:<id>`); sem token → tela de entrar com apelido.
- Rotas de página: `GET /jogos/prancheta` (criar: apelido + rodadas 1–3) e `GET /jogos/prancheta/s/{id}` (viva → jogo; `sumula(id)` → súmula; nenhum → aviso "a sala acabou ou o servidor reiniciou" com botão "Nova sala", status 404).
- Commit: `tipo: descrição` em pt-BR, uma linha, sem escopo e sem trailer.

## Review Focus

- Celular com teclado aberto ao chutar: o campo de chute fica visível (`visualViewport`/`scrollIntoView`), o quadro pode encolher.
- Quem desenha com o dedo e a página rolando: `touch-action: none` no canvas, `pointercancel` encerra o traço.
- Aba em segundo plano voltando: o `estado` da reconexão redesenha tudo, sem traço duplicado (o `id` do traço manda).
- Expulso ou sala encerrada: a tela mostra o aviso certo e para de reconectar.
- Resposta 429 ao desenhar rápido demais: junta os pontos no próximo pedaço em vez de perder o traço.

---

### Task 1: rotas de página e template

**Files:** Create `src/geral/web/prancheta_paginas.py`, `src/geral/web/templates/prancheta.html.j2`, `src/geral/web/templates/prancheta_sumula.html.j2`; Modify `src/geral/web/app.py` (uma linha: `app.include_router(paginas_prancheta(prancheta, render))`, depois que a fatia D estiver no main); Test `tests/test_web_prancheta_paginas.py`.

**Interfaces — Consumes** (fatia D, `geral.web.prancheta`): `Prancheta.viva(sala_id) -> bool`, `Prancheta.sumula(sala_id) -> dict | None`; API sob `/api/jogos/prancheta` e eventos conforme a spec (`estado` traz `jogadores[i].cartoes` e `cartoes_para_sair`). Enquanto D não estiver no main, teste com um `Prancheta` falso (só `viva`/`sumula`).
**Produces:** `paginas_prancheta(prancheta, render: Callable[..., Response]) -> APIRouter`, com `render` = o helper de template do `app.py`.

- [ ] Testes: `test_pagina_de_criar`, `test_sala_viva_abre_o_jogo` (o HTML traz o id da sala no `data-sala`), `test_sala_encerrada_mostra_sumula` (apelidos e palavras da súmula na página, sem desenho), `test_sala_inexistente_mostra_aviso` (404 + "Nova sala"). Ver falhar, implementar, verde, commit `feat: páginas da prancheta`.

### Task 2: o jogo no navegador

**Files:** Create `src/geral/static/geral/prancheta.js`, `src/geral/static/geral/prancheta.css`; Modify `prancheta.html.j2`.

- [ ] Portar o rascunho: trocar os dados falsos por `fetch` às rotas e `EventSource` nos eventos; todas as telas (espera, escolha, desenhando, chutando, cartão, intervalo, fim) dirigidas pelo `estado`. Commit `feat: prancheta jogável no navegador`.

### Task 3: ponta a ponta e fotos (depois que a fatia D estiver no main)

- [ ] Rebase no main, ligar o router no `app.py`, subir o app local e rodar um script Playwright (no scratchpad, não no repositório) com 3 navegadores (1 celular 390×844, 2 computador 1366×800): criar, entrar, começar, escolher, desenhar, chutar errado, na trave e certo, intervalo, até a súmula. Fotos de cada tela, celular e computador. Corrigir o que quebrar com teste red/green quando for regra do servidor.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run pytest`; commit; PR em pt-BR com as fotos citadas pelo caminho.
