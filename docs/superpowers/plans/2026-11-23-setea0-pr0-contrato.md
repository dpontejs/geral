# 7a0 do clube — PR 0: contrato

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fixar os tipos, as chaves de adversários e dados de teste, para os PRs de dados (1) e motor (2) andarem em paralelo.

**Architecture:** pacote novo `geral.games.setea0`, puro (sem rede, sem web). Modelos Pydantic, `chaves.toml` escrito à mão e um gerador determinístico de dados de teste em `tests/`.

**Tech Stack:** Python 3.12, Pydantic, tomllib, pytest.

**Spec:** `docs/features/setea0.md`

## Global Constraints

- Código, nomes e logs em inglês, exceto termos de domínio já usados no pacote da Carreira (`oferta`, `jogo`, `campanha`, `forca`); textos para o torcedor em pt-BR.
- Commits: `tipo: descrição` em pt-BR, uma linha, sem escopo e sem trailer de coautoria.
- Antes de commitar: `uv run ruff check . && uv run ruff format --check . && uv run pytest`.

## Review Focus

- Edição sem 7a0 (`csa` sem entrada em `chaves.toml`, `geral`): `chaves()` não tem a chave, e quem consome devolve 404. Teste em Task 2.
- Adversário citado em `chaves.toml` sem `[clube.*]`: o carregamento falha cedo. Teste em Task 2.

---

### Task 1: modelos e esquemas

**Files:**
- Create: `src/geral/games/setea0/__init__.py` (docstring de uma linha), `src/geral/games/setea0/modelos.py`
- Test: `tests/test_setea0_modelos.py`

**Interfaces — Produces** (todos em `modelos.py`):
- `type Posicao = Literal["GOL", "ZAG", "LAT", "MEI", "ATA"]`
- `ESQUEMAS: dict[str, tuple[Posicao, ...]]`: `"4-3-3"`, `"4-4-2"`, `"4-2-3-1"` (MEI×5, ATA×1), `"3-5-2"` (sem LAT: ZAG×3, MEI×5), `"5-3-2"` (ZAG×3, LAT×2). Ordem das vagas: GOL, LAT, ZAG, MEI, ATA.
- `MODOS: dict[str, int] = {"classico": 3, "almanaque": 1}` (trocas de década).
- `Jogador(BaseModel)`: `id: str`, `nome: str`, `posicoes: list[Posicao]` (≥ 1), `passagens: list[tuple[int, int]]` (anos de início e fim no clube; vazia nos adversários da base da velha), `forca: int` (1–99, `Field(ge=1, le=99)`).
  - Método `decadas() -> set[int]`: as décadas (1970, 1980…) que as passagens tocam.
- `Clube(BaseModel)`: `nome: str`, `jogadores: list[Jogador]`.
- `Dados(BaseModel)`: `versao: str`, `clubes: dict[str, Clube]` (chave = slug, por exemplo `"abc"` ou `"america-rn"`).
- `Rodada(BaseModel)`: `rodada: int` (0–10), `troca: int` (trocas já usadas), `decada: int`, `jogadores: list[Jogador]`, `trocas_restantes: int`.
- `Escolha(BaseModel)`: `rodada: int`, `troca: int`, `jogador: str` (id), `vaga: int` (índice em `ESQUEMAS[esquema]`).
- `Escalado(BaseModel)`: `jogador: Jogador`, `decada: int`, `vaga: int`.
- `Gol(BaseModel)`: `minuto: int`, `autor: str`, `nosso: bool`.
- `Cobranca(BaseModel)`: `resultado: Literal["gol", "defesa", "fora", "trave", "motor"]`.
- `Disputa(BaseModel)`: `nossas: list[bool]`, `deles: list[bool]` (True = gol).
- `Partida(BaseModel)`: `n: int` (1–7), `adversario: str` (slug), `gols: list[Gol]`, `nosso: int`, `deles: int`, `disputa: Disputa | None`, `venceu: bool`.
- `PedidoDePenalti(BaseModel)`: `n: int`, `adversario: str`, `nosso: int`, `deles: int`, `disputa: Disputa`, `cobrador: str`, `chance: int` (força do cobrador, dificuldade do minijogo).
- `Campanha(BaseModel)`: `edicao`, `modo`, `esquema`, `escalacao: list[Escalado]`, `partidas: list[Partida]`, `campeao: bool`, `marcas: list[str]`, `versao: str`.
- `class JogadaInvalida(ValueError)`.

- [ ] **Step 1: Write the failing tests** `test_esquemas_tem_11_vagas_e_1_goleiro` (para todo esquema: `len == 11`, `count("GOL") == 1`, e a ordem das vagas é não decrescente em `["GOL", "LAT", "ZAG", "MEI", "ATA"].index`) e `test_decadas_das_passagens` (`passagens=[(1968, 1976), (1981, 1981)]` → `{1960, 1970, 1980}`; vazia → `set()`).
- [ ] **Step 2: Run** `uv run pytest tests/test_setea0_modelos.py -n0`. Expected: FAIL (`ModuleNotFoundError`).
- [ ] **Step 3: Implement** `modelos.py` como acima.
- [ ] **Step 4: Run** de novo. Expected: PASS.
- [ ] **Step 5: Commit** `feat: modelos e esquemas do 7a0 do clube`

### Task 2: chaves, carregamento e dados de teste

**Files:**
- Create: `src/geral/games/setea0/chaves.toml`, `src/geral/games/setea0/dados.py`, `tests/setea0_fake.py`
- Test: `tests/test_setea0_modelos.py`

**Interfaces — Produces:**
- `chaves.toml`:
  - `[edicao.<slug>]` com `nome`, `adversarios` (6 slugs, do mais fraco ao mais forte), `final` (slug) e `publicado = false`.
  - `[clube.<slug>]` com `nome`, `origem` (`"velha"` com `wikidata`, ou `"ptwiki"` com `categoria`).
  - Para toda edição, existe `[clube.<edição>]` com origem `"ptwiki"`.
- Conteúdo de `chaves.toml` (o dev pode reordenar no PR):

  | Edição | Adversários (do mais fraco ao mais forte) | Final |
  |---|---|---|
  | abc | ceara, fortaleza, santa-cruz, vitoria, sport, bahia | america-rn |
  | csa | ceara, fortaleza, santa-cruz, vitoria, sport, bahia | crb |
  | nautico | abc, ceara, fortaleza, santa-cruz, vitoria, bahia | sport |
  | flamengo | atletico-mg, gremio, cruzeiro, internacional, sao-paulo, palmeiras | vasco |
  | vasco | atletico-mg, gremio, cruzeiro, internacional, sao-paulo, palmeiras | flamengo |
  | palmeiras | atletico-mg, gremio, cruzeiro, internacional, sao-paulo, flamengo | corinthians |

  - Clubes com origem velha e seus ids: Ceará Q1052219, Fortaleza Q188841, Santa Cruz Q508440, Vitória Q274465, Sport Q219098, Bahia Q198032, Atlético-MG Q270995, Grêmio Q221695, Cruzeiro Q188277, Internacional Q80845, São Paulo Q38568, Corinthians Q35933.
  - Clubes com origem ptwiki, categoria "Futebolistas do/da …": ABC Futebol Clube, Clube Náutico Capibaribe, Centro Sportivo Alagoano, Clube de Regatas do Flamengo, Club de Regatas Vasco da Gama, Sociedade Esportiva Palmeiras, América Futebol Clube (Rio Grande do Norte), Clube de Regatas Brasil.
- `dados.py`:
  - `DADOS = Path(__file__).parent / "setea0.json"`.
  - `chaves() -> dict` (lê o toml uma vez e valida que todo slug citado tem `[clube.*]`; senão, `ValueError`).
  - `carregar(path: Path = DADOS) -> Dados` (com cache).
- `tests/setea0_fake.py`: `dados_de_teste() -> Dados` (determinístico, `random.Random(7)`):
  - `abc`: 60 jogadores nas décadas de 1970, 1980, 2000 e 2010 (≥ 12 por década, todas as posições presentes) e 3 jogadores em 1940 (década rala).
  - Cada adversário de `chaves()["edicao"]["abc"]` e `america-rn`: 18 jogadores sem passagens, forças de 40 a 95.

- [ ] **Step 1: Write the failing tests:**
  - `test_toda_edicao_tem_6_adversarios_e_final` (para as 6 edições);
  - `test_slug_sem_clube_falha` (um toml temporário via `monkeypatch` do caminho → `ValueError`);
  - `test_geral_nao_tem_7a0` (`"geral" not in chaves()["edicao"]`);
  - `test_dados_de_teste_validam` (`Dados.model_validate(dados_de_teste().model_dump())`, e `abc` tem década de 1940 com 3 jogadores).
- [ ] **Step 2: Run** e ver falhar. **Step 3: Implement.** **Step 4: Run** `uv run pytest -n0 tests/test_setea0_modelos.py`, PASS.
- [ ] **Step 5: Portões completos** (comando das Global Constraints), depois commit `feat: chaves de adversários e dados de teste do 7a0`.
- [ ] **Step 6:** push e PR "7a0 do clube: contrato", com a página da feature e os três planos.
