# 7a0 do clube — PR 2: motor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** motor puro e determinístico. Sorteia as décadas, valida a escalação, joga partida a partida com disputa de pênaltis e monta a campanha com marcas.

**Architecture:** `setea0/motor.py` sem estado. Toda função recebe `dados: Dados` (os testes usam `tests/setea0_fake.py`) e reprocessa a partir da semente, como `carreira/motor.py`.

**Tech Stack:** Python 3.12, `random.Random` com semente em string, Pydantic, pytest + xdist.

**Spec:** `docs/features/setea0.md`. **Depende de:** PR 0. Roda em paralelo com o PR 1 e não lê o `setea0.json` real.

## Global Constraints

- Como no PR 0. Testes que simulam muitas campanhas fazem isso **numa passada só** e sem pedir pênalti ao torcedor (`"motor"` em tudo). A suíte inteira continua perto de 1 minuto.
- Gol do pênalti pelo motor usa a mesma fórmula da Carreira: `p = clamp(0.45 + (forca - 60) / 100, 0.35, 0.85)`.

## Review Focus

- O torcedor escolhe o mesmo jogador em duas rodadas (ele aparece em duas décadas) → `JogadaInvalida`. Teste em Task 1.
- Chamada de `jogo(n)` depois da eliminação, ou com `n` maior que 7 → `JogadaInvalida`. Teste em Task 2.
- Disputa empatada depois das 5 cobranças → alternadas até decidir. Nunca há loop infinito: com 20 cobranças por lado sem decisão, o motor decide. Teste em Task 2.
- Escalação com menos de 11 jogadores ou duas pessoas na mesma vaga → `JogadaInvalida`. Teste em Task 1.

---

### Task 1: oferta e validação

**Files:** Create `src/geral/games/setea0/motor.py`. Test `tests/test_setea0_motor.py`.

**Interfaces — Consumes:** `modelos.*`, `dados.chaves()`, `tests/setea0_fake.dados_de_teste()`.

**Interfaces — Produces:**
- `MIN_DECADA = 8`, `TAMANHO_OFERTA = 10`.
- `decadas(dados, edicao) -> list[int]`: as décadas com pelo menos `MIN_DECADA` jogadores, em ordem.
- `oferta(dados, edicao, semente: str, rodada: int, troca: int) -> Rodada`:
  - `rng = Random(f"{semente}:{rodada}:{troca}")`;
  - a década sai uniforme de `decadas(...)`;
  - entram até 10 jogadores da década, com 1 de cada linha (GOL, defesa = ZAG ou LAT, MEI, ATA) quando houver;
  - a lista vem ordenada por força decrescente.
- `escalar(dados, edicao, semente, modo, esquema, escolhas: list[Escolha]) -> list[Escalado]`. Levanta `JogadaInvalida` quando:
  - não são 11 escolhas, as rodadas não vão de 0 a 10, ou há vaga repetida ou fora do esquema;
  - o jogador não está na `oferta` da sua `(rodada, troca)` ou se repete;
  - `troca` não é crescente ou passa de `MODOS[modo]`;
  - o esquema ou o modo não existem.

- [ ] **Step 1: Testes que falham:**
  - `test_oferta_so_tem_jogadores_do_clube_na_decada`;
  - `test_decadas_ralas_nao_saem` (1940 com 3 nunca sai em 500 sementes);
  - `test_mesma_semente_mesma_oferta` e `test_troca_muda_a_decada_ou_os_nomes`;
  - `test_escalacao_trapaceada_da_jogada_invalida` (um caso por regra acima, parametrizado).
- [ ] **Step 2–4:** rodar, ver falhar, implementar, rodar e ver passar.
- [ ] **Step 5:** commit `feat: oferta de décadas e escalação do 7a0`.

### Task 2: partida, disputa e campanha

**Files:** Modify `motor.py`. Test `tests/test_setea0_motor.py`, `tests/test_setea0_calibragem.py`.

**Interfaces — Produces:**
- `encaixe(jogador: Jogador, vaga: Posicao) -> float`:
  - 1.0 na posição do jogador;
  - 0.85 nas vizinhas (LAT↔ZAG, LAT↔MEI, MEI↔ATA);
  - 0.3 se um lado da troca é GOL;
  - 0.6 nos outros casos.
- `forca_do_time(escalados, esquema) -> float`: a média de `forca × encaixe`.
- `adversario(dados, slug) -> list[Jogador]`: os 11 mais fortes no 4-4-2, preenchendo por encaixe se faltar alguma posição.
- `FATORES = (0.80, 0.85, 0.90, 0.95, 1.00, 1.05)` para os jogos 1–6. Final: `FATORES[-1] + BONUS_CLASSICO` (`BONUS_CLASSICO = 0.03`).
- Gols: Poisson com `λ = 1.35 × (nossa / deles) ** K` para cada lado (`K` calibrado; ponto de partida 3).
  - O autor sai com peso ATA 5, MEI 3, LAT 1, ZAG 1, GOL 0, vezes a força.
  - Os minutos são distintos, entre 1 e 90, ordenados.
  - O `rng` de cada jogo é `Random(f"{semente}:jogo:{n}")`.
- Disputa:
  - 5 cobranças alternadas, nós primeiro; depois alternadas até decidir; no máximo 20 por lado, e aí vence quem tem o goleiro mais forte.
  - Nossos cobradores são os 5 mais fortes entre ATA e MEI, depois os outros, em ciclo.
  - Cobrança nossa: o resultado vem de `cobrancas`, e `"motor"` usa a fórmula da Carreira.
  - Cobrança deles: `p = clamp(0.75 - (forca_do_nosso_goleiro - 60) / 200, 0.55, 0.9)`.
- `jogo(dados, edicao, semente, modo, esquema, escolhas, cobrancas: list[list[Cobranca]], n: int) -> Partida | PedidoDePenalti`:
  - reprocessa os jogos de 1 a n;
  - cada disputa consome `cobrancas[i]`, e quando a lista acaba sem decisão devolve `PedidoDePenalti`;
  - `n > 7`, ou `n` depois da eliminação, levanta `JogadaInvalida`.
- `campanha(dados, edicao, semente, modo, esquema, escolhas, cobrancas) -> Campanha`: joga até o 7º jogo ou até a eliminação, com marcas e `versao=dados.versao`. Se alguma disputa ficar pendente, levanta `JogadaInvalida`.
- `campanha_motor(dados, edicao, semente, modo, esquema, escolhas) -> Campanha`: o motor bate todas as cobranças. Os testes de massa usam esta função, numa passada.

- [ ] **Step 1: Testes que falham:**
  - `test_mesma_entrada_mesma_campanha`;
  - `test_fora_de_posicao_perde_forca` (`encaixe` com a tabela acima);
  - `test_final_e_o_classico_e_ao_menos_tao_forte_quanto_o_6o` e `test_jogos_1_a_6_em_ordem_crescente` (força efetiva do adversário);
  - `test_empate_pede_cobranca_do_torcedor` (acha uma semente com empate; `jogo` devolve `PedidoDePenalti` até ter cobranças suficientes, e o adversário cobra sozinho);
  - `test_motor_bate_os_penaltis` (`"motor"` é determinístico; `campanha_motor` é igual a `campanha` com `"motor"` em tudo);
  - `test_disputa_termina` (cobranças sempre `"fora"` e goleiros iguais → a disputa decide em até 20);
  - `test_jogo_depois_da_eliminacao_e_invalido`.
- [ ] **Step 2–4:** rodar, ver falhar, implementar, rodar e ver passar.
- [ ] **Step 5:** `test_calibragem` em `tests/test_setea0_calibragem.py`, numa passada com 1000 sementes:
  - time guloso (em cada rodada, o mais forte que encaixa numa vaga livre) fecha 7 vitórias em 10–30%;
  - time aleatório fecha em menos de 3%;
  - o ABC dos dados de teste e um "flamengo" sintético (o mesmo gerador com outra semente e forças 20% maiores) ficam a ±50% um do outro, graças à força relativa.
  - Ajuste `K`, `FATORES` e λ até passar, e registre os valores finais na descrição do PR.
- [ ] **Step 6:** commit `feat: partidas, pênaltis e campanha do 7a0`.

### Task 3: marcas

**Files:** Create `src/geral/games/setea0/marcas.toml`. Modify `motor.py`. Test `tests/test_setea0_motor.py`.

**Interfaces:**
- `marcas.toml`: `[<id>] nome, texto` (pt-BR, uma linha), para estas 8 marcas:
  - `sete-a-zero`: um jogo vencido por 7 a 0 ou mais, com 0 gol sofrido;
  - `campeao`: 7 vitórias;
  - `artilheiro`: um jogador com 7 ou mais gols na campanha;
  - `nos-penaltis`: final decidida nos pênaltis;
  - `virada-na-final`: esteve atrás no placar da final e venceu;
  - `paredao`: campeão com no máximo 2 gols sofridos;
  - `caiu-na-final`: perdeu o 7º jogo;
  - `estreia-amarga`: perdeu o 1º jogo.
- `marcas(campanha_parcial) -> list[str]`, na ordem do toml.

- [ ] **Step 1: Testes que falham:**
  - `test_placar_7_a_0_vira_marca_rara` (em 1000 campanhas gulosas, aparece em ≥ 1 e em ≤ 5%);
  - `test_cada_marca_tem_texto`;
  - `test_marcas_por_caso` (partidas montadas à mão para cada regra).
- [ ] **Step 2–4:** rodar, ver falhar, implementar, rodar e ver passar.
- [ ] **Step 5:** portões completos. Commit `feat: marcas da campanha do 7a0`. PR "7a0 do clube: motor".
