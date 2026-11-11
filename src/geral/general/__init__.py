"""Edição geral: Brazilian football's week by série, the Geral's own newsletter.

See docs/features/edicao-geral.md.
"""

from geral.teams import Team

# Série name -> its ge championship page (table API and news feed).
SERIES = {
    "Série A": "https://ge.globo.com/futebol/brasileirao-serie-a/",
    "Série B": "https://ge.globo.com/futebol/brasileirao-serie-b/",
    "Série C": "https://ge.globo.com/futebol/brasileirao-serie-c/",
    "Série D": "https://ge.globo.com/futebol/brasileirao-serie-d/",
}

GENERAL_SLUG = "geral"
# The edição geral on the page: one more entry of the web catalog (sign-up, confirmation,
# unsubscribe, saved edition, /t/geral), never in teams.toml, so the team pipeline (matches,
# ESPN, `due` per team) never sees it. Built without validation: it follows no club.
GENERAL_EDITION = Team.model_construct(
    slug=GENERAL_SLUG,
    name="Geral",
    newsletter="Edição geral",
    fans="quem gosta de futebol brasileiro",
    espn_id=0,
    ge_url=SERIES["Série A"],
    news_query="",
    keywords=(),
    accent="#8E8B84",  # concreto, docs/features/identidade-geral.md
    leagues=(),
    league=None,
    other_sports={},
    listed=False,  # not a torcida: out of the scoreboard, the team grid and the games
    sender=GENERAL_SLUG,
    ge_id=None,
    ge_tables={},
    cbf_id=None,
    cbf_tables={},
)
