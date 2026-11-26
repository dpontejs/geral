"""The winners' celebration (dev, 2026-11-26): its timing and squad, run by node."""

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULO = ROOT / "src/geral/static/geral/mano-festa.js"


def _rodar(corpo: str):
    node = shutil.which("node")
    assert node, "node is needed to run the page's module (GitHub's runners have it)"
    script = f"import * as F from {json.dumps(MODULO.as_uri())};" + corpo
    feito = subprocess.run(
        [node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert feito.returncode == 0, feito.stderr
    return json.loads(feito.stdout)


def test_letreiro_do_campeao():
    titulos = _rodar(
        "console.log(JSON.stringify(['Náutico', 'Palmeiras', ' ', null].map(F.tituloCampeao)))"
    )
    assert titulos == ["NÁUTICO CAMPEÃO", "PALMEIRAS CAMPEÃO", "CAMPEÃO", "CAMPEÃO"]


def test_elenco_igual_nos_dois_navegadores_com_o_goleiro_de_sempre():
    """The same squad from the same seeds; the keeper wears the 1, the others vary."""
    a, b, outra = _rodar(
        "const e = () => F.elenco('k7m2qx:1', 'k7m2qx:goleiro:0:vasco');"
        "console.log(JSON.stringify([e(), e(), F.elenco('k7m2qx:2', 'k7m2qx:goleiro:0:vasco')]))"
    )
    assert a == b
    assert len(a) == 5
    goleiros = [j for j in a if j["papel"] == "goleiro"]
    assert len(goleiros) == 1 and goleiros[0]["visual"]["numero"] == 1
    assert a[0]["papel"] == "batedor"  # the lifter is a kicker
    numeros = [j["visual"]["numero"] for j in a if j["papel"] == "batedor"]
    assert len(set(numeros)) == len(numeros) and 1 not in numeros
    assert [j["visual"] for j in a] != [j["visual"] for j in outra]  # another match, other men
    # the keeper is the match's own: the same look whatever the match
    assert goleiros[0]["visual"] == [j for j in outra if j["papel"] == "goleiro"][0]["visual"]


def test_festa_dura_uns_7_segundos_e_segura():
    r = _rodar(
        "const ms = [0, 1000, 3000, F.FESTA_MS, F.FESTA_MS + 5000];"
        "console.log(JSON.stringify({dura: F.FESTA_MS,"
        " cam: ms.map((t) => F.cameraDaFesta(t)),"
        " taca: ms.map((t) => F.taca(t)),"
        " pulos: [F.FESTA_MS, F.FESTA_MS + 5000].map((t) => F.pulo(t, 0.3)),"
        " pulando: [500, 900, 1300, 2100].map((t) => F.pulo(t, 0.3))}))"
    )
    assert 6000 <= r["dura"] <= 8000
    angulos = [c["angulo"] for c in r["cam"]]
    assert angulos == sorted(angulos) and angulos[0] < angulos[2]  # it goes round them
    assert r["cam"][3] == r["cam"][4]  # then holds
    assert r["taca"][0] == 0 and r["taca"][2:] == [1, 1, 1]  # the cup goes up and stays
    assert r["pulos"] == [0, 0]  # still at the end
    assert max(r["pulando"]) > 0.3


def test_menos_movimento_fica_parado():
    """prefers-reduced-motion: no orbit, no jumping; the cup already up."""
    r = _rodar(
        "const ms = [0, 1500, 4000, 9000];"
        "console.log(JSON.stringify({cam: ms.map((t) => F.cameraDaFesta(t, true)),"
        " taca: ms.map((t) => F.taca(t, true)), pulo: ms.map((t) => F.pulo(t, 0.2, true))}))"
    )
    assert all(c == r["cam"][0] for c in r["cam"])
    assert r["taca"] == [1, 1, 1, 1]
    assert r["pulo"] == [0, 0, 0, 0]
