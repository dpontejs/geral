from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import respx
from ge_series import mock_series

from geral.central.build import build_snapshot
from geral.central.models import NewsItem
from geral.central.news import collect_news, first_paragraph, news_id
from geral.general import SERIES
from geral.models import Article

TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=TZ)
A = {"Série A": SERIES["Série A"]}
AB = {"Série A": SERIES["Série A"], "Série B": SERIES["Série B"]}


def article(slug: str, hours_ago: int, path: str = "noticia") -> Article:
    return Article(
        url=f"https://ge.globo.com/futebol/{path}/2026/11/21/{slug}.ghtml",
        title=f"Título {slug}",
        source="ge",
        published_at=NOW - timedelta(hours=hours_ago),
        summary_hint=f"Linha fina {slug}",
        image_url=f"https://s2-ge.glbimg.com/{slug}.jpg",
    )


def feeds(by_serie: dict[str, list[Article]]):
    return lambda name, page: by_serie.get(name, [])


def test_collect_news_merges_series_newest_first() -> None:
    news = collect_news(
        NOW,
        [],
        series=AB,
        fetch_feed=feeds(
            {"Série A": [article("a1", 5), article("a2", 1)], "Série B": [article("b1", 3)]}
        ),
        fetch_lead=lambda a: f"Lead {a.title}",
    )
    assert [n.title for n in news] == ["Título a2", "Título b1", "Título a1"]
    assert [n.serie_slug for n in news] == ["a", "b", "a"]
    assert news[0].summary == "Linha fina a2" and news[0].lead == "Lead Título a2"
    assert news[0].id == news_id(news[0].url) and len(news[0].id) == 12


def test_collect_news_skips_videos_and_repeats() -> None:
    shared = article("shared", 2)
    news = collect_news(
        NOW,
        [],
        series=AB,
        fetch_feed=feeds({"Série A": [shared, article("v", 1, path="video")], "Série B": [shared]}),
        fetch_lead=lambda a: None,
    )
    assert [n.title for n in news] == ["Título shared"]
    assert news[0].serie_slug == "a"


def test_collect_news_reuses_lead_and_keeps_empty_serie() -> None:
    fetched = []

    def lead(a: Article) -> str:
        fetched.append(a.url)
        return "novo"

    known = article("a1", 5)
    previous = [
        NewsItem(
            id=news_id(known.url),
            serie_slug="a",
            serie_name="Série A",
            title="Título a1",
            url=known.url,
            published_at=known.published_at,
            lead="guardado",
        ),
        NewsItem(
            id="b-old",
            serie_slug="b",
            serie_name="Série B",
            title="Antiga da B",
            url="https://ge.globo.com/b-old",
            published_at=NOW - timedelta(hours=30),
        ),
    ]
    news = collect_news(
        NOW,
        previous,
        series=AB,
        fetch_feed=feeds({"Série A": [known, article("a2", 1)]}),
        fetch_lead=lead,
    )
    by_title = {n.title: n for n in news}
    assert by_title["Título a1"].lead == "guardado"
    assert fetched == [article("a2", 1).url]
    assert "Antiga da B" in by_title  # the B's feed came back empty: its stories stay


def test_first_paragraph_cuts_on_a_word() -> None:
    assert first_paragraph("Curto.\nSegundo parágrafo.") == "Curto."
    long = "palavra " * 100
    cut = first_paragraph(long)
    assert len(cut) <= 321 and cut.endswith("…") and not cut.endswith(" …")
    assert first_paragraph(None) is None and first_paragraph("  \n ") is None


def test_news_refresh_hourly() -> None:
    calls = []

    def news(now, previous):
        calls.append(now)
        return []

    kw = dict(client=httpx.Client(), next_matches=lambda now: [], series=A, news=news)
    with respx.mock(assert_all_called=False) as router:
        mock_series(router, only=("Série A",))
        first = build_snapshot(NOW, None, **kw)
        second = build_snapshot(NOW + timedelta(minutes=30), first, **kw)
        build_snapshot(NOW + timedelta(minutes=70), second, **kw)
    assert calls == [NOW, NOW + timedelta(minutes=70)]
    assert second.news_at == NOW
