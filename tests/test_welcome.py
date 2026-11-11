from test_renderer import full_newsletter

from geral.render.renderer import render
from geral.teams import get_team
from geral.web.welcome import add_welcome


def test_welcome_box_goes_right_below_the_header_stripe_with_the_team_brand() -> None:
    nautico = get_team("nautico")
    newsletter = full_newsletter().model_copy(update={"team": nautico})
    html, text = render(newsletter)

    welcomed_html, welcomed_text = add_welcome(html, text, nautico)

    title = "Boas-vindas à Timbu News!"
    stripe = welcomed_html.index('height="5"')
    box = welcomed_html.index(title)
    headline = welcomed_html.index(newsletter.headline)
    assert stripe < box < headline
    assert welcomed_html.count(title) == 1
    assert "#C60000" in welcomed_html[box - 400 : box]
    assert "Náutico" in welcomed_html[box : box + 600]
    assert welcomed_text.startswith(title) and welcomed_text.endswith(text)


def test_without_the_stripe_only_the_text_gets_the_welcome() -> None:
    html, text = add_welcome("<p>x</p>", "x", get_team("abc"))

    assert html == "<p>x</p>"
    assert text.startswith("Boas-vindas à Elefante News!") and text.endswith("x")
