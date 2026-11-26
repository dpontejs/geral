"""The kicker's look is the same in both browsers and changes from kick to kick (mano-visual.js)."""

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULO = ROOT / "src/geral/static/geral/mano-visual.js"


def rodar(corpo: str):
    node = shutil.which("node")
    assert node, "node is needed to run the page's module (GitHub's runners have it)"
    script = f"import {{ visual, CABELOS, NUMEROS }} from {json.dumps(MODULO.as_uri())};{corpo}"
    feito = subprocess.run(
        [node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert feito.returncode == 0, feito.stderr
    return json.loads(feito.stdout)


def test_mesma_cobranca_mesmo_batedor_e_cobrancas_seguidas_diferentes():
    saida = rodar(
        "const a = [...Array(12).keys()].map((i) => visual('k7m2qx:1', i));"
        "const b = [...Array(12).keys()].map((i) => visual('k7m2qx:1', i));"
        "console.log(JSON.stringify({a, b, cabelos: CABELOS, numeros: NUMEROS}));"
    )
    assert saida["a"] == saida["b"]
    for antes, depois in zip(saida["a"], saida["a"][1:], strict=False):
        assert antes["numero"] != depois["numero"]
        assert antes["cabelo"] != depois["cabelo"]
    for v in saida["a"]:
        assert v["cabelo"] in saida["cabelos"]
        assert v["numero"] in saida["numeros"] and v["numero"] != 1
        assert 0.95 <= v["escala"] <= 1.05
    assert len({v["pele"] for v in saida["a"]}) >= 3


def test_goleiro_fixo_com_a_camisa_1():
    saida = rodar(
        "const g = [0, 3, 9].map((i) => visual('k7m2qx:goleiro:0:vasco', i, 'goleiro'));"
        "const outro = visual('k7m2qx:goleiro:1:vasco', 0, 'goleiro');"
        "console.log(JSON.stringify({g, outro}));"
    )
    assert saida["g"][0] == saida["g"][1] == saida["g"][2]
    assert saida["g"][0]["numero"] == 1 and saida["outro"]["numero"] == 1
    assert saida["g"][0]["escala"] == 1
