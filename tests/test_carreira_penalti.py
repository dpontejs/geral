import random

import pytest
from test_carreira_motor import ate_o_fim, entrada

from geral.games.carreira import regras
from geral.games.carreira.dados import carregar
from geral.games.carreira.draft import JogadaInvalida, montar, oferta
from geral.games.carreira.motor import (
    LANCES,
    MAX_LANCES,
    TIPOS_LANCE,
    chance_penalti,
    simular,
)

GOL, MOTOR = 0, 4


def com(semente: str, minijogos: bool = True, **extra):
    e = entrada(semente, **extra)
    return e.model_copy(update={"modo": "completa", "minijogos": minijogos})


def jogar(e, lance=lambda p: GOL, resto=lambda p, rng: 0):
    """Play to the end; `lance` answers the penalty. Returns (career, penalties asked, entry)."""
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


def _com_lance(n=40, tipo=None, **extra):
    """Seeds whose career (answering 0 to everything) reaches a penalty (of this kind)."""
    achadas = []
    for i in range(n):
        e = com(f"p{i}", **extra)
        _, lances, _ = jogar(e)
        if any(tipo in (None, p.lance.tipo) for p in lances):
            achadas.append(e)
    return achadas


def _penaltis(c) -> int:
    return sum(1 for t in c.temporadas if t.lance)


def _evento(tipo: str, resultado: str) -> str:
    fim = "gol" if resultado == "gol" else "erro"
    return f"penalti-{fim}" if tipo == "final" else f"penalti-{tipo}-{fim}"


# -- when: any match, every position ------------------------------------------------------------


def test_o_lance_diz_a_partida_o_adversario_o_minuto_e_a_competicao() -> None:
    dados = carregar()
    vistos = set()
    for i in range(40):
        _, lances, _ = jogar(com(f"p{i}"))
        for p in lances:
            lance = p.lance
            vistos.add(lance.tipo)
            assert lance.tipo in TIPOS_LANCE and p.id == f"penalti-{lance.tipo}"
            assert p.opcoes == list(LANCES)
            assert lance.adversario and lance.adversario != lance.clube
            assert lance.competicao and lance.minuto.endswith("'")
            assert 1 <= p.info[0].chance <= 99
            if lance.tipo == "final":
                assert lance.copa == lance.competicao and lance.minuto == "90+4'"
                assert lance.copa in {liga.copa for liga in dados.ligas.values()}
            else:
                assert not lance.copa
    assert vistos == set(TIPOS_LANCE)


def test_a_frase_muda_com_a_partida() -> None:
    frases = {}
    for i in range(40):
        for p in jogar(com(f"p{i}"))[1]:
            frases.setdefault(p.lance.tipo, p.pergunta)
    assert set(frases) == set(TIPOS_LANCE)
    assert "Final" in frases["final"] and "Final" not in frases["jogo"]
    assert len(set(frases.values())) == 3


def test_a_chance_do_lance_e_a_finalizacao_do_jogador() -> None:
    # The draft's finishing, give or take what the day-to-day did to it along the way.
    alto = [p.info[0].chance for e in _com_lance(30, melhor=True) for p in jogar(e)[1]]
    baixo = [p.info[0].chance for e in _com_lance(30, melhor=False) for p in jogar(e)[1]]
    assert alto and baixo
    assert sum(alto) / len(alto) > sum(baixo) / len(baixo) + 15
    e = _com_lance(20)[0]
    assert abs(jogar(e)[1][0].info[0].chance - _finalizacao(e)) <= 10


@pytest.mark.parametrize("posicao", regras.POSICOES)
def test_penalti_em_todas_as_posicoes(posicao) -> None:
    dados, n = carregar(), 300
    com_penalti = 0
    for i in range(n):
        e = entrada(f"q{i}", posicao=posicao, melhor=(True, False, None)[i % 3])
        com_penalti += _penaltis(ate_o_fim(e, dados)[0]) > 0
    assert com_penalti >= 0.85 * n, com_penalti


def test_media_de_penaltis_por_carreira() -> None:
    dados, total, n = carregar(), 0, 500
    for i in range(n):
        e = entrada(f"q{i}", posicao=regras.POSICOES[i % 5], melhor=(True, False, None)[i % 3])
        total += _penaltis(ate_o_fim(e, dados)[0])
    assert 2 <= total / n <= 3, total / n


def test_no_maximo_um_por_temporada_e_quatro_por_carreira() -> None:
    maximo = 0
    for i in range(60):
        carreira, lances, _ = jogar(com(f"m{i}", melhor=True))
        # a season tells one penalty: every one asked is in a season of its own
        assert len(lances) == _penaltis(carreira) <= MAX_LANCES
        maximo = max(maximo, len(lances))
    assert maximo == MAX_LANCES
    dados = carregar()
    for i in range(300):
        c, _ = ate_o_fim(entrada(f"q{i}", posicao=regras.POSICOES[i % 5]), dados)
        assert _penaltis(c) <= MAX_LANCES


def _temporada_do_lance(e, tipo, resposta):
    """The season of the first penalty of this kind, answering `resposta` to it."""
    carreira, _, _ = jogar(e, lance=lambda p: resposta if p.lance.tipo == tipo else GOL)
    return next(t for t in carreira.temporadas if t.lance and t.lance.tipo == tipo), carreira


@pytest.mark.parametrize("tipo", ["jogo", "classico"])
def test_jogo_comum_nao_mexe_em_titulo(tipo) -> None:
    sementes = _com_lance(40, tipo=tipo)[:5]
    assert sementes
    for e in sementes:
        gol, _ = _temporada_do_lance(e, tipo, GOL)
        erro, _ = _temporada_do_lance(e, tipo, 1)
        assert gol.ano == erro.ano
        assert gol.titulos == erro.titulos
        assert gol.gols == erro.gols + 1  # the penalty is a goal of the season
        assert gol.lance.resultado == "gol" and erro.lance.resultado == "defesa"
        assert gol.manchete == gol.lance.manchete and erro.manchete == erro.lance.manchete
        assert _evento(tipo, "gol") in gol.eventos and _evento(tipo, "defesa") in erro.eventos


def test_classico_usa_o_rival_e_da_as_marcas() -> None:
    dados = carregar()
    por_nome = {m.nome: i for i, m in dados.marcas.items()}
    sementes = _com_lance(40, tipo="classico")[:5]
    assert sementes
    for e in sementes:
        for resposta, marca in ((GOL, "frio-nas-decisoes"), (2, "perdeu-o-penalti")):
            t, carreira = _temporada_do_lance(e, "classico", resposta)
            derbies = dados.classicos_de(dados.clubes[t.clube_id])
            assert (t.lance.competicao, t.lance.adversario) in [(n, r.nome) for n, r in derbies]
            assert marca in [por_nome[n] for n in carreira.final.marcas]


def test_jogo_do_campeonato_e_contra_um_clube_da_liga() -> None:
    dados = carregar()
    vistos = 0
    for e in _com_lance(30, tipo="jogo")[:8]:
        _, carreira = _temporada_do_lance(e, "jogo", GOL)
        for t in carreira.temporadas:
            if t.lance and t.lance.tipo == "jogo":
                vistos += 1
                liga = dados.ligas[dados.clubes[t.clube_id].liga]
                assert t.lance.competicao == liga.campeonato
                da_liga = {c.nome for c in dados.clubes.values() if c.liga == liga.id}
                assert t.lance.adversario in da_liga - {t.clube}
                minuto = t.lance.minuto
                assert minuto.startswith("90+") or 70 <= int(minuto.rstrip("'")) <= 90
    assert vistos >= 5


# -- the final: as before -----------------------------------------------------------------------


@pytest.mark.parametrize("resposta", [0, 1, 2, 3])
def test_gol_da_o_titulo_e_erro_tira(resposta) -> None:
    dados = carregar()
    sementes = _com_lance(40, tipo="final")[:6]
    assert sementes
    for e in sementes:
        t, carreira = _temporada_do_lance(e, "final", resposta)
        assert t.lance.resultado == LANCES[resposta]
        copa = t.lance.copa
        if resposta == GOL:
            assert copa in t.titulos
            assert "frio-nas-decisoes" in _ids(dados, carreira)
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
        for i in range(120):
            carreira, lances, _ = jogar(com(f"s{i}", minijogos=False, melhor=melhor))
            assert not lances
            for t in carreira.temporadas:
                if t.lance:
                    gols[melhor][0] += t.lance.resultado == "gol"
                    gols[melhor][1] += 1
    alto, baixo = (gols[m][0] / gols[m][1] for m in (True, False))
    assert gols[True][1] >= 150 and gols[False][1] >= 150
    assert alto > baixo + 0.1
    assert 0.3 <= baixo and alto <= 0.9


def test_motor_bate_quando_pedido() -> None:
    for e in _com_lance(20)[:5]:
        pelo_motor, _, _ = jogar(e, lance=lambda p: MOTOR)
        sem, lances, _ = jogar(e.model_copy(update={"minijogos": False}))
        assert not lances
        assert pelo_motor.temporadas == sem.temporadas
        assert pelo_motor.final.titulos == sem.final.titulos


def test_replay_estavel() -> None:
    """The same answers give the same career; answering a penalty never changes the past."""
    dados = carregar()
    for e in _com_lance(10)[:3]:
        carreira, _, final = jogar(e, lance=lambda p: 1)
        assert simular(dados, "geral", final) == carreira
        corte = final  # cut right before the first penalty
        while not (p := simular(dados, "geral", corte).pendente) or p.tipo != "lance":
            corte = corte.model_copy(update={"escolhas": corte.escolhas[:-1]})
        antes = simular(dados, "geral", corte).temporadas
        for r in range(len(LANCES)):
            resposta = corte.model_copy(update={"escolhas": [*corte.escolhas, r]})
            assert simular(dados, "geral", resposta).temporadas[: len(antes)] == antes


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


# Cup titles per career of strikers and midfielders (answering 0) measured on origin/main before
# the penalty (eaa6d2d7), with this exact loop: 717 in 1000 careers (Rápida).
COPAS_ANTES = 0.717
# The same loop in a Completa career without minigames, measured at 3d072e2c (the final's penalty
# only, before the penalty went to every match): 300 careers.
COPAS_ANTES_COMPLETA = 0.897  # 269 in 300


def _copas(modo: str, n: int) -> tuple[float, int]:
    dados = carregar()
    copas = {liga.copa for liga in dados.ligas.values() if liga.copa}
    total = finais = 0
    for i in range(n):
        e = entrada(f"t{i}", posicao=("atacante", "meia")[i % 2], melhor=(True, False, None)[i % 3])
        c, _ = ate_o_fim(e.model_copy(update={"modo": modo}), dados)
        total += sum(1 for t in c.temporadas for x in t.titulos if x in copas)
        finais += sum(1 for t in c.temporadas if t.lance and t.lance.tipo == "final")
    return total / n, finais


def test_taxa_de_copas_sem_minijogos_parecida_com_a_de_hoje() -> None:
    taxa, finais = _copas("rapida", 1000)
    assert abs(taxa - COPAS_ANTES) <= 0.2 * COPAS_ANTES, taxa
    assert finais > 300  # the final's penalty does show up


def test_taxa_de_copas_da_completa_sem_minijogos_parecida_com_a_de_hoje() -> None:
    taxa, finais = _copas("completa", 300)
    assert abs(taxa - COPAS_ANTES_COMPLETA) <= 0.2 * COPAS_ANTES_COMPLETA, taxa
    assert finais > 90


def test_gol_do_lance_nao_conta_a_historia_duas_vezes() -> None:
    """The penalty's own headline tells the goal: the 'sangue frio' title event waits for another
    season."""
    vistos = 0
    for e in _com_lance(40):
        carreira, _, _ = jogar(e)
        for t in carreira.temporadas:
            if t.lance and t.lance.resultado == "gol":
                vistos += 1
                assert "penalti-sem-tremer" not in t.eventos, (e.semente, t.ano)
    assert vistos >= 10


def test_manchetes_do_penalti_por_partida() -> None:
    dados = carregar()
    eventos = {e.id: e for e in dados.eventos}
    for tipo in TIPOS_LANCE:
        for resultado in ("gol", "defesa"):
            evento = eventos[_evento(tipo, resultado)]
            assert evento.peso == 0 and not evento.unico and len(evento.manchetes) >= 4
    for e in _com_lance(30)[:10]:
        carreira, _, _ = jogar(e, lance=lambda p: GOL if p.lance.tipo == "jogo" else 1)
        for t in carreira.temporadas:
            if t.lance:
                assert _evento(t.lance.tipo, t.lance.resultado) in t.eventos, t.eventos
                assert t.manchete and "{" not in t.manchete
