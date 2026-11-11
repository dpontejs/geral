def test_quanto_foi_is_gone(client) -> None:
    assert client.get("/jogos/quanto-foi").status_code == 404
    assert (
        client.post("/api/jogos/quanto-foi/geral/1", json={"guesses": [[0, 0]]}).status_code == 404
    )
    assert "quanto-foi" not in client.get("/").text


def test_intervalo_cards_share_one_layout(client) -> None:
    intervalo = client.get("/").text.split('id="intervalo"', 1)[1].split("</section>", 1)[0]

    cards = intervalo.count('class="board mini')
    assert cards == 6
    assert intervalo.count('class="lamp tag"') == cards
    assert intervalo.count('class="lamp title"') == cards
    assert intervalo.count('class="go') == cards  # a footer on every card, playable or not
    assert 'class="lamp big' not in intervalo and 'class="series"' not in intervalo


def test_craque_page_does_not_say_nome_de_guerra(client) -> None:
    assert "nome de guerra" not in client.get("/jogos/craque-do-dia").text.lower()
