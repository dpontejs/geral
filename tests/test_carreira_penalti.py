import random

import pytest
from test_carreira_motor import entrada

from geral.games.carreira.dados import carregar
from geral.games.carreira.draft import JogadaInvalida, montar, oferta
from geral.games.carreira.motor import (
    LANCES,
    MAX_LANCES,
    chance_penalti,
    simular,
)

GOL, MOTOR = 0, 4


def com(semente: str, minijogos: bool = True, **extra):
    e = entrada(semente, **extra)
    return e.model_copy(update={"modo": "completa", "minijogos": minijogos})


def jogar(e, lance=lambda p: GOL, resto=lambda p, rng: 0):
    """Play to the end; `lance` answers the penalty. Returns (career, the lance questions)."""
    dados, rng, lances = carregar(), random.Random(e.semente), []
    while (carreira := simular(dados, "geral", e)).final is None:
        p = carreira.pendente
        if p.tipo == "lance":
            lances.append(p)
            resposta = lance(p)
        else:
            resposta = resto(p, rng)
        e = e.model_copy(update={"escolhas": [*e.escolhas, resposta]})
    return carreira, lances, e


def _finalizacao(e) -> int:
    return montar(oferta(carregar(), "geral", e.semente_draft, e.craque.clube), e.roubos)[
        "finalizacao"
    ]


def _com_lance(n=40, **extra):
    """Seeds whose career (answering 0 to everything) reaches a penalty."""
    achadas = []
    for i in range(n):
        e = com(f"p{i}", **extra)
        _, lances, _ = jogar(e)
        if lances:
            achadas.append(e)
    return achadas


def test_final_vai_para_o_penalti() -> None:
    achou = 0
    for i in range(40):
        e = com(f"p{i}")
        _, lances, _ = jogar(e)
        for p in lances:
            achou += 1
            assert p.id == "penalti-final"
            assert p.opcoes == list(LANCES)
            assert p.lance and p.lance.copa and p.lance.adversario
            assert p.lance.adversario != p.lance.clube
            assert 1 <= p.info[0].chance <= 99
    assert achou >= 5


def test_a_chance_do_lance_e_a_finalizacao_do_jogador() -> None:
    # The draft's finishing, give or take what the day-to-day did to it along the way.
    alto = [p.info[0].chance for e in _com_lance(30, melhor=True) for p in jogar(e)[1]]
    baixo = [p.info[0].chance for e in _com_lance(30, melhor=False) for p in jogar(e)[1]]
    assert alto and baixo
    assert sum(alto) / len(alto) > sum(baixo) / len(baixo) + 15
    e = _com_lance(20)[0]
    assert abs(jogar(e)[1][0].info[0].chance - _finalizacao(e)) <= 10


@pytest.mark.parametrize("resposta", [0, 1, 2, 3])
def test_gol_da_o_titulo_e_erro_tira(resposta) -> None:
    dados = carregar()
    for e in _com_lance(25)[:6]:
        carreira, lances, final = jogar(e, lance=lambda p: resposta)
        t = next(t for t in carreira.temporadas if t.lance)
        assert t.lance.resultado == LANCES[resposta]
        copa = lances[0].lance.copa
        if resposta == GOL:
            assert copa in t.titulos
            assert "frio-nas-decisoes" in [m for m in _ids(dados, carreira)]
        else:
            assert copa not in t.titulos
            assert "perdeu-o-penalti" in _ids(dados, carreira)
        assert t.manchete == t.lance.manchete and t.manchete


def _ids(dados, carreira) -> list[str]:
    por_nome = {m.nome: i for i, m in dados.marcas.items()}
    return [por_nome[n] for n in carreira.final.marcas]


def test_sem_minijogos_nao_pergunta_e_sorteia_pela_finalizacao() -> None:
    assert chance_penalti(60) == pytest.approx(0.45)
    assert chance_penalti(20) == 0.35 and chance_penalti(99) == pytest.approx(0.84)
    gols = {True: [0, 0], False: [0, 0]}  # by good draft: [goals, kicks]
    for melhor in (True, False):
        for i in range(250):
            carreira, lances, _ = jogar(com(f"s{i}", minijogos=False, melhor=melhor))
            assert not lances
            for t in carreira.temporadas:
                if t.lance:
                    gols[melhor][0] += t.lance.resultado == "gol"
                    gols[melhor][1] += 1
    alto, baixo = (gols[m][0] / gols[m][1] for m in (True, False))
    assert gols[True][1] >= 50 and gols[False][1] >= 20
    assert alto > baixo
    assert 0.3 <= baixo and alto <= 0.9


def test_motor_bate_quando_pedido() -> None:
    for e in _com_lance(20)[:5]:
        pelo_motor, _, _ = jogar(e, lance=lambda p: MOTOR)
        sem, lances, _ = jogar(e.model_copy(update={"minijogos": False}))
        assert not lances
        assert pelo_motor.temporadas == sem.temporadas
        assert pelo_motor.final.titulos == sem.final.titulos


def test_no_maximo_dois_lances_e_so_atacante_ou_meia() -> None:
    maximo = 0
    for i in range(60):
        _, lances, _ = jogar(com(f"m{i}", melhor=True))
        assert len(lances) <= MAX_LANCES
        maximo = max(maximo, len(lances))
    assert maximo == MAX_LANCES
    for posicao in ("zagueiro", "lateral", "volante"):
        for i in range(25):
            carreira, lances, _ = jogar(com(f"z{i}", posicao=posicao, melhor=True))
            # a defender only kicks if he turned into a midfielder along the way
            if carreira.final.posicao == posicao:
                assert not lances
                assert not any(t.lance for t in carreira.temporadas)


def test_resposta_de_lance_invalida() -> None:
    e = _com_lance(20)[0]
    _, _, final = jogar(e)
    dados = carregar()
    # cut the answers right before the penalty and send an option that does not exist
    while True:
        carreira = simular(dados, "geral", final)
        if carreira.pendente and carreira.pendente.tipo == "lance":
            break
        final = final.model_copy(update={"escolhas": final.escolhas[:-1]})
    for ruim in (5, 9):
        with pytest.raises(JogadaInvalida):
            simular(dados, "geral", final.model_copy(update={"escolhas": [*final.escolhas, ruim]}))
