from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
            lead="guardada",
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
    from geral.central.models import CentralSnapshot
    from geral.central.news import refresh_news

    calls = []

    def news(now, previous):
        calls.append(now)
        return []

    first = refresh_news(CentralSnapshot(updated_at=NOW, series=[]), NOW, news)
    tables = CentralSnapshot(updated_at=NOW, series=[], news=first.news, news_at=first.news_at)
    second = refresh_news(tables, NOW + timedelta(minutes=30), news)
    refresh_news(second, NOW + timedelta(minutes=70), news)
    assert calls == [NOW, NOW + timedelta(minutes=70)]
    assert second.news_at == NOW


def test_leads_only_for_the_stories_kept() -> None:
    from geral.central import news as news_module

    fetched = []
    many = [article(f"s{i}", i % 40) for i in range(70)]
    collect_news(
        NOW,
        [],
        series=A,
        fetch_feed=feeds({"Série A": many}),
        fetch_lead=lambda a: fetched.append(a.url) or "lead",
    )
    assert len(fetched) == news_module.MAX_NEWS


def test_missing_lead_is_tried_again() -> None:
    known = article("a1", 5)
    previous = [
        NewsItem(
            id=news_id(known.url),
            serie_slug="a",
            serie_name="Série A",
            title="Título a1",
            url=known.url,
            published_at=known.published_at,
            lead=None,
        )
    ]
    news = collect_news(
        NOW,
        previous,
        series=A,
        fetch_feed=feeds({"Série A": [known]}),
        fetch_lead=lambda a: "agora veio",
    )
    assert news[0].lead == "agora veio"


def test_kept_stories_of_an_empty_feed_expire_after_48_hours() -> None:
    old = NewsItem(
        id="old",
        serie_slug="d",
        serie_name="Série D",
        title="Velha da D",
        url="https://ge.globo.com/d-old",
        published_at=NOW - timedelta(hours=49),
    )
    recent = old.model_copy(
        update={"id": "recent", "title": "Recente da D", "published_at": NOW - timedelta(hours=10)}
    )
    news = collect_news(
        NOW,
        [old, recent],
        series={"Série D": SERIES["Série D"]},
        fetch_feed=feeds({}),
        fetch_lead=lambda a: None,
    )
    assert [n.title for n in news] == ["Recente da D"]


def test_only_https_ge_links_enter() -> None:
    bad = [
        article("x", 1).model_copy(update={"url": "javascript:alert(1)//noticia/"}),
        article("y", 1).model_copy(update={"url": "http://ge.globo.com/futebol/noticia/y.ghtml"}),
        article("z", 1).model_copy(update={"url": "https://evil.example/noticia/z"}),
        article("ok", 1),
    ]
    fetched = []
    news = collect_news(
        NOW,
        [],
        series=A,
        fetch_feed=feeds({"Série A": bad}),
        fetch_lead=lambda a: fetched.append(a.url),
    )
    assert [n.title for n in news] == ["Título ok"] and len(fetched) == 1


def test_refresher_saves_tables_before_collecting_news(tmp_path) -> None:
    from geral.central.models import CentralSnapshot
    from geral.central.refresh import Refresher
    from geral.central.store import load_snapshot

    path = tmp_path / "central.json"
    seen = []

    def news(now, old):
        seen.append(load_snapshot(path))  # the tables are already on disk
        return []

    def build(now, previous, client=None):
        return CentralSnapshot(updated_at=now, series=[])

    assert Refresher(path, 600, build=build, news=news, clock=lambda: NOW).run_once()
    assert seen[0] is not None and seen[0].updated_at == NOW
    assert load_snapshot(path).news_at == NOW
