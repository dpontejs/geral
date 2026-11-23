# Carreira: o pênalti decisivo (primeiro minijogo)

- **Data:** 2026-11-23
- **Status:** aprovada
- **ADRs:** —

## Objetivo

Um momento de destaque jogável dentro da carreira: a final de copa decidida num pênalti que o
torcedor bate, com a mecânica e o visual do rascunho aprovado pelo dev (mira que passeia, barra
de força em lâmpadas, goleiro que mergulha, placar de lâmpadas e recorte de jornal). Inspiração:
GAMBETA (`docs/pesquisa/joguinhos-de-carreira.md`). É **destaque, não progressão**: decide um título
e uma marca, não mexe na evolução do jogador.

## Fora de escopo

- Falta, passe, cabeçada e outros lances (próximos minijogos, depois de medir este).
- Goleiro jogável; disputa de pênaltis em série (é uma cobrança só).
- Antitrapaça: o resultado vem do navegador; é um jogo para compartilhar, não um ranking.

## Contratos

- **Quando:** depois dos números da temporada, se o clube tem `liga.copa` e o jogador é atacante ou
  meia, sorteia-se "chegou à final da copa" (chance calibrada para que, **sem minijogos**, a taxa de
  títulos de copa fique a ±20% da de hoje). Se chegou, a final vai para o pênalti. No máximo
  **2 lances por carreira**. O sorteio acontece antes da pergunta, para o replay ficar estável.
- `Entrada.minijogos: bool = False` (links antigos não têm lance). A tela manda `True` ou `False`
  conforme a chave "com/sem minijogos" do formulário (padrão: com). Entra no código do link:
  1 bit a mais no formato binário, e um código antigo decodifica como `False`.
- **Com minijogos:** o motor devolve `Escolha(tipo="lance", id="penalti-final", ...)`, com
  `opcoes = ["gol", "defesa", "fora", "trave", "motor"]` e `info[0].chance` igual à **finalização**
  do jogador (a tela usa essa nota como dificuldade). A resposta é o índice do resultado; `4`
  ("deixar o motor bater") sorteia como sem minijogos.
- **Sem minijogos (ou resposta 4):** gol com `p = clamp(0.45 + (finalizacao - 60) / 100, 0.35, 0.85)`.
- **Resultado:** gol → o título da copa entra na temporada, com a manchete de pênalti decisivo e a
  marca `frio-na-marca-da-cal`; erro → sem título, com a manchete do erro e a marca
  `perdeu-o-penalti`. Se o PR de conteúdo já tiver uma marca equivalente (por exemplo,
  `frio-nas-decisoes`), use a existente.
- `Temporada.lance: ResultadoLance | None` (`resultado`, `adversario`, `manchete`), para a linha do
  tempo e o card mostrarem o lance.
- **Tela:** `static/geral/penalti.js` (módulo novo, a partir do rascunho), aberto quando
  `pendente.tipo == "lance"`. O placar mostra o clube contra o adversário (o rival do clássico,
  se a copa for estadual, ou outro clube da liga), "90+4'" e o nome da copa. O controle de teste
  "Finalização" sai: a dificuldade vem de `info[0].chance`. Funciona com clique, toque e espaço.
  Botão "Deixar o motor bater".
- Formulário: no lugar do antigo seletor de modo, uma chave com dois cartões, **Com minijogos** e
  **Sem minijogos**, no mesmo estilo dos cartões antigos.

## Critérios de aceite (como testes)

- [ ] `test_final_vai_para_o_penalti`: dado atacante num clube com copa, em N sementes aparece uma
  `Escolha(tipo="lance")` com a finalização em `info[0].chance`.
- [ ] `test_gol_da_o_titulo_e_erro_tira`: respondendo 0, a temporada tem o título da copa e a marca
  de gol; respondendo 1, 2 ou 3, não tem o título e tem a marca de erro.
- [ ] `test_sem_minijogos_nao_pergunta_e_sorteia_pela_finalizacao`: com `minijogos=False` não há
  pendente `lance`; em 2000 sorteios, a taxa de gol fica perto de `p` (finalização alta > baixa).
- [ ] `test_motor_bate_quando_pedido`: a resposta 4 dá o mesmo resultado que `minijogos=False`.
- [ ] `test_no_maximo_dois_lances_e_so_atacante_ou_meia`.
- [ ] `test_taxa_de_copas_sem_minijogos_parecida_com_a_de_hoje` (±20% em 1000 carreiras).
- [ ] `test_link_guarda_minijogos_e_codigo_antigo_abre`: ida e volta com `minijogos=True`; um código
  fixado do formato atual decodifica com `False`.
- [ ] `test_realismo_continua`: `test_carreira_realismo.py` passa sem ajuste no teste.
- [ ] Web: `test_formulario_tem_a_chave_de_minijogos` e o payload do `lance`.

## Verificação ponta a ponta

```bash
uv run pytest tests/test_carreira_*.py tests/test_web_carreira.py
```

Subir o app localmente e jogar no navegador (celular e computador): uma carreira com minijogos até
cair num pênalti, bater, ver o título (ou não) na linha do tempo, a marca e o card; abrir o link
compartilhado e ver o mesmo resultado; outra carreira sem minijogos. Mandar as fotos ao dev antes de
commitar o visual.

## Riscos e dúvidas abertas

- Frequência: 2 lances numa carreira de ~20 temporadas pode ser pouco ou muito; medir jogando.
- O rascunho foi feito para tela vertical (~440 px); no computador, centralizar no mesmo tamanho.
