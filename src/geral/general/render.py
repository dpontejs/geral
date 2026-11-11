"""The edição geral as e-mail: HTML (inlined CSS) and plain text, in the Geral's colors."""

from geral.general.edition import GeneralEdition
from geral.render.renderer import render_pair

# docs/features/identidade-geral.md
COLORS = {"paper": "#EFE4CC", "ink": "#1E1E1E", "concrete": "#8E8B84", "ticket": "#E3B23C"}


def render_general(
    edition: GeneralEdition, logo_url: str | None = None, unsubscribe_url: str | None = None
) -> tuple[str, str]:
    return render_pair(
        "general",
        {"e": edition, "logo_url": logo_url, "unsubscribe_url": unsubscribe_url, **COLORS},
    )
