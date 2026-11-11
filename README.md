# Geral

Hub de newsletters de futebol brasileiro, com o nome do setor do Maracanã antigo onde toda
torcida se misturava: cada time tem a sua (Almirante News, Porco News,
Elefante News, Timbu News...), com notícias resumidas por IA, estatísticas da ESPN, próximo jogo e
classificação. Projeto feito por diversão, sem ligação oficial com os clubes. Nasceu do código da
[Urubu News](https://github.com/dpontejs/flamengo-news).

Arquitetura e decisões: [`docs/PLAN.md`](docs/PLAN.md). Backlog: [`docs/TASKS.md`](docs/TASKS.md).
Times: [`src/geral/teams.toml`](src/geral/teams.toml).

## Rodando

```bash
uv sync
cp .env.example .env   # preencha GEMINI_API_KEY
uv run geral preview --team vasco --out out/vasco.html
uv run geral run --team palmeiras    # DRY_RUN=true não envia
```
