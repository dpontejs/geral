# Prancheta — regras da sala (fatia A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a sala da Prancheta como regras puras (sem servidor): fases, vez, palavras, chutes, dicas, pontos, cartão vermelho, ausência e súmula, com relógio injetado.

**Architecture:** `Sala` é um objeto síncrono; todo método recebe `agora: datetime` e devolve `list[Evento]` que o hub (fatia D) entrega. A privacidade (quem vê a palavra, as opções, a trave) é decidida aqui. O banco de palavras entra por um `Protocol`; os testes usam um banco falso.

**Tech Stack:** Python 3.12, dataclasses, `rapidfuzz` não é usado aqui (é do `julgar`, fatia B), pytest.

**Spec:** `docs/features/prancheta.md` (seções Regras, Contratos › Sala ↔ hub, Jogador, Traço, Eventos, Limites).

## Global Constraints

- Código, nomes de função e logs em inglês **exceto** os nomes do contrato, que ficam como na página (`Sala`, `Evento`, `entrar`, `agir`, `avancar`, `foto`, `fase`, `tracos`...).
- Constantes: `MAX_JOGADORES = 10`, `TEMPO_ESCOLHA = 15 s`, `TEMPO_DESENHO = 80 s`, `TEMPO_INTERVALO = 6 s`, `AUSENCIA = 30 s`, `BASE = {"facil": 5, "media": 7, "dificil": 10}`, `PISO = 2`, `ASSISTENCIA = 2`, `PEDACO_MAX = 64`, `PONTOS_MAX = 20_000`, `CHUTE_MAX = 40`, `CHUTE_INTERVALO = 0.5 s`, `PEDACOS_POR_SEGUNDO = 40`.
- Testes não usam `sleep`: avançam `agora`. Suíte inteira segue em ~1 min.
- Commit: `tipo: descrição` em pt-BR, uma linha, sem escopo e sem trailer.

## Review Focus

- Palavra vazando por qualquer caminho (`foto`, `estado`, `dica`, `chute` errado que contém a palavra, `fim` antes da hora) — `test_palavra_nunca_vaza` varre todos os eventos e fotos de um lance inteiro.
- Dois chutes certos "ao mesmo tempo" e o último a acertar encerrando o lance no meio de `agir` — `test_ultimo_acerto_encerra_o_lance`.
- Quem desenha sai durante a `escolha` (não só no `desenho`) — `test_desenhista_sai_na_escolha`.
- Sala com 2 jogadores e um sai: vai a `fim` e grava súmula uma vez só — `test_fim_uma_vez_so`.
- Apelido repetido na mesma sala — `test_apelido_repetido_422`.

---

### Task 1: tipos comuns e filtro de palavrão

**Files:**
- Create: `src/geral/games/prancheta/__init__.py` (vazio), `src/geral/games/prancheta/tipos.py`, `src/geral/games/prancheta/filtro.py`, `src/geral/games/prancheta/palavroes.txt`
- Test: `tests/test_prancheta_filtro.py`

**Interfaces — Produces** (a fatia B cria `tipos.py` com **este mesmo conteúdo, byte a byte**; não mude sem combinar):

```python
"""Types shared by the Prancheta's room rules and word bank."""

import random
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Protocol

Dificuldade = Literal["facil", "media", "dificil"]
Veredito = Literal["certo", "trave", "errado"]


@dataclass(frozen=True)
class Palavra:
    texto: str
    aceita: tuple[str, ...]
    dificuldade: Dificuldade
    tipo: str
    temas: tuple[str, ...]


class Banco(Protocol):
    def opcoes(self, tema: str, rng: random.Random, usadas: set[str]) -> list[Palavra]: ...
    def julgar(self, chute: str, palavra: Palavra) -> Veredito: ...


def normalizar(texto: str) -> str:
    """Lowercase, no accents, punctuation as spaces, spaces collapsed."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).split())
```

`filtro.py`: `tem_palavrao(texto: str) -> bool` — palavra inteira de `normalizar(texto)` (ou sequência de palavras, para expressões) presente em `palavroes.txt` (normalizado, uma por linha, `#` comentário). Lista curta, pt-BR, ~40 termos de baixo calão e ofensas; **sem** termos de futebol que soam mal ("bicha" fica, "frango" e "pipoqueiro" não).

- [ ] **Step 1:** testes: `test_normalizar` (`"  Pé-de-Anjo! "` → `"pe de anjo"`); `test_palavrao_palavra_inteira` (um termo da lista dentro de frase → True; o mesmo termo como pedaço de outra palavra → False); `test_futebol_nao_e_palavrao` (`"frango"`, `"pipoqueiro"`, `"cavadinha"` → False). Rodar e ver falhar.
- [ ] **Step 2:** implementar; `uv run pytest tests/test_prancheta_filtro.py` verde.
- [ ] **Step 3:** commit `feat: tipos e filtro de palavrão da prancheta`.

### Task 2: entrar, começar, escolher e desenhar

**Files:**
- Create: `src/geral/games/prancheta/sala.py`, `tests/prancheta_fakes.py`
- Test: `tests/test_prancheta_sala.py`

**Interfaces — Produces** (a fatia D usa exatamente isto):

```python
@dataclass
class Evento:
    tipo: str            # estado | traco | desfazer | limpar | chute | acerto | trave | dica | fim
    dados: dict          # o JSON do contrato, já com "seq"
    para: int | None = None
    exceto: int | None = None

class ErroSala(Exception):
    def __init__(self, status: int, motivo: str): ...   # 403, 409, 422 ou 429

class Sala:
    def __init__(self, id: str, tema: str, rodadas: int, banco: Banco, rng: random.Random, agora: datetime): ...
    encerrada: bool
    def entrar(self, apelido: str, agora: datetime) -> tuple[int, str, list[Evento]]  # (jogador, token, eventos)
    def jogador(self, token: str) -> int                                    # ErroSala(403) se inválido/expulso
    def agir(self, jogador: int, acao: dict, agora: datetime) -> list[Evento]  # acao = {"tipo": ..., ...}
    def conectou(self, jogador: int, agora: datetime) -> list[Evento]
    def desconectou(self, jogador: int, agora: datetime) -> list[Evento]
    def avancar(self, agora: datetime) -> list[Evento]
    def foto(self, jogador: int, agora: datetime) -> dict                   # o "estado" do contrato
    def sumula(self) -> dict
```

`tests/prancheta_fakes.py`: `BancoFalso` com palavras fixas (`"Bicicleta"` fácil, `"Gol olímpico"` média, `"Frasqueira"` difícil, e mais 3 por dificuldade), `julgar` exato por `normalizar` e trave se começa igual; e um helper `sala_com(n, agora)` que cria a sala e faz `n` jogadores entrarem e conectarem.

Regras desta task (da página): token `secrets.token_urlsafe(16)`; anfitrião = 1º; `comecar` só do anfitrião, ≥ 2 presentes, senão 409; fila da rodada = presentes por ordem de entrada; `escolha` manda `opcoes` só ao desenhista (via `foto`/`estado` com `para`); `escolher{indice}` 0–2; prazo da escolha vencido em `avancar` → sorteia com `rng`; `traco` só do desenhista na fase `desenho` (409 fora), pedaço > 64 pontos ou coordenada fora de 0–1000 → 422, total > 20 000 pontos → 422; `traco` vai com `exceto=desenhista`; `desfazer{}` tira o último `id`, `limpar{}` zera; entrar no meio → fim da fila da rodada em curso; 11º → 409; apelido de 2–16 após `strip`, palavrão ou repetido (normalizado) → 422.

- [ ] **Step 1:** testes: `test_anfitriao_comeca_com_dois`, `test_so_anfitriao_comeca_409`, `test_opcoes_so_para_quem_desenha` (fotos dos outros com `opcoes is None` e `palavra is None`), `test_escolha_vencida_sorteia`, `test_traco_fora_da_vez_409`, `test_traco_repassado_exceto_desenhista`, `test_traco_invalido_422`, `test_desfazer_e_limpar`, `test_entra_no_meio_vai_para_o_fim_da_fila`, `test_sala_cheia_409`, `test_apelido_repetido_422`, `test_apelido_com_palavrao_422`, `test_token_invalido_403`. Ver falhar.
- [ ] **Step 2:** implementar; verde.
- [ ] **Step 3:** commit `feat: sala da prancheta com vez, escolha da palavra e traços`.

### Task 3: chutes, dicas, pontos e fim do lance

**Files:** Modify `sala.py`; Test `tests/test_prancheta_sala.py`

Regras: `chute{texto}` ≤ 40 caracteres (422), 1 a cada 0,5 s por jogador (429), desenhista ou quem já acertou → 409. `julgar`: `certo` → `acerto{jogador, pontos}` para todos, pontos `max(BASE[dif] − (k − 1), 2)`, +2 ao desenhista, `gols += 1`, `assist += 1`; `trave` → `trave{texto}` só para quem chutou; `errado` → `chute{jogador, texto}` para todos, **salvo** se `tem_palavrao` ou se `normalizar(texto)` contém `normalizar` do `texto`/`aceita` da palavra (aí só volta para quem chutou como `chute`). Dica: `dica` = lista por caractere (`None` = apagada; não-letra sempre visível); aos 50% e 75% do `TEMPO_DESENHO`, `avancar` acende uma letra apagada por `rng`, com teto `len(letras) // 3`, e emite `dica{dica}` a todos menos o desenhista. Lance termina por prazo ou quando todos os presentes não-desenhistas acertaram → `intervalo` (palavra no `estado` de todos) → após 6 s, próximo da fila / próxima rodada / `fim`.

- [ ] **Step 1:** testes: `test_pontos_por_ordem_e_dificuldade` (difícil: 10, 9, 8…; piso 2), `test_assistencia_de_quem_desenha`, `test_chute_certo_nao_aparece`, `test_trave_e_palavrao_nao_sao_transmitidos`, `test_julgar_recebe_o_texto_cru` (o banco recebe o chute sem normalizar), `test_dicas_aos_50_e_75_porcento`, `test_dica_nunca_passa_de_um_terco`, `test_ultimo_acerto_encerra_o_lance`, `test_lance_acaba_no_prazo`, `test_chute_rapido_demais_429`, `test_palavra_nunca_vaza` (roda um lance inteiro, junta todos os eventos/fotos destinados a não-desenhistas antes do `intervalo` e verifica que nenhum JSON contém o texto normalizado nem um `aceita`). Ver falhar.
- [ ] **Step 2:** implementar; verde.
- [ ] **Step 3:** commit `feat: chutes, dicas e pontos da prancheta`.

### Task 4: ausência, saída, cartão vermelho e súmula

**Files:** Modify `sala.py`; Test `tests/test_prancheta_sala.py`

Regras: `conectou`/`desconectou` contam conexões (o hub chama em cada stream; presente se ≥ 1); ausente quando sem conexão há ≥ 30 s (em `avancar`). Vez de ausente é pulada; desenhista que sai (`sair`), é expulso ou fica ausente durante `escolha`/`desenho` → `intervalo`, pontos ficam. Anfitrião passa ao presente mais antigo ao sair/ser expulso/ficar ausente. `tirar{alvo}` só do anfitrião; `cartao{alvo}` registra o voto, maioria estrita dos presentes sem o alvo expulsa; voto cai quando o votante sai. Expulso: token passa a dar 403. < 2 presentes em jogo → `fim`. `fim{sumula}` uma vez só, `encerrada = True`. `sumula()` = `{"id", "tema", "jogadores": [{apelido, pontos, gols, assist}] por pontos desc, "lances": [{"desenhista", "palavra", "acertaram": [apelidos em ordem]}]}`.

- [ ] **Step 1:** testes: `test_vez_de_ausente_e_pulada`, `test_quem_desenha_sai_lance_vai_ao_intervalo`, `test_desenhista_sai_na_escolha`, `test_anfitriao_passa_ao_mais_antigo`, `test_cartao_vermelho_por_maioria`, `test_voto_cai_quando_votante_sai`, `test_expulso_nao_age`, `test_so_anfitriao_tira_409`, `test_reconectar_recebe_tracos_do_desenho_atual` (`foto` traz `tracos` inteiros), `test_fim_uma_vez_so`, `test_sumula_ordenada_por_pontos`. Ver falhar.
- [ ] **Step 2:** implementar; verde; `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
- [ ] **Step 3:** commit `feat: ausência, cartão vermelho e súmula da prancheta`.
