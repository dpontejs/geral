# Prancheta: desenhar e adivinhar em sala privada

- **Data:** 2026-11-23 (ajustes de 2026-11-24: pedir para entrar, 12 gizes, dica de quem desenha,
  pular a vez; 2026-11-25: reta, retângulo, círculo e balde; nova partida na mesma sala)
- **Status:** entregue (PRs #84, #85, #86, #88, #90, #92 e a entrada em /jogos); ajustes de
  2026-11-24 em `feat/prancheta-sala-ajustes`
- **ADRs:** — (sala em memória num processo só: registrado nas Decisões do PLAN)

## Objetivo

Joguinho de desenhar e adivinhar com tema de futebol, **ao vivo**, numa sala privada que quem cria
manda por link no grupo. Na sua vez, você desenha na prancheta do técnico (quadro verde, traço de
giz) e os outros chutam o que é. Nome, visual e regras são da Geral; do gênero, só a mecânica.
Um banco só de palavras de futebol, sem tema por time. Ao fim, a súmula fica no mesmo link curto.

## Fora de escopo

- Salas públicas, lista de salas, conta/login, ranking geral, partida contra o computador.
- Guardar desenhos (a súmula não tem desenho: nada de usuário para moderar depois).
- Desenho por imagem colada. (Balde de tinta e formas prontas saíram desta lista em 2026-11-25,
  decisão do dev: ver "Ferramentas de desenho".)
- Sobreviver a deploy: reiniciar o processo derruba as salas abertas (a página avisa).
- Mais de um processo do uvicorn (o hub é em memória; hoje o Dockerfile roda um só).

## Regras (decididas com o dev em 2026-11-23)

- **Sala:** de 2 a 10 jogadores, cada um com apelido (2–16 caracteres, sem login, filtro de
  palavrão). Quem cria é o anfitrião e escolhe só as **rodadas** (1–3, fixas desde o início; cada
  jogador desenha uma vez por rodada). Dá para entrar no meio: vai para o fim da fila da rodada
  em curso (a partida fica um pouco mais longa).
- **Pedir para entrar** (dev, 2026-11-24): só quem cria entra direto. Quem abre o link escolhe o
  apelido e fica em "pedindo para entrar" até o anfitrião **aceitar** ou **recusar** (só ele vê os
  pedidos). Aceito, entra como antes (no meio do jogo, fim da fila). Recusado, recebe um aviso
  educado e o token do pedido deixa de valer (pode pedir de novo, com outro pedido). Pedido não
  ocupa vaga dos 10 até ser aceito; no máximo 10 pedidos esperando (409). Aceitar com a sala cheia
  dá 409 e o pedido continua. Se o anfitrião sai, o próximo herda os pedidos. Pedido sem conexão
  de eventos por 30 s cai. O apelido do pedido não pode repetir o de um jogador nem o de outro
  pedido.
- **Fases do lance:** `escolha` (quem desenha escolhe 1 de 3 palavras: fácil, média, difícil;
  15 s, senão sorteia) → `desenho` (80 s) → `intervalo` (palavra revelada, 6 s) → próximo lance.
  O lance acaba antes se todos os presentes acertarem. Antes do 1º lance, `espera`; no fim, `fim`
  (a sala fica aberta 10 min esperando a próxima partida; ver "Nova partida").
- **Dicas de quem desenha** (dev, 2026-11-24, no lugar das automáticas): a palavra aparece desde
  o início como lâmpadas apagadas, uma por letra; espaço, hífen, ponto e dígito aparecem desde o
  início e não contam como letra. Quem desenha tem o botão "dar dica", que acende uma letra ao
  acaso: a 1ª fica liberada aos 50% do tempo, a 2ª aos 75% (uma por marco, acumulam se ele
  esperar; nunca mais de 1/3 das letras, então palavra de 1–2 letras não tem dica e de 3–5 tem
  uma). Dar é escolha dele; nada acende sozinho.
- **Pular a vez** (dev, 2026-11-24): quem desenha pode pular na `escolha` ou no `desenho`. O lance
  vai ao `intervalo` (a palavra aparece, se já tinha sido escolhida), os pontos já ganhos ficam,
  ninguém perde nada e o jogo segue.
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

- **Ferramentas de desenho** (dev, 2026-11-25): além do giz livre, quem desenha tem **reta**,
  **retângulo** e **círculo/elipse** (só o contorno) e o **balde** (pinta a região fechada em volta
  do toque). As formas seguem o dedo com prévia só na tela de quem desenha e vão uma vez, ao
  soltar; o balde vai no toque. Cor e espessura valem para todas; com o apagador, a forma apaga e o
  balde limpa a região. Desfazer tira o último item (traço, forma ou balde); limpar zera tudo.
- **Nova partida na mesma sala** (dev, 2026-11-25): no `fim`, o anfitrião tem "Nova partida" e
  escolhe de novo as rodadas (1–3). A sala volta à `espera` com os mesmos jogadores (mesmos
  tokens), placar zerado; quem está **ausente** sai da sala (o token deixa de valer); os pedidos
  esperando continuam. As palavras já jogadas na sala não voltam enquanto o banco tiver outras da
  mesma dificuldade. Quem não é anfitrião vê "Esperando o anfitrião" com o botão de sair. No `fim`
  dá para pedir para entrar, aceitar, recusar e sair (quem entra no `fim` joga a próxima, não entra
  na súmula da que acabou). Sem nova partida em 10 min, a sala fecha de vez. Cartões já dados
  continuam valendo (a regra do voto não muda). Cada partida tem a **sua súmula**, no seu link
  (`/jogos/prancheta/s/{sala}-{n}`, n = 1, 2, …); o link da sala segue sendo a sala viva enquanto
  ela existe e, depois que fecha, mostra a súmula da última partida.

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
- **Palavras** (`palavras.toml`): banco único, **sem tema** (decisão do dev em 2026-11-23: nada
  de tema por time; palavras de futebol que qualquer torcedor brasileiro reconhece, e uma ligada a
  um clube só entra se for de todos, como "Maracanã"). `[[palavra]] texto, aceita = [...],
  dificuldade = "facil"|"media"|"dificil", tipo = "lance"|"jogador"|"clube"|"estadio"|"mascote"|
  "apelido"|"torcida"|"objeto"|"tecnico"`. Mínimos (teste): ≥ 300 no total, ≥ 60 por dificuldade.
  Sem `texto` repetido. `palavras.py`: `opcoes(rng, usadas) -> list[Palavra]` (3, uma por
  dificuldade, sem repetir na partida) e `julgar(chute, palavra) -> Literal["certo", "trave",
  "errado"]`.
- **Traço:** coordenadas inteiras 0–1000 num quadro 4:3. `{"id": int, "forma": "livre"|"reta"|
  "ret"|"circ", "cor": 0–12, "esp": 1|2|3, "pts": [[x, y], ...], "fim": bool}` (`forma` ausente =
  `livre`, como antes de 2026-11-25). O giz livre chega em pedaços (≤ 64 pontos cada, mesmo `id`);
  uma forma chega inteira, num pedaço só, com 2 pontos (início e fim; no `circ`, os cantos da caixa
  da elipse) e `fim: true`, e o `id` dela não pode ser de item que já existe (422).
  **Balde:** `{"id": int, "cor": 0–12, "pt": [x, y]}`, ação e evento `balde`. Traços, formas e
  baldes dividem a mesma sequência de `id` e a mesma lista `tracos` do `estado`, em ordem (o balde
  se reconhece por ter `pt`). Cor 0 = apagador (cor do quadro); 1–12 = gizes (branco, amarelo,
  laranja, vermelho, rosa, azul, verde, roxo, marrom, cinza, azul-escuro, preto; a paleta fica em 2
  fileiras de 7 no celular). Desfazer tira o último `id`; limpar zera. Teto: 20 mil pontos por
  desenho; uma forma pesa os seus 2 pontos e um balde pesa 500 (no máximo 40 baldes por desenho,
  porque cada um repinta o quadro inteiro ao refazer). Forma e balde contam no limite de pedaços
  por segundo.
- **Mesmo desenho em toda tela:** cada navegador pinta o quadro num canvas fora da tela de tamanho
  fixo (1000×750, o mesmo espaço das coordenadas), refazendo os itens em ordem, e escala para o
  canvas visível. O balde procura a borda numa cópia gêmea pintada em cor lisa (sem o grão do giz,
  cujos furinhos deixariam a tinta vazar), com tolerância pequena para a suavização das bordas, e
  cresce 1 px para encostar no contorno. A tinta sai com o grão do giz, mais leve que o do traço.
  Navegadores diferentes podem divergir em um pixel na borda (suavização), nunca na região.
- **Rotas** (prefixo `/api/jogos/prancheta`):
  - `GET /jogos/prancheta` (criar) e `GET /jogos/prancheta/s/{id}` (sala viva, inclusive no
    `fim` → jogo; senão a súmula com esse id, ou a última súmula da sala com esse id; sem sala nem
    súmula → "a sala acabou ou o servidor reiniciou").
  - `POST /salas {apelido, rodadas}` → `{id, jogador, token}`; `id` = 6 caracteres base32.
  - `POST /salas/{id}/entrar {apelido}` → `{jogador, token, pendente: true}`: é um **pedido**
    (`jogador` = o id que ele terá se aceito); 409 muitos pedidos/encerrada, 422 apelido.
  - `POST /salas/{id}/acao {token, tipo, ...}`, `tipo` ∈ `comecar | escolher{indice} | traco{...}
    | balde{id, cor, pt} | desfazer | limpar | chute{texto} | cartao{alvo} | tirar{alvo} | sair |
    aceitar{pedido} | recusar{pedido} | dica | pular | nova_partida{rodadas}` (união discriminada
    do Pydantic; `nova_partida` só do anfitrião e só no `fim`, 409; rodadas fora de 1–3, 422). 403 token inválido/expulso/
    recusado; 409 ação fora da vez/fase, pedido ainda esperando ou dica ainda travada; 204 se aceita.
  - `GET /salas/{id}/eventos?token=` (SSE, `event:` = tipo, `data:` = JSON com `seq`). Reconectar
    sempre recebe a foto de novo. O token de um pedido também ouve (para saber a resposta).
- **Eventos (contrato de C, D e E):**
  - `estado` (ao conectar e a cada mudança de fase ou de jogadores): `{seq, voce, fase, rodada,
    rodadas, partida, sumula, prazo, agora, desenhista, jogadores: [{id, apelido, pontos, gols, assist,
    presente, anfitriao, acertou}], dica, opcoes, palavra, tracos}`. `prazo` e `agora` em ISO UTC
    (a tela corrige o relógio pela diferença). `dica`: um item por caractere, a letra se acesa,
    `null` se apagada (não-letras sempre visíveis). `opcoes`: só para quem desenha na `escolha`,
    `[{texto, dificuldade}]` na ordem fácil, média, difícil (`escolher{indice}` = 0–2), senão `null`.
    `palavra`: para quem desenha a partir do `desenho`, para todos no `intervalo` e no `fim`, senão
    `null`. `tracos`: os traços inteiros do desenho atual. `dicas`: só para quem desenha no
    `desenho`, `{dadas, marcos: [ISO, ...]}` (quando cada dica libera), senão `null`. `pedidos`: só
    para o anfitrião, `[{id, apelido}]`, senão `null`. `partida`: 1, 2, … na sala. `sumula`: no
    `fim`, o id da súmula desta partida (`{sala}-{partida}`), senão `null`.
  - `estado` de um **pedido** esperando: `{seq, voce, fase: "pedido", agora, apelido, anfitriao}`
    (o apelido do anfitrião; nada da sala). Aceito, passa a receber o `estado` de jogador.
  - `traco` `{id, forma, cor, esp, pts, fim}`: cada pedaço repassado como chegou, a todos **menos**
    quem desenha (ele já desenhou na tela). `balde {id, cor, pt}`, idem. `desfazer {id}`,
    `limpar {}`.
  - `chute {jogador, texto}` (só os errados e longe); `acerto {jogador, pontos}`; `trave {texto}`
    (privado); `dica {dica}` (a todos menos quem desenha, que recebe um `estado` novo);
    `pulou {jogador}` (antes do `estado` do intervalo); `recusado {}` (só ao pedido, e o fluxo
    dele fecha); `fim {sumula}` (o mesmo JSON gravado na tabela; `sumula` traz `id` da partida,
    `sala` e `partida` além de jogadores e lances). O fluxo de eventos **não** fecha no `fim`.
- **Hub:** dicionário de salas em memória; um laço do lifespan chama `sala.avancar(agora)` a cada
  0,5 s e transmite o que mudou. Sala sem ninguém conectado por 10 min, ou com 3 h, é encerrada
  (uma partida em curso vai ao `fim` e grava a súmula); também a que passou 10 min no `fim` sem
  nova partida. Encerrada, sai da memória e os fluxos fecham.
  `web/prancheta.py` expõe `criar_prancheta(db_path, now, sleep, limite_salas: RateLimiter) ->
  Prancheta` (com `.router` e `.rodar()`, a tarefa do laço). No `app.py` entram só: criar o objeto
  (passando o `RateLimiter` de lá), `include_router` e iniciar/parar `.rodar()` no lifespan.
- **Banco:** `prancheta_sumulas(id TEXT PK, criada_em, encerrada_em, dados JSON, sala TEXT)` no
  mesmo SQLite, uma linha por partida, gravada ao entrar em `fim` (jogadores com
  pontos/gols/assistências; lances com quem desenhou, a palavra e quem acertou, em ordem).
  `id` = `{sala}-{partida}`, `criada_em` = início da partida. A coluna `sala` (e um índice) entrou
  em 2026-11-25 por `ALTER TABLE` na subida; súmulas antigas têm `id` = sala e `sala` nula, e
  continuam no mesmo link. Não toca no `store.py`.
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
- [x] `test_dicas_so_quando_quem_desenha_pede`, `test_dica_liberada_aos_50_e_75_porcento`,
  `test_dica_nunca_passa_de_um_terco` e `test_foto_de_quem_desenha_traz_os_marcos_das_dicas`
  (com relógio injetado; substituem `test_dicas_aos_50_e_75_porcento`, de 2026-11-24).
- [x] `test_quem_abre_o_link_pede_para_entrar`, `test_anfitriao_aceita_o_pedido`,
  `test_anfitriao_recusa_o_pedido`, `test_novo_anfitriao_herda_os_pedidos`,
  `test_pedidos_nao_ocupam_vaga_e_tem_teto`, `test_pedido_sem_conexao_cai_depois_de_30_s`; no
  servidor, `test_quem_pede_espera_e_o_anfitriao_aceita` e `test_recusado_e_avisado_e_o_fluxo_fecha`.
- [x] `test_quem_desenha_pula_e_o_lance_vai_ao_intervalo`, `test_quem_desenha_pula_na_escolha`,
  `test_so_quem_desenha_pula_409`; `test_doze_gizes_e_o_apagador` e `test_dica_e_pular_pela_rota`.
- [x] Ferramentas (2026-11-25): `test_formas_de_dois_pontos`, `test_forma_invalida_422`,
  `test_forma_nao_reaproveita_id`, `test_balde_repassado_e_na_foto_em_ordem`,
  `test_balde_invalido_422`, `test_desfazer_e_limpar_com_formas_e_balde`,
  `test_balde_e_formas_contam_no_teto`, `test_traco_sem_forma_e_livre`; no servidor,
  `test_formas_e_balde_pela_rota`.
- [x] Nova partida (2026-11-25): `test_fim_deixa_a_sala_aberta_para_nova_partida`,
  `test_anfitriao_comeca_nova_partida`, `test_nova_partida_so_do_anfitriao_e_so_no_fim`,
  `test_nova_partida_tira_ausentes_e_mantem_pedidos`, `test_no_fim_da_para_pedir_aceitar_e_sair`,
  `test_sala_fecha_dez_minutos_depois_do_fim`; no servidor, `test_nova_partida_pela_rota`,
  `test_sala_fecha_dez_minutos_depois_do_fim` e `test_tabela_antiga_ganha_a_coluna_da_sala`;
  nas páginas, `test_sala_viva_vale_mais_que_sumula` (substitui
  `test_sumula_vale_mais_que_sala_viva`) e `test_sumula_de_cada_partida_no_seu_link`.
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
Nos ajustes de 2026-11-24: pede para entrar, o anfitrião recusa um e aceita outro, paleta de 12
gizes no PC e no celular de 390 px, botão de dica travado e liberado, e pular na escolha e no
desenho.
Nas ferramentas de 2026-11-25: bandeja no PC e no celular de 390 px, uma cena com cada ferramenta
vista por quem chuta em outro tamanho de tela (miniaturas iguais), prévia da forma, desfazer e
recarregar a página (o desenho se refaz igual a partir de `tracos`). Na nova partida: tela de
`fim` do anfitrião (rodadas e "Nova partida") e de quem espera (celular), a sala de volta à
`espera` com os três, a 2ª partida começando com placar zerado e a súmula da 1ª no seu link.

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
