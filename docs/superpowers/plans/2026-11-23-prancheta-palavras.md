# Prancheta — banco de palavras (fatia B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** as palavras da Prancheta (futebol brasileiro, Nordeste em destaque, ABC e Náutico com tema próprio) e o juiz do chute.

**Architecture:** `palavras.toml` curado à mão (versionado, sem gerar em tempo de execução) e `palavras.py`, que carrega, sorteia as 3 opções e julga o chute. Implementa o `Banco` de `tipos.py`.

**Tech Stack:** Python 3.12, `tomllib`, `rapidfuzz` (já é dependência), pytest.

**Spec:** `docs/features/prancheta.md` (Contratos › Palavras; Regras › Chute).

## Global Constraints

- `tipos.py` e `__init__.py` têm o conteúdo **byte a byte** do plano da fatia A (`docs/superpowers/plans/2026-11-23-prancheta-sala.md`, Task 1, bloco Produces). Copie de lá; não altere.
- Mínimos: `geral` ≥ 300 palavras com ≥ 60 por dificuldade; `nordeste` ≥ 80; `abc` ≥ 40 e `nautico` ≥ 40 próprias. Tema de clube = slug do `src/geral/teams.toml`.
- Toda palavra tem de ser **desenhável ou mimável** por alguém comum em 80 s (jogador só se tem traço marcante: cabelo, comemoração, apelido-objeto). Nada ofensivo, nada de tragédia (acidentes, mortes).
- Fatos verificados: ídolo, estádio, mascote e apelido de clube precisam existir de verdade. Fontes: `src/geral/games/carreira/conhecidos.toml`, `src/geral/games/craques/*.toml`, `src/geral/games/clubes.toml`, `src/geral/games/velha/base.json`, `src/geral/teams.toml` e Wikipédia em pt. Na dúvida, fica de fora.
- Commit: `tipo: descrição` em pt-BR, uma linha, sem escopo e sem trailer.

## Review Focus

- Chute com acento/caixa/pontuação diferentes do texto — `test_julgar_normaliza_acento_e_apelido`.
- Chute que é o texto mais uma palavra ("bicicleta linda") não é certo, mas é trave — `test_texto_a_mais_e_trave`.
- Palavras curtas (≤ 4 letras) gerando "trave" para qualquer coisa parecida — `test_palavra_curta_so_trave_com_uma_letra_trocada`.
- Tema de clube sem palavras de alguma dificuldade — `opcoes` completa com `geral` (`test_tema_clube_completa_com_geral`).
- Partida longa esgotando as palavras do tema — `test_opcoes_sem_repetir_ate_esgotar_e_depois_libera`.

---

### Task 1: `palavras.py` e o juiz

**Files:**
- Create: `src/geral/games/prancheta/__init__.py`, `src/geral/games/prancheta/tipos.py` (cópias da fatia A), `src/geral/games/prancheta/palavras.py`, `src/geral/games/prancheta/palavras.toml` (só ~20 palavras por enquanto)
- Test: `tests/test_prancheta_palavras.py`

**Interfaces — Produces** (a fatia D usa):

```python
class BancoToml:               # implementa tipos.Banco
    palavras: list[Palavra]
    def opcoes(self, tema: str, rng: random.Random, usadas: set[str]) -> list[Palavra]: ...
    def julgar(self, chute: str, palavra: Palavra) -> Veredito: ...
    def temas_disponiveis(self) -> list[str]: ...   # "geral", "nordeste", depois clubes com ≥ 40, em ordem alfabética

def carregar(path: Path | None = None) -> BancoToml   # padrão: palavras.toml ao lado; cache por processo
```

Formato do TOML (da página): `[[palavra]]` com `texto`, `aceita = [...]` (opcional, padrão `[]`), `dificuldade`, `tipo` ∈ `lance|jogador|clube|estadio|mascote|apelido|torcida|objeto|tecnico`, `temas = [...]`. Valor fora do domínio → `ValueError` ao carregar.

`opcoes`: uma palavra por dificuldade, na ordem fácil, média, difícil, escolhidas com `rng` entre as do tema cujo `texto` não está em `usadas` (o chamador põe a escolhida em `usadas`); se faltar no tema, completa com `geral`; se esgotar, ignora `usadas`. Tema `geral` = palavras com `"geral"` em `temas`.

`julgar`: `c = normalizar(chute)`; `certo` se `c` é igual a `normalizar` do `texto` ou de algum `aceita`; senão `trave` se `fuzz.ratio(c, alvo) ≥ 80` para algum alvo, ou se `c` contém o alvo inteiro; senão `errado`. Palavras de até 4 letras: trave só com distância de edição 1 (`rapidfuzz.distance.Levenshtein`).

- [ ] **Step 1:** testes: `test_carrega_e_valida_dominio`, `test_opcoes_uma_por_dificuldade_em_ordem`, `test_opcoes_respeita_usadas`, `test_opcoes_sem_repetir_ate_esgotar_e_depois_libera`, `test_tema_clube_completa_com_geral`, `test_julgar_normaliza_acento_e_apelido` (`"gol olimpico"` e `"GOL OLÍMPICO!"` certos para "Gol olímpico"; um `aceita` também), `test_texto_a_mais_e_trave`, `test_quase_e_trave` (`"bicicléta"`, `"biciclta"`), `test_palavra_curta_so_trave_com_uma_letra_trocada`, `test_longe_e_errado`. Ver falhar.
- [ ] **Step 2:** implementar; verde.
- [ ] **Step 3:** commit `feat: banco de palavras e juiz do chute da prancheta`.

### Task 2: o conteúdo

**Files:** Modify `palavras.toml`; Create `tests/test_prancheta_conteudo.py`

Organize o TOML em blocos comentados por tipo. Ideias (não lista fechada): lances (bicicleta, chapéu, caneta, pedalada, elástico, cavadinha, paradinha, gol olímpico, gol de placa, folha seca, carrinho, impedimento, pênalti, escanteio, VAR, cartão vermelho, bola na trave, frango, cera), objetos (apito, chuteira, caneleira, bandeirinha, trave, rede, taça, braçadeira, prancheta, corneta, bandeirão), estádios (Maracanã, a Geral do Maracanã, Arena das Dunas, Frasqueira, Aflitos, Ilha do Retiro, Arruda, Castelão, Fonte Nova, Rei Pelé, Almeidão…), mascotes e apelidos (Urubu, Porco, Vovô, Leão da Ilha, Timbu, Elefante, Cobra Coral, Azulão…), torcidas e cultura (bandeirão, mosaico, charanga, coreografia, olé, hino), jogadores com traço desenhável (da lista curada e dos craques do Nordeste), técnicos com marca visual. Na dúvida sobre um fato, procure na Wikipédia em pt e, se não confirmar, deixe de fora.

- [ ] **Step 1:** testes: `test_minimos_do_banco_de_palavras` (os mínimos das Global Constraints), `test_sem_palavra_repetida` (por `normalizar(texto)`), `test_aceita_nao_colide_entre_palavras` (um `aceita` não é `texto`/`aceita` de outra), `test_temas_sao_conhecidos` (todo tema ∈ `{"geral","nordeste"}` ∪ slugs do `teams.toml`), `test_abc_e_nautico_disponiveis`. Ver falhar.
- [ ] **Step 2:** escrever o conteúdo até os testes passarem.
- [ ] **Step 3:** gerar a amostra para o dev revisar: na descrição do PR, 15 palavras por tema (`geral`, `nordeste`, `abc`, `nautico`), misturando dificuldades, e a contagem por tema × dificuldade × tipo.
- [ ] **Step 4:** `uv run ruff check . && uv run ruff format --check . && uv run pytest` verde; commit `feat: palavras da prancheta com o nordeste, o abc e o náutico`.
