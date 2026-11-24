# 7a0 do clube — PR 4: tela, rotas, link e campanha guardada

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o torcedor joga o 7a0 do seu clube no site, do esquema ao card, e compartilha um link curto que abre mesmo depois de os dados mudarem.

**Architecture:**
- Rotas FastAPI em `web/app.py`, sem estado de jogo: cada chamada reprocessa a partir da semente com `setea0.motor`, como a Carreira.
- Campanha terminada vai para a tabela `setea0_guardado`, no mesmo SQLite.
- Página `setea0.html.j2` + `static/geral/setea0.js`, a partir do rascunho aprovado (`docs/features/setea0-rascunho.html`), e o minijogo `penalti.js` da Carreira.

**Tech Stack:** FastAPI, Jinja, JS sem framework (como `carreira.js`), SQLite, pytest + TestClient.

**Spec:** `docs/features/setea0.md`. **Motor:** `src/geral/games/setea0/motor.py` (no main).

## Global Constraints

- Como nos PRs anteriores: commits em pt-BR, uma linha, sem escopo e sem trailer.
- Portões antes de commitar: `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
- Visual na identidade aprovada (placar de lâmpadas, gramado, papel). **Fotos no celular (390 px) e no computador (1366 px) ao dev antes de commitar o visual.**
- Edição com `publicado = false` dá 404, a não ser com `SETEA0_PREVIA=1` no ambiente, para o dev testar na VPS antes de ligar.

## Review Focus

- Dados mudam no meio de uma partida (`versao` diferente) → 409 com mensagem, nunca outra campanha em silêncio. Teste em Task 2.
- Mesmo link pedido duas vezes, ou a mesma campanha terminada duas vezes → uma linha só na tabela. Teste em Task 1.
- Campanha forjada (cobranças inventadas, escolha fora da oferta) → 422, e nada é guardado. Teste em Task 2.
- Muitas campanhas da mesma rede → o jogo termina, mas a partir do limite não guarda nem gera link. Teste em Task 2.
- Modo Almanaque: a API não manda as estrelas. Teste em Task 2.

---

### Task 1: campanha guardada

**Files:** Create `src/geral/web/setea0_guardado.py`. Test `tests/test_setea0_guardado.py`.

**Interfaces — Produces:**
- `codigo(edicao, semente, modo, esquema, escolhas, cobrancas, versao) -> str`: 10 caracteres base64url do sha256 do JSON ordenado da entrada.
- `class GuardadoStore(path)`, com o SQL `CREATE TABLE IF NOT EXISTS setea0_guardado (codigo TEXT PRIMARY KEY, campanha BLOB NOT NULL, criada_em TEXT NOT NULL)`:
  - `guardar(codigo, campanha_json, agora)` comprime com zlib e usa `INSERT OR IGNORE`;
  - `guardada(codigo) -> str | None`.

- [ ] **Step 1:** testes que falham:
  - `test_codigo_curto_e_estavel` (10 caracteres; a mesma entrada dá o mesmo código; uma cobrança diferente dá outro);
  - `test_guardar_duas_vezes_fica_uma`;
  - `test_guardada_desconhecida_e_none`.
- [ ] **Step 2–4:** rodar, ver falhar, implementar, rodar e ver passar. **Step 5:** commit `feat: campanha do 7a0 guardada para o link`.

### Task 2: rotas

**Files:** Modify `src/geral/web/app.py` (rotas, entrada `7a0` em `games()`, limite por rede). Create `src/geral/web/templates/setea0.html.j2`: nesta task, só o esqueleto com o JSON da página. Test `tests/test_web_setea0.py`.

**Interfaces — Produces (a API que a Task 3 consome):**
- `GET /jogos/7a0`: escolha do clube, com as edições publicadas. É a "geral" das abas.
- `GET /jogos/7a0/{edicao}`: a página do jogo. 404 se a edição não está publicada.
- `GET /jogos/7a0/c/{codigo}`: o card da campanha guardada (`setea0.html.j2` com `compartilhada`). Código desconhecido dá 404 com a mensagem "Esse link do 7a0 não abre. Que tal montar o seu time?".
- `POST /api/jogos/7a0/{edicao}/oferta`, com o corpo `{semente: str|None, versao: str|None, modo, rodada, troca}`, devolve `{semente, versao, epoca: {rotulo}, jogadores: [{id, nome, posicoes, anos: "1967–1981", estrelas: 1-5 | null, idolo: bool}], trocas_restantes}`.
  - O servidor sorteia a `semente` quando ela vem vazia.
  - As estrelas são `1 + (forca - 1) * 5 // 99`, e saem `null` no Almanaque.
  - `idolo` vem de `idolos.toml`.
- `POST /api/jogos/7a0/{edicao}/jogo`, com o corpo `{semente, versao, modo, esquema, escolhas: [Escolha], cobrancas: [[Cobranca]], n}`, devolve uma de duas coisas:
  - `{partida: Partida, adversario: {nome}, fim: bool, campanha: Campanha|null, codigo: str|null}`;
  - `{pedido: PedidoDePenalti, adversario: {nome}}`.
  - `fim` é verdadeiro no 7º jogo ou na derrota.
  - No fim, a rota chama `motor.campanha` e guarda o resultado; depois do limite da rede (`SETEA0_POR_REDE = 30` por hora, o `RateLimiter` da Carreira), não guarda e devolve `codigo: null`.
- Erros: `versao` diferente da dos dados dá 409, com `{"detail": "O 7a0 foi atualizado enquanto você jogava. Comece um time novo.", "atualizado": true}`; `JogadaInvalida` dá 422.

- [ ] **Step 1:** testes que falham (os dados de teste entram por `monkeypatch` de `setea0.dados.carregar`, e `chaves()` com `abc` publicado):
  - `test_pagina_do_clube_publicado` e `test_clube_nao_publicado_da_404`, este com `SETEA0_PREVIA=1` abrindo;
  - `test_oferta_sorteia_semente` e `test_almanaque_sem_estrelas`;
  - `test_campanha_inteira_pela_api` (11 ofertas, escolha gulosa, jogos de 1 a 7 com `"motor"` em cada pedido de pênalti, e no fim `codigo` não nulo);
  - `test_link_abre_apos_mudar_os_dados` (troca a `versao` dos dados e o card continua igual);
  - `test_versao_diferente_da_409`, `test_cobranca_forjada_da_422_e_nao_guarda` e `test_limite_por_rede_nao_guarda`.
- [ ] **Step 2–4:** rodar, ver falhar, implementar, rodar e ver passar. **Step 5:** commit `feat: rotas do 7a0 do clube`.

### Task 3: tela

**Files:** Modify `setea0.html.j2`. Create `src/geral/static/geral/setea0.js` (CSS no `<style>` do template, como no rascunho, ou em `jogos.css`, se houver reuso). Modify `src/geral/web/templates/edicao.html.j2` e o cartão do hub `/jogos` (`desc`: "Monte o time dos sonhos do seu clube, uma época por rodada, e tente a campanha perfeita: 7 jogos, 7 vitórias.").

**Fluxo** (as telas são as do rascunho aprovado):
1. **Início:** modo (Clássico ou Almanaque, em cartões como os "Com/Sem minijogos" da Carreira) e esquema (chips).
2. **Escalar:**
   - O placar mostra "Rodada N de 11 · esquema · modo" e a época sorteada.
   - O gramado tem as vagas, e a lista tem os jogadores com a posição, os anos e as estrelas.
   - Tocar num jogador acende as vagas livres em que ele encaixa (todas ficam disponíveis). Tocar numa vaga escala o jogador.
   - "Trocar época (N)" pede a oferta com `troca + 1`.
   - Um jogador já escalado aparece apagado ("já está no time").
3. **Jogo:**
   - O placar de lâmpadas mostra o 7 jogos, o `Seu {clube}` contra o `{adversário}` e os gols com minuto e autor.
   - Os gols acendem um a um, com ~400 ms entre eles.
   - Botões "Próximo jogo" e "Simular o resto". O "Simular o resto" manda `"motor"` em todo pedido de pênalti.
4. **Pênalti:**
   - `PedidoDePenalti` abre `window.jogarPenalti(el, {finalizacao: chance, clube, adversario, tipo: n == 7 ? "final" : "jogo", minuto: "Pênaltis"})`.
   - O resultado entra em `cobrancas`, e a chamada é repetida.
5. **Card:** como o rascunho, com "Compartilhar" (Web Share, e na falta dele copiar `/jogos/7a0/c/{codigo}`) e "Jogar de novo".

- [ ] **Step 1:** subir o servidor local com `SETEA0_PREVIA=1` e jogar uma campanha do ABC e uma do Flamengo, inclusive um pênalti no minijogo e um link aberto em aba anônima.
- [ ] **Step 2:** fotos das 4 telas (escalar, jogo, pênalti, card) em 390 px e 1366 px, mandadas ao dev. **Esperar a aprovação.**
- [ ] **Step 3:** `test_pagina_tem_o_js_e_os_dados` (o HTML referencia `setea0.js` e traz o JSON com a edição e os esquemas); portões completos; commit `feat: tela do 7a0 do clube`; PR "7a0 do clube: tela e link".
