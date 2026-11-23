# Carreira: realismo (draft com gente de verdade e carreiras que podem não decolar)

- **Data:** 2026-11-17
- **Status:** aprovada (no chat, 2026-11-17)
- **ADRs:** —
- **Entre os projetos 4 e 5** (vem antes do desafio com o mesmo sorteio).

## Objetivo

O dev achou as carreiras irreais: o draft nunca dá errado e quase toda carreira decola. Medido
(200 carreiras, draft escolhido como uma pessoa escolhe): 0% não decolam, 78% viram craques
mundiais, auge mediano 94; draft mediano 80 porque as 9 opções são todas lendas (46% das notas
≥ 80). Meta **equilibrada**: com um bom draft, de 10 carreiras, 2–3 não decolam, 4–5 bons
profissionais, 2–3 craques, uma lenda de vez em quando.

## Fora de escopo

- Esconder os números do draft (modo purista); minijogos.

## Contratos

- **Draft com gente de verdade:** a oferta tem **10 nomes** (8 da vez + 2 reservas para os **2
  sorteios**): **1 lenda** curada (o achado do draft) e **9 jogadores reais conhecidos** da base
  do jogo da velha. *Conhecido* (`jogadores.conhecido`, revisto em 2026-11-23): brasileiro (sem
  país esportivo/cidadania além do Brasil, ou jogou pela Seleção — Marcelo, Marquinhos) e fama
  (nº de Wikipédias) ≥ 40, ou Seleção com fama ≥ 20, ou passou por clube nordestino com fama ≥ 25.
  `carreira/conhecidos.toml` dá o nome de torcedor a quem a base lista pelo nome de registro
  (Marcelo Vieira da Silva Júnior → Marcelo) e tira quem é mais conhecido como técnico (Felipão,
  Tite…) e os nomes de registro sem apelido confirmado.
  Pool: **455 jogadores de linha**, **142 do Nordeste** (antes: todos os ~5.050 de linha). Nota dos jogadores por fórmula, determinística pelo id: nível pela fama (fama 20 ≈ 62, fama 40 ≈ 67,
  fama 80+ ≈ 72; recalibrado com o pool novo para o draft cuidadoso continuar em ~71 de mediana,
  média 70,6 antes, 71,0 depois), perfil pela posição (atacante finaliza, zagueiro marca e cabeceia,
  meio-campo passa e dribla, lateral corre), ruído de ±6. Quem começa no Nordeste: a lenda é da
  região e ≥ 3 jogadores da região (passaram por clube nordestino). `Lenda.tipo: "lenda" |
  "jogador"` e `Lenda.resumo` ("Atacante · 1997–2018") para a tela. A versão dos dados passa a
  incluir a base.
- **Realização:** o draft é potencial. Cada carreira sorteia quanto se realiza
  (`teto = 45 + (geral do draft − 45) × r`, `r` sorteado) e o crescimento anual depende de jogar
  (minutos) e da **forma** da temporada; clube grande demais antes dos 21 trava o crescimento.
  **Forma** por temporada (sorteio) mexe nos números e uma temporada muito ruim ganha manchete
  própria. **Lesão grave** baixa o teto para sempre. **Dia a dia** com risco maior (chance das
  opções arriscadas menor).
- `Escolha`/API sem mudança de formato; `oferta` devolve 10; `montar` aceita 8 de 10.

## Critérios de aceite (como testes)

- [x] `test_oferta_tem_uma_lenda_e_nove_jogadores_reais` (e 2 sorteios: 10 nomes, 8 distintos usados).
- [x] `test_os_jogadores_do_draft_sao_conhecidos` (pool entre 300 e 500; todo jogador da oferta passa no critério).
- [x] `test_estrangeiro_e_desconhecido_ficam_fora`.
- [x] `test_nota_de_jogador_da_base_segue_fama_e_posicao` (determinística; atacante finaliza mais que marca).
- [x] `test_quem_comeca_no_nordeste_ve_jogadores_da_regiao` (a lenda é da região, ≥ 3 jogadores, ≥ 60 nomes distintos em 50 ofertas, mesma semente = mesma oferta).
- [x] `test_draft_humano_tem_mediana_perto_de_70` (1.000 drafts sequenciais: p50 entre 66 e 74).
- [x] `test_distribuicao_equilibrada` (400 carreiras com draft humano: não decolou 18–32%,
  craque 18–35%, lenda > 0 e ≤ 8%).
- [x] `test_temporada_ruim_tem_manchete_de_temporada_ruim`.
- [x] `test_lesao_grave_baixa_o_teto`.
