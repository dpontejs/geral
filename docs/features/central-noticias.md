# Central: aba de notícias (parte 2 de 2)

- **Data:** 2026-11-21
- **Status:** proposta
- **ADRs:** —

## Objetivo

A segunda aba da Central (`docs/features/central.md`): um feed das notícias das quatro séries,
como nos portais esportivos, para o torcedor se atualizar sem sair da Geral. Cada notícia abre
uma página de leitura dentro da Geral, com o começo da matéria e o link para lê-la inteira no ge.

## Fora de escopo

- IA (resumo ou reescrita) e a matéria inteira na Geral: republicar o texto do ge é cópia de
  conteúdo protegido. A Geral mostra título, linha fina, foto, o primeiro parágrafo e o link.
- Outras fontes além do ge; notícias por time (já estão nas newsletters).

## Contratos

- **Rotas:** `GET /central/noticias?serie=a|b|c|d` (sem `serie`: todas) e
  `GET /central/noticias/{id}` (404 com mensagem se a notícia saiu do feed). As duas abas
  ("Tabelas e jogos", "Notícias") ficam no topo de `/central` e de `/central/noticias`.
- **Modelo:** `NewsItem(id, serie_slug, serie_name, title, summary, image_url, url,
  published_at, lead)` em `CentralSnapshot.news`, com `news_at`; `id` = 12 primeiros
  caracteres do SHA-1 da URL (estável entre atualizações).
- **Coleta** (`geral.central.news.collect_news`): o feed JSON de cada série no ge
  (`GECollector`, 3 páginas, últimas 48 horas), só URLs de matéria (`/noticia/`), sem repetir
  URL entre séries, as 60 mais novas. Série cujo feed vem vazio mantém as notícias anteriores
  dela.
- **Primeiro parágrafo:** `extract_content` (trafilatura) uma única vez por URL; a notícia que já
  estava no retrato reaproveita o `lead`. `first_paragraph` corta em 320 caracteres, no fim de
  uma palavra, com reticências. Falha na extração: a página mostra só a linha fina.
- **Atualização:** de hora em hora, na mesma thread da Central (como os próximos jogos).
- **Página inicial:** o bloco "Central" ganha as três manchetes mais novas.

## Critérios de aceite (como testes)

- [ ] `test_collect_news_merges_series_newest_first`: dados os feeds da A e da B, quando coleta, então uma lista só, da mais nova para a mais velha, com a série de cada uma.
- [ ] `test_collect_news_skips_videos_and_repeats`: URL sem `/noticia/` fica de fora; a mesma URL em duas séries entra uma vez.
- [ ] `test_collect_news_reuses_lead_and_keeps_empty_serie`: notícia já conhecida não é baixada de novo; série com feed vazio mantém as anteriores.
- [ ] `test_first_paragraph_cuts_on_a_word`.
- [ ] `test_news_refresh_hourly`: o retrato só recoleta notícias depois de uma hora.
- [ ] `test_news_page_lists_and_filters`: `/central/noticias?serie=b` só com a B; cartões com foto, título e linha fina.
- [ ] `test_news_reading_page`: título, linha fina, primeiro parágrafo e "Continue lendo no ge" com a URL da matéria.
- [ ] `test_news_reading_page_unknown_id_is_404`.
- [ ] `test_home_shows_latest_headlines`.

## Verificação ponta a ponta

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
uv run geral central && uv run uvicorn geral.web.app:create_app --factory  # abrir /central/noticias
```

## Riscos e dúvidas abertas

- Primeira coleta baixa até 60 matérias (1 por segundo, ~1 minuto); depois, só as novas.
