"""Drafts: each team edition is built first (kept on the page) and sent later."""

from datetime import datetime
from zoneinfo import ZoneInfo

from test_renderer import full_newsletter
from webkit import AUTH

from geral.models import Newsletter

TZ = ZoneInfo("America/Sao_Paulo")
URL = "/api/teams/vasco/drafts/news/2026-11-16"


def draft_in(**changes) -> dict:
    body = {
        "label": "Notícias — 16/11/2026",
        "newsletter": full_newsletter().model_dump(mode="json"),
        "build_at": datetime(2026, 11, 16, 8, 0, tzinfo=TZ).isoformat(),
        "send_at": datetime(2026, 11, 16, 13, 0, tzinfo=TZ).isoformat(),
    }
    return body | changes


def test_newsletter_survives_json_round_trip() -> None:
    newsletter = full_newsletter()

    assert Newsletter.model_validate_json(newsletter.model_dump_json()) == newsletter


def test_put_draft_then_get(client) -> None:
    assert client.put(URL, json=draft_in(), headers=AUTH).status_code == 204

    draft = client.get(URL, headers=AUTH).json()

    assert draft["label"] == "Notícias — 16/11/2026"
    assert Newsletter.model_validate(draft["newsletter"]) == full_newsletter()
    assert (draft["held"], draft["removed_topics"], draft["sent_at"]) == (False, [], None)


def test_put_draft_twice_is_409_and_keeps_first(client) -> None:
    client.put(URL, json=draft_in(), headers=AUTH)

    again = client.put(URL, json=draft_in(label="outro"), headers=AUTH)

    assert again.status_code == 409
    assert client.get(URL, headers=AUTH).json()["label"] == "Notícias — 16/11/2026"


def test_get_unknown_draft_is_404(client) -> None:
    assert client.get(URL, headers=AUTH).status_code == 404


def test_drafts_require_token(client) -> None:
    assert client.put(URL, json=draft_in()).status_code == 401
    assert client.get(URL).status_code == 401
    assert client.post(f"{URL}/sent").status_code == 401


def test_unknown_team_is_404(client) -> None:
    url = "/api/teams/xyz/drafts/news/2026-11-16"

    assert client.put(url, json=draft_in(), headers=AUTH).status_code == 404


def test_mark_sent_sets_sent_at(client) -> None:
    client.put(URL, json=draft_in(), headers=AUTH)

    assert client.post(f"{URL}/sent", headers=AUTH).status_code == 204
    assert client.get(URL, headers=AUTH).json()["sent_at"] is not None
    assert (
        client.post("/api/teams/vasco/drafts/pre/2026-11-16/sent", headers=AUTH).status_code == 404
    )


def test_drafts_are_kept_per_team_kind_and_day(client) -> None:
    client.put(URL, json=draft_in(), headers=AUTH)

    assert client.get("/api/teams/vasco/drafts/post/2026-11-16", headers=AUTH).status_code == 404
    assert client.get("/api/teams/abc/drafts/news/2026-11-16", headers=AUTH).status_code == 404


# --- the owner's review decisions ----------------------------------------------------------


def saved(store, kind: str = "news", day: str = "2026-11-16", send_hour: int = 13):
    store.save_draft(
        "vasco",
        kind,
        day,
        f"{kind} {day}",
        full_newsletter().model_dump_json(),
        datetime(2026, 11, 16, 8, 0, tzinfo=TZ),
        datetime(2026, 11, 16, send_hour, 0, tzinfo=TZ),
    )
    return store.draft("vasco", kind, day)


def test_hold_then_release_records_released_at(store) -> None:
    draft = saved(store)
    late = datetime(2026, 11, 16, 15, 0, tzinfo=TZ)

    assert store.set_held(draft.id, True, late).held is True
    released = store.set_held(draft.id, False, late)

    assert released.held is False and released.released_at == late


def test_remove_and_restore_topic(store) -> None:
    draft = saved(store)

    assert store.set_topic_removed(draft.id, 1, True).removed_topics == [1]
    assert store.set_topic_removed(draft.id, 0, True).removed_topics == [0, 1]
    assert store.set_topic_removed(draft.id, 1, False).removed_topics == [0]


def test_pending_drafts_leave_out_the_sent_ones(store) -> None:
    news, post = saved(store), saved(store, "post", "2026-11-17")
    store.mark_draft_sent("vasco", "news", "2026-11-16", datetime(2026, 11, 16, 13, 1, tzinfo=TZ))

    assert [d.id for d in store.pending_drafts()] == [post.id]
    assert store.draft_by_id(news.id).sent_at is not None


def test_released_due_lists_only_late_releases(store) -> None:
    early, late = saved(store), saved(store, "post", "2026-11-17")
    store.set_held(early.id, True, datetime(2026, 11, 16, 9, 0, tzinfo=TZ))
    store.set_held(early.id, False, datetime(2026, 11, 16, 10, 0, tzinfo=TZ))  # before 13:00
    store.set_held(late.id, True, datetime(2026, 11, 16, 9, 0, tzinfo=TZ))
    store.set_held(late.id, False, datetime(2026, 11, 16, 14, 0, tzinfo=TZ))  # after 13:00

    due = store.released_due(datetime(2026, 11, 16, 14, 5, tzinfo=TZ))

    assert [d.id for d in due] == [late.id]


def test_store_adds_released_at_to_an_old_drafts_table(tmp_path) -> None:
    import sqlite3

    from geral.web.store import SubscriberStore

    db = tmp_path / "old.db"
    with sqlite3.connect(db) as old:
        old.execute(
            "CREATE TABLE drafts (id INTEGER PRIMARY KEY, team TEXT NOT NULL, kind TEXT NOT NULL,"
            " day TEXT NOT NULL, label TEXT NOT NULL, newsletter_json TEXT NOT NULL,"
            " build_at TEXT NOT NULL, send_at TEXT NOT NULL, held INTEGER NOT NULL DEFAULT 0,"
            " removed_topics TEXT NOT NULL DEFAULT '[]', sent_at TEXT, UNIQUE (team, kind, day))"
        )

    store = SubscriberStore(db)
    SubscriberStore(db)  # twice: the migration is idempotent

    assert saved(store).released_at is None


def test_released_due_only_for_3h_after_the_release(store) -> None:
    late = saved(store)
    store.set_held(late.id, True, datetime(2026, 11, 16, 9, 0, tzinfo=TZ))
    store.set_held(late.id, False, datetime(2026, 11, 16, 14, 0, tzinfo=TZ))

    assert store.released_due(datetime(2026, 11, 16, 16, 59, tzinfo=TZ))
    assert store.released_due(datetime(2026, 11, 16, 17, 0, tzinfo=TZ)) == []


def test_draft_send_at_must_have_a_timezone(client) -> None:
    body = draft_in(send_at="2026-11-16T13:00:00")

    assert client.put(URL, json=body, headers=AUTH).status_code == 422


def test_publish_now_before_send_at_is_due_right_away(store) -> None:
    draft = saved(store)  # sends at 13:00
    store.publish_now(draft.id, datetime(2026, 11, 16, 9, 30, tzinfo=TZ))

    due = store.released_due(datetime(2026, 11, 16, 9, 35, tzinfo=TZ))

    assert [d.id for d in due] == [draft.id]


def test_hold_after_publish_now_cancels_it(store) -> None:
    draft = saved(store)
    store.publish_now(draft.id, datetime(2026, 11, 16, 9, 30, tzinfo=TZ))
    store.set_held(draft.id, True, datetime(2026, 11, 16, 9, 31, tzinfo=TZ))
    store.set_held(draft.id, False, datetime(2026, 11, 16, 9, 32, tzinfo=TZ))  # back to 13:00

    assert store.released_due(datetime(2026, 11, 16, 9, 35, tzinfo=TZ)) == []
