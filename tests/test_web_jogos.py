def test_quanto_foi_is_gone(client) -> None:
    assert client.get("/jogos/quanto-foi").status_code == 404
    assert (
        client.post("/api/jogos/quanto-foi/geral/1", json={"guesses": [[0, 0]]}).status_code == 404
    )
    assert "quanto-foi" not in client.get("/").text
