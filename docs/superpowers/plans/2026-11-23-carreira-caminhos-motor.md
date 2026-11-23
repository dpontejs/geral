# Carreira: caminhos (motor) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PR 1 de `docs/features/carreira-caminhos.md`: marcas, decisões com risco, arcos garantidos, mudança de posição, manchetes sem repetir, tela; com conteúdo de exemplo mínimo. O grosso do conteúdo e `test_variedade_de_decisoes` (≥ 60% fora do mercado, que depende do volume de decisões) são o PR 2.

**Architecture:** Marcas são ids gravados em `_Simulacao.historico` (o que `Condicao.requer/exclui` já lê). Decisões e dia a dia passam a compartilhar um único aplicador de opção com risco. Arcos: uma marca com decisão `continua` pendente força a pergunta da temporada seguinte.

**Tech Stack:** Python 3.12, pydantic, TOML, pytest; JS puro em `carreira.js`.

**Spec:** `docs/features/carreira-caminhos.md`

## Global Constraints

- Código, nomes e logs em inglês; textos do jogo em pt-BR. Commits em pt-BR, `tipo: descrição`, sem escopo, uma linha, sem trailer.
- Antes de cada commit: `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
- Nunca reusar id de escolha/rotina/marca (links guardam a ordem das respostas).
- `test_carreira_realismo.py` continua passando sem enfraquecer: ajuste parâmetros, não testes.
- Mesma `Entrada` → mesma carreira; uma resposta nova não muda temporadas anteriores.

## Review Focus

- Link antigo (`/jogos/carreira/c/{codigo}`) de antes do deploy: abre e mostra o card (`codigo.py` já trata draft/dados mudados) — teste na Task 4.
- Resposta para uma decisão com risco que não existe (índice fora): `JogadaInvalida`, como hoje — teste na Task 2.
- Arco cuja próxima decisão nunca casa (jogador aposentou ou idade passou): a carreira termina normalmente — teste na Task 3.
- Marca gravada duas vezes (mesma marca por caminhos diferentes): efeito aplicado uma vez só — teste na Task 2.
- Opção arriscada mostra "arriscada" e a chance real (com bônus), igual ao que o motor sorteia — teste na Task 2 (`Escolha.info`).

---

### Task 1: Dados — marcas, opções com risco, `continua`, `Efeito.posicao`, validação

**Files:** Create `src/geral/games/carreira/marcas.toml`; Modify `src/geral/games/carreira/dados.py`; Test `tests/test_carreira_dados.py`

**Interfaces — Produces:**
- `@dataclass(frozen=True) class Marca: id: str; nome: str; texto: str; efeito: Efeito = Efeito()`; `Dados.marcas: dict[str, Marca]`.
- `Opcao` ganha `chance: int = 100`, `bonus: str = ""`, `sucesso: Efeito = Efeito()`, `fracasso: Efeito = Efeito()`, `marca: str = ""`, `marca_fracasso: str = ""` (assim `chance_de(opcao, notas)` do motor serve aos dois tipos). `OpcaoRotina` ganha `marca`, `marca_fracasso`.
- `Decisao.continua: bool = False`. `Efeito.posicao: str = ""` (valor em `regras.POSICOES`).
- Ids válidos para `requer`/`exclui`/`marca`: ids de eventos, decisões e marcas.

- [x] Testes: `test_carrega_marcas_e_opcao_com_risco` (TOML de `tmp_path` com marca e opção `chance = 20, marca = "x"` → campos carregados); `test_dados_rejeitam_marca_inexistente` (`requer = ["nao-existe"]` → `ValueError` citando o id); `test_dados_rejeitam_posicao_invalida`. Rodar: FAIL.
- [x] Implementar em `dados.py` (seguir `_efeito`/`_condicao`); validação no fim de `carregar`. Atenção: hoje `requer` só cita eventos — confirmar que os dados reais passam. Rodar: PASS.
- [x] Commit `feat: marcas e opções com risco nos dados da carreira`.

### Task 2: Motor — aplicar opção com risco e marca (decisões e dia a dia)

**Files:** Modify `src/geral/games/carreira/motor.py`; Test `tests/test_carreira_caminhos.py` (novo)

**Interfaces — Consumes:** Task 1. **Produces:** `_Simulacao._aplicar(opcao: Opcao | OpcaoRotina) -> tuple[bool, Efeito]` (sorteia `chance_de`, aplica atributos/nota/teto como hoje em `_dia_a_dia`, grava marca); `_Simulacao._marcar(marca_id: str) -> None` (no-op se já está em `historico`; aplica `Marca.efeito`; guarda o nome em `self.marcas_novas`). `Temporada.marcas: list[str] = []`. `InfoOpcao.arriscada: bool = False` (chance ≤ 25).

- [x] Testes (usar `Dados` montado em `tmp_path` ou monkeypatch de `dados.decisoes`, como `test_carreira_motor.py` faz): `test_marca_gravada_conforme_o_resultado`; `test_marca_repetida_aplica_efeito_uma_vez`; `test_decisao_com_risco_mostra_chance_e_arriscada` (`Escolha.info[i].chance == chance_de(...)`, `arriscada` com chance 20); `test_resposta_fora_das_opcoes_e_invalida`; `test_decisao_sem_clube_nao_segura_o_mercado` (após decisão "ficar", `_mercado` roda no mesmo inverno). FAIL.
- [x] `_dia_a_dia` passa a usar `_aplicar`; `_pergunta` aplica `_aplicar` na opção escolhida e devolve `decidiu=True` só se mudou de clube ou aposentou; `_escolha` preenche `info` quando alguma opção tem chance < 100 ou efeito. Marcas novas vão para a `Temporada` da temporada seguinte (a linha do tempo conta "ganhou a braçadeira" ao lado do que aconteceu). PASS.
- [x] Commit `feat: decisões com risco e marcas no motor da carreira`.

### Task 3: Arcos garantidos e teto por modo

**Files:** Modify `motor.py`; Test `tests/test_carreira_caminhos.py`

**Interfaces — Produces:** `MAX_ESCOLHAS = {"rapida": 5, "completa": 8}`; `ARCO_TENTATIVAS = 2`; `_Simulacao.arco: tuple[str, int] | None` (marca que abriu o arco, tentativas restantes).

- [ ] Testes: `test_arco_continua_na_temporada_seguinte` (Rápida e Completa; com `perguntadas` já no teto, a próxima `Escolha.id` é a decisão `continua` que requer a marca); `test_arco_segue_a_ordem` (o passo 2 nunca aparece sem a marca); `test_arco_que_nao_casa_morre` (condição impossível → após 2 temporadas, a carreira termina normal); `test_teto_por_modo` (Rápida nunca passa de 5 perguntas sorteadas; Completa de 8). FAIL.
- [ ] Em `_pergunta`: se há arco pendente e alguma decisão `continua` não perguntada casa e requer a marca, ela é escolhida sem `CHANCE_ESCOLHA` nem teto; passos de arco não entram na contagem do teto (guardar à parte). Decisões `continua` nunca saem no sorteio comum. PASS.
- [ ] Commit `feat: arcos garantidos e mais decisões por carreira`.

### Task 4: Posição nova, marcas no final, finais por marca, manchetes sem repetir

**Files:** Modify `motor.py`, `final.py`, `codigo.py` (só `resumir`); Test `tests/test_carreira_caminhos.py`, `tests/test_carreira_codigo.py`

**Interfaces — Produces:** `Final.posicao: str`, `Final.marcas: list[str]` (nomes); `finais.toml` aceita `requer = ["marca"]` (lido de `numeros(...)` + marcas passadas a `rotular(dados, temporadas, marcas)`); `resumir` usa `final.posicao`.

- [ ] Testes: `test_virou_meia_muda_posicao_e_nota` (efeito `posicao = "meia"` → `self.posicao`, `geral(...)` recalculado, `Final.posicao == "meia"`, `Resumo.posicao == "meia"`); `test_final_por_marca` (entrada de `finais.toml` com `requer` vence quando a marca existe); `test_manchete_nao_repete_na_carreira` (200 carreiras: nenhum texto repetido quando o evento tinha outro não usado); `test_link_antigo_ainda_abre` (código fixado em `test_carreira_codigo.py` continua decodificando e a rota responde 200). FAIL.
- [ ] Implementar: `posicao` em `_aplicar`/`_marcar`; `self.manchetes_usadas: set[str]` e escolha entre as não usadas do evento (fallback: todas). PASS.
- [ ] Commit `feat: mudança de posição, marcas no card e manchetes sem repetir`.

### Task 5: Tela, conteúdo de exemplo e realismo

**Files:** Modify `src/geral/static/geral/carreira.js` (+ CSS do template se precisar), `escolhas.toml`, `marcas.toml`, `scripts/carreira_amostra.py`; Test `tests/test_carreira_caminhos.py`, `tests/test_web_carreira.py`

- [ ] Conteúdo: 6 marcas (capitao, polemico, brigou-com-tecnico, virou-meia, idolo-de-um-clube, baladeiro); 2 arcos completos (técnico: briga → banco → sair/desculpas; braçadeira: aceitar → crise no vestiário → liderar/se omitir); 4 decisões fora do mercado; 2 opções arriscadas (chance 15–25). `carreira_amostra.py` ganha `--modo` e respostas aleatórias.
- [ ] Testes: `test_mesmo_draft_caminhos_diferentes`; `test_arriscar_tudo_nao_quebra_o_realismo` (respondendo sempre a opção de menor chance em 500 carreiras: lendas ≤ 5%, não decolam ≥ 15%); `test_replay_estavel`; teste web: payload da `Escolha` com `info.arriscada` e `Final.marcas`. FAIL→PASS.
- [ ] JS: selo "arriscada" na opção (`info.arriscada`); marcas da temporada na linha do tempo; marcas na tela final e no card. Conferir no navegador (`/jogos/carreira`) uma Rápida e uma Completa.
- [ ] Commit `feat: marcas e decisões arriscadas na tela da carreira`; push; PR contra `main` (descrição em pt-BR, sem atribuição a IA), marcar a feature como "em andamento (PR 1)".
