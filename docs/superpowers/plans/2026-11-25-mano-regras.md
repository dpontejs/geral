# Mano a Mano — Fatia 1 (regras, bot e disputa) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** As regras puras do Mano a Mano: resolver uma cobrança (pênalti ou falta), o bot nos 3 níveis e o placar da disputa, calibrados para ~60% de gols.

**Architecture:** Pacote `geral/games/mano/` só com Python puro e determinístico (todo sorteio vem de um `random.Random` passado de fora), como `geral/games/prancheta/`. Nada de rede, servidor ou banco: a fatia 2 (sala/hub) consome estas funções.

**Tech Stack:** Python 3.12, Pydantic v2, pytest.

**Spec:** `docs/features/mano-a-mano.md` (seção Regras).

## Global Constraints

- Código, nomes e logs em inglês **exceto** os nomes do domínio já em pt-BR na página (`chute`, `defesa`, `barreira`, `lado`…), como no resto de `games/`.
- Coordenadas do gol: `x` 0–1000 da esquerda para a direita **como o batedor vê**; `y` 0–1000 do chão ao travessão. `lado` do goleiro usa o mesmo referencial (`"esquerda"` = `x < 333`); a tela do goleiro espelha os rótulos (fatia 3/4).
- `barra` 0–1000, uma parada; centro ideal 500.
- Toda constante de ajuste fica no topo de `regras.py` em MAIÚSCULAS; só elas mudam para passar a calibragem.
- Commits `tipo: descrição` em pt-BR, uma linha, sem trailer. Antes: `uv run ruff check . && uv run ruff format --check . && uv run pytest -n auto`.

## Review Focus

- Alvo exatamente no poste/travessão (x=0, x=1000, y=1000): deve dar `trave` ou `fora`, nunca gol nem exceção.
- `barra` nos extremos 0 e 1000: desvio máximo, sem estourar o tipo (`onde` pode sair de 0–1000; é `int` livre).
- Falta com barreira encostada na trave (`x` perto de 0 ou 1000): a faixa coberta é cortada em 0–1000, sem erro.
- Bot `dificil` sem histórico (1ª cobrança): escolhe como o `facil`, sem divisão por zero.
- Disputa decidida antes da 5ª: `acabou` vira `True` no lance exato em que um não alcança mais.

---

### Task 1: Tipos e `resolver` do pênalti

**Files:**
- Create: `src/geral/games/mano/__init__.py`, `src/geral/games/mano/tipos.py`, `src/geral/games/mano/regras.py`
- Test: `tests/test_mano_regras.py`

**Interfaces:**
- Produces (`tipos.py`):
  - `Lado = Literal["esquerda", "fica", "direita"]`, `Trajetoria = Literal["rasteira", "por_cima", "pelo_lado"]`, `Resultado = Literal["gol", "defesa", "trave", "fora", "barreira"]`, `Modo = Literal["penaltis", "faltas"]`
  - `class Chute(BaseModel)`: `alvo: tuple[int, int]` (cada um 0–1000, validado), `barra: int` (0–1000), `trajetoria: Trajetoria | None = None`, `curva: float = 0` (−1 a 1)
  - `class Defesa(BaseModel)`: `lado: Lado`, `saida: bool` (o servidor já decidiu se caiu na janela)
  - `class Barreira(BaseModel)`: `n: int` (2–5), `x: int` (0–1000)
  - `class Posicao(BaseModel)`: `nome: Literal["meia_lua", "entrada_esquerda", "entrada_direita"]`, `desvio: int` (soma em `x` da bola, −80 a 80)
  - `class Lance(BaseModel)`: `chute: Chute`, `defesa: Defesa`, `barreira: Barreira | None`, `posicao: Posicao | None`, `onde: tuple[int, int]` (onde a bola foi de fato), `resultado: Resultado`
- Produces (`regras.py`): `resolver(chute: Chute, defesa: Defesa, rng: random.Random, *, barreira: Barreira | None = None, posicao: Posicao | None = None) -> Lance`; `faixa_boa(alvo: tuple[int, int], falta: bool) -> int` (largura da faixa boa da barra)

- [ ] **Step 1: Write the failing tests**

```python
def test_faixa_estreita_perto_da_trave():
    assert faixa_boa((500, 300), falta=False) > faixa_boa((60, 300), falta=False)
    assert faixa_boa((500, 300), falta=False) > faixa_boa((500, 950), falta=False)
    assert faixa_boa((500, 300), falta=True) < faixa_boa((500, 300), falta=False)

def test_barra_na_faixa_vai_onde_mirou():  # within ±RUIDO
    lance = resolver(Chute(alvo=(150, 300), barra=500), Defesa(lado="direita", saida=False), Random(1))
    assert abs(lance.onde[0] - 150) <= RUIDO and lance.resultado == "gol"

def test_barra_fora_da_faixa_desvia():  # away from the goal's centre, proportional to the error
    perto = resolver(Chute(alvo=(150, 300), barra=500 + faixa_boa((150, 300), False) // 2 + 50), ...)
    longe = resolver(Chute(alvo=(150, 300), barra=1000), ...)
    assert longe.onde[0] < perto.onde[0] < 150 + RUIDO
    assert longe.resultado in {"fora", "trave"}

def test_goleiro_no_lado_certo_defende_ate_meia_altura():
    for y in (0, 300, ALTURA_PULO):
        assert resolver(Chute(alvo=(150, y), barra=500), Defesa(lado="esquerda", saida=False), Random(2)).resultado == "defesa"

def test_angulo_so_em_parte():  # P_ANGULO of the time, over 2000 seeds, ±5 pp
    ...  # alvo (120, 900), lado "esquerda": share of "defesa" ≈ P_ANGULO

def test_fica_cobre_o_centro_inteiro():  # alvo (500, 950) with lado "fica" → defesa

def test_saida_no_tempo_alcanca_o_vizinho():
    chute = Chute(alvo=(333 + ALCANCE_SAIDA - 20, 300), barra=500)
    assert resolver(chute, Defesa(lado="esquerda", saida=True), Random(3)).resultado == "defesa"
    assert resolver(chute, Defesa(lado="esquerda", saida=False), Random(3)).resultado == "gol"

def test_alvo_no_poste_e_trave_ou_fora():  # alvo (0, 300), (1000, 500), (500, 1000), 200 seeds: never "gol"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_mano_regras.py -v` — Expected: FAIL (module missing).

- [ ] **Step 3: Implement `tipos.py` and `resolver`/`faixa_boa` for penalties.** Starting constants (tuned only in Task 3):
  `FAIXA_MIN = 60`, `FAIXA_MAX = 320`, `FAIXA_POR_DIST = 1.1` (faixa = clamp(FAIXA_MIN + FAIXA_POR_DIST·d), d = distância do alvo ao poste ou travessão mais próximo), `FATOR_FALTA = 0.8`, `DESVIO_POR_ERRO = 0.7` (o erro fora da faixa empurra `onde` para longe do centro do gol `(500, 0)`), `RUIDO = 20` (uniforme ±), `TRAVE = 25` (|x|≤25, |x−1000|≤25 ou |y−1000|≤25 com o outro eixo dentro → `trave`; além do gol → `fora`), `ALTURA_PULO = 600`, `P_ANGULO = 0.35`, `ALCANCE_SAIDA = 120`. Order: compute `onde` → `fora`/`trave` → covered by the keeper → `defesa` → else `gol`.

- [ ] **Step 4: Run** the tests — Expected: PASS.
- [ ] **Step 5: Commit** `feat: regras do pênalti do mano a mano`

### Task 2: Falta com barreira

**Files:** Modify `src/geral/games/mano/regras.py`; Test `tests/test_mano_regras.py`

**Interfaces:**
- Consumes: Task 1 types.
- Produces: `resolver(..., barreira=Barreira, posicao=Posicao)` handles falta; `cobertura(barreira: Barreira) -> tuple[int, int]` (faixa x coberta, cortada em 0–1000); `ALTURA_BARREIRA = 450`, `MEIA_LARGURA_POR_HOMEM = 55`.

- [ ] **Step 1: Failing tests**

```python
def test_barreira_bloqueia_rasteira():  # alvo x inside cobertura, trajetoria "rasteira" → "barreira"
def test_rasteira_fora_da_barreira_segue():  # alvo x outside cobertura → not "barreira"
def test_pelo_lado_com_pouca_curva_bate_na_barreira():  # |curva| < 0.3 inside cobertura → "barreira"; curva 0.8 → passes
def test_por_cima_fraco_bate_na_barreira():  # barra below the faixa → "barreira"; above it → "fora" when the error is large
def test_cobertura_cortada_no_gol():  # Barreira(n=5, x=20) → (0, 20 + 5*55)
def test_posicao_desvia_a_bola():  # same chute, Posicao desvio +60 → onde[0] 60 larger (± RUIDO)
```

- [ ] **Step 2: Run** — FAIL. **Step 3:** implement (rasteira forces `onde[1] ≤ 150`; `por_cima` needs `onde[1] > ALTURA_BARREIRA` inside the coverage, its error below the faixa pulls y down). **Step 4:** PASS. **Step 5: Commit** `feat: falta com barreira no mano a mano`

### Task 3: Calibragem

**Files:** Test `tests/test_mano_calibragem.py`; Modify constants in `regras.py` only.

- [ ] **Step 1: Failing/real test** `test_calibragem`: 10 000 lances com `Random(semente)` fixo por modo; aleatório = `alvo` uniforme em 0–1000², `barra` uniforme 0–1000, `lado` uniforme, `saida` 50%; na falta também `Barreira(n uniforme 2–5, x uniforme)`, `trajetoria` uniforme, `curva` uniforme −1..1, `Posicao` uniforme com `desvio` uniforme −80..80. Assert `0.55 <= gols/10000 <= 0.65` em cada modo; print the rates.
- [ ] **Step 2:** run; tune constants until PASS; record the final rates in the commit's PR body.
- [ ] **Step 3: Commit** `test: calibragem do mano a mano em 60% de gols`

### Task 4: Bot

**Files:** Create `src/geral/games/mano/bot.py`; Test `tests/test_mano_bot.py`

**Interfaces:**
- Produces: `Nivel = Literal["facil", "medio", "dificil"]` (in `tipos.py`); `chutar(nivel: Nivel, historico: list[Lance], rng, *, barreira: Barreira | None) -> Chute`; `defender(nivel, historico: list[Lance], rng) -> Defesa`; `armar(nivel, rng) -> Barreira`. `historico` = lances anteriores **do adversário humano** na partida, no papel oposto (os chutes dele quando o bot defende; as defesas dele quando o bot bate). `ACERTO_SAIDA = {"facil": 0.3, "medio": 0.5, "dificil": 0.7}`.
- `facil`: tudo uniforme como na calibragem. `medio`: lado/coluna preferida sorteada uma vez do `rng` na primeira chamada da partida (passada pelo chamador via semente da partida), usada 60% das vezes. `dificil`: com ≥ 1 lance no histórico, pula na coluna (terço de `onde`/`alvo`) mais frequente dos últimos 3 chutes em 75%; como batedor mira no terço onde o humano menos pulou, a 150 de distância das bordas, `barra` 500 ± 40. Sem histórico, como `facil`.

- [ ] **Step 1: Failing tests**

```python
def test_bot_dificil_pune_quem_repete():  # human always Chute(alvo=(150, 300), barra=500); 500 matches × 5 kicks, history grows; goals < 40%
def test_bot_facil_nao_le_padrao():  # same scenario vs facil: goals > 50%
def test_saida_do_bot_por_nivel():  # 5000 defenders per level: share of saida within ±3 pp of ACERTO_SAIDA
def test_dificil_sem_historico_nao_quebra():  # defender("dificil", [], Random(0)) returns a Defesa
def test_armar_dentro_dos_limites():  # 2 <= n <= 5, 0 <= x <= 1000
```

- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS. **Step 5: Commit** `feat: bot do mano a mano em três níveis`

### Task 5: Placar da disputa

**Files:** Create `src/geral/games/mano/disputa.py`; Test `tests/test_mano_disputa.py`

**Interfaces:**
- Produces: `class Disputa` (dataclass): `cobrancas: list[tuple[int, bool]]` (jogador 0|1, gol); `batedor() -> int` (quem bate agora: 0 começa, alterna); `registrar(gol: bool) -> None`; `placar() -> tuple[int, int]`; `acabou() -> bool`; `vencedor() -> int | None`; `wo(perdedor: int) -> None` (encerra com o outro vencedor). `SERIE = 5`.

- [ ] **Step 1: Failing tests**

```python
def test_disputa_alternada_e_morte_subita():  # 5×5 tied 4×4 → continues; after a pair where one scores and the other misses → acabou, vencedor
def test_disputa_acaba_quando_nao_da_mais_para_alcancar():  # 3×0 after 3 each → acabou (other can reach at most 2)
def test_morte_subita_so_decide_apos_o_par():  # in alternadas, first kicker scores → not acabou yet
def test_quem_sai_perde_por_wo():  # wo(1) → acabou, vencedor 0, placar kept
def test_registrar_depois_do_fim_da_erro():  # ValueError
```

- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS. **Step 5: Commit** `feat: placar da disputa do mano a mano`

### Task 6: PR

- [ ] Gates green; push `feat/mano-regras`; `gh pr create` in pt-BR (body: calibration rates, constants changed, no AI attribution). Do not merge.
