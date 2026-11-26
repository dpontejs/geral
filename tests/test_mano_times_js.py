"""The page's team list and the scene's kits follow the rules' TIMES (teams.toml)."""

import json
import re
from pathlib import Path

from geral.games.mano.times import TIMES

ESTATICO = Path(__file__).resolve().parents[1] / "src/geral/static/geral"


def test_lista_de_times_da_pagina_e_a_da_regra():
    js = (ESTATICO / "mano.js").read_text(encoding="utf-8")
    corpo = re.search(r"^const TIMES = (\{.*\});$", js, re.MULTILINE)
    assert corpo, "mano.js must keep `const TIMES = {...};` on one line"
    pagina = json.loads(re.sub(r"(\w+):", r'"\1":', corpo.group(1)))
    assert list(pagina.items()) == list(TIMES.items())


def test_cada_time_tem_uniforme_e_cor_de_goleiro():
    cena = (ESTATICO / "mano-cena.js").read_text(encoding="utf-8")
    uniformes = cena[cena.index("const UNIFORMES = {") : cena.index("const COR_DO_GOLEIRO")]
    goleiro = re.search(r"^const COR_DO_GOLEIRO = \{(.*)\};$", cena, re.MULTILINE)
    assert goleiro
    for slug in TIMES:
        assert re.search(rf"^  {slug}: \{{$", uniformes, re.MULTILINE), slug
        assert re.search(rf"\b{slug}:", goleiro.group(1)), slug
