# Seções especiais: histórias e "Neste dia"

- **Data:** 2026-11-16
- **Status:** entregue (#52, #53 e este)
- **ADRs:** —

## Objetivo

O ABC e o Náutico estão na entressafra e recebem uma edição magra por semana. A ideia é que as
edições de notícias **contem histórias** do clube (um jogo histórico, um ídolo, uma história do
clube ou da torcida) e tragam um **"Neste dia"**. As seções continuam quando a temporada voltar.
Tudo sai de um **acervo curado**: a IA só monta o texto a partir do que foi coletado das fontes e
nunca escreve de memória. Um verificador automático descarta o que não bate com a fonte, e a
revisão das edições (#50, #51) é a rede final. O dono não valida item a item.

## Fora de escopo

- **Ainda não feito (no `docs/TASKS.md`):** Google News (matérias de memória e de torcedor) e RSSSF
  (placares) como fontes. Os PRs #52 a #54 usam só a Wikipédia pt e o Wikidata; as menções a essas
  duas fontes em "Como funciona" descrevem o desenho, não o que está no ar.

- Histórias enviadas pela torcida (formulário + moderação): ideia boa, mas é outra feature.
- Outros times: a configuração é por time no catálogo, mas o lançamento é só ABC e Náutico.
- Hemeroteca da BN e Internet Archive (OCR ruim, quase sem jornal): ficam como fonte futura.

## Abordagens

1. **Acervo no site, abastecido sozinho (escolhida).** Um job do Actions coleta, escreve e verifica
   toda semana e quando o acervo fica baixo. A montagem só sorteia uma história pronta. Montagem
   barata e rápida; uma recusa do verificador acontece com dias de folga.
2. Acervo como arquivo no repo, por PR: o dono veria o diff, mas cada reabastecimento seria um PR,
   o oposto de "não validar todos".
3. Escrever na hora da montagem: sem tabela nem job, mas não sobra tempo para descartar e tentar de
   novo, e fica difícil não repetir temas.

## Como funciona

- **Catálogo** (`teams.toml`): `specials = true` e `wikipedia = "<artigo pt>"`, `wikidata = "Q…"`
  (ABC `Q287129`, Náutico `Q73971`).
- **Fontes por tipo** (reusa `geral.games.mediawiki`/`ptwiki`):
  - jogo histórico: seções de jogos marcantes e páginas de clássicos e de temporadas (RSSSF Brasil
    para conferir placar quando houver);
  - ídolo: jogador com artigo pt citado na seção "Ídolos" (ou equivalente) do artigo do clube ou
    na lista do Craque do dia (`games/craques/<time>.toml`); os demais do Wikidata ficam de fora;
  - clube/torcida: seções do artigo do clube (símbolos/mascote, estádio, torcidas, história) e
    matérias de memória ou de torcedor achadas no Google News ("relembre", "há X anos", "torcedor"),
    com o texto completo extraído como já se faz com as notícias (`processing.extract`).
- **Job `geral acervo --team <slug>`** (Actions, semanal + quando `< 8` prontas): escolhe fontes
  ainda não usadas, extrai o trecho, pede ao Gemini uma história de 120–180 palavras (prompt pt-BR:
  só o trecho, sem fatos externos) com título, tipo, data do fato (se houver) e uma linha de resumo.
- **Verificador** (sem LLM): todo número, ano, data e nome próprio da história precisa aparecer no
  trecho da fonte; senão, a história é recusada e registrada (`story_rejections`). Até 10 aceitas por
  rodada.
- **Banco** (`stories`): `id, team, kind (jogo|idolo|clube), title, body, summary, fact_date,
  source_url, source_title, created_at, used_label, discarded`. A fonte é citada no rodapé da seção (CC BY-SA).
- **"Neste dia"**: fatos com data, tirados de `stories.fact_date` (com o `summary`) e dos aniversários
  dos ídolos (mesmo critério acima; Wikidata P569). Texto por template, sem LLM:
  "Há 63 anos, nascia Bita, …" / "Em 19/08/1934, …".
- **Na montagem** (notícias de time com `specials`): sorteio independente de cada seção com material
  — história (chance alta, tipo também sorteado) e "Nesta semana" (fatos até 3 dias antes ou depois
  do envio; o título era "Neste dia", mas a janela trazia fatos de outro dia); pode sair
  uma, as duas ou nenhuma. Sem notícia e sem jogo, a história entra sempre. Com seção, as notícias
  vão a no máximo 6 tópicos (hoje 8). A história é **reservada** na montagem (`used_label` = rótulo
  da edição), para dois rascunhos não pegarem a mesma; se a edição não sair, ela não volta.
  *(decisão do construtor)*
- **Entressafra**: só times com `specials`; sem jogo nos próximos 14 dias, além da segunda, uma
  edição de notícias na **quinta** (`plan()` recebe o calendário semanal do time; o gatilho da VPS
  não muda). Edição sem notícia nem jogo, mas com história, sai (hoje não sairia).
- **Revisão**: história e "Neste dia" aparecem como itens na página `/revisao`, que deixa tirá-los.
  História tirada é **descartada** (`discarded`), nunca volta ao sorteio. *(decisão do construtor)*

## Contratos

- API (token): `GET /api/teams/{team}/stories/next?kinds=…` → história não usada; `POST
  /api/teams/{team}/stories` (job); `POST /api/teams/{team}/stories/{id}/used`; `GET
  /api/teams/{team}/stories/count`.
- `Newsletter` ganha `story: Story | None` e `on_this_day: list[str]`.

## Critérios de aceite (como testes)

- [x] `test_verifier_rejects_a_year_not_in_the_source`, `test_verifier_accepts_names_and_dates_in_the_source`
- [x] `test_job_tops_up_to_10_and_skips_used_sources`
- [x] `test_draw_reserves_an_unused_story` (reserva na montagem)
- [x] `test_on_this_day_includes_idol_birthdays`
- [x] `test_specials_get_monday_and_thursday_in_the_offseason`
- [x] `test_story_only_edition_is_not_empty`
- [x] `test_section_caps_news_at_6_topics`
- [x] `test_removed_story_is_discarded_and_not_sent`

## Corte em PRs

1. Acervo: tabela, API, job (coleta → escrita → verificador) e workflow semanal. Sem efeito nas edições.
2. Edição: seção história + "Neste dia" + sorteio + item na revisão.
3. Entressafra: quinta e edição só com história.

## Riscos e dúvidas abertas

- O verificador por "string na fonte" pode recusar paráfrases legítimas ("hexacampeão" × "seis
  títulos"). Medir a taxa de recusa na primeira rodada antes de afrouxar.
- Licença: Wikipédia CC BY-SA, citar a fonte; matérias de jornal, só resumir e linkar.
