from geral.games.carreira.dados import carregar
from geral.games.carreira.jogadores import jogadores_da_base


def _pool() -> dict[str, str]:
    return {j.wikidata: j.nome for j in jogadores_da_base(carregar())}


def test_jogador_aparece_pelo_nome_que_o_torcedor_conhece() -> None:
    pool = _pool()
    assert pool["Q38136"] == "Marcelo"  # Marcelo Vieira da Silva Júnior
    assert pool["Q312772"] == "Fred"  # Frederico Chaves Guedes
    assert pool["Q312454"] == "Falcão"  # Paulo Roberto Falcão


def test_nenhum_nome_de_registro_no_draft() -> None:
    longos = [nome for nome in _pool().values() if len(nome.split()) >= 4]
    assert longos == []


def test_quem_e_conhecido_como_tecnico_fica_fora() -> None:
    nomes = set(_pool().values())
    assert not nomes & {"Felipão", "Tite", "Péricles Chamusca", "Abel Braga", "Cuca"}


def test_ajustes_apontam_para_jogadores_da_base() -> None:
    from geral.games.carreira.jogadores import _ajustes
    from geral.games.velha.base import load

    base = load().players
    apelidos, fora = _ajustes()
    nomes = {p.nome for p in base.values()}
    assert [i for i in apelidos if i not in base] == []
    assert [x for x in fora if x not in base and x not in nomes] == []
