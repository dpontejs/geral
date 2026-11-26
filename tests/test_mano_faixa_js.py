"""The bar's good band drawn by the page is the rules' own: the JS port matches `faixa_boa`."""

import json
import shutil
import subprocess
from pathlib import Path

from geral.games.mano.regras import FAIXA_CAVADINHA, faixa_boa

ROOT = Path(__file__).resolve().parents[1]
MODULO = ROOT / "src/geral/static/geral/mano-faixa.js"


def test_faixa_do_cliente_bate_com_a_regra():
    node = shutil.which("node")
    assert node, "node is needed to run the page's module (GitHub's runners have it)"
    pontos = [(x, y) for x in range(0, 1001, 10) for y in range(0, 1001, 50)]
    script = (
        f"import {{ larguraFaixa, faixaBoa }} from {json.dumps(MODULO.as_uri())};"
        f"const pontos = {json.dumps(pontos)};"
        "const saida = [false, true].map((falta) => pontos.map((p) =>"
        " [larguraFaixa(p, falta), faixaBoa(p, falta)]));"
        "console.log(JSON.stringify(saida));"
    )
    feito = subprocess.run(
        [node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert feito.returncode == 0, feito.stderr
    resultado = json.loads(feito.stdout)
    for falta, linha in zip((False, True), resultado, strict=True):
        for (x, y), (largura, (lo, hi)) in zip(pontos, linha, strict=True):
            esperado = faixa_boa((x, y), falta)
            assert largura == esperado, (x, y, falta)
            assert (lo, hi) == (500 - esperado / 2, 500 + esperado / 2), (x, y, falta)


def test_faixa_da_cavadinha_do_cliente_bate_com_a_regra():
    node = shutil.which("node")
    assert node, "node is needed to run the page's module (GitHub's runners have it)"
    script = (
        f"import {{ faixaCavadinha }} from {json.dumps(MODULO.as_uri())};"
        "console.log(JSON.stringify(faixaCavadinha()));"
    )
    feito = subprocess.run(
        [node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert feito.returncode == 0, feito.stderr
    assert json.loads(feito.stdout) == [500 - FAIXA_CAVADINHA / 2, 500 + FAIXA_CAVADINHA / 2]
