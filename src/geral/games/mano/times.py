"""The Geral's teams a Mano a Mano player can wear: slug -> name, from teams.toml.

In alphabetical order of the name (the selector's); the kits are drawn by mano-cena.js per slug.
"""

from geral.teams import load_teams

TIMES: dict[str, str] = {
    slug: time.name for slug, time in sorted(load_teams().items(), key=lambda par: par[1].name)
}
