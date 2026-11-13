"""The edição geral as e-mail: HTML (inlined CSS) and plain text, in the Geral's colors."""

from geral.general.edition import GeneralEdition
from geral.render.renderer import render_pair

# docs/features/identidade-geral.md
COLORS = {
    "paper": "#EFE4CC",
    "ink": "#1E1E1E",
    "concrete": "#5B6B5E",
    "ticket": "#E3B23C",
    "turf": "#0E3320",
    "pitch": "#1F7A3D",
    "wash": "#D3E2C6",  # the field away from the stands
    "board": "#0B0B0A",
    "lamp": "#FFC21A",
}


def render_general(
    edition: GeneralEdition, static_url: str | None = None, unsubscribe_url: str | None = None
) -> tuple[str, str]:
    """`static_url` is the public `/static/geral` with the logo and the field art
    (scripts/make_email_art.py); without it (a local preview) the e-mail has no images."""
    return render_pair(
        "general",
        {"e": edition, "static": static_url, "unsubscribe_url": unsubscribe_url, **COLORS},
    )
