# Mano a Mano: batedor contra goleiro, por link ou contra o bot

- **Data:** 2026-11-25
- **Status:** proposta
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
- **Barra (minha decisão):** um só valor `barra` 0–1000, uma parada. No pênalti é precisão: fora
  da faixa boa, desvia. Na falta `por_cima` é também força: abaixo da faixa bate na barreira,
  acima sai por cima. Força não existe à parte.
- **Barreira (minha decisão):** `x` na mesma projeção 0–1000 da boca do gol vista da posição da
  falta; cobre `n × 110` de largura centrada em `x`, até 45% da altura (os jogadores pulam).
  Sem geometria do campo: a posição sorteada só muda o desenho e um desvio fixo da curva.
- **Saída (minha decisão):** os dois travam → evento `cobranca_inicio {chute_em}` (relógio do
  servidor, 1,5 s à frente: corrida do batedor). Janela de 600 ms a partir de `chute_em`; o
  servidor só resolve e manda `cobranca` (escolhas + resultado) quando a janela fecha.
- **Prazos:** 10 s para a barreira e para cada escolha; acabou, escolha ao acaso.
- **Equilíbrio:** ~60% de gols com os dois lados aleatórios, definidos como: `alvo` uniforme na
  boca do gol, `barra` uniforme, lado do goleiro uniforme, saída na janela em 50%, barreira e
  trajetória uniformes.
- **Goleiro tapado na falta (minha decisão na fatia 1, a confirmar com o dev):** na falta, a bola
  que o goleiro alcança só vira defesa em 40% (`P_DEFESA_FALTA`); o resto entra e o `Lance` sai
  com `tapado=True` para o replay mostrar. Sem isso a barreira (bloqueia ~17% das faltas) deixa a
  falta ~12 pp abaixo do pênalti e nenhuma constante comum põe os dois modos em 55–65%.
- **Disputa:** 5 cobranças para cada um, alternando os papéis, e acaba antes quando não dá mais
  para alcançar (como a disputa de verdade); empate → alternadas até alguém errar. Quem cria a
  sala escolhe o modo.
- **Bot:** `facil` escolhe ao acaso; `medio` tem manias (lado preferido); `dificil` lê o padrão
  do adversário (últimas escolhas dele na partida) e pula ou mira contra ele. Acerta a saída em
  30/50/70% por nível.
- **Abandono (minha decisão):** quem sai ou fica 30 s sem conexão perde por W.O.; a súmula é
  gravada com o placar até ali e a marca "W.O.".
- **Câmeras (dev, rascunho B):** quem bate vê de trás do batedor; quem defende, de dentro do gol,
  de costas para a rede. O replay de cada lance roda na câmera de cada um.

## Contratos

- **Regras puras** `geral/games/mano/`: `regras.py` (`resolver(cobranca, defesa, barreira,
  posicao, rng) -> Lance`), `bot.py` (`escolher(nivel, papel, historico, rng)`), `sala.py` (fases
  `espera → barreira? → escolha → cobranca → resultado → … → fim`, relógio injetado, devolve
  `list[Evento]` como a `Sala` da Prancheta). Tipos Pydantic em `tipos.py`.
- **Rotas** (prefixo `/api/jogos/mano`): `POST /salas {apelido, modo: "penaltis"|"faltas",
  bot: null|"facil"|"medio"|"dificil"}` → `{id, jogador, token}`; `POST /salas/{id}/entrar
  {apelido}` (409 cheia); `POST /salas/{id}/acao {token, tipo}` com `tipo` ∈ `barreira{n, x} |
  chute{alvo, barra, trajetoria?, curva?} | defesa{lado} | saida{ms} | revanche | sair`;
  `GET /salas/{id}/eventos?token=` (SSE). Páginas `GET /jogos/mano` e `/jogos/mano/s/{id}`.
- **Privacidade:** a escolha de um nunca chega ao outro antes de os dois travarem (decidido
  dentro da `Sala`). `saida` vale se chegar ao servidor dentro da janela (+150 ms de folga para a
  rede); o cliente anima a corrida até `chute_em` e o voo da bola com o resultado de `cobranca`.
- **Front:** Three.js fixado numa versão, vendorizado em `static/vendor/` (sem npm/CDN), cena
  low-poly sombreada chapada na paleta da Geral (lâmpada, concreto, papel, gramado), placar de
  lâmpadas em HTML por cima do canvas, Fullscreen API.
- **Banco:** `mano_sumulas(id PK, criada_em, encerrada_em, dados JSON)`, gravada no `fim`.
- **Limites:** criar sala 20/h por rede (`RateLimiter`); 1 ação a cada 0,3 s por jogador.

## Critérios de aceite (como testes)

- [ ] `test_escolha_nunca_vaza`: dado o batedor travado, quando o goleiro recebe eventos, então nada traz o alvo até `cobranca`.
- [ ] `test_goleiro_no_lado_certo_defende_ate_meia_altura` e `test_angulo_so_em_parte`.
- [ ] `test_barra_fora_da_faixa_desvia` e `test_faixa_estreita_perto_da_trave`.
- [ ] `test_saida_no_tempo_alcanca_o_vizinho` e `test_saida_fora_da_janela_nao_conta`.
- [ ] `test_barreira_bloqueia_rasteira` e `test_por_cima_fraco_bate_na_barreira`.
- [ ] `test_calibragem`: 10 mil lances aleatórios × aleatórios → 55–65% de gols, nos dois modos.
- [ ] `test_bot_dificil_pune_quem_repete`: batedor que sempre mira à esquerda marca < 40% contra ele.
- [ ] `test_disputa_alternada_e_morte_subita` e `test_prazo_estourado_escolhe_ao_acaso`.
- [ ] `test_sala_cheia_409`, `test_token_de_outra_sala_403`, `test_acao_fora_da_fase_409`.
- [ ] `test_revanche_zera_e_grava_sumula_de_cada_partida` e `test_quem_sai_perde_por_wo`.
- [ ] `test_disputa_acaba_quando_nao_da_mais_para_alcancar`.

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
