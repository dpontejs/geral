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


def _rodar(script: str):
    node = shutil.which("node")
    assert node, "node is needed to run the page's module (GitHub's runners have it)"
    feito = subprocess.run(
        [node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert feito.returncode == 0, feito.stderr
    return json.loads(feito.stdout)


def test_mirar_alto_acelera_a_barra():
    """Aiming high costs (dev, 2026-11-26): the same below y=600, up to +45% at the crossbar."""
    ys = list(range(0, 1001, 50))
    pressa, periodo, cavadinha = _rodar(
        f"import {{ pressaBarra, periodoBarra }} from {json.dumps(MODULO.as_uri())};"
        f"const ys = {json.dumps(ys)};"
        "console.log(JSON.stringify([ys.map((y) => pressaBarra([500, y])),"
        " ys.map((y) => periodoBarra([500, y])), periodoBarra([500, 500], true)]));"
    )
    por_y = dict(zip(ys, pressa, strict=True))
    assert all(por_y[y] == 1 for y in ys if y <= 600)
    assert por_y[1000] == 1.45
    altas = [por_y[y] for y in ys if y >= 600]
    assert altas == sorted(altas) and len(set(altas)) == len(altas)  # the higher, the faster
    assert periodo[0] == 1000 and round(periodo[-1]) == round(1000 / 1.45)
    assert cavadinha == 1000  # the cavadinha keeps its pace


def test_pressa_nao_depende_do_lado():
    pressa = _rodar(
        f"import {{ pressaBarra }} from {json.dumps(MODULO.as_uri())};"
        "console.log(JSON.stringify([0, 250, 500, 1000].map((x) => pressaBarra([x, 800]))));"
    )
    assert len(set(pressa)) == 1
