# Mano a Mano: batedor contra goleiro, por link ou contra o bot

- **Data:** 2026-11-25
- **Status:** entregue (PRs #107–#114); **faltas desligadas** por `MANO_FALTAS` (padrão `False`)
  até o dev refinar (2026-11-25): a página só oferece pênaltis e a API recusa `modo: "faltas"` (422)
- **ADRs:** — (Three.js como primeira dependência de front: nas Decisões do PLAN)

## Objetivo

Duelo de leitura entre batedor e goleiro, em tela cheia no computador: cada um escolhe às
escondidas, a cobrança acontece e quem leu melhor o outro leva. Contra o bot (3 níveis) ou contra
um amigo numa sala por link, em **pênaltis** ou **faltas diretas**. Nasceu de um jogo de reflexo
que o dev jogava; o reflexo puro foi descartado (a rede decide a defesa) em favor da adivinhação.
Nome provisório: "Mano a Mano" (decisão minha; o dev pode trocar).

## Fora de escopo

- Reflexo de verdade (goleiro arrastando a luva até a bola), ranking, sala com mais de 2,
  campeonato, celular em pé (no celular só deitado, como segundo plano).
- Reaproveitar `penalti.js` (decisão do dev: cena nova e mais elaborada).
- Sobreviver a deploy (sala em memória, como a Prancheta).

## Regras (decididas com o dev em 2026-11-25)

- **Batedor:** mira livre num ponto do gol `alvo=(x, y)` em 0–1000 (largura × altura), depois
  para a barra de força/precisão. A faixa boa da barra estreita perto da trave e do travessão;
  fora da faixa a bola desvia na direção do erro (trave ou fora). Na falta, escolhe também a
  trajetória: `rasteira | por_cima | pelo_lado` e a curva (−1 a 1).
- **Goleiro (mais fácil, pedido do dev):** só 3 escolhas, `esquerda | fica | direita`; a altura
  é automática. O pulo cobre o seu terço inteiro até a meia altura; o ângulo (faixa de cima, perto
  da trave) só em parte. Ficar cobre o centro inteiro.
- **Tempo da saída = bônus:** depois que os dois travam, a cobrança começa; o goleiro aperta uma
  tecla, e acertando a janela alcança até a beira do terço vizinho. Errar só tira o bônus.
- **Falta:** antes das escolhas, o goleiro arma a **barreira** (2 a 5 jogadores, posição na linha),
  que o batedor vê. A barreira bloqueia a `rasteira` e a `pelo_lado` que passam por ela; `por_cima`
  com força baixa demais bate nela, alta demais sai. Posições sorteadas: meia-lua, entradas da área.
- Na falta o goleiro é o mesmo do pênalti; a barreira é o que torna a falta mais difícil. Bola
  alcançada é sempre defendida (dev, 2026-11-25).
- **Barra (minha decisão):** um só valor `barra` 0–1000, uma parada. No pênalti é precisão: fora
  da faixa boa, sobe ou sai fraca (ver abaixo, 2026-11-26). Na falta `por_cima` é também força: abaixo da faixa bate na barreira,
  acima sai por cima. Força não existe à parte.
- **Barreira (minha decisão):** `x` na mesma projeção 0–1000 da boca do gol vista da posição da
  falta; cobre `n × 110` de largura centrada em `x`, até 45% da altura (os jogadores pulam).
  Sem geometria do campo: a posição sorteada só muda o desenho e um desvio fixo da curva.
- **Saída (minha decisão):** os dois travam → evento `cobranca_inicio {chute_em}` (relógio do
  servidor, 1,5 s à frente: corrida do batedor). Janela de 600 ms a partir de `chute_em`; o
  servidor só resolve e manda `cobranca` (escolhas + resultado) quando a janela fecha.
- **Prazos:** 10 s para a barreira e para cada escolha; acabou, escolha ao acaso.
- **Equilíbrio:** 50–60% no pênalti (era ~60%; dev, 2026-11-26: pênalti mais difícil para o
  batedor), ~45–50% na falta (dev, 2026-11-25), com os dois lados
  aleatórios, definidos como: `alvo` uniforme na boca do gol, `barra` uniforme, lado do goleiro
  uniforme, saída na janela em 50%, barreira e trajetória uniformes.
- **Disputa:** 5 cobranças para cada um, alternando os papéis, e acaba antes quando não dá mais
  para alcançar (como a disputa de verdade); empate → alternadas até alguém errar. Quem cria a
  sala escolhe o modo; quem começa batendo é sorteado a cada partida (dev, 2026-11-25).
- **Bot:** `facil` escolhe ao acaso; `medio` tem manias (lado preferido); `dificil` lê o padrão
  do adversário (últimas escolhas dele na partida) e pula ou mira contra ele. Acerta a saída em
  30/50/70% por nível.
- **Abandono (minha decisão):** quem sai ou fica 30 s sem conexão perde por W.O.; a súmula é
  gravada com o placar até ali e a marca "W.O.".
- **Pênalti mais difícil para o batedor (dev, 2026-11-26):** no pênalti o erro da barra tem
  direção. **Acima** da faixa a bola sobe a partir da mira (`SUBIDA_POR_ERRO` = 2 por unidade de
  erro): um pouco acima no alto bate no travessão, bem acima isola (letreiro "ISOLOU"). **Abaixo**
  da faixa é chute fraco: a bola cai a partir da mira (`QUEDA_POR_ERRO` = 2: bola fraca não chega
  no ângulo) e o alcance do goleiro cresce 1 por unidade de erro, até `ALCANCE_FRACO` (= o bônus
  da saída, 90), somado à saída, em qualquer altura, e pega o ângulo do seu lado; não é defesa
  automática (o canto oposto segue gol). A falta segue com o desvio simétrico de antes. A barra
  ficou 30% mais rápida na cena (volta inteira em 1 s em vez de 1,3 s). E o pênalti ganhou faixa
  própria, mais estreita (`FAIXA_PENALTI_*`): 120 na trave ou no travessão, +1 por unidade de
  distância, até 450 no meio (a da falta seguiu 250–500 × 0,95). Mirando no canto (x = 90), a
  faixa tem 210: com a barra a 2 unidades por ms, a janela é de ~105 ms, duas vezes por volta.
- **Cavadinha (dev, 2026-11-26):** só no pênalti, um botão no lugar da mira. `Chute.cavadinha`
  (padrão `false`); a mira é ignorada (vai a `(500, 500)`). Faixa própria e mais estreita
  (`FAIXA_CAVADINHA` = 160, fixa). Na faixa: goleiro que `fica` defende, goleiro que pula para
  qualquer lado (com ou sem saída) toma o gol. Acima da faixa sai por cima; abaixo, o goleiro se
  recupera e defende. Na falta a sala descarta o campo. O bot `dificil` goleiro fica (90%) quando
  o humano bateu 2 cavadinhas nas últimas 3; o bot batedor cava de vez em quando (4% no `medio`,
  6% no `dificil`, nunca no `facil`). Na calibragem o batedor aleatório cava 5% dos pênaltis.
  O voo da cavadinha na tela é mais longo (1150 ms contra 600): o servidor segura o resultado
  550 ms a mais (`VOO_CAVADINHA_A_MAIS`), para a próxima cobrança não atropelar a animação.
- **Time de cada jogador (dev, 2026-11-26):** ao criar e ao entrar, cada um escolhe um dos 6 times
  da Geral (`teams.toml`, em ordem alfabética); o bot sorteia um time diferente do humano. O
  placar e a súmula mostram os times ("FLAMENGO × ABC") com o apelido ao lado; as lâmpadas seguem
  amarelas, cor de clube só no uniforme (o dev recusou cor de clube no painel). Uniformes simples
  na cena (camisa com o padrão do clube numa textura pequena, calção e meião lisos, sem escudo nem
  marca); o goleiro veste um uniforme neutro com uma faixa da cor do time. Os dois com o mesmo
  time vale (Fla × Fla): quem entrou depois veste o reserva (`uniforme: "fora"`).
- **Câmeras (dev, rascunho B):** quem bate vê de trás do batedor; quem defende, de dentro do gol,
  de costas para a rede. O replay de cada lance roda na câmera de cada um.
- **Jogadores arredondados (dev, 2026-11-26, maquete "A · arredondado, proporção real"):** no
  lugar das caixas, tronco em cápsula, calção em cilindro, pescoço, cabeça redonda com cabelo,
  braços e pernas em cápsulas com quadril/joelho e ombro/cotovelo, chuteira arredondada,
  sombreado suave (`MeshStandardMaterial`) e sombra do sol só dos jogadores, da bola e do gol. Sem
  rosto. A camisa é uma textura por jogador que dá a volta no tronco: o padrão do clube só no
  peito e nas costas (a faixa do Vasco não passa para os lados), lados e mangas lisos (`lado`),
  ou os aros do Flamengo dando a volta; o goleiro de cada clube com manga comprida e luvas.
- **Animação de desenho animado (dev, 2026-11-26, opção C):** o batedor dá um passo atrás
  agachado antes de correr, arma a perna perto da bola e segura (tremendo) até o resultado chegar,
  e bate rápido com a perna seguindo; a bola achata no pé e voa esticada na direção do voo; o
  goleiro estica o corpo no mergulho e passa um pouco do ponto antes de voltar (ease-out-back);
  estouro de linhas de papel na batida e de lâmpada na rede no gol, com a tela tremendo um
  instante (sem tremor para quem pede menos movimento no sistema). Os tempos do servidor não
  mudam: a batida é na janela fechada (`chute_em` + 600 ms), o voo dura o mesmo (a cavadinha,
  550 ms a mais), o achatado sai do tempo de voo.
- **Um batedor diferente a cada cobrança (dev, 2026-11-26):** cor de pele, cabelo (curto,
  raspado, black, topo crespo, careca, moicano, coque), cor do cabelo, faixa na cabeça às vezes,
  altura ±5% e número nas costas (7, 9, 10, 11, 8, 19, 17, 21...). Vem de `mano-visual.js`, puro,
  semeado pela sala, pela partida e pela contagem da cobrança, então os dois navegadores veem o
  mesmo batedor; cabelo e número mudam sempre de uma cobrança para a seguinte. O goleiro de cada
  um é sempre o mesmo na sala (semente: sala + vaga + time) e veste a 1.
- **Súmula sem o lance a lance (dev, 2026-11-26):** a tela do fim e a página da súmula mostram
  o placar, os times, quem venceu (ou "Sem vencedor", e o W.O.), o link e os botões; a lista de
  cobranças (quem bateu, o que deu) saiu. O servidor segue gravando `cobrancas` na súmula, e as
  súmulas antigas abrem do mesmo jeito.
- **Mirar alto custa (dev, 2026-11-26):** quanto mais alta a mira, mais rápida a barra. Até
  y = 600 nada muda (uma volta em 1 s); de 600 ao travessão a velocidade sobe em linha reta até
  +45% (volta em ~690 ms). A cavadinha mantém o ritmo. Só tempo no navegador
  (`pressaBarra`/`periodoBarra` em `mano-faixa.js`): a regra da faixa no servidor não muda. Com a
  barra apressada a moldura dela pisca no ritmo da varredura (fixa para quem pede menos
  movimento) e, na primeira vez em cada navegador, a dica diz "Mais alto, barra mais rápida: pare
  na faixa acesa". Vale também na falta (o pedido não a excluiu).
- **Taça no fim (dev, 2026-11-26):** quando a partida acaba com vencedor (também por W.O. e
  contra o bot), a cena mostra a comemoração de quem venceu, igual nos dois navegadores (quem
  perdeu vê o outro time comemorar): o batedor e três companheiros (visuais variados de
  `mano-visual.js`, semente sala + partida, uniforme do time) e o goleiro do time (o mesmo da
  partida, a 1) juntos perto da marca do pênalti. Um levanta uma taça simples low-poly amarelo
  lâmpada (nenhuma taça de verdade), os outros pulam de braços para cima, confete amarelo sai da
  taça e a câmera gira devagar em volta. O letreiro, embaixo, diz "<TIME> CAMPEÃO". Dura 7 s e
  segura a última pose; a tela do fim (placar, revanche, súmula) segue logo abaixo, e a rolagem
  até a revanche espera a festa. Com menos movimento pedido no sistema: câmera parada, sem
  confete nem pulos, taça já no alto. A revanche desfaz tudo (`reiniciar`) e libera materiais e
  texturas da festa. Fica em `mano-festa.js` (tempo e elenco puros, testados com node). Empate
  sem vencedor segue com "FIM DE JOGO".
- **Corrida com passada (dev, 2026-11-26):** a corrida do batedor é um ciclo de marcha ligado à
  distância percorrida (2,25 ciclos, o pé não escorrega): coxas alternando, joelho dobrando no
  balanço para trás e cedendo um pouco no apoio, braços contra as pernas com cotovelo dobrado,
  tronco inclinado com um leve sobe e desce. Ela termina com a perna do chute atrás e a outra
  chegando para plantar, e se mistura em 160 ms na paradinha e na armada. Os tempos não mudam
  (a batida segue na janela fechada depois de `chute_em`).
- **Animação refinada no estilo cartum (dev, 2026-11-27):** substitui a passada acima. A corrida
  são quatro passos com pegadas fixas no chão (IK de duas articulações na perna: o quadril passa
  por cima do pé plantado, nada escorrega), o último mais longo até o pé de apoio ao lado da
  bola; o batedor corre de frente para a corrida e gira para o gol no fim. Na armada ele inclina
  para trás e para o lado do apoio, abre o braço livre e engatilha a perna do chute (corpo um
  pouco achatado); a batida estica o corpo, o joelho estala reto logo antes do contato e a perna
  sobe no acompanhamento, desce um passo à frente com um pulinho no pé de apoio. Um resultado
  atrasado ganha 50 ms para o balanço inteiro antes de a bola sair (sem salto de pose). O
  goleiro dá um split step na armada do batedor, carrega para o lado e mergulha com os braços
  indo para a bola (o de perto pelo lado, o de longe por cima do rosto, nunca para trás); bola
  alta voa subindo, bola baixa cai de lado; chega ao ponto quando a bola chega, cai na grama e
  achata no pouso. Cabeça e cabelo vêm um tempo atrás (movimento secundário). Tudo é função do
  relógio da cobrança (nada de aleatório nem dt), igual nos dois navegadores; com menos movimento
  pedido no sistema saem o achatar/esticar, o pulinho, o passar do ponto e o cabelo.

## Contratos

- **Regras puras** `geral/games/mano/`: `regras.py` (`resolver(cobranca, defesa, barreira,
  posicao, rng) -> Lance`), `bot.py` (`escolher(nivel, papel, historico, rng)`), `sala.py` (fases
  `espera → barreira? → escolha → cobranca → resultado → … → fim`, relógio injetado, devolve
  `list[Evento]` como a `Sala` da Prancheta). Tipos Pydantic em `tipos.py`.
- **Rotas** (prefixo `/api/jogos/mano`): `POST /salas {apelido, time, modo: "penaltis"|"faltas",
  bot: null|"facil"|"medio"|"dificil"}` → `{id, jogador, token}`; `POST /salas/{id}/entrar
  {apelido, time}` (409 cheia; `time` fora da lista, 422); `POST /salas/{id}/acao {token, tipo}` com `tipo` ∈ `barreira{n, x} |
  chute{alvo, barra, trajetoria?, curva?, cavadinha?} | defesa{lado} | saida{ms} | revanche | sair`;
  `GET /salas/{id}/eventos?token=` (SSE). Páginas `GET /jogos/mano` e `/jogos/mano/s/{id}`.
- **Privacidade:** a escolha de um nunca chega ao outro antes de os dois travarem (decidido
  dentro da `Sala`). `saida` vale se chegar ao servidor dentro da janela (+150 ms de folga para a
  rede); o cliente anima a corrida até `chute_em` e o voo da bola com o resultado de `cobranca`.
- **Front:** Three.js fixado numa versão, vendorizado em `static/vendor/` (sem npm/CDN), cena
  low-poly na paleta da Geral (jogadores arredondados, sombreado suave) (lâmpada, concreto, papel, gramado), placar de
  lâmpadas em HTML por cima do canvas, Fullscreen API.
- **Banco:** `mano_sumulas(id PK, criada_em, encerrada_em, dados JSON)`, gravada no `fim`.
- **Limites:** criar sala 20/h por rede (`RateLimiter`); 1 ação a cada 0,3 s por jogador.

## Critérios de aceite (como testes)

- [x] `test_escolha_nunca_vaza`: dado o batedor travado, quando o goleiro recebe eventos, então nada traz o alvo até `cobranca`.
- [x] `test_goleiro_no_lado_certo_defende_ate_meia_altura` e `test_angulo_so_em_parte`.
- [x] `test_barra_fora_da_faixa_desvia` e `test_faixa_estreita_perto_da_trave`.
- [x] `test_um_pouco_acima_da_faixa_no_alto_e_travessao`, `test_abaixo_da_faixa_e_chute_fraco_que_o_goleiro_alcanca`,
  `test_chute_fraco_no_alto_cai_e_o_goleiro_pega` e `test_chute_fraco_nao_e_defesa_automatica`.
- [x] `test_cavadinha_contra_quem_fica_e_defesa_e_contra_quem_pula_e_gol`,
  `test_cavadinha_tem_faixa_mais_estreita` e `test_bot_dificil_fica_contra_quem_repete_a_cavadinha`.
- [x] `test_quem_acerta_a_barra_no_canto_ainda_perde_alguns`: batedor "humano" (canto, barra perto do
  centro da faixa) contra goleiro que acerta o lado metade das vezes; a taxa medida vai no PR.
- [x] `test_saida_no_tempo_alcanca_o_vizinho` e `test_saida_fora_da_janela_nao_conta`.
- [x] `test_barreira_bloqueia_rasteira` e `test_por_cima_fraco_bate_na_barreira`.
- [x] `test_calibragem`: 10 mil lances aleatórios × aleatórios → 50–60% de gols no pênalti e
  45–50% na falta.
- [x] `test_bot_dificil_pune_quem_repete`: batedor que sempre mira à esquerda marca < 40% contra ele.
- [x] `test_disputa_alternada_e_morte_subita` e `test_prazo_estourado_escolhe_ao_acaso`.
- [x] `test_sala_cheia_409`, `test_token_de_outra_sala_403`, `test_acao_fora_da_fase_409`.
- [x] `test_revanche_zera_e_grava_sumula_de_cada_partida` e `test_quem_sai_perde_por_wo`.
- [x] `test_disputa_acaba_quando_nao_da_mais_para_alcancar`.
- [x] `test_mirar_alto_acelera_a_barra` e `test_pressa_nao_depende_do_lado` (node roda `mano-faixa.js`).
- [x] `test_elenco_igual_nos_dois_navegadores_com_o_goleiro_de_sempre`, `test_festa_dura_uns_7_segundos_e_segura`,
  `test_menos_movimento_fica_parado` e `test_letreiro_do_campeao` (node roda `mano-festa.js`).

## Verificação ponta a ponta

`uv run pytest -n auto`; app local + Playwright com 2 navegadores (um batedor, um goleiro) num
pênalti e numa falta, e uma partida contra o bot; fotos em tela cheia ao dev antes do merge.

## Fatias (um PR cada)

0. Esta página + decisão no PLAN. 1. **Regras + bot + calibragem** (Python puro).
2. **Servidor** (sala, hub, rotas, SSE, súmula). 3. **Rascunho da cena** em Three.js com eventos
falsos, as duas câmeras, pênalti e falta → fotos ao dev. 4. **Tela ligada ao servidor** + entrada
em /jogos. 1 e 3 andam em paralelo.

## Riscos e dúvidas abertas

- A barra e a saída são medidas no navegador: dá para trapacear. Aceito (jogo entre amigos).
- Three.js puxa o visual para "jogo 3D genérico"; a cena precisa de paleta e formas da Geral.
