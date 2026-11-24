from geral.games.setea0.modelos import ESQUEMAS, Jogador

ORDEM = ["GOL", "LAT", "ZAG", "MEI", "ATA"]


def test_esquemas_tem_11_vagas_e_1_goleiro():
    for nome, vagas in ESQUEMAS.items():
        assert len(vagas) == 11, nome
        assert vagas.count("GOL") == 1, nome
        indices = [ORDEM.index(v) for v in vagas]
        assert indices == sorted(indices), nome


def test_decadas_das_passagens():
    def jogador(passagens):
        return Jogador(id="Q1", nome="X", posicoes=["MEI"], passagens=passagens, forca=50)

    assert jogador([(1968, 1976), (1981, 1981)]).decadas() == {1960, 1970, 1980}
    assert jogador([]).decadas() == set()
