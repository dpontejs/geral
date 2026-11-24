import sqlite3
from datetime import datetime

from geral.web.setea0_guardado import GuardadoStore, codigo

AGORA = datetime(2026, 11, 24, 12, 0)
ENTRADA = dict(
    edicao="abc",
    semente="s1",
    modo="classico",
    esquema="4-3-3",
    escolhas=[{"rodada": 1, "jogador": "j1", "vaga": 0}],
    cobrancas=[[{"resultado": "gol"}]],
    versao="v1",
)


def test_codigo_curto_e_estavel():
    um = codigo(**ENTRADA)
    assert len(um) == 10
    assert um == codigo(**ENTRADA)
    assert all(c.isalnum() or c in "-_" for c in um)
    outra = {**ENTRADA, "cobrancas": [[{"resultado": "defesa"}]]}
    assert codigo(**outra) != um


def test_guardar_duas_vezes_fica_uma(tmp_path):
    store = GuardadoStore(tmp_path / "geral.db")
    store.guardar("abcdefghij", '{"a": 1}', AGORA)
    store.guardar("abcdefghij", '{"a": 2}', AGORA)
    assert store.guardada("abcdefghij") == '{"a": 1}'
    with sqlite3.connect(tmp_path / "geral.db") as db:
        assert db.execute("SELECT COUNT(*) FROM setea0_guardado").fetchone() == (1,)


def test_guardada_desconhecida_e_none(tmp_path):
    assert GuardadoStore(tmp_path / "geral.db").guardada("nada") is None
