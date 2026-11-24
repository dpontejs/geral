# 7a0 do clube — PR 1: dados (elencos, força, ídolos)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** gerar `src/geral/games/setea0/setea0.json` com os elencos por década das 6 edições, mais América-RN e CRB (Wikipédia pt), e os adversários de todos os tempos (base da velha). Cada jogador tem força de 1 a 99.

**Architecture:** um script de rede (`scripts/import_setea0.py`) que reaproveita `geral.games.ptwiki`, mais funções puras e testadas em `setea0/importacao.py` e `setea0/forca.py`. A revisão humana acontece em listas TOML por clube, como em `jogadores_pt.toml`.

**Tech Stack:** Python 3.12, httpx, respx (testes), pytest.

**Spec:** `docs/features/setea0.md`. **Depende de:** PR 0 (`modelos.py`, `chaves.toml`, `dados.py`). Roda em paralelo com o PR 2.

## Global Constraints

- Como no PR 0. Além disso: os testes não acessam a internet (respx). Só o script, rodado à mão, acessa a rede.
- `publicado` continua `false` em todas as edições. Quem liga é o dev, depois de revisar.

## Review Focus

- Página sem infobox, posição vazia ou anos que não batem com os clubes: o jogador fica fora e entra no relatório, sem derrubar o script. Teste em Task 2.
- Jogador que passou duas vezes pelo clube (1990–1992 e 1998): as duas passagens contam. Teste em Task 2.
- Empréstimo e sub-20 aparecem no infobox como clube: só conta a passagem cujo clube é o da edição. Teste em Task 2.
- Ídolo de `idolos.toml` que não existe no elenco: erro no script, nunca uma nota silenciosa num homônimo. Teste em Task 3.

---

### Task 1: força

**Files:** Create `src/geral/games/setea0/forca.py`. Test `tests/test_setea0_forca.py`.

**Interfaces — Produces:**
- `percentis(famas: list[int]) -> list[float]`: o percentil de cada fama dentro do próprio clube (0–1, empates com o mesmo valor).
- `forca(percentil: float, anos: int | None, selecao: bool) -> int`:
  - `round(35 + 40 * percentil + 2.5 * min(anos, 8) + (6 if selecao else 0))`, limitada a 1–99;
  - `anos=None` (adversário da velha, sem passagens) usa 4.
- O dev pode recalibrar as constantes. O que importa é o que os testes pedem.

- [ ] **Step 1: Testes que falham:**
  - `test_forca_cresce_com_fama_anos_e_selecao` (cada fator, com os outros fixos, aumenta a força);
  - `test_forca_entre_1_e_99` (extremos);
  - `test_percentil_e_relativo_ao_clube` (`percentis([1, 1, 5, 50])` → `[0, 0, 0.67, 1]`, aproximadamente).
- [ ] **Step 2–4:** rodar, ver falhar, implementar, rodar e ver passar.
- [ ] **Step 5:** commit `feat: força dos jogadores do 7a0`.

### Task 2: importação pura

**Files:** Create `src/geral/games/setea0/importacao.py`. Test `tests/test_setea0_importacao.py`.

**Interfaces — Produces:**
- `posicoes(texto: str) -> list[Posicao]`, partindo do campo `posição` do infobox pt (os casos reais estão em `carreiras_pt.json`):
  - Goleiro → GOL; Zagueiro, Líbero e Quarto-zagueiro → ZAG;
  - Lateral, Lateral-direito, Lateral-esquerdo e Ala → LAT;
  - Volante, Meia, Meio-campista, Médio, Meia-atacante e Ponta-de-lança → MEI;
  - Atacante, Centroavante e Ponta → ATA;
  - vários valores ("Zagueiro e volante") → lista sem repetição, na ordem do texto; nada reconhecido → `[]`.
- `passagens(stints: list[ptwiki.Stint], clube_qid: str) -> list[tuple[int, int]]`: só as passagens no clube, com as consecutivas fundidas.
- `jogador_ptwiki(pagina: dict, clube_qid: str, fama: int) -> tuple[dict | None, str | None]`: o jogador sem força (`id`, `nome`, `posicoes`, `passagens`, `fama`) ou o motivo da exclusão, para o relatório.
- `jogadores_velha(base: velha.base.Base, clube_qid: str) -> list[dict]`: `posicoes` vem da base (`goleiro` → GOL, `zagueiro` → ZAG, `lateral` → LAT, `meio-campo` → MEI, `atacante` → ATA), `passagens=[]`, `fama` e `selecao`.
- `montar(brutos: dict[str, list[dict]], idolos: dict[str, dict[str, int]]) -> Dados`:
  - aplica `forca`, com percentil por clube;
  - sobrescreve a força dos ídolos;
  - `versao` = os 12 primeiros caracteres do sha256 do JSON ordenado.

- [ ] **Step 1: Testes que falham:**
  - `test_posicoes_normaliza` (tabela com 10 textos reais, incluindo `""` e `"Coordenador de futebol e volante"` → `["MEI"]`);
  - `test_so_passagens_no_clube_e_funde_consecutivas`;
  - `test_pagina_sem_infobox_vira_relatorio`;
  - `test_ida_e_volta_contam_as_duas`;
  - `test_montar_versao_muda_com_os_dados`.
- [ ] **Step 2–4:** rodar, ver falhar, implementar, rodar e ver passar.
- [ ] **Step 5:** commit `feat: importação dos elencos do 7a0`.

### Task 3: script, listas revisáveis e ídolos

**Files:**
- Create: `scripts/import_setea0.py`, `src/geral/games/setea0/elencos/<slug>.toml` (8 arquivos), `src/geral/games/setea0/idolos.toml`, `src/geral/games/setea0/setea0.json`.
- Modify: `src/geral/games/ptwiki.py` (acrescenta `sitelinks(client, qids, pause=1) -> dict[str, int]`, via `wbgetentities` com `props=sitelinks`, contando só as Wikipédias, que terminam em `wiki` e não são `commonswiki`).
- Test: `tests/test_ptwiki.py` (sitelinks com respx), `tests/test_setea0_importacao.py`.

**Interfaces:**
- `elencos/<slug>.toml`: `[[jogador]] pagina, nome, incluir = true`.
  - Gerado por `uv run python scripts/import_setea0.py --sugerir <slug>` a partir da categoria.
  - ABC e Náutico começam com o que já está em `jogadores_pt.toml`, que já foi revisado.
  - A sugestão grava `incluir = false`, com um comentário do motivo, quando a página não tem infobox, os anos no clube somam menos de 1 temporada ou a posição está vazia.
- `idolos.toml`:
  - `[<slug>]`, com `"<id wikidata>" = <força>` e um comentário com o nome.
  - Começa com `craques/{flamengo,vasco,palmeiras}.toml` (casando pelo nome com o elenco; força 92 por padrão) e com `carreira/lendas.toml`.
  - ABC, Náutico e CSA ganham uma lista nova de 15 a 20 ídolos, com o cabeçalho `# RASCUNHO: revisar nomes e notas`.
- `uv run python scripts/import_setea0.py` baixa tudo (cache em `~/.cache/geral/setea0.json`; `--cache` reconstrói sem rede), grava `setea0.json` e imprime o relatório:
  - excluídos por motivo;
  - décadas com pelo menos 8 jogadores por edição;
  - ídolos não encontrados, que fazem o script sair com código 1.

- [ ] **Step 1:** teste com respx de `sitelinks` e `test_idolo_inexistente_e_erro` (no `montar` ou num helper `aplicar_idolos`). Ver falhar, implementar, ver passar.
- [ ] **Step 2:** implementar o script, gerar as 8 listas, rodar o import de verdade e commitar `setea0.json` com as listas.
- [ ] **Step 3:** teste sobre o arquivo real, `test_dados_reais_cobrem_as_edicoes`:
  - toda edição tem pelo menos 4 décadas com pelo menos 8 jogadores;
  - todo adversário e toda final tem pelo menos 11 jogadores, com pelo menos 1 GOL.
- [ ] **Step 4:** portões completos. Commit `feat: elencos, força e ídolos do 7a0 das seis edições`.
- [ ] **Step 5:** PR "7a0 do clube: dados". A descrição traz o relatório e, para cada clube, o que o dev precisa revisar (lista e ídolos).
