# Prancheta: desenhar e adivinhar em sala privada

- **Data:** 2026-11-23
- **Status:** aprovada
- **ADRs:** — (sala em memória num processo só: registrado nas Decisões do PLAN)

## Objetivo

Joguinho de desenhar e adivinhar com tema de futebol, **ao vivo**, numa sala privada que quem cria
manda por link no grupo. Na sua vez, você desenha na prancheta do técnico (quadro verde, traço de
giz) e os outros chutam o que é. Nome, visual e regras são da Geral; do gênero, só a mecânica.
Palavras com o Nordeste como diferencial. Ao fim, a súmula fica no mesmo link curto.

## Fora de escopo

- Salas públicas, lista de salas, conta/login, ranking geral, partida contra o computador.
- Guardar desenhos (a súmula não tem desenho: nada de usuário para moderar depois).
- Balde de tinta, formas prontas, desenho por imagem colada.
- Sobreviver a deploy: reiniciar o processo derruba as salas abertas (a página avisa).
- Mais de um processo do uvicorn (o hub é em memória; hoje o Dockerfile roda um só).

## Regras (decididas com o dev em 2026-11-23)

- **Sala:** de 2 a 10 jogadores, cada um com apelido (2–16 caracteres, sem login, filtro de
  palavrão). Quem cria é o anfitrião e escolhe o **tema** (`geral`, `nordeste` ou slug de clube
  do `teams.toml` com palavras suficientes) e as **rodadas** (1–3, fixas desde o início; cada
  jogador desenha uma vez por rodada). Dá para entrar no meio: vai para o fim da fila da rodada
  em curso (a partida fica um pouco mais longa).
- **Fases do lance:** `escolha` (quem desenha escolhe 1 de 3 palavras: fácil, média, difícil;
  15 s, senão sorteia) → `desenho` (80 s) → `intervalo` (palavra revelada, 6 s) → próximo lance.
  O lance acaba antes se todos os presentes acertarem. Antes do 1º lance, `espera`; no fim, `fim`.
- **Dicas automáticas:** a palavra aparece desde o início como lâmpadas apagadas, uma por letra;
  espaço, hífen, ponto e dígito aparecem desde o início e não contam como letra. Aos 50% e aos 75%
  do tempo acende uma letra ao acaso (no máximo 1/3 das letras). Quem desenha não pede dica.
- **Pontos:** o k-ésimo a acertar ganha `max(base − (k − 1), 2)`, com base 5/7/10 para
  fácil/média/difícil. Quem desenha ganha 2 por acerto (assistência). A súmula mostra pontos,
  gols (acertos) e assistências.
- **Chute:** até 40 caracteres. Certo = igual a `texto` ou a um `aceita`, normalizado (minúsculas,
  sem acento, sem pontuação, espaços colapsados). "Na trave" = `rapidfuzz.fuzz.ratio ≥ 80` e não
  certo, avisado **só a quem chutou**. Só o chute errado e longe é mostrado a todos: nem o
  certo (os outros veem só "fulano acertou") nem o "na trave" (entregaria a palavra). Chute com
  palavrão também não é mostrado. Quem já acertou e quem desenha não chutam.
- **Palavrão:** lista curta curada em `geral/games/prancheta/palavroes.txt` (pt-BR, uma por linha),
  comparada por palavra inteira no texto normalizado (`filtro.py`). Vale para apelido (422) e chute.
- **Cartão vermelho:** o anfitrião tira alguém direto; qualquer um vota contra outro, e a maioria
  dos presentes (sem contar o alvo) tira. O voto vale até o alvo sair; sai quem votou, sai o voto.
  O token do expulso deixa de valer.
- **Ausência:** sem conexão de eventos por 30 s = ausente (não conta para "todos acertaram");
  se for a vez dele, o lance é pulado. Se quem desenha sai, é expulso ou fica ausente no meio do
  lance, o lance vai para o `intervalo` e os pontos já ganhos ficam. O anfitrião passa ao jogador
  presente mais antigo quando sai, é expulso ou fica ausente. Menos de 2 presentes no jogo = `fim`.

## Contratos

- **Módulos:** `geral/games/prancheta/` (`sala.py` regras puras com relógio injetado, `filtro.py`
  + `palavroes.txt`, `palavras.py` + `palavras.toml`), `geral/web/prancheta.py` (hub, `APIRouter`,
  súmula), template `prancheta.html.j2` com JS/CSS inline, como os outros joguinhos.
- **`Sala` ↔ hub:** todo método recebe `agora` e devolve `list[Evento]`, com
  `Evento(tipo, dados, para: int | None = None, exceto: int | None = None)` (`para=None` = todos).
  `Sala` numera os eventos (`seq`). Métodos: `entrar(apelido)`, `agir(jogador, acao)`,
  `conectou(jogador)`, `desconectou(jogador)`, `avancar()` e `foto(jogador) -> dict` (o `estado`).
  A sala recebe um `Banco` (Protocol com `opcoes` e `julgar`), para A andar sem B (banco falso).
  A privacidade (palavra, trave, opções) é decidida **dentro da `Sala`**; o hub só entrega.
- **Jogador:** `id` inteiro sequencial na sala (1, 2, …); `alvo` em `cartao`/`tirar` é esse `id`.
- **Palavras** (`palavras.toml`): `[[palavra]] texto, aceita = [...], dificuldade =
  "facil"|"media"|"dificil", tipo = "lance"|"jogador"|"clube"|"estadio"|"mascote"|"apelido"|
  "torcida"|"objeto"|"tecnico", temas = ["geral", "nordeste", "<slug>"]`. Mínimos (teste): `geral`
  ≥ 300 com ≥ 60 por dificuldade; `nordeste` ≥ 80; clube (slug do `teams.toml`) só vira tema com
  ≥ 40 próprias (o resto completa com `geral`): na v1, **obrigatórios `abc` e `nautico`**; os
  outros entram quando chegarem a 40. `clubes.toml` é só fonte. Sem `texto` repetido.
  `temas_disponiveis() -> list[str]` diz o que a tela de criar oferece e o servidor aceita. Fontes: `conhecidos.toml`, `clubes.toml`, base da
  velha e curadoria (lances, estádios, mascotes, apelidos, a Geral do Maracanã).
  `palavras.py`: `opcoes(tema, rng) -> list[Palavra]` (3, uma por dificuldade, sem repetir na
  partida) e `julgar(chute, palavra) -> Literal["certo", "trave", "errado"]`.
- **Traço:** coordenadas inteiras 0–1000 num quadro 4:3. `{"id": int, "cor": 0–7, "esp": 1|2|3,
  "pts": [[x, y], ...], "fim": bool}`; um traço chega em pedaços (≤ 64 pontos cada, mesmo `id`).
  Cor 0 = apagador (cor do quadro). Desfazer tira o último `id`; limpar zera. Teto: 20 mil pontos
  por desenho.
- **Rotas** (prefixo `/api/jogos/prancheta`):
  - `GET /jogos/prancheta` (criar) e `GET /jogos/prancheta/s/{id}` (sala viva → jogo; encerrada →
    súmula; sem sala nem súmula → "a sala acabou ou o servidor reiniciou").
  - `POST /salas {apelido, tema, rodadas}` → `{id, jogador, token}`; `id` = 6 caracteres base32.
  - `POST /salas/{id}/entrar {apelido}` → `{jogador, token}`; 409 cheia/encerrada, 422 apelido.
  - `POST /salas/{id}/acao {token, tipo, ...}`, `tipo` ∈ `comecar | escolher{indice} | traco{...}
    | desfazer | limpar | chute{texto} | cartao{alvo} | tirar{alvo} | sair` (união discriminada
    do Pydantic). 403 token inválido/expulso; 409 ação fora da vez/fase; 204 se aceita.
  - `GET /salas/{id}/eventos?token=` (SSE, `event:` = tipo, `data:` = JSON com `seq`). Reconectar
    sempre recebe a foto de novo.
- **Eventos (contrato de C, D e E):**
  - `estado` (ao conectar e a cada mudança de fase ou de jogadores): `{seq, voce, fase, rodada,
    rodadas, tema, prazo, agora, desenhista, jogadores: [{id, apelido, pontos, gols, assist,
    presente, anfitriao, acertou}], dica, opcoes, palavra, tracos}`. `prazo` e `agora` em ISO UTC
    (a tela corrige o relógio pela diferença). `dica`: um item por caractere, a letra se acesa,
    `null` se apagada (não-letras sempre visíveis). `opcoes`: só para quem desenha na `escolha`,
    `[{texto, dificuldade}]` na ordem fácil, média, difícil (`escolher{indice}` = 0–2), senão `null`.
    `palavra`: para quem desenha a partir do `desenho`, para todos no `intervalo` e no `fim`, senão
    `null`. `tracos`: os traços inteiros do desenho atual.
  - `traco` `{id, cor, esp, pts, fim}`: cada pedaço repassado como chegou, a todos **menos** quem
    desenha (ele já desenhou na tela). `desfazer {id}`, `limpar {}`.
  - `chute {jogador, texto}` (só os errados e longe); `acerto {jogador, pontos}`; `trave {texto}`
    (privado); `dica {dica}`; `fim {sumula}` (o mesmo JSON gravado na tabela).
- **Hub:** dicionário de salas em memória; um laço do lifespan chama `sala.avancar(agora)` a cada
  0,5 s e transmite o que mudou. Sala sem ninguém conectado por 10 min, ou com 3 h, é encerrada.
  `web/prancheta.py` expõe `criar_prancheta(db_path, now, sleep, limite_salas: RateLimiter) ->
  Prancheta` (com `.router` e `.rodar()`, a tarefa do laço). No `app.py` entram só: criar o objeto
  (passando o `RateLimiter` de lá), `include_router` e iniciar/parar `.rodar()` no lifespan.
- **Banco:** `prancheta_sumulas(id TEXT PK, tema, criada_em, encerrada_em, dados JSON)` no mesmo
  SQLite, gravada ao entrar em `fim` (jogadores com pontos/gols/assistências; lances com quem
  desenhou, a palavra e quem acertou, em ordem). Não toca no `store.py`.
- **Limites:** criar sala 20/h por rede (`RateLimiter`); por jogador, 1 chute a cada 0,5 s e 40
  pedaços de traço por segundo (acima disso, 429 sem efeito).

## Critérios de aceite (como testes)

- [ ] `test_palavra_nunca_vaza`: dado um lance em `desenho`, quando qualquer outro jogador recebe
  `estado` ou eventos, então nenhum contém o `texto` nem um `aceita` até o `intervalo`.
- [ ] `test_chute_certo_nao_aparece`: dado um acerto, então os outros recebem só `acerto{jogador}`;
  `test_trave_e_palavrao_nao_sao_transmitidos`.
- [ ] `test_quem_desenha_sai_lance_vai_ao_intervalo` e `test_anfitriao_passa_ao_mais_antigo`.
- [ ] `test_trave_so_para_quem_chutou` e `test_julgar_normaliza_acento_e_apelido`.
- [ ] `test_pontos_por_ordem_e_dificuldade` e `test_assistencia_de_quem_desenha`.
- [ ] `test_dicas_aos_50_e_75_porcento` (com relógio injetado; nunca mais de 1/3 das letras).
- [ ] `test_lance_acaba_quando_todos_acertam` e `test_vez_de_ausente_e_pulada`.
- [ ] `test_entra_no_meio_vai_para_o_fim_da_fila` e `test_sala_cheia_409`.
- [ ] `test_acao_fora_da_vez_409` e `test_token_de_outra_sala_403`.
- [ ] `test_cartao_vermelho_por_maioria` e `test_expulso_nao_age` (403 com o token antigo).
- [ ] `test_reconectar_recebe_traços_do_desenho_atual`.
- [ ] `test_fim_grava_sumula_e_link_mostra_sumula`; `test_sala_inexistente_mostra_aviso`.
- [ ] `test_limites_de_chute_e_traco_429` e `test_criar_sala_limitado_por_rede`.
- [ ] `test_minimos_do_banco_de_palavras` e `test_sem_palavra_repetida`.

## Verificação ponta a ponta

`uv run pytest` (suíte segue em ~1 min: regras testadas sem servidor; SSE com relógio e `sleep`
injetados, como `duel_events`). Depois, com o app local, um script Playwright abre 3 navegadores
(um com tela de celular), cria a sala, entra, desenha, acerta, chega à súmula e tira fotos.

## Fatias (um PR cada; subagentes em worktrees)

0. Esta página + a decisão no PLAN (`docs/prancheta`).
1. Em paralelo: **A** `sala.py` (regras, banco de palavras falso nos testes) · **B** `palavras.toml`
   + `palavras.py` (amostra para o dev revisar) · **C** rascunho visual em
   `docs/features/prancheta-rascunho.html` com eventos falsos → fotos celular/PC para o dev.
2. Em paralelo, depois de A e B: **D** servidor (`web/prancheta.py`, rotas, SSE, súmula, limites;
   no `app.py` só as 3 ligações descritas no Hub) · **E** a tela (`prancheta.html.j2`), a partir de C aprovado, contra
   estes contratos; mergeia depois de D.
3. **F**: entrada em `/jogos` e abas, Playwright ponta a ponta, `TASKS.md`. É a única fatia que
   mexe em arquivos compartilhados com o 7a0.

## Riscos e dúvidas abertas

- Desenho no celular com o dedo: o traço tem de sair liso (pointer events + `touch-action: none`);
  o rascunho C prova antes da tela de verdade.
- Caddy precisa deixar o SSE aberto sem buffer (já funciona no duelo da velha).
