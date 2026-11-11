# 0001. Trazer a Urubu News para dentro da Geral

- **Data:** 2026-11-10
- **Status:** aceito
- **Substitui:** —

## Contexto

A Urubu News (`~/flamengo-news`) já está no ar, com página própria (`urubunews.diegoponte.dev`),
inscritos em SQLite na VPS, envio pelo Actions e bolão (PRs #27 e #28). A Geral nasceu de uma cópia
desse código, generalizada por time. O dono quer a Urubu como a primeira torcida da Geral, e não só
como um link para fora.

## Decisão

A Geral assume a Urubu News: o Flamengo vira uma entrada do `teams.toml`, e os inscritos, o envio,
a edição guardada e o bolão passam para o app da Geral, separados por torcida. A marca Urubu News
continua (nome, logo, cor).

## Alternativas consideradas

- Geral só lista a Urubu e aponta para a página dela: mantém dois apps, dois bancos e dois bolões,
  e o placar da Geral não teria os dados da Urubu.
- Pacote compartilhado entre os dois projetos: dois deploys e versões casadas, sem ganho para o
  leitor.

## Consequências

- Um código, um banco e um placar para todas as torcidas; o bolão da Urubu vira o bolão de todas.
- Os links já enviados (`/unsubscribe`, `/confirm`, `/palpite`, `/bolao`, `/static` em
  `urubunews.diegoponte.dev` e `flamengo.diegoponte.dev`) precisam continuar funcionando: o app da
  Geral atende esses hosts, com os mesmos tokens (mesmo `SUBSCRIBE_SECRET`).
- Migração de dados: inscritos, palpites e ranking da temporada vão do SQLite da Urubu para o da
  Geral, todos marcados com `team = flamengo`.
- Até a migração, a Urubu segue no código atual e nada muda para os leitores dela.

## Como reverter

Reativar o app e o workflow da Urubu (código intacto no repositório `flamengo-news`), exportar do
banco da Geral os inscritos e palpites com `team = flamengo` de volta para o SQLite da Urubu e
apontar o DNS de `urubunews.diegoponte.dev` para o app antigo. Custo: um a dois dias, mais um
e-mail de aviso se algum link mudar.
