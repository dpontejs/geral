import pytest
from webkit import Clock, FakeMailer, make_client

from geral.config import Settings, get_settings
from geral.web.store import SubscriberStore


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Keep the developer's .env and exported settings out of the tests.

    Settings reads `.env` from the working directory, so every test runs from an
    empty temporary directory with no project variables in the environment.
    """
    monkeypatch.chdir(tmp_path)
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def no_espn_calendar(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI plans editions from ESPN's calendar; tests start from an empty one, offline."""
    import geral.__main__ as cli

    monkeypatch.setattr(cli, "_fixtures", lambda team, settings, now: [])


@pytest.fixture(autouse=True)
def flamengo_in_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI tests come from the Urubu News: `--team flamengo` is the test-only team."""
    from fakes import FLAMENGO

    import geral.__main__ as cli
    from geral.teams import get_team

    monkeypatch.setattr(
        cli, "get_team", lambda slug: FLAMENGO if slug == "flamengo" else get_team(slug)
    )


# --- web app ---------------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path) -> SubscriberStore:
    return SubscriberStore(tmp_path / "subscribers.db")


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(store, mailer, clock):
    return make_client(store, mailer, clock)
