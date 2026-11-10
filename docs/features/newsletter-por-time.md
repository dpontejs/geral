# Newsletter de qualquer time

- **Data:** 2026-11-10
- **Status:** proposta
- **ADRs:** —

## Objetivo

Gerar e enviar a newsletter de qualquer time do catálogo com o mesmo pipeline da Urubu News,
trocando só o parâmetro `--team`. É a base de todas as outras fatias do hub.

## Fora de escopo

- Página de inscrição e escolha de times (fatia 2); aqui o envio usa `NEWSLETTER_RECIPIENTS`.
- Agenda automática multi-time (`due`) e disparo pela VPS (fatia 2).
- Coletores de sites oficiais de clubes (o `flamengo_oficial` não é portado).

## Contratos

```python
# src/resenha/teams.py — lê src/resenha/teams.toml
class Team(BaseModel):
    slug: str                 # "botafogo"
    name: str                 # "Botafogo"
    fans: str                 # "alvinegros"
    espn_id: int              # conferir na ESPN ao cadastrar
    ge_slug: str              # ge.globo.com/futebol/times/<ge_slug>/
    news_query: str           # busca do Google News
    colors: tuple[str, str]   # primária, secundária (hex)
    leagues: list[str]        # ["bra.1", "conmebol.libertadores", "bra.copa_do_brazil"]

def load_teams(path: Path | None = None) -> dict[str, Team]: ...
def get_team(slug: str) -> Team: ...  # UnknownTeam com a lista de slugs válidos
```

- CLI: `resenha preview --team <slug> [--edition ...] [--out ...]` e `resenha run --team <slug>`;
  slug desconhecido sai com código 2 e lista os válidos.
- Prompts e templates recebem `team` no contexto; nenhum texto fixo de Flamengo/Urubu.
- Filtro "Brasil afora" exclui notícias com o nome do **próprio** time no título.
- Banco: nenhum nesta fatia.

## Critérios de aceite (como testes)

- [ ] `test_load_teams_validates_catalog`: dado o `teams.toml` real, quando carrega, então todo time tem slug único, cores hex e ESPN id.
- [ ] `test_get_team_unknown_lists_valid_slugs`: dado slug inexistente, quando busca, então `UnknownTeam` cita os slugs válidos.
- [ ] `test_ge_collector_uses_team_slug`: dado `Team(ge_slug="botafogo")`, quando coleta, então requisita a página do Botafogo (respx).
- [ ] `test_google_news_uses_team_query`: dado um time, quando coleta, então a URL do RSS usa `news_query`.
- [ ] `test_espn_stats_use_team_id`: dado `espn_id=6086`, quando busca jogos, então chama o schedule desse id.
- [ ] `test_render_uses_team_name_and_colors`: dado um time, quando renderiza, então o HTML traz nome e cor primária e não traz "Flamengo".
- [ ] `test_prompts_have_no_hardcoded_club`: dado qualquer prompt, quando renderiza para o Botafogo, então não contém "Flamengo" nem "rubro-negr".
- [ ] `test_preview_unknown_team_exits_2`: dado `--team xyz`, quando roda o preview, então sai com código 2.

## Verificação ponta a ponta

```bash
uv run ruff check . && uv run pytest
uv run resenha preview --team botafogo --out out/botafogo.html   # abrir no navegador
uv run resenha preview --team palmeiras --out out/palmeiras.html
```

## Riscos e dúvidas abertas

- IDs da ESPN e slugs do ge precisam ser conferidos time a time ao cadastrar.
- Escudos: a Urubu News usa o CDN da ESPN pelo team id; deve servir para todos.
