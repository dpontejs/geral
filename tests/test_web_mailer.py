import json

import httpx
import pytest
import respx

from geral.send.resend_sender import RESEND_BATCH_URL, UNSUBSCRIBE_PLACEHOLDER
from geral.teams import get_team
from geral.web.mailer import LogMailer, MailError, ResendConfirmationMailer

URL = "https://geral.test/confirm?token=abc.def.ghi"
RESEND_URL = "https://api.resend.com/emails"


def mailer() -> ResendConfirmationMailer:
    return ResendConfirmationMailer(
        api_key="re_test", sender="Qualquer <news@example.com>", public_url="https://geral.test"
    )


@respx.mock
def test_confirmation_is_from_the_geral_and_lists_the_chosen_newsletters() -> None:
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "e1"}))

    mailer().send_confirmation("ana@example.com", URL, [get_team("vasco"), get_team("nautico")])

    payload = json.loads(route.calls.last.request.content)
    assert route.calls.last.request.headers["Authorization"] == "Bearer re_test"
    assert payload["to"] == ["ana@example.com"]
    assert payload["from"] == "Geral <geral@example.com>"
    assert payload["subject"] == "Confirme sua inscrição na Geral"
    assert (
        '<img src="https://geral.test/static/geral/logo-email.png" alt="Geral"' in payload["html"]
    )
    for content in (payload["html"], payload["text"]):
        assert URL in content
        assert "Almirante News" in content and "Timbu News" in content


@respx.mock
def test_resend_error_raises_mail_error() -> None:
    respx.post(RESEND_URL).mock(return_value=httpx.Response(422, json={"message": "invalid"}))

    with pytest.raises(MailError, match="invalid"):
        mailer().send_confirmation("ana@example.com", URL, [get_team("abc")])


@respx.mock
def test_network_error_raises_mail_error() -> None:
    respx.post(RESEND_URL).mock(side_effect=httpx.ConnectError("down"))

    with pytest.raises(MailError):
        mailer().send_confirmation("ana@example.com", URL, [get_team("abc")])


@respx.mock
def test_edition_goes_from_the_team_newsletter_with_the_personal_unsubscribe_link() -> None:
    route = respx.post(RESEND_BATCH_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "e1"}]})
    )
    unsubscribe = "https://geral.test/unsubscribe?token=T"

    mailer().send_edition(
        "ana@example.com",
        get_team("palmeiras"),
        "Boas-vindas! Edição",
        f'<a href="{UNSUBSCRIBE_PLACEHOLDER}">sair</a>',
        f"sair: {UNSUBSCRIBE_PLACEHOLDER}",
        unsubscribe,
    )

    [email] = json.loads(route.calls.last.request.content)
    assert email["from"] == "Porco News <porco@example.com>"
    assert email["to"] == ["ana@example.com"]
    assert f'href="{unsubscribe}"' in email["html"]
    assert email["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


@respx.mock
def test_edition_send_failure_raises_mail_error() -> None:
    respx.post(RESEND_BATCH_URL).mock(return_value=httpx.Response(400, json={"message": "no"}))

    with pytest.raises(MailError):
        mailer().send_edition("a@example.com", get_team("abc"), "S", "<p>x</p>", "x", "u")


@respx.mock
def test_notification_is_plain_text() -> None:
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "n1"}))

    mailer().send_notification("dono@example.com", "Novo na Geral", "ana entrou")

    payload = json.loads(route.calls.last.request.content)
    assert payload["to"] == ["dono@example.com"] and payload["text"] == "ana entrou"


def test_log_mailer_sends_nothing(caplog) -> None:
    LogMailer().send_confirmation("ana@example.com", URL, [get_team("abc")])

    assert URL in caplog.text
