import pytest
from setea0_fake import dados_de_teste

from geral.games.setea0 import motor
from geral.games.setea0.modelos import ESQUEMAS, Escolha, JogadaInvalida

DADOS = dados_de_teste()
LINHA = {"GOL": "GOL", "ZAG": "DEF", "LAT": "DEF", "MEI": "MEI", "ATA": "ATA"}


def escolhas_validas(semente="s", esquema="4-4-2", modo="classico", trocas=None):
    """A legal lineup: per round, the strongest offered player that fits a free slot."""
    trocas = trocas or [0] * 11
    livres = list(range(11))
    usados: set[str] = set()
    escolhas = []
    for rodada in range(11):
        r = motor.oferta(DADOS, "abc", semente, rodada, trocas[rodada], modo)
        candidatos = [j for j in r.jogadores if j.id not in usados]
        melhor = max(
            ((j, v) for j in candidatos for v in livres),
            key=lambda jv: (motor.encaixe(jv[0], ESQUEMAS[esquema][jv[1]]), jv[0].forca),
        )
        jogador, vaga = melhor
        livres.remove(vaga)
        usados.add(jogador.id)
        escolhas.append(Escolha(rodada=rodada, troca=trocas[rodada], jogador=jogador.id, vaga=vaga))
    return escolhas


def test_decadas_com_ao_menos_8_jogadores():
    assert motor.decadas(DADOS, "abc") == [1970, 1980, 2000, 2010]


def test_oferta_so_tem_jogadores_do_clube_na_decada():
    ids_abc = {j.id for j in DADOS.clubes["abc"].jogadores}
    for i in range(50):
        r = motor.oferta(DADOS, "abc", f"o{i}", i % 11, 0)
        assert r.decada in motor.decadas(DADOS, "abc")
        assert 1 <= len(r.jogadores) <= motor.TAMANHO_OFERTA
        assert len({j.id for j in r.jogadores}) == len(r.jogadores)
        for j in r.jogadores:
            assert j.id in ids_abc and r.decada in j.decadas()
        assert {LINHA[p] for j in r.jogadores for p in j.posicoes} == {"GOL", "DEF", "MEI", "ATA"}
        forcas = [j.forca for j in r.jogadores]
        assert forcas == sorted(forcas, reverse=True)
        assert r.trocas_restantes == 3


def test_decadas_ralas_nao_saem():
    assert all(motor.oferta(DADOS, "abc", f"r{i}", 0, 0).decada != 1940 for i in range(500))


def test_mesma_semente_mesma_oferta():
    assert motor.oferta(DADOS, "abc", "x", 3, 1) == motor.oferta(DADOS, "abc", "x", 3, 1)


def test_troca_muda_a_decada_ou_os_nomes():
    for i in range(20):
        a = motor.oferta(DADOS, "abc", f"t{i}", 2, 0)
        b = motor.oferta(DADOS, "abc", f"t{i}", 2, 1)
        assert (a.decada, [j.id for j in a.jogadores]) != (b.decada, [j.id for j in b.jogadores])


def test_escalacao_valida_tem_11_com_a_decada_da_oferta():
    escalados = motor.escalar(DADOS, "abc", "s", "classico", "4-4-2", escolhas_validas())
    assert [e.vaga for e in escalados] == list(range(11))
    for e in escalados:
        assert e.decada in e.jogador.decadas()


def _trapaca(regra: str) -> tuple[str, str, list[Escolha]]:
    modo, esquema = "classico", "4-4-2"
    es = escolhas_validas()
    if regra == "menos de 11":
        es = es[:10]
    elif regra == "rodada repetida":
        es[3] = es[3].model_copy(update={"rodada": 2})
    elif regra == "vaga repetida":
        es[1] = es[1].model_copy(update={"vaga": es[0].vaga})
    elif regra == "vaga fora do esquema":
        es[1] = es[1].model_copy(update={"vaga": 11})
    elif regra == "jogador fora da oferta":
        ofertados = {j.id for j in motor.oferta(DADOS, "abc", "s", 4, 0).jogadores}
        fora = next(j.id for j in DADOS.clubes["abc"].jogadores if j.id not in ofertados)
        es[4] = es[4].model_copy(update={"jogador": fora})
    elif regra == "jogador repetido":
        # the same player offered in two rounds (he played in two decades)
        es = _escolhas_com_repetido()
    elif regra == "troca decrescente":
        es = escolhas_validas(trocas=[1] * 5 + [0] * 6)
    elif regra == "trocas a mais":
        es = escolhas_validas(modo="classico", trocas=[0] * 9 + [2, 2])
        modo = "almanaque"
    elif regra == "esquema inexistente":
        esquema = "2-3-5"
    elif regra == "modo inexistente":
        modo = "turbo"
    return modo, esquema, es


def _escolhas_com_repetido() -> list[Escolha]:
    es = escolhas_validas()
    primeiro = es[0].jogador
    return [es[0], es[1].model_copy(update={"jogador": primeiro}), *es[2:]]


REGRAS = [
    "menos de 11",
    "rodada repetida",
    "vaga repetida",
    "vaga fora do esquema",
    "jogador fora da oferta",
    "jogador repetido",
    "troca decrescente",
    "trocas a mais",
    "esquema inexistente",
    "modo inexistente",
]


@pytest.mark.parametrize("regra", REGRAS)
def test_escalacao_trapaceada_da_jogada_invalida(regra):
    modo, esquema, es = _trapaca(regra)
    with pytest.raises(JogadaInvalida):
        motor.escalar(DADOS, "abc", "s", modo, esquema, es)


def test_mesmo_jogador_em_duas_decadas_nao_entra_duas_vezes():
    # a player whose spell crosses two decades shows up in both offers
    from geral.games.setea0.modelos import Clube, Dados, Jogador

    abc = list(DADOS.clubes["abc"].jogadores)
    ponte = Jogador(id="Qponte", nome="Ponte", posicoes=["MEI"], passagens=[(1979, 1980)], forca=99)
    dados = Dados(
        versao="t", clubes={**DADOS.clubes, "abc": Clube(nome="ABC", jogadores=[ponte, *abc])}
    )
    rodadas = {}
    for semente in (f"p{i}" for i in range(400)):
        rs = [motor.oferta(dados, "abc", semente, r, 0) for r in range(11)]
        com = [r.rodada for r in rs if any(j.id == "Qponte" for j in r.jogadores)]
        if len(com) >= 2:
            rodadas = {"semente": semente, "rodadas": com[:2]}
            break
    assert rodadas, "no seed offers the bridging player twice"
    semente = rodadas["semente"]
    livres = list(range(11))
    es = []
    usados: set[str] = set()
    for rodada in range(11):
        r = motor.oferta(dados, "abc", semente, rodada, 0)
        if rodada in rodadas["rodadas"]:
            jogador = "Qponte"
        else:
            jogador = next(j.id for j in r.jogadores if j.id not in usados and j.id != "Qponte")
        usados.add(jogador)
        es.append(Escolha(rodada=rodada, troca=0, jogador=jogador, vaga=livres.pop(0)))
    with pytest.raises(JogadaInvalida):
        motor.escalar(dados, "abc", semente, "classico", "4-4-2", es)
