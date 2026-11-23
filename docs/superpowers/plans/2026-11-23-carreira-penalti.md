# Carreira: pênalti decisivo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a final de copa decidida num pênalti jogável (ou sorteado pela finalização), com a chave "com/sem minijogos" no formulário.

**Architecture:** O lance é uma `Escolha(tipo="lance")` como as outras: a resposta (índice do resultado) entra em `Entrada.escolhas`, então replay e link seguem iguais. O sorteio "chegou à final" acontece no rng da temporada, antes da pergunta. A tela reaproveita o rascunho `docs/features/carreira-penalti-rascunho.html` como módulo `penalti.js`.

**Tech Stack:** Python 3.12, pydantic, pytest; JS puro + canvas.

**Spec:** `docs/features/carreira-penalti.md`

## Global Constraints

- Partir do `origin/main` **depois** dos PRs de conteúdo (decisões/marcas e manchetes) e do #76 (sem Rápida) mergeados; rebasear se preciso.
- Commits em pt-BR, `tipo: descrição`, sem escopo, uma linha, sem trailer. Antes de commitar: `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
- Não enfraquecer teste; `test_carreira_realismo.py` passa sem ajuste.
- Visual na identidade da Geral (o rascunho já está nela); mostrar fotos ao dev antes do commit da tela.

## Review Focus

- Link antigo (formato binário atual, sem o bit de minijogos) abre e refaz igual — Task 3.
- Resposta de lance fora de 0–4 → `JogadaInvalida` — Task 1.
- Carreira sem minijogos não muda a distribuição de títulos de copa além de ±20% — Task 2.
- Jogador que muda de posição (virou meia/zagueiro) — a elegibilidade usa a posição atual — Task 1.
- Tela: toque no celular não dispara clique duplo (pointerdown + click) — Task 4.

---

### Task 1: Motor — o lance

**Files:** Modify `src/geral/games/carreira/motor.py`, `marcas.toml`, `eventos.toml` (2 eventos de manchete com peso 0: `penalti-gol`, `penalti-erro`, ≥ 4 manchetes cada); Test `tests/test_carreira_penalti.py` (novo)

**Produces:** `Entrada.minijogos: bool = False`; `Escolha.tipo` aceita `"lance"`; `MAX_LANCES = 2`; `CHANCE_FINAL` (calibrada na Task 2); `chance_penalti(finalizacao: int) -> float` = `clamp(0.45 + (f - 60) / 100, 0.35, 0.85)`; `ResultadoLance(resultado: Literal["gol","defesa","fora","trave"], adversario: str, manchete: str)`; `Temporada.lance: ResultadoLance | None = None`.

- [x] Testes `test_final_vai_para_o_penalti`, `test_gol_da_o_titulo_e_erro_tira`, `test_sem_minijogos_nao_pergunta_e_sorteia_pela_finalizacao`, `test_motor_bate_quando_pedido`, `test_no_maximo_dois_lances_e_so_atacante_ou_meia`, `test_resposta_de_lance_invalida`. FAIL.
- [x] Em `_temporada`, quando `liga.copa`, posição atual em (atacante, meia), lances < 2 e o sorteio de `CHANCE_FINAL` passa: a copa **não** sai do sorteio normal daquela temporada; vira lance. Com minijogos, a temporada fica pendente na pergunta do lance (siga o padrão de `_pergunta`/`_resposta`); sem minijogos ou resposta 4, sorteia com `chance_penalti`. Gol: título + marca `frio-na-marca-da-cal` + manchete `penalti-gol`; erro: marca `perdeu-o-penalti` + `penalti-erro`. Adversário: rival do clássico (`_campos_classico`) ou outro clube da mesma liga, escolhido sem rng extra fora do lance. PASS.
- [x] Commit `feat: pênalti decisivo na final de copa da carreira`.

### Task 2: Calibragem

**Files:** `motor.py` (`CHANCE_FINAL`); Test `tests/test_carreira_penalti.py`

- [x] `test_taxa_de_copas_sem_minijogos_parecida_com_a_de_hoje`: medir a taxa de copas em 1000 carreiras com o código do `origin/main` (fixar o número no teste com comentário de onde veio) e exigir ±20% com `minijogos=False`. Ajustar `CHANCE_FINAL` até passar; rodar `test_carreira_realismo.py`.
- [x] Commit `feat: calibra a frequência do pênalti decisivo`.

### Task 3: Link e API

**Files:** `codigo.py`, `web/app.py`; Test `tests/test_carreira_codigo.py`, `tests/test_web_carreira.py`

- [x] `test_link_guarda_minijogos_e_codigo_antigo_abre` (fixar um código gerado **antes** da mudança); teste web do payload do `lance` (`tipo`, `info[0].chance`) e da linha do tempo com `lance`. FAIL.
- [x] 1 bit de `minijogos` no formato, compatível com os códigos atuais (use o byte de versão do formato para distinguir). Corpo da API aceita `minijogos: bool = False`. PASS.
- [x] Commit `feat: link e API guardam a escolha de minijogos`.

### Task 4: Tela

**Files:** Create `src/geral/static/geral/penalti.js` (do rascunho; exporta `jogarPenalti(el, {finalizacao, clube, adversario, copa}) -> Promise<"gol"|"defesa"|"fora"|"trave"|"motor">`); Modify `carreira.js`, `carreira.html.j2`, `jogos.css`; Test `tests/test_web_carreira.py`

- [x] `test_formulario_tem_a_chave_de_minijogos` (dois cartões, padrão "com"). FAIL → PASS.
- [x] `carreira.js`: chave do formulário → `estado.minijogos`; pendente `lance` abre o pênalti no lugar dos cartões de opção e responde o índice; botão "Deixar o motor bater" → 4. Linha do tempo e card mostram o lance ("Pênalti na final: gol"). Sem o controle de Finalização do rascunho.
- [x] Subir o app local, jogar no navegador (390 px e 1280 px) uma carreira com e uma sem minijogos, abrir o link; fotos para o dev. Commit `feat: tela do pênalti decisivo e chave de minijogos`; push; PR.
