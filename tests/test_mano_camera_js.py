"""The camera's timing (mano-camera.js): the push-in at the strike and the goal's slow replay."""

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULO = ROOT / "src/geral/static/geral/mano-camera.js"


def _rodar(corpo: str):
    node = shutil.which("node")
    assert node, "node is needed to run the page's module (GitHub's runners have it)"
    script = (
        f"import * as c from {json.dumps(MODULO.as_uri())};console.log(JSON.stringify({corpo}));"
    )
    feito = subprocess.run(
        [node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert feito.returncode == 0, feito.stderr
    return json.loads(feito.stdout)


def test_zoom_so_aparece_no_chute_e_volta_ao_normal():
    # strike at 1000, ball lands at 1600
    zooms = _rodar(
        "[0, 850, 1000, 1150, 1400, 1600, 2000, 2600, 3500].map((t) =>"
        " c.zoomDoChute(t, { tGolpe: 1000, fimVoo: 1600, lento: 1 }))"
    )
    antes, quase, golpe, logo, voo, chegada, depois, voltando, fim = zooms
    assert antes == 1 and quase == 1
    assert 1 < golpe < logo <= voo  # pushes in from the strike
    assert voo == chegada == c_max() and depois == c_max()  # held while the ball flies
    assert 1 < voltando < c_max()  # eases back
    assert fim == 1


def c_max():
    return _rodar("c.ZOOM_CHUTE")


def test_zoom_espera_o_lance():
    # no lance yet: tGolpe is Infinity (JSON can't carry it, so the module gets it in JS)
    assert _rodar("c.zoomDoChute(5000, { tGolpe: Infinity, fimVoo: Infinity, lento: 1 })") == 1


def test_replay_cabe_antes_da_proxima_cobranca():
    # strike at 1000, landing at 1600, the next kick's phase at 1000 + 3000 (RESULTADO)
    plano = _rodar("c.planoReplay({ tGolpe: 1000, fimVoo: 1600, ate: 4000 })")
    assert plano is not None
    assert plano["inicio"] >= 1600 + 300  # the GOL sign and the shake are seen first
    duracao = (plano["ate"] - plano["de"]) * plano["fator"]
    assert plano["inicio"] + duracao <= 4000 - 200  # done before the next kick, with a margin
    assert plano["de"] < 1000 < 1600 < plano["ate"]  # from just before the strike past the net
    assert 1.3 <= plano["fator"] <= 2.2  # slow, but not a crawl


def test_sem_tempo_nao_tem_replay():
    assert _rodar("c.planoReplay({ tGolpe: 1000, fimVoo: 2600, ate: 3300 })") is None
    assert _rodar("c.planoReplay({ tGolpe: 1000, fimVoo: 1600, ate: null })") is None


def test_replay_mais_longo_nao_passa_do_lento_maximo():
    plano = _rodar("c.planoReplay({ tGolpe: 1000, fimVoo: 1600, ate: 20000 })")
    assert plano["fator"] == _rodar("c.REPLAY_LENTO_MAX")


def test_relogio_do_replay_anda_devagar_e_acaba():
    plano = _rodar("c.planoReplay({ tGolpe: 1000, fimVoo: 1600, ate: 4000 })")
    p = json.dumps(plano)
    i, f = plano["inicio"], plano["fator"]
    tempos = _rodar(
        f"[{i - 1}, {i}, {i + 100}, {i + (plano['ate'] - plano['de']) * f + 1}]"
        f".map((t) => c.relogioReplay({p}, t))"
    )
    assert tempos[0] is None  # not started
    assert tempos[1] == plano["de"]
    assert abs(tempos[2] - (plano["de"] + 100 / f)) < 1e-6
    assert tempos[3] is None  # over


def test_camera_do_replay_fica_do_lado_do_chute():
    direita = _rodar("c.cameraReplay(2.5, 0)")
    esquerda = _rodar("c.cameraReplay(-2.5, 0)")
    assert esquerda["posicao"][0] < 0 < direita["posicao"][0]
    for cam in (direita, esquerda):
        x, y, z = cam["posicao"]
        assert abs(x) > 3.66 + 1  # outside the posts: the net never fills the picture
        assert 1 < y < 5
        assert cam["olhar"][2] > 0  # looking out to the pitch: the kicker is in the picture
