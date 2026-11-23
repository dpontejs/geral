# Carreira: modos Rápida e Completa, dia a dia e tela nova

- **Data:** 2026-11-16
- **Status:** aprovada. **Atualização 2026-11-23:** a Rápida saiu da tela a pedido do dev; só a
  Completa é oferecida (padrão da API também). O motor continua refazendo carreiras Rápidas, para
  os links antigos abrirem. A personalização passa a ser "com ou sem minijogos" (vem com o pênalti).
- **ADRs:** —
- **Depois de:** `carreira.md` (motor e primeira tela). Projeto 1 de 5: base → Nordeste →
  veredito das torcidas → capa da Geral → desafio com o mesmo sorteio.

## Objetivo

O dev testou a primeira tela: ritmo rápido demais, troca de clube sem ter escolhido, coluna de
números solta e sem graça. Agora: **uma versão só** (sem edição por time) e **dois modos**:
**Rápida** (~1 min, como hoje, até 4 perguntas) e **Completa** (temporada a temporada: uma
situação de **dia a dia** com % de chance por temporada e o **mercado só com o aceite** do
torcedor). Tela nova, menos placar e mais jornal esportivo.

## Fora de escopo

- Nordeste, veredito das torcidas, capa da Geral, desafio (projetos 2 a 5).
- Goleiro; minijogos jogáveis.

## Contratos

- **Edição única:** `/jogos/carreira` (as rotas `/{edição}` somem; a antiga `/jogos/carreira/vasco`
  redireciona para `/jogos/carreira`). O torcedor escolhe o clube de partida entre todos os
  brasileiros; draft só com lendas `geral`.
- `Entrada.modo: Literal["rapida", "completa"] = "rapida"` (vai no código compartilhável).
- **Dia a dia** (`carreira/rotina.toml`, ≥ 30 situações: treino extra, folga, imprensa, festa,
  dieta, vídeo dos adversários, conversa com o técnico, mudar de posição no treino, ajudar a base,
  jogar no sacrifício…): `[[rotina]] id, texto, condicao, [[rotina.opcao]] texto, chance (0–100),
  bonus (atributo que soma (nota−70)/2 à chance, opcional), sucesso = Efeito, fracasso = Efeito`.
  `Efeito` ganha `atributos = {finalizacao = 3}` (a nota geral é recalculada). Uma por
  temporada dos 17 anos em diante, só no modo Completa; o resultado vale para a temporada que vem.
- **Mercado** no modo Completa: nenhuma transferência sem pergunta. A proposta que o mercado
  faria vira `Escolha` ("O {destino} quer {nome}" — aceitar / ficar). Exceções sem pergunta, com
  manchete própria: volta de empréstimo e dispensa (nota ≪ nível do clube). No modo Rápida a
  transferência segue automática, mas a temporada mostra "chegou do X" para não pegar de surpresa.
- `Escolha` ganha `tipo: Literal["dia", "mercado", "decisao"]` e, por opção, `chance: int | None`
  e `efeitos: str` ("+3 finalização · 30%: lesão leve"). `Temporada` ganha `chegou_de: str | None`
  e `rotina: {situacao, escolha, deu_certo, efeito} | None`.
- `escolhas` até 60 (Completa tem ~20–30 respostas).
- **Tela** (decisão minha, mostrada rodando antes do commit): topo fixo pequeno no estilo
  placar (nome, idade, clube, nota geral); a **temporada atual em destaque** como recorte de
  jornal (ano/idade, clube grande, jogos · gols · assistências em linha, taças em selos, a
  manchete em letra de título); as anteriores numa **linha do tempo** compacta; decisões como
  cartões por opção com **barra de chance** (verde/vermelho) e efeitos. Rápida: avança sozinha a
  ~1,8 s por temporada, toque para adiantar; Completa: botão "Jogar a temporada".

## Critérios de aceite (como testes)

- [x] `test_completa_pergunta_o_dia_a_dia_toda_temporada` (17+ anos, até a aposentadoria).
- [x] `test_completa_nao_troca_de_clube_sem_aceite` (só volta de empréstimo e dispensa, com manchete).
- [x] `test_chance_do_dia_a_dia_bate_com_o_sorteio` (2.000 rolagens: frequência ±4 p.p. da chance mostrada).
- [x] `test_efeito_de_atributo_muda_a_nota_da_temporada_seguinte`.
- [x] `test_rapida_mostra_de_onde_veio_quem_chegou` (`chegou_de` em toda troca).
- [x] `test_prefixo_estavel_nos_dois_modos` e `test_toda_rotina_e_alcancavel`.
- [x] `test_edicao_de_time_redireciona_para_a_unica`.

## Verificação ponta a ponta

Playwright: uma carreira Rápida e uma Completa inteiras (desktop 1280 e celular 390), sem erro
de JS nem rolagem lateral; fotos de cada etapa para o dev aprovar antes do commit do visual.
