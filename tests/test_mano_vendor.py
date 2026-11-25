"""The Mano a Mano scene runs on a vendored, pinned Three.js: no CDN, no npm in the app."""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "src/geral/static/vendor/three"
DRAFT = ROOT / "docs/features/mano-a-mano-rascunho.html"
SCENE = ROOT / "src/geral/static/geral/mano-cena.js"


def test_three_vendorizado_e_fixado():
    core = (VENDOR / "three.core.js").read_text()
    module = (VENDOR / "three.module.js").read_text()
    assert "const REVISION = '187';" in core
    assert "from './three.core.js'" in module
    assert "MIT License" in (VENDOR / "LICENSE").read_text()


def test_vendor_bate_com_o_pacote_do_npm():
    # SHA256SUMS records the files as they come out of three-0.187.0.tgz
    # (registry shasum face29ee2de9bcc31a1b573a76f224e35e0b2894).
    linhas = (VENDOR / "SHA256SUMS").read_text().split("\n")
    somas = dict(reversed(linha.split()) for linha in linhas if linha.strip())
    assert set(somas) == {"three.core.js", "three.module.js", "LICENSE"}
    for nome, soma in somas.items():
        assert hashlib.sha256((VENDOR / nome).read_bytes()).hexdigest() == soma, nome


def test_cena_e_rascunho_importam_do_vendor_sem_cdn():
    cena = SCENE.read_text()
    assert re.search(r"from ['\"]\.\./vendor/three/three\.module\.js['\"]", cena)
    rascunho = DRAFT.read_text()
    assert "../../src/geral/static/geral/mano-cena.js" in rascunho
    for texto in (cena, rascunho):
        for cdn in ("cdn.", "unpkg", "jsdelivr", "esm.sh", "skypack"):
            assert cdn not in texto
