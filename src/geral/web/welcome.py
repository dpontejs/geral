"""Welcome box on top of the edition a new subscriber gets right after confirming.

Stored editions are already rendered (CSS inlined), so the box goes right below the header's
stripe, the one row with `height="5"`; without it only the plain text gets the welcome.
"""

import re
from html import escape

from geral.teams import Team

FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
STRIPE_ROW = re.compile(r'height="5"[^>]*>.*?</tr>', re.DOTALL)


def welcome_text(team: Team) -> tuple[str, str]:
    title = f"Boas-vindas à {team.newsletter}!"
    text = (
        f"A newsletter segue a agenda do {team.name}: um pré-jogo no dia da partida, com "
        "escalações, palpites e onde assistir; um pós-jogo na manhã seguinte, com placar e "
        "análise; e, quando o intervalo entre os jogos é maior, um resumo das notícias. Abaixo vai "
        "a última edição, para você já ir lendo."
    )
    return title, text


def add_welcome(html: str, text: str, team: Team) -> tuple[str, str]:
    """The edition with the welcome box (HTML) and paragraph (text) on top."""
    title, body = welcome_text(team)
    box = (
        f"<tr><td style='font-family:{FONT}; padding:24px 24px 0 24px'>"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f"<td style='background-color:#F4EFE6; border-left:4px solid {team.accent}; "
        "padding:12px 16px'><p style='font-size:13px; font-weight:800; letter-spacing:1px; "
        f"text-transform:uppercase; color:{team.accent}; margin:0 0 4px 0'>{escape(title)}</p>"
        "<p style='font-size:15px; line-height:1.5; color:#1C1C1C; margin:0'>"
        f"{escape(body)}</p></td></tr></table></td></tr>"
    )
    welcomed = STRIPE_ROW.sub(lambda m: m.group(0) + "\n  " + box, html, count=1)
    return welcomed, f"{title}\n{body}\n\n{text}"
