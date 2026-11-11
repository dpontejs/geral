from datetime import UTC, datetime, timedelta

import pytest

from geral.web.store import RequestResult, SubscriberStore

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
ANA = "ana@example.com"


@pytest.fixture
def store(tmp_path) -> SubscriberStore:
    return SubscriberStore(tmp_path / "subscribers.db")


def subscribe(store: SubscriberStore, email: str, teams: list[str], when=NOW) -> list[str]:
    store.request(email, teams, when)
    return store.confirm(email, when)


def test_new_email_is_pending_with_its_teams(store: SubscriberStore) -> None:
    result = store.request("  Ana@Example.com ", ["vasco", "nautico", "vasco"], NOW)

    assert result is RequestResult.SEND_CONFIRMATION
    assert store.get(ANA).status == "pending"
    assert store.active("vasco") == [] and store.teams_of(ANA) == []
    assert store.pending_teams(ANA) == ["nautico", "vasco"]


def test_confirm_activates_the_email_and_returns_the_new_teams(store: SubscriberStore) -> None:
    store.request(ANA, ["vasco", "nautico"], NOW)

    assert store.confirm(ANA, NOW) == ["nautico", "vasco"]
    assert store.active("vasco") == [ANA] and store.active("nautico") == [ANA]
    assert store.confirm(ANA, NOW + timedelta(hours=1)) == []  # idempotent, nothing new


def test_active_subscriber_adding_a_team_waits_for_confirmation(store: SubscriberStore) -> None:
    subscribe(store, ANA, ["vasco"])

    assert store.request(ANA, ["vasco", "abc"], NOW) is RequestResult.SEND_CONFIRMATION
    assert store.teams_of(ANA) == ["vasco"]
    assert store.get(ANA).status == "active"
    assert store.confirm(ANA, NOW) == ["abc"]
    assert store.teams_of(ANA) == ["abc", "vasco"]


def test_active_subscriber_with_nothing_new_needs_no_confirmation(store: SubscriberStore) -> None:
    subscribe(store, ANA, ["vasco"])

    assert store.request(ANA, ["vasco"], NOW) is RequestResult.ALREADY_ACTIVE


def test_confirmation_is_not_resent_within_cooldown(store: SubscriberStore) -> None:
    store.request(ANA, ["vasco"], NOW)

    assert store.request(ANA, ["vasco"], NOW + timedelta(minutes=5)) is RequestResult.COOLDOWN
    later = NOW + timedelta(minutes=11)
    assert store.request(ANA, ["vasco"], later) is RequestResult.SEND_CONFIRMATION


def test_confirm_unknown_email_fails(store: SubscriberStore) -> None:
    assert store.confirm("ninguem@example.com", NOW) is None


def test_leave_one_team_keeps_the_others(store: SubscriberStore) -> None:
    subscribe(store, ANA, ["vasco", "nautico"])

    store.leave(ANA, "nautico", NOW)

    assert store.teams_of(ANA) == ["vasco"]
    assert store.get(ANA).status == "active"


def test_leaving_the_last_team_unsubscribes(store: SubscriberStore) -> None:
    subscribe(store, ANA, ["vasco"])

    store.leave(ANA, "vasco", NOW)

    assert store.get(ANA).status == "unsubscribed"
    assert store.active("vasco") == []


def test_leave_all(store: SubscriberStore) -> None:
    subscribe(store, ANA, ["vasco", "abc"])

    store.leave_all(ANA, NOW)

    assert store.get(ANA).status == "unsubscribed" and store.teams_of(ANA) == []


def test_old_confirmation_link_does_not_undo_an_unsubscribe(store: SubscriberStore) -> None:
    subscribe(store, ANA, ["vasco"])
    store.leave_all(ANA, NOW)

    assert store.confirm(ANA, NOW) is None
    assert store.active("vasco") == []


def test_resubscribe_after_unsubscribe_requires_confirmation(store: SubscriberStore) -> None:
    subscribe(store, ANA, ["vasco"])
    store.leave_all(ANA, NOW)

    assert store.request(ANA, ["abc"], NOW) is RequestResult.SEND_CONFIRMATION
    assert store.get(ANA).status == "pending"
    assert store.confirm(ANA, NOW) == ["abc"]


def test_active_lists_only_that_team_in_confirmation_order(store: SubscriberStore) -> None:
    subscribe(store, "b@example.com", ["vasco"], NOW)
    subscribe(store, ANA, ["vasco", "abc"], NOW + timedelta(minutes=1))

    assert store.active("vasco") == ["b@example.com", ANA]
    assert store.active("abc") == [ANA]
    assert store.active("palmeiras") == []


def test_counts_per_team(store: SubscriberStore) -> None:
    subscribe(store, ANA, ["vasco", "abc"])
    subscribe(store, "b@example.com", ["vasco"])
    store.request("c@example.com", ["abc"], NOW)  # pending: not counted

    assert store.counts() == {"vasco": 2, "abc": 1}


def test_data_survives_reopening_the_database(tmp_path) -> None:
    path = tmp_path / "nested" / "subscribers.db"
    subscribe(SubscriberStore(path), ANA, ["vasco"])

    assert SubscriberStore(path).active("vasco") == [ANA]


def test_latest_edition_is_kept_per_team(store: SubscriberStore) -> None:
    assert store.latest_edition("vasco") is None
    store.set_latest_edition("vasco", "Antiga", "<p>a</p>", "a", NOW)
    store.set_latest_edition("vasco", "Nova", "<p>n</p>", "n", NOW + timedelta(days=4))
    store.set_latest_edition("abc", "Do ABC", "<p>x</p>", "x", NOW)

    vasco = store.latest_edition("vasco")
    assert (vasco.subject, vasco.html, vasco.text) == ("Nova", "<p>n</p>", "n")
    assert vasco.published_at == NOW + timedelta(days=4)
    assert set(store.latest_editions()) == {"vasco", "abc"}


def test_confirmations_sent_since_counts_recent_requests(store: SubscriberStore) -> None:
    store.request("old@example.com", ["vasco"], NOW - timedelta(days=2))
    store.request("a@example.com", ["vasco"], NOW - timedelta(hours=3))
    store.request("b@example.com", ["vasco"], NOW)

    assert store.confirmations_sent_since(NOW - timedelta(days=1)) == 2


def test_purge_removes_stale_pending_and_old_unsubscribed(store: SubscriberStore) -> None:
    old = NOW - timedelta(days=31)
    store.request("stale@example.com", ["vasco"], old)
    subscribe(store, "gone@example.com", ["vasco"], old)
    store.leave_all("gone@example.com", old)
    subscribe(store, "recent-out@example.com", ["vasco"], NOW)
    store.leave_all("recent-out@example.com", NOW)
    subscribe(store, "fan@example.com", ["vasco"], old)
    store.request("fan@example.com", ["abc"], old)  # never confirmed the second team

    removed = store.purge(NOW)

    assert removed == 2
    assert store.get("stale@example.com") is None and store.get("gone@example.com") is None
    assert store.get("recent-out@example.com").status == "unsubscribed"
    assert store.active("vasco") == ["fan@example.com"]
    assert store.pending_teams("fan@example.com") == []


def test_active_subscriber_also_waits_the_cooldown(store: SubscriberStore) -> None:
    subscribe(store, ANA, ["vasco"])

    assert store.request(ANA, ["abc"], NOW) is RequestResult.SEND_CONFIRMATION
    soon = NOW + timedelta(minutes=5)
    assert store.request(ANA, ["nautico"], soon) is RequestResult.COOLDOWN
    later = NOW + timedelta(minutes=11)
    assert store.request(ANA, ["nautico"], later) is RequestResult.SEND_CONFIRMATION


def test_daily_cap_counts_every_confirmation_sent(store: SubscriberStore) -> None:
    for minutes in (0, 11, 22):
        store.request(ANA, ["vasco"], NOW + timedelta(minutes=minutes))

    assert store.confirmations_sent_since(NOW - timedelta(hours=1)) == 3


def test_asking_again_keeps_the_pending_team_alive(store: SubscriberStore) -> None:
    store.request(ANA, ["abc"], NOW - timedelta(days=29))
    store.request(ANA, ["abc"], NOW)  # a fresh link

    store.purge(NOW + timedelta(days=2))

    assert store.confirm(ANA, NOW + timedelta(days=2)) == ["abc"]


def test_confirming_with_nothing_left_to_confirm_is_not_a_subscription(
    store: SubscriberStore,
) -> None:
    store.request(ANA, ["abc"], NOW)
    store._run("DELETE FROM subscriptions WHERE email = ?", ANA)

    assert store.confirm(ANA, NOW) is None
    assert store.get(ANA).status == "pending"
