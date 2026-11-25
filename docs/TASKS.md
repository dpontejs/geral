# Tasks

Ordem de execução. Cada fatia vira um PR; a página da fatia fica em `docs/features/`.

## Fatia 1 — Newsletter de qualquer time (`docs/features/newsletter-por-time.md`)
- [x] T1: esqueleto do projeto (`pyproject.toml`, `uv`, ruff, pytest, CI) copiando a configuração da Urubu News
- [x] T2: catálogo `teams.toml` + `load_teams()` validado com pydantic (Vasco, Palmeiras, ABC, Náutico)
- [x] T3: copiar coleta, resumo, ESPN, render e envio da Urubu News, trocando constantes do Flamengo por `Team`
- [x] T4: prompts e templates parametrizados pelo time (nome, torcida, cores, escudo)
- [x] T5: CLI `geral preview --team <slug>` e `geral run --team <slug>`

## Fatia 2 — Portal e inscrição por torcida
- [x] Portar o app web da Urubu News (inscrição com confirmação, descadastro, boas-vindas, edição guardada) com `team` em tudo: um e-mail, várias torcidas; descadastro por torcida e geral
- [x] Página inicial no visual do rascunho aprovado (https://claude.ai/artifact/4TwD5bpDS9NBmFoN6onH5b): torcidas, ingresso, "seu time ainda não chegou?", placar
- [x] Servir as marcas em `/static/<time>/` e usá-las no cabeçalho da newsletter (`logo_url`)
- [x] Edição guardada por torcida: cada envio real publica a última edição daquela torcida; quem se inscreve recebe a última de cada torcida escolhida (boas-vindas)
- [x] `/api/subscribers?team=<slug>` e envio só para quem assina a torcida
- [x] Portal no ar em https://geral.diegoponte.dev (imagem no GHCR, stack no `infra`, auto-deploy)
- [ ] `geral due --all` + workflow por torcida (`docs/features/agenda-automatica.md`) e disparo pela VPS
- [x] Decidir cota do LLM: chave paga (ver PLAN §5)

## Fatia 2a — A Urubu News entra na Geral (`docs/adr/0001-geral-assume-a-urubu-news.md`)
- [x] Flamengo no `teams.toml` com a marca Urubu News (logo, cor, outras modalidades)
- [x] Portar o bolão por torcida (cartela, palpite, ranking da temporada) e somar no placar da Geral
- [x] Migrar inscritos, palpites e ranking do SQLite da Urubu, com `team = flamengo`
- [x] O app da Geral atende `urubunews.diegoponte.dev` e `flamengo.diegoponte.dev` com os mesmos tokens (links já enviados seguem funcionando)
- [x] Desligar o envio da Urubu no repositório antigo só depois da primeira edição enviada pela Geral

## Em outro chat
- [ ] Revisão de design do portal (tirar a "cara de IA"), na linha da identidade da Geral
- [ ] Exploração dos joguinhos e da gamificação ("7 a 0", cartola simples); o bolão fica na parte 2a

## Fatia 2b — Dados das Séries C, D e estaduais (ABC)
- [x] Cliente da API de tabelas do ge (`api.globoesporte.globo.com/tabela/{tUUID}/fase/{slug}/...`): jogos, resultados e classificação; tUUID e fases lidos da página do campeonato a cada execução (`docs/features/dados-serie-c.md`)
- [x] Autores dos gols pela API de jogos da CBF (Séries C e D) e pênaltis do mata-mata pelo ge; o estadual fica só com o placar (a CBF não o tem e o HTML do jogo no ge não traz os lances)
- [x] Notícias do time pelo feed JSON da página do ge (no lugar da raspagem do HTML, que fica de reserva)
- [x] Pernambucano: segundo leitor, para o formato `tabela-context` (fases e tabela da página, jogos pelo GraphQL do ge); o Náutico entra no 2º turno (Frevo)

## Fatia 2c — Novas torcidas
- [x] CSA (Azulão News): Série D e Alagoano pelo ge, gols pela CBF, seções especiais; notícias que citam a Mancha Azul ficam de fora (`exclude_terms`)
- [x] CSA: notícias das categorias de base (sub-20, sub-17, sub-15) no "Saiba mais"
- [x] CSA: ícone do Nano Banana no lugar do provisório (`docs/features/identidade-visual-times.md`)
- [x] CSA: caixa `azulao@` do remetente (conta Google criada pelo dono)

## Fatia 3 — Pedido de time e ranking de torcidas
- [x] Formulário "meu time não está aqui" (time + e-mail opcional para avisar quando nascer) e os mais pedidos (`docs/features/pedido-de-time.md`)
- [x] Comando que avisa por e-mail quem pediu, quando a torcida nascer (`geral avisar-pedido`, primeiro uso com o CSA)
- [ ] Página pública de ranking: inscritos por time e por série

## Fatia 4 — Edição geral por série (`docs/features/edicao-geral.md`)
- [x] 4a: montar a edição geral (resultados, tabela e notícias da Série A à D pelo ge, textos do Gemini) e `geral edicao-geral` com prévia e envio para a lista fixa
- [x] 4b: inscrição "Edição geral" no portal, edição guardada e envio toda segunda aos inscritos

## Revisão das edições (`docs/features/revisao-das-edicoes.md`)
- [x] Agenda montar/enviar, rascunho no portal e gatilho com etapa (#50, infra#29)
- [x] Página `/revisao`, e-mail por rascunho, segurar/soltar e tirar tópicos (#51)
- [ ] Editar o texto de um tópico na revisão (hoje só segurar ou tirar)
- [ ] Prévia da revisão com o logo da marca e com a manchete já reescrita quando um tópico sai

## Seções especiais: histórias e "Neste dia" (`docs/features/secoes-especiais.md`)
- [x] Acervo: coleta na Wikipédia, escrita pelo Gemini só a partir do trecho, verificador e job noturno (#52)
- [x] História e "Neste dia" nas edições, sorteadas, e tirar na revisão (#53)
- [x] Quinta na entressafra e aniversários dos ídolos no "Neste dia" (#54)
- [ ] Google News como fonte do acervo: matérias de memória ("relembre", "há X anos") e histórias de torcedor, com o texto completo extraído como nas notícias
- [ ] RSSSF Brasil como fonte: conferir placar dos jogos históricos e achar jogos marcantes dos estaduais (as páginas dos estaduais ano a ano ainda não foram localizadas)
- [ ] Histórias enviadas pela torcida (formulário + moderação)
- [ ] Detectar a mesma fonte quando a seção da Wikipédia é renomeada (hoje vira chave nova)
- [ ] Outros times com seções especiais (basta `specials` no catálogo, depois de checar o material na Wikipédia)
  - [x] CSA: 29 trechos em 2026-11-19 (26 de história e jogos, como os 22 x 0 de 1945, o Jogo do Xaxado e as finais do Clássico das Multidões; 3 ídolos: Jacozinho, Dida e Freitas Nascimento)

## Central (`docs/features/central.md`)
- [x] Tabelas, rodadas, playoffs e resumo das Séries A–D em `/central`, com chamada na inicial
- [x] Aba de notícias: feed do ge com página de leitura e "Continue lendo no ge", paginada

## Fatia 5 — Cartola simples (o bolão por torcida já vem na 2a)

## Fatia 6 — Joguinhos "7 a 0"
Ideias tiradas dos joguinhos de futebol que viralizaram em 2026 (7a0/Sete a Zero, The Fenômeno,
El Ídolo, Destiny Eleven, Copero, GAMBETA, Missing 11).
- [x] Carreira: draft de lendas e carreira simulada, modos Rápida/Completa, Nordeste, veredito das
  torcidas e Fábrica de craques, capa da Geral (`docs/features/carreira*.md`; PRs #56 e #57)
- [ ] Revisar as notas das lendas (`src/geral/games/carreira/lendas.toml`): ainda é o rascunho;
  faltam Alberi (ABC) e ídolos do CRB, sem id na base
- [ ] Carreira, desafio com o mesmo sorteio: link "joga com o meu draft" e placar lado a lado
  (projeto 5, sem guardar nada no servidor)
- [x] **Prancheta**: desenhar e adivinhar ao vivo, em sala privada por link, sem tema, com súmula
  no link curto (`docs/features/prancheta.md`; PRs #84–#86, #88, #90, #92 e este)
  - [ ] Conferir num celular de verdade o teclado aberto sobre o campo de chute
  - [ ] Pedaço de traço reenviado depois de queda de rede duplica um trecho (raro; aceito por ora)
- [x] **Mano a Mano**: batedor contra goleiro em 3D, pênaltis ou faltas, contra o bot ou por link,
  com súmula por partida (`docs/features/mano-a-mano.md`; PRs #107–#112 e este)
  - [ ] Conferir num celular de verdade deitado (toque na saída, tela cheia no Android)
  - [ ] Refinar a falta e religar (`MANO_FALTAS=1`; desligada pelo dev em 2026-11-25)
- [ ] **7a0 do clube**: montar o time dos sonhos de um clube com quem já vestiu a camisa e tentar
  vencer um mata-mata (o 7a0 original é só de seleções em Copas). Dados: a base do jogo da velha
  (5.495 jogadores com clubes, posição, período e fama) já basta para elencos e força; o diferencial
  é o ABC e o Náutico terem o seu
- [ ] **Escalação do dia** (estilo Missing 11): mostra um jogo (data, placar, competição), o campo
  com o esquema e as 11 camisas numeradas; o torcedor adivinha quem jogou em cada posição, com dicas.
  Dados pesquisados em 2026-11-18:
  - ESPN (`summary?event=`, já usada pela Geral): titulares, posição detalhada, número e reservas;
    Série A desde pelo menos 2009 (esquema tático a partir de ~2014), Série B, Libertadores e Copa do
    Brasil. A Série C vem **sem** escalação (o ABC fica de fora enquanto estiver nela)
  - Wikipédia: "Ficha técnica" com escalações nos jogos marcantes (finais, títulos, Copa de 1970);
    serve para uma lista curada de ~30 jogos por time, inclusive ABC e Náutico
  - A decidir: jogos recentes da ESPN (volume, automático), históricos curados (memória da torcida)
    ou os dois

## Fatia 7 — Fóruns
