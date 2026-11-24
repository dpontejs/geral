"""scripts/import_setea0.py --sugerir: new pages join a list without undoing its review."""

import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import import_setea0  # noqa: E402

REVISADA = """# CSA: revisada pelo dev.

[[jogador]]
pagina = "Dida (futebolista)"
nome = "Dida"
incluir = false  # cortado na revisão
"""


def raw(*titulos: str) -> dict:
    pages = {t: {"qid": f"Q{i}", "text": "Só texto.", "clubes": ""} for i, t in enumerate(titulos)}
    return {"titulos": {"csa": list(titulos)}, "pages": pages, "ids": {}, "fama": {}, "ano": 2026}


def test_sugerir_acrescenta_so_as_paginas_novas_no_fim(tmp_path, monkeypatch):
    monkeypatch.setattr(import_setea0, "ELENCOS", tmp_path)
    lista = tmp_path / "csa.toml"
    lista.write_text(REVISADA, encoding="utf-8")

    import_setea0.sugerir(raw("Dida (futebolista)", "Novo Goleiro"), "csa")

    texto = lista.read_text(encoding="utf-8")
    assert texto.startswith(REVISADA)  # the review survives, byte for byte
    novo = texto[len(REVISADA) :]
    assert "# Goleiros e subcategorias (" in novo
    assert "Dida" not in novo
    jogadores = tomllib.loads(texto)["jogador"]
    assert [j["pagina"] for j in jogadores] == ["Dida (futebolista)", "Novo Goleiro"]
    assert jogadores[1]["incluir"] is False  # same rules: no infobox, cut
    assert "sem infobox" in novo


def test_sugerir_sem_paginas_novas_nao_muda_a_lista(tmp_path, monkeypatch):
    monkeypatch.setattr(import_setea0, "ELENCOS", tmp_path)
    lista = tmp_path / "csa.toml"
    lista.write_text(REVISADA, encoding="utf-8")
    import_setea0.sugerir(raw("Dida (futebolista)"), "csa")
    assert lista.read_text(encoding="utf-8") == REVISADA


def test_sugerir_cria_a_lista_quando_nao_existe(tmp_path, monkeypatch):
    monkeypatch.setattr(import_setea0, "ELENCOS", tmp_path)
    import_setea0.sugerir(raw("Novo Goleiro"), "csa")
    jogadores = tomllib.loads((tmp_path / "csa.toml").read_text(encoding="utf-8"))["jogador"]
    assert [j["pagina"] for j in jogadores] == ["Novo Goleiro"]
