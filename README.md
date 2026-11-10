# Resenha (nome provisório)

Hub de newsletters de futebol brasileiro: cada time tem a sua (Almirante News, Porco News,
Elefante News, Timbu News...), com notícias resumidas por IA, estatísticas da ESPN, próximo jogo e
classificação. Projeto feito por diversão, sem ligação oficial com os clubes. Nasceu do código da
[Urubu News](https://github.com/dpontejs/flamengo-news).

Arquitetura e decisões: [`docs/PLAN.md`](docs/PLAN.md). Backlog: [`docs/TASKS.md`](docs/TASKS.md).
Times: [`src/resenha/teams.toml`](src/resenha/teams.toml).

## Rodando

```bash
uv sync
cp .env.example .env   # preencha GEMINI_API_KEY
uv run resenha preview --team vasco --out out/vasco.html
uv run resenha run --team palmeiras    # DRY_RUN=true não envia
```
