"""The owner's review page: a signed link per draft; hold/release the edition, drop topics."""

import re
from datetime import timedelta

import pytest
from test_renderer import full_newsletter
from webkit import NOW, SECRET, make_client

from geral.models import Topic
from geral.web.tokens import make_token

OWNER = "dono@example.com"


@pytest.fixture
def owner(store, mailer, clock):
    return make_client(store, mailer, clock, NOTIFY_EMAIL=OWNER)


def link(when=NOW, purpose: str = "review", email: str = OWNER) -> str:
    return make_token(SECRET, purpose, email, when)


def newsletter():
    n = full_newsletter()
    rumor = Topic(title="Rumor de contratação", summary="Um meia é sondado.", importance=3)
    return n.model_copy(update={"topics": [*n.topics, rumor]})


def draft(store, send_in=timedelta(hours=5), kind: str = "news", team: str = "flamengo"):
    day = (NOW + send_in).date().isoformat()
    store.save_draft(
        team,
        kind,
        day,
        f"Notícias — {day}",
        newsletter().model_dump_json(),
        NOW,
        NOW + send_in,
    )
    return store.draft(team, kind, day)


def post(client, path: str, token: str | None = None):
    return client.post(path, data={"t": token or link()}, follow_redirects=False)


def test_review_page_lists_pending_drafts(owner, store) -> None:
    d = draft(store)

    page = owner.get(f"/revisao?t={link()}")

    assert page.status_code == 200
    assert "Urubu News" in page.text and d.label in page.text
    assert "Vitória no clássico" in page.text and "Rumor de contratação" in page.text
    assert page.headers["cache-control"] == "no-store"
    assert page.headers["referrer-policy"] == "no-referrer"


def test_review_page_rejects_token_of_other_purpose(owner, store) -> None:
    draft(store)

    assert owner.get(f"/revisao?t={link(purpose='team-requests')}").status_code == 404
    assert owner.get(f"/revisao?t={link(email='outro@example.com')}").status_code == 404
    assert owner.get("/revisao").status_code == 404


def test_review_page_rejects_expired_token(owner) -> None:
    old = link(NOW - timedelta(days=8))

    assert owner.get(f"/revisao?t={old}").status_code == 404


def test_review_actions_reject_a_bad_token(owner, store) -> None:
    d = draft(store)

    response = post(owner, f"/revisao/{d.id}/segurar", link(purpose="team-requests"))

    assert response.status_code == 404
    assert store.draft_by_id(d.id).held is False


def test_hold_and_release_from_the_page(owner, store) -> None:
    d = draft(store)

    held = post(owner, f"/revisao/{d.id}/segurar")

    assert held.status_code == 303 and held.headers["location"].startswith("/revisao?t=")
    assert store.draft_by_id(d.id).held is True
    assert "segurada" in owner.get(f"/revisao?t={link()}").text.lower()

    post(owner, f"/revisao/{d.id}/soltar")
    assert store.draft_by_id(d.id).held is False


def test_remove_topic_from_the_page_hides_it_in_the_preview(owner, store) -> None:
    d = draft(store)

    assert post(owner, f"/revisao/{d.id}/topicos/0/tirar").status_code == 303

    assert store.draft_by_id(d.id).removed_topics == [0]
    preview = owner.get(f"/revisao/{d.id}/previa?t={link()}")
    assert preview.status_code == 200
    assert "Um meia é sondado." in preview.text
    assert "venceu o Fluminense por 1 a 0" not in preview.text

    post(owner, f"/revisao/{d.id}/topicos/0/voltar")
    assert store.draft_by_id(d.id).removed_topics == []


def test_remove_topic_after_sent_is_409(owner, store) -> None:
    d = draft(store)
    store.mark_draft_sent("flamengo", "news", d.day, NOW)

    assert post(owner, f"/revisao/{d.id}/topicos/0/tirar").status_code == 409
    assert post(owner, f"/revisao/{d.id}/segurar").status_code == 409
    assert store.draft_by_id(d.id).removed_topics == []


def test_remove_unknown_topic_is_404(owner, store) -> None:
    d = draft(store)

    assert post(owner, f"/revisao/{d.id}/topicos/7/tirar").status_code == 404
    assert post(owner, "/revisao/999/segurar").status_code == 404
    assert store.draft_by_id(d.id).removed_topics == []


def test_held_and_late_draft_can_still_be_changed(owner, store, clock) -> None:
    d = draft(store)
    post(owner, f"/revisao/{d.id}/segurar")
    clock.now = NOW + timedelta(hours=8)  # past its send time

    assert post(owner, f"/revisao/{d.id}/topicos/1/tirar", link(clock.now)).status_code == 303
    assert post(owner, f"/revisao/{d.id}/soltar", link(clock.now)).status_code == 303
    assert store.draft_by_id(d.id).released_at == clock.now


def test_release_after_a_newer_edition_is_409(owner, store, clock) -> None:
    d = draft(store)
    post(owner, f"/revisao/{d.id}/segurar")
    clock.now = NOW + timedelta(days=3)
    store.set_latest_edition("flamengo", "Urubu News — Notícias — x", "h", "t", clock.now)

    response = post(owner, f"/revisao/{d.id}/soltar", link(clock.now))

    assert response.status_code == 409
    assert store.draft_by_id(d.id).held is True


def test_review_page_says_when_nothing_is_pending(owner) -> None:
    page = owner.get(f"/revisao?t={link()}")

    assert page.status_code == 200
    assert re.search(r"nenhuma edição", page.text, re.I)


def test_saving_a_draft_emails_the_owner_the_review_link(owner, mailer) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from webkit import AUTH

    tz = ZoneInfo("America/Sao_Paulo")
    body = {
        "label": "Notícias — 16/11/2026",
        "newsletter": newsletter().model_dump(mode="json"),
        "build_at": datetime(2026, 11, 16, 8, 0, tzinfo=tz).isoformat(),
        "send_at": datetime(2026, 11, 16, 13, 0, tzinfo=tz).isoformat(),
    }

    put = owner.put("/api/teams/flamengo/drafts/news/2026-11-16", json=body, headers=AUTH)

    assert put.status_code == 204
    [(to, subject, text)] = mailer.notifications
    assert to == OWNER
    assert subject == "Revisar: Urubu News — Notícias — 16/11/2026, sai às 13:00"
    found = re.search(r"https://geral\.test(/revisao\?t=[\w.\-]+)", text)
    assert found, text
    assert "Rumor de contratação" in text
    assert owner.get(found.group(1)).status_code == 200


def test_draft_saved_even_if_the_notice_fails(owner, mailer, store, monkeypatch) -> None:
    from webkit import AUTH

    from geral.web.mailer import MailError

    def down(*args):
        raise MailError("resend down")

    monkeypatch.setattr(mailer, "send_notification", down)
    body = {
        "label": "Notícias — 16/11/2026",
        "newsletter": newsletter().model_dump(mode="json"),
        "build_at": "2026-11-16T08:00:00-03:00",
        "send_at": "2026-11-16T13:00:00-03:00",
    }

    put = owner.put("/api/teams/flamengo/drafts/news/2026-11-16", json=body, headers=AUTH)

    assert put.status_code == 204
    assert store.draft("flamengo", "news", "2026-11-16") is not None


def test_a_second_put_of_the_same_draft_sends_no_notice(owner, mailer) -> None:
    from webkit import AUTH

    body = {
        "label": "Notícias — 16/11/2026",
        "newsletter": newsletter().model_dump(mode="json"),
        "build_at": "2026-11-16T08:00:00-03:00",
        "send_at": "2026-11-16T13:00:00-03:00",
    }
    owner.put("/api/teams/flamengo/drafts/news/2026-11-16", json=body, headers=AUTH)
    owner.put("/api/teams/flamengo/drafts/news/2026-11-16", json=body, headers=AUTH)

    assert len(mailer.notifications) == 1


def test_release_when_a_newer_draft_exists_is_409(owner, store, clock) -> None:
    old = draft(store)
    post(owner, f"/revisao/{old.id}/segurar")
    clock.now = NOW + timedelta(days=3)
    store.save_draft(
        "flamengo",
        "post",
        "2026-11-13",
        "Pós-jogo",
        newsletter().model_dump_json(),
        clock.now,
        clock.now + timedelta(hours=5),
    )

    response = post(owner, f"/revisao/{old.id}/soltar", link(clock.now))

    assert response.status_code == 409  # the newer one already carries its news
    assert store.draft_by_id(old.id).held is True


def test_late_draft_not_released_says_it_did_not_go_out(owner, store, clock) -> None:
    d = draft(store)
    post(owner, f"/revisao/{d.id}/segurar")
    post(owner, f"/revisao/{d.id}/soltar")  # let go before its time, then the send failed
    clock.now = NOW + timedelta(hours=9)

    page = owner.get(f"/revisao?t={link(clock.now)}")

    assert "não saiu" in page.text.lower()
    assert "próxima verificação" not in page.text


# --- special sections in the review ------------------------------------------------------------


def with_sections(store):
    from geral.models import Story

    store.add_story(
        "flamengo",
        {
            "kind": "clube",
            "title": "A história",
            "body": "Texto da história.",
            "summary": "s",
            "fact_date": "",
            "source_url": "u",
            "source_title": "t",
            "source_key": "k",
            "rejected_reason": None,
        },
        NOW,
    )
    drawn = store.draw_story("flamengo", "L")
    n = newsletter().model_copy(
        update={"story": Story(**drawn), "on_this_day": ["Há 10 anos, em 01/01/2016: algo."]}
    )
    day = (NOW + timedelta(hours=5)).date().isoformat()
    store.save_draft(
        "flamengo", "news", day, "Notícias", n.model_dump_json(), NOW, NOW + timedelta(hours=5)
    )
    return store.draft("flamengo", "news", day), drawn["id"]


def test_review_lists_the_story(owner, store) -> None:
    with_sections(store)

    page = owner.get(f"/revisao?t={link()}").text

    assert "A história" in page and "Nesta semana" in page


def test_removed_story_is_discarded_and_not_sent(owner, store) -> None:
    from geral.models import Newsletter

    d, story_id = with_sections(store)

    assert post(owner, f"/revisao/{d.id}/historia/tirar").status_code == 303

    kept = Newsletter.model_validate_json(store.draft_by_id(d.id).newsletter_json)
    assert kept.story is None and kept.on_this_day  # what the send reads
    assert store.draw_story("flamengo", "L") is None  # discarded: never drawn again
    assert "Texto da história." not in owner.get(f"/revisao/{d.id}/previa?t={link()}").text


def test_remove_on_this_day(owner, store) -> None:
    from geral.models import Newsletter

    d, _ = with_sections(store)

    post(owner, f"/revisao/{d.id}/neste-dia/tirar")

    kept = Newsletter.model_validate_json(store.draft_by_id(d.id).newsletter_json)
    assert kept.on_this_day == [] and kept.story is not None
