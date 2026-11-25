# Mano a Mano — Fatia 2 (sala, hub, rotas, SSE, súmula) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O servidor do Mano a Mano: a sala de 2 (ou 1 + bot) com as fases da disputa, o hub em memória com SSE + POST, as rotas e a súmula, usando as regras já no main (`geral/games/mano/`).

**Architecture:** `geral/games/mano/sala.py` = regras da sala, puras, com relógio injetado, devolvendo `list[Evento]` (o mesmo desenho de `geral/games/prancheta/sala.py`). `geral/web/mano.py` = hub copiado do padrão de `geral/web/prancheta.py` (dict de salas, laço `passo()` a cada 0,25 s, uma fila por conexão, `_Fluxo`, filtro do token no log, `criar_mano(db_path, now, limite_salas, sleep, rng) -> Mano` com `.router` e `.rodar()`). Ligação no `app.py` igual à da Prancheta. Sem página ainda (fatia 4); a rota de página só devolve 404 até lá.

**Tech Stack:** FastAPI, SSE (StreamingResponse), Pydantic v2, SQLite, pytest (relógio e `sleep` injetados, como `tests/test_web_prancheta.py`).

**Spec:** `docs/features/mano-a-mano.md` (Regras, Contratos, Critérios).

## Global Constraints

- Usar `resolver`, `bot.chutar/defender/armar`, `Disputa` do main sem mudar suas regras. **Um `random.Random` novo por partida** (revanche inclusive), semeado do `rng` do hub — exigência do `bot.py`.
- No pênalti, o servidor descarta `trajetoria`/`curva` do chute; na falta, `trajetoria` é obrigatória (422 sem ela).
- Prazos: `PRAZO_ESCOLHA = 10 s` (barreira, chute, defesa; estourou → escolha ao acaso, uniforme como na calibragem), `CORRIDA = 1,5 s` (de travar a `chute_em`), `JANELA = 600 ms` a partir de `chute_em`, `FOLGA = 150 ms`, `RESULTADO = 3 s` (replay) antes da próxima cobrança.
- Posição da falta: sorteada por cobrança entre `meia_lua | entrada_esquerda | entrada_direita` com `desvio` uniforme −80..80, revelada aos dois antes da barreira.
- Abandono: `sair` ou 30 s sem conexão de eventos → `Disputa.wo(perdedor)`, súmula gravada com "W.O.". Sala vazia 10 min ou com 3 h → encerrada.
- Limites: criar sala 20/h por rede (`RateLimiter` do app); 1 ação a cada 0,3 s por jogador (429 sem efeito).
- Commits `tipo: descrição` pt-BR, uma linha, sem trailer; gates verdes antes de cada commit.

## Review Focus

- `saida` chegando duas vezes, antes de `chute_em` ou depois da janela + folga: só a primeira dentro de `[chute_em, chute_em + JANELA + FOLGA]` vale; as outras são 204 sem efeito.
- Jogador manda `chute` sendo o goleiro, ou `defesa` sendo o batedor: 409.
- O 2º humano entra numa sala contra o bot, ou numa sala já com 2: 409.
- Reconectar no meio da `escolha` depois de já ter travado: a foto diz que você travou, sem revelar a escolha do outro.
- Revanche pedida por um só: espera o outro (contra o bot, imediata); súmula da 1ª partida fica no seu id.

---

### Task 1: `Sala` — fases, privacidade e disputa

**Files:** Create `src/geral/games/mano/sala.py`; Test `tests/test_mano_sala.py`

**Interfaces:**
- Consumes: `tipos.*`, `regras.resolver`, `bot.*`, `disputa.Disputa`.
- Produces: `Evento(tipo: str, dados: dict, para: int | None = None)`; `ErroSala(status: int, motivo: str)`; `class Sala`: `Sala(id: str, modo: Modo, bot: Nivel | None, agora: datetime, rng: random.Random)`, `entrar(apelido, agora) -> tuple[int, list[Evento]]` (jogador 0 cria, 1 entra; com bot o 1 é o bot), `agir(jogador: int, acao: dict, agora) -> list[Evento]`, `conectou/desconectou(jogador, agora) -> list[Evento]`, `avancar(agora) -> list[Evento]`, `encerrar(agora) -> list[Evento]`, `foto(jogador) -> dict`, `sumula() -> dict | None`, `encerrada: bool`, `criada_em`.
- Fases: `espera` → (`barreira` só na falta, o goleiro arma) → `escolha` (os dois travam) → `corrida` (até `chute_em`) → `voo` (janela da saída) → `resultado` → próxima ou `fim`.
- Eventos: `estado` (foto: `{fase, voce, papel, prazo, agora, placar, serie: [[gol|null…], …], posicao, barreira, travou: {voce: bool, outro: bool}, jogadores}`), `cobranca_inicio {chute_em}`, `cobranca {lance, placar}` (a todos), `fim {sumula}`.

- [ ] **Step 1: Failing tests**
  - `test_escolha_nunca_vaza` — batedor trava; o goleiro recebe só `travou.outro = True`; nenhum evento para ele contém `alvo`/`barra` até `cobranca`.
  - `test_saida_dentro_da_janela_conta` / `test_saida_fora_da_janela_nao_conta` / `test_saida_repetida_vale_a_primeira`.
  - `test_prazo_estourado_escolhe_ao_acaso` — sem `chute` em 10 s, a cobrança acontece com um chute válido.
  - `test_papel_errado_409` e `test_acao_fora_da_fase_409`.
  - `test_falta_tem_posicao_e_barreira_antes_da_escolha` e `test_penalti_descarta_trajetoria`.
  - `test_disputa_acaba_quando_nao_da_mais_para_alcancar` (pela sala) e `test_quem_sai_perde_por_wo`; `test_ausente_30s_perde_por_wo`.
  - `test_contra_o_bot_ele_escolhe_sozinho` — com `bot="dificil"`, só o humano age e a partida chega ao `fim`.
  - `test_revanche_zera_e_grava_sumula_de_cada_partida` — súmulas `"{sala}-1"`, `"{sala}-2"`; revanche só quando os dois pedem (bot pede sempre); novo `Random` por partida (o bot `medio` pode mudar de mania).
- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS. **Step 5: Commit** `feat: sala do mano a mano com fases, prazos, bot e revanche`

### Task 2: Hub, rotas, SSE e súmula

**Files:** Create `src/geral/web/mano.py`; Modify `src/geral/web/app.py` (criar, `include_router`, laço no lifespan atrás de um `settings.MANO_LACO` como `PRANCHETA_LACO`); Test `tests/test_web_mano.py`

**Interfaces:**
- Produces: rotas da página da spec com prefixo `/api/jogos/mano`: `POST /salas {apelido, modo, bot}` → 201 `{id, jogador, token}`; `POST /salas/{id}/entrar {apelido}` → `{jogador, token}` (409 cheia/com bot/encerrada, 422 apelido pelo `filtro` da Prancheta); `POST /salas/{id}/acao` com união discriminada `barreira{n, x} | chute{alvo, barra, trajetoria?, curva?} | defesa{lado} | saida{} | revanche{} | sair{}` (403 token, 409 fase/papel, 429 limite, 204 ok); `GET /salas/{id}/eventos?token=` (SSE; reconectar recebe `estado` de novo). `Mano.viva(id)`, `Mano.sumula(id)` (por id da partida ou o último da sala). Tabela `mano_sumulas(id PK, sala, criada_em, encerrada_em, dados JSON)`.
- `saida` é carimbada com `now()` do hub ao chegar (não com o relógio do cliente).

- [ ] **Step 1: Failing tests** — `test_criar_e_entrar`, `test_sala_cheia_409`, `test_token_de_outra_sala_403`, `test_criar_sala_limitado_por_rede`, `test_limite_de_acoes_429`, `test_eventos_sse_privados` (o goleiro não recebe o `alvo` antes de `cobranca`), `test_reconectar_recebe_a_foto`, `test_fim_grava_sumula`, `test_sala_abandonada_e_encerrada`, `test_partida_inteira_contra_o_bot_pela_api`.
- [ ] **Step 2:** FAIL. **Step 3:** implementar (copiar o padrão do hub da Prancheta; se `_Fluxo`, `_sse` e o filtro do token puderem ser importados de `geral.web.prancheta` sem gambiarra, importar; senão mover para `geral/web/sse.py` e importar nos dois, sem mudar comportamento). **Step 4:** PASS + suíte inteira. **Step 5: Commit** `feat: servidor do mano a mano com salas ao vivo e súmula`

### Task 3: Página da spec e PR

- [ ] Marcar na página da feature os critérios cobertos; `git push -u origin feat/mano-servidor`; `gh pr create` em pt-BR (sem atribuição de IA). Não mergear.
