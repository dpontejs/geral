import re

import pytest


def menu(html: str) -> str:
    return re.search(r'<nav aria-label="Seções">(.*?)</nav>', html, re.S).group(1)


def current(html: str) -> list[str]:
    return re.findall(r'aria-current="page"[^>]*>([^<]+)<', menu(html))


def test_menu_has_no_home_anchors(client) -> None:
    nav = menu(client.get("/").text)
    assert "#torcidas" not in nav and "#placar" not in nav
    assert [t for t in re.findall(r">([^<]+)</a>", nav)] == [
        "Início",
        "Central",
        "Joguinhos",
        "Peça seu time",
        "Entrar na Geral",
    ]


@pytest.mark.parametrize(
    ("path", "lit"),
    [
        ("/", "Início"),
        ("/central", "Central"),
        ("/central?serie=b", "Central"),
        ("/jogos", "Joguinhos"),
        ("/jogos/onde-jogou", "Joguinhos"),
        ("/pedir", "Peça seu time"),
    ],
)
def test_menu_lights_the_current_page(client, path, lit) -> None:
    assert current(client.get(path).text) == [lit]
