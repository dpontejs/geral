# Prancheta — servidor (fatia D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** colocar a `Sala` (já no main) no ar: hub em memória, rotas da API, SSE, limites e súmula no SQLite.

**Architecture:** `web/prancheta.py` guarda as salas num dicionário, serializa o acesso com um `asyncio.Lock` por sala, entrega os `Evento` da `Sala` às filas (`asyncio.Queue`) das conexões SSE conforme `para`/`exceto`, e roda um laço (`rodar()`) que chama `avancar` a cada 0,5 s. A súmula vai para `prancheta_sumulas` quando sai o evento `fim`.

**Tech Stack:** FastAPI, Pydantic (união discriminada), sqlite3, asyncio, pytest + httpx `ASGITransport`.

**Spec:** `docs/features/prancheta.md` (Contratos › Rotas, Eventos, Hub, Banco, Limites). Regras: `src/geral/games/prancheta/sala.py`; banco: `palavras.carregar()`.

## Global Constraints

- Um processo só; nada de estado fora do hub e do SQLite. Não tocar no `store.py`.
- No `app.py`, só: criar o objeto (`criar_prancheta(...)`, passando `RateLimiter(20, timedelta(hours=1))` criado lá, o caminho do SQLite, `now`), `app.include_router(prancheta.router)` e iniciar/cancelar `prancheta.rodar()` no `lifespan` (só se não for teste: siga o padrão do `CENTRAL_REFRESH`, por exemplo `settings.PRANCHETA_LACO = True` por padrão e `False` nos testes, ou o teste injeta `sleep`).
- SSE: `event: <tipo>` + `data: <json>`; `: ping` a cada 15 s; resposta com `Cache-Control: no-cache` e `X-Accel-Buffering: no` (como o duelo da velha).
- Commit: `tipo: descrição` em pt-BR, uma linha, sem escopo e sem trailer. Suíte ~1 min: nenhum teste espera relógio real; use `now` e `sleep` injetados.

## Review Focus

- Duas abas do mesmo jogador: `conectou`/`desconectou` por conexão, presença só cai quando a última fecha — `test_duas_abas_mesmo_jogador`.
- Cliente que some sem fechar o SSE: a fila não cresce sem limite (fila com `maxsize=500`; cheia → derruba a conexão, o navegador reconecta e recebe a foto) — `test_fila_cheia_derruba_a_conexao`.
- Ação chegando enquanto o laço avança a mesma sala (lock por sala) — `test_acoes_concorrentes_nao_quebram_seq`.
- Súmula gravada duas vezes (fim + purga) — `INSERT OR IGNORE`; `test_sumula_gravada_uma_vez`.
- `id` de sala colidindo — sorteia de novo até não existir nem na memória nem na tabela.

---

### Task 1: votos de cartão no `estado`

A tela mostra "1 de 3 cartões" e a `Sala` não expõe votos. **Files:** Modify `src/geral/games/prancheta/sala.py`; Test `tests/test_prancheta_sala.py`.

- [ ] Teste `test_estado_traz_cartoes_por_jogador`: depois de um voto contra o jogador 3, toda `foto` tem `jogadores[i]["cartoes"]` (3 → 1, outros → 0) e o voto emite `estado` para todos. `jogadores[i]["cartoes_para_sair"]` = maioria estrita dos presentes sem o alvo. Ver falhar, implementar, verde, commit `feat: votos de cartão vermelho no estado da prancheta`.

### Task 2: hub, rotas e SSE

**Files:** Create `src/geral/web/prancheta.py`; Modify `src/geral/web/app.py` (só as ligações acima); Test `tests/test_web_prancheta.py`.

**Interfaces — Produces** (a fatia E usa):

```python
def criar_prancheta(db_path: str | Path, now: Callable[[], datetime], limite_salas: RateLimiter,
                    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                    banco: Banco | None = None, rng: random.Random | None = None) -> Prancheta

class Prancheta:
    router: APIRouter                       # só /api/jogos/prancheta/...
    async def rodar(self) -> None           # laço do lifespan
    def viva(self, sala_id: str) -> bool
    def sumula(self, sala_id: str) -> dict | None   # da tabela
```

Rotas (spec): `POST /salas {apelido, rodadas}` → 201 `{id, jogador, token}` (rodadas 1–3, 422 fora; 429 pelo `limite_salas` por `network(ip)` de `team_requests`); `POST /salas/{id}/entrar {apelido}` → `{jogador, token}`; `POST /salas/{id}/acao` com corpo Pydantic `Acao = Annotated[Comecar | Escolher | Traco | Desfazer | Limpar | Chute | Cartao | Tirar | Sair, Field(discriminator="tipo")]`, cada um com `token`; `ErroSala.status` vira o HTTP (`{"erro": motivo}`), 204 se aceita; sala inexistente → 404 em todas. `GET /salas/{id}/eventos?token=` → 403 token ruim; na conexão, `conectou` + 1º evento = `estado` da `foto`; ao fechar, `desconectou`.

- [ ] **Step 1:** testes de rota (cliente `httpx.AsyncClient(transport=ASGITransport(app))`, `now` falso): `test_criar_e_entrar`, `test_rodadas_fora_422`, `test_criar_sala_limitado_por_rede`, `test_sala_inexistente_404`, `test_acao_fora_da_vez_409`, `test_token_de_outra_sala_403`, `test_expulso_nao_age`, `test_limites_de_chute_e_traco_429`, `test_sse_comeca_com_estado`, `test_palavra_nunca_vaza` (dois clientes SSE: o que chuta nunca recebe a palavra antes do `intervalo`), `test_traco_chega_aos_outros_e_nao_volta`, `test_reconectar_recebe_tracos_do_desenho_atual`, `test_duas_abas_mesmo_jogador`, `test_fila_cheia_derruba_a_conexao`, `test_acoes_concorrentes_nao_quebram_seq`. Ver falhar.
- [ ] **Step 2:** implementar; verde. Commit `feat: servidor da prancheta com salas em memória e eventos ao vivo`.

### Task 3: laço, súmula e purga

**Files:** Modify `src/geral/web/prancheta.py`; Test `tests/test_web_prancheta.py`.

Tabela `prancheta_sumulas(id TEXT PRIMARY KEY, criada_em TEXT, encerrada_em TEXT, dados TEXT)` (`CREATE TABLE IF NOT EXISTS` no construtor, como `carreira_placar.py`). `rodar()`: a cada 0,5 s, `avancar(now())` em cada sala, entrega eventos; ao ver `fim`, grava a súmula; sala sem conexão há 10 min ou com 3 h → `fim` forçado (se em jogo) e sai da memória.

- [ ] **Step 1:** testes (chamando um passo do laço, `passo()`, em vez de esperar): `test_fim_grava_sumula`, `test_sumula_gravada_uma_vez`, `test_sala_abandonada_sai_da_memoria`, `test_sala_de_tres_horas_encerra`, `test_viva_e_sumula` (viva → `True`; depois do fim → `False` e `sumula(id)` com os jogadores). Ver falhar.
- [ ] **Step 2:** implementar; verde; `uv run ruff check . && uv run ruff format --check . && uv run pytest`. Commit `feat: súmula e limpeza das salas da prancheta`.
- [ ] **Step 3:** conferir à mão: `uv run uvicorn geral.web.app:create_app --factory`, criar sala e entrar com `curl`, abrir `curl -N .../eventos?token=` e ver `estado` chegar. PR com a descrição em pt-BR.
