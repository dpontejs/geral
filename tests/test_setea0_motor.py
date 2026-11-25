import random

import pytest
from setea0_fake import dados_de_teste
from setea0_times import gulosas

from geral.games.setea0 import motor
from geral.games.setea0.modelos import (
    Campanha,
    Cobranca,
    Escolha,
    JogadaInvalida,
    Jogador,
    Partida,
    PedidoDePenalti,
)

DADOS = dados_de_teste()


def escolhas_validas(semente="s", esquema="4-4-2", modo="classico", trocas=None):
    return gulosas(DADOS, "abc", semente, esquema, modo, trocas)


def test_epocas_do_clube():
    rotulos = [e.rotulo for e in motor.epocas_do_clube(DADOS, "abc")]
    # dev decision 2026-11-24: eras from 1970; the 1940 trio no longer opens "anos 40 a 70"
    assert rotulos == ["anos 70", "anos 80", "anos 90 a 2000", "anos 2010"]


def test_oferta_so_tem_jogadores_do_clube_na_epoca():
    ids_abc = {j.id for j in DADOS.clubes["abc"].jogadores}
    for i in range(50):
        r = motor.oferta(DADOS, "abc", f"o{i}", i % 11, 0)
        assert r.epoca in motor.epocas_do_clube(DADOS, "abc")
        assert 1 <= len(r.jogadores) <= motor.TAMANHO_OFERTA
        assert len({j.id for j in r.jogadores}) == len(r.jogadores)
        for j in r.jogadores:
            assert j.id in ids_abc and r.epoca.contem(j)
        assert {p for j in r.jogadores for p in j.posicoes} == {"GOL", "LAT", "ZAG", "MEI", "ATA"}
        forcas = [j.forca for j in r.jogadores]
        assert forcas == sorted(forcas, reverse=True)
        assert r.trocas_restantes == 3


def test_oferta_tem_as_5_posicoes_mesmo_com_uma_rara():
    from geral.games.setea0.modelos import Clube, Dados

    def jogador(i, posicao):
        return Jogador(
            id=f"Qr{i}", nome=f"R{i}", posicoes=[posicao], passagens=[(2011, 2012)], forca=50
        )

    raros = [jogador(i, p) for i, p in enumerate(["GOL", "LAT", "ZAG"])]
    meio = [jogador(10 + i, "MEI" if i % 2 else "ATA") for i in range(30)]
    dados = Dados(versao="t", clubes={"abc": Clube(nome="ABC", jogadores=raros + meio)})
    for i in range(30):
        r = motor.oferta(dados, "abc", f"p{i}", 0, 0)
        assert {p for j in r.jogadores for p in j.posicoes} == {"GOL", "LAT", "ZAG", "MEI", "ATA"}


def test_decadas_ralas_viram_epoca():
    # dev decision 2026-11-24: eras from 1970; the thin decade joined now is the 90s (one
    # player who stayed on from the 80s), no longer the 1940 trio
    epocas = motor.epocas_do_clube(DADOS, "abc")
    juntas = next(e for e in epocas if e.rotulo == "anos 90 a 2000")
    assert (juntas.inicio, juntas.fim) == (1990, 2000)
    for epoca in epocas:
        assert sum(epoca.contem(j) for j in DADOS.clubes["abc"].jogadores) >= 8
    sorteadas = {motor.oferta(DADOS, "abc", f"r{i}", 0, 0).epoca.rotulo for i in range(200)}
    assert "anos 90 a 2000" in sorteadas and "anos 90" not in sorteadas


def test_quem_so_jogou_antes_de_1970_nunca_aparece():
    antigos = {j.id for j in DADOS.clubes["abc"].jogadores if max(j.decadas()) < 1970}
    assert len(antigos) == 3  # the fake ABC's 1940 trio
    for i in range(200):
        for t in range(2):
            r = motor.oferta(DADOS, "abc", f"a{i}", i % 11, t)
            assert r.epoca.inicio >= 1970
            assert not antigos & {j.id for j in r.jogadores}


def test_mesma_semente_mesma_oferta():
    assert motor.oferta(DADOS, "abc", "x", 3, 1) == motor.oferta(DADOS, "abc", "x", 3, 1)


def test_troca_nunca_repete_epoca_da_rodada():
    for i in range(100):
        vistas = [motor.oferta(DADOS, "abc", f"t{i}", 2, t).epoca for t in range(4)]
        assert len({e.rotulo for e in vistas}) == 4, vistas  # the fake ABC has exactly 4 eras


def test_troca_com_poucas_epocas_nao_repete_a_anterior():
    from geral.games.setea0.modelos import Clube, Dados

    dois = [j for j in DADOS.clubes["abc"].jogadores if j.decadas() & {2000, 2010}]
    dados = Dados(versao="t", clubes={**DADOS.clubes, "abc": Clube(nome="ABC", jogadores=dois)})
    assert len(motor.epocas_do_clube(dados, "abc")) == 2
    for i in range(50):
        vistas = [motor.oferta(dados, "abc", f"t{i}", 0, t).epoca for t in range(4)]
        assert all(a != b for a, b in zip(vistas, vistas[1:], strict=False)), vistas


def test_clube_sem_epoca_da_jogada_invalida():
    from geral.games.setea0.modelos import Clube, Dados

    sem_anos = [j.model_copy(update={"passagens": []}) for j in DADOS.clubes["abc"].jogadores]
    dados = Dados(versao="t", clubes={"abc": Clube(nome="ABC", jogadores=sem_anos)})
    with pytest.raises(JogadaInvalida):
        motor.oferta(dados, "abc", "s", 0, 0)


def test_escalacao_valida_tem_11_com_a_epoca_da_oferta():
    escalados = motor.escalar(DADOS, "abc", "s", "classico", "4-4-2", escolhas_validas())
    assert [e.vaga for e in escalados] == list(range(11))
    for e in escalados:
        assert e.epoca.contem(e.jogador)


def _trapaca(regra: str) -> tuple[str, str, str, list[Escolha]]:
    modo, esquema, semente = "classico", "4-4-2", "s"
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
        es, semente = _escolhas_com_repetido(), _semente_do_repetido()
    elif regra == "troca decrescente":
        es = escolhas_validas(trocas=[1] * 5 + [0] * 6)
    elif regra == "trocas a mais":
        es = escolhas_validas(modo="classico", trocas=[0] * 9 + [2, 2])
        modo = "almanaque"
    elif regra == "esquema inexistente":
        esquema = "2-3-5"
    elif regra == "modo inexistente":
        modo = "turbo"
    return modo, esquema, semente, es


def _semente_do_repetido() -> str:
    """A seed whose 11 offers show twice a player whose spell crosses two decades."""
    for semente in (f"p{i}" for i in range(400)):
        ids = [j.id for r in range(11) for j in motor.oferta(DADOS, "abc", semente, r, 0).jogadores]
        if len(ids) != len(set(ids)):
            return semente
    raise AssertionError("no seed offers a two-decade player twice")


def _escolhas_com_repetido(trocar_o_repetido: bool = False) -> list[Escolha]:
    """Picks him in both rounds (or, with `trocar_o_repetido`, someone else the second time)."""
    ofertas = [motor.oferta(DADOS, "abc", _semente_do_repetido(), r, 0) for r in range(11)]
    ids = [j.id for r in ofertas for j in r.jogadores]
    repetido = next(i for i in ids if ids.count(i) > 1)
    rodadas = [r.rodada for r in ofertas if any(j.id == repetido for j in r.jogadores)]
    usados: set[str] = set()
    es = []
    for r in ofertas:
        if r.rodada in rodadas and not (trocar_o_repetido and r.rodada == rodadas[1]):
            jogador = repetido
        else:
            jogador = next(j.id for j in r.jogadores if j.id not in usados | {repetido})
        usados.add(jogador)
        es.append(Escolha(rodada=r.rodada, troca=0, jogador=jogador, vaga=r.rodada))
    return es


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
    modo, esquema, semente, es = _trapaca(regra)
    with pytest.raises(JogadaInvalida):
        motor.escalar(DADOS, "abc", semente, modo, esquema, es)


def test_mesmo_jogador_em_duas_decadas_nao_entra_duas_vezes():
    # the fake ABC's last player of each decade stays into the next one
    semente = _semente_do_repetido()
    with pytest.raises(JogadaInvalida, match="já está no time"):
        motor.escalar(DADOS, "abc", semente, "classico", "4-4-2", _escolhas_com_repetido())
    valida = _escolhas_com_repetido(trocar_o_repetido=True)
    assert len(motor.escalar(DADOS, "abc", semente, "classico", "4-4-2", valida)) == 11


# --- partida, disputa e campanha ---

MOTOR = Cobranca(resultado="motor")
GOL = Cobranca(resultado="gol")
FORA = Cobranca(resultado="fora")


def _jogador(posicao, forca=80):
    return Jogador(id=f"Q{posicao}{forca}", nome=posicao, posicoes=[posicao], forca=forca)


def test_mesma_entrada_mesma_campanha():
    es = escolhas_validas("igual")
    a = motor.campanha_motor(DADOS, "abc", "igual", "classico", "4-4-2", es)
    b = motor.campanha_motor(DADOS, "abc", "igual", "classico", "4-4-2", es)
    assert a == b and isinstance(a, Campanha) and a.versao == "teste"
    assert 1 <= len(a.partidas) <= 7
    for p in a.partidas:
        minutos = [g.minuto for g in p.gols]
        assert minutos == sorted(minutos) and len(set(minutos)) == len(minutos)
        assert all(1 <= m <= 90 for m in minutos)
        assert p.nosso == sum(g.nosso for g in p.gols)
        assert p.deles == sum(not g.nosso for g in p.gols)


@pytest.mark.parametrize(
    ("posicao", "vaga", "esperado"),
    [
        ("ATA", "ATA", 1.0),
        ("LAT", "ZAG", 0.85),
        ("ZAG", "LAT", 0.85),
        ("LAT", "MEI", 0.85),
        ("MEI", "ATA", 0.85),
        ("ATA", "MEI", 0.85),
        # dev decision 2026-11-24: out of position costs much more, in goal above all (a team
        # with a centre-back in goal still reached game 5); was 0.3 for goal, 0.6 elsewhere
        ("GOL", "ATA", 0.1),
        ("ZAG", "GOL", 0.1),
        ("MEI", "GOL", 0.1),
        ("ZAG", "ATA", 0.45),
        ("LAT", "ATA", 0.45),
    ],
)
def test_fora_de_posicao_perde_forca(posicao, vaga, esperado):
    assert motor.encaixe(_jogador(posicao), vaga) == esperado


def test_time_fora_de_posicao_e_mais_fraco():
    escalados = motor.escalar(DADOS, "abc", "s", "classico", "4-4-2", escolhas_validas())
    certo = motor.forca_do_time(escalados, "4-4-2")
    trocado = [e.model_copy(update={"vaga": 10 - e.vaga}) for e in escalados]
    assert motor.forca_do_time(trocado, "4-4-2") < certo


def test_time_sem_goleiro_desaba():
    from geral.games.setea0.modelos import ESQUEMAS, Escalado

    vagas = ESQUEMAS["4-4-2"]

    def time(trocada: int) -> list[Escalado]:
        epoca = motor.TODOS_OS_TEMPOS
        return [
            Escalado(jogador=_jogador("ZAG" if i == trocada else v), epoca=epoca, vaga=i)
            for i, v in enumerate(vagas)
        ]

    certo = motor.forca_do_time(time(-1), "4-4-2")
    assert certo == 80
    # one man out of position up front costs his share; in goal, the whole team sinks
    assert motor.forca_do_time(time(10), "4-4-2") == pytest.approx((10 * 80 + 80 * 0.45) / 11)
    sem_goleiro = motor.forca_do_time(time(0), "4-4-2")
    assert motor.EXPOENTE_GOLEIRO == 0.2
    assert sem_goleiro == pytest.approx((10 * 80 + 80 * 0.1) / 11 * 0.1**0.2)
    assert sem_goleiro < 0.65 * certo


def test_adversario_tem_11_no_4_4_2():
    time = motor.adversario(DADOS, "bahia")
    assert len(time) == 11 and len({j.id for j in time}) == 11
    assert [j.posicoes[0] for j in time][:1] == ["GOL"]


def test_jogos_1_a_6_em_ordem_crescente():
    forcas = [motor.forca_do_adversario(DADOS, "abc", n) for n in range(1, 7)]
    assert forcas == sorted(forcas) and len(set(forcas)) == 6


def test_final_e_o_classico_e_ao_menos_tao_forte_quanto_o_6o():
    assert motor.forca_do_adversario(DADOS, "abc", 7) >= motor.forca_do_adversario(DADOS, "abc", 6)
    final = motor.adversarios(DADOS, "abc")
    assert final[-1] == "america-rn" and len(final) == 7


def _semente_com_empate(n=1):
    for i in range(400):
        semente = f"e{i}"
        es = escolhas_validas(semente)
        p = motor.jogo(DADOS, "abc", semente, "classico", "4-4-2", es, [], n)
        if isinstance(p, PedidoDePenalti):
            return semente, es
    raise AssertionError("no draw in 400 seeds")


def test_empate_pede_cobranca_do_torcedor():
    semente, es = _semente_com_empate()
    cobrancas: list[Cobranca] = []
    pedidos = 0
    while True:
        r = motor.jogo(DADOS, "abc", semente, "classico", "4-4-2", es, [cobrancas], 1)
        if isinstance(r, Partida):
            break
        pedidos += 1
        assert r.nosso == r.deles and r.n == 1 and r.adversario == "ceara"
        assert len(r.disputa.nossas) == len(cobrancas) == len(r.disputa.deles)
        assert r.cobrador and 1 <= r.chance <= 99
        cobrancas = [*cobrancas, GOL]
        assert pedidos < 50
    assert r.disputa is not None and r.disputa.nossas == [True] * len(r.disputa.nossas)
    assert len(r.disputa.deles) >= 1  # the opponent kicked on his own
    assert pedidos == len(r.disputa.nossas) >= 3


def test_pedido_de_penalti_traz_os_gols_do_jogo():
    """The board plays the drawn match on its clock before the shootout (dev, 2026-11-24)."""
    for i in range(400):
        semente = f"e{i}"
        es = escolhas_validas(semente)
        r = motor.jogo(DADOS, "abc", semente, "classico", "4-4-2", es, [], 1)
        if isinstance(r, PedidoDePenalti) and r.nosso > 0:
            break
    else:
        raise AssertionError("no scoring draw in 400 seeds")
    assert len(r.gols) == r.nosso + r.deles
    assert sum(g.nosso for g in r.gols) == r.nosso
    final = motor.jogo(DADOS, "abc", semente, "classico", "4-4-2", es, [[MOTOR] * 20], 1)
    assert final.gols == r.gols


def test_motor_bate_os_penaltis():
    semente, es = _semente_com_empate()
    a = motor.jogo(DADOS, "abc", semente, "classico", "4-4-2", es, [[MOTOR] * 40], 1)
    b = motor.jogo(DADOS, "abc", semente, "classico", "4-4-2", es, [[MOTOR] * 40], 1)
    assert isinstance(a, Partida) and a == b and a.disputa is not None
    todas = [[MOTOR] * 40 for _ in range(7)]
    com_motor = motor.campanha(DADOS, "abc", semente, "classico", "4-4-2", es, todas)
    assert com_motor == motor.campanha_motor(DADOS, "abc", semente, "classico", "4-4-2", es)


def test_disputa_termina():
    ruins = [_jogador("ATA", 50)] * 5
    disputa, venceu = motor.disputa(
        random.Random(1), ruins, [FORA] * 100, chance_deles=0.0, goleiros=(70.0, 70.0)
    )
    assert venceu in (True, False)
    assert len(disputa.nossas) == len(disputa.deles) == 20
    assert not any(disputa.nossas) and not any(disputa.deles)
    _, mais_forte = motor.disputa(
        random.Random(1), ruins, [FORA] * 100, chance_deles=0.0, goleiros=(80.0, 70.0)
    )
    assert mais_forte is True


def test_disputa_pendente_quando_faltam_cobrancas():
    disputa, venceu = motor.disputa(
        random.Random(1), [_jogador("ATA")] * 5, [GOL, GOL], chance_deles=1.0, goleiros=(70, 70)
    )
    assert venceu is None and disputa.nossas == [True, True] and disputa.deles == [True, True]


def test_disputa_acaba_quando_nao_da_mais_para_alcancar():
    disputa, venceu = motor.disputa(
        random.Random(1), [_jogador("ATA")] * 5, [GOL] * 5, chance_deles=0.0, goleiros=(70, 70)
    )
    assert venceu is True and len(disputa.nossas) == 3 and len(disputa.deles) == 3


def test_jogo_depois_da_eliminacao_e_invalido():
    for i in range(200):
        semente = f"x{i}"
        es = escolhas_validas(semente)
        c = motor.campanha_motor(DADOS, "abc", semente, "classico", "4-4-2", es)
        if not c.campeao:
            caiu = len(c.partidas)
            assert not c.partidas[-1].venceu
            todas = [[MOTOR] * 40 for _ in range(7)]
            if caiu < 7:
                with pytest.raises(JogadaInvalida):
                    motor.jogo(DADOS, "abc", semente, "classico", "4-4-2", es, todas, caiu + 1)
            with pytest.raises(JogadaInvalida):
                motor.jogo(DADOS, "abc", semente, "classico", "4-4-2", es, todas, 8)
            with pytest.raises(JogadaInvalida):
                motor.jogo(DADOS, "abc", semente, "classico", "4-4-2", es, todas, 0)
            return
    raise AssertionError("no elimination in 200 seeds")


def test_campanha_com_disputa_pendente_e_invalida():
    semente, es = _semente_com_empate()
    with pytest.raises(JogadaInvalida):
        motor.campanha(DADOS, "abc", semente, "classico", "4-4-2", es, [])


# --- marcas ---


def _partida(n, nosso, deles, gols=None, disputa=None, venceu=None):
    from geral.games.setea0.modelos import Gol

    if gols is None:
        gols = [Gol(minuto=i + 1, autor=f"Meia {n}.{i}", nosso=True) for i in range(nosso)] + [
            Gol(minuto=50 + i, autor="Rival", nosso=False) for i in range(deles)
        ]
    if venceu is None:
        venceu = nosso > deles
    return Partida(
        n=n,
        adversario="x",
        gols=gols,
        nosso=nosso,
        deles=deles,
        disputa=disputa,
        venceu=venceu,
    )


def test_placar_7_a_0_vira_marca_rara():
    com = 0
    for i in range(1000):
        semente = f"cal{i}"
        es = gulosas(DADOS, "abc", semente)
        c = motor.campanha_motor(DADOS, "abc", semente, "classico", "4-4-2", es)
        com += "sete-a-zero" in c.marcas
    assert 1 <= com <= 50, com


def test_cada_marca_tem_texto():
    marcas = motor.textos_das_marcas()
    assert list(marcas) == [
        "sete-a-zero",
        "campeao",
        "artilheiro",
        "nos-penaltis",
        "virada-na-final",
        "paredao",
        "caiu-na-final",
        "estreia-amarga",
    ]
    for marca in marcas.values():
        assert marca["nome"].strip() and marca["texto"].strip()
        assert "\n" not in marca["texto"]


def test_marcas_por_caso():
    from geral.games.setea0.modelos import Disputa, Gol

    vitorias = [_partida(n, 2, 1) for n in range(1, 7)]
    assert motor.marcas([_partida(1, 7, 0)]) == ["sete-a-zero"]
    assert motor.marcas([_partida(1, 8, 1)]) == []
    assert motor.marcas([*vitorias, _partida(7, 1, 0)]) == ["campeao"]
    assert motor.marcas([_partida(1, 0, 1)]) == ["estreia-amarga"]
    assert motor.marcas([*vitorias, _partida(7, 0, 2)]) == ["caiu-na-final"]
    paredao = [_partida(n, 1, 0) for n in range(1, 7)]
    assert motor.marcas([*paredao, _partida(7, 2, 1)]) == ["campeao", "paredao"]
    assert motor.marcas([*paredao[:3], _partida(4, 0, 1)]) == []  # few goals, but not champion
    quatro = [Gol(minuto=i + 1, autor="Alberi", nosso=True) for i in range(4)]
    artilheiro = [_partida(n, 4, 0, gols=quatro) for n in range(1, 3)]  # Alberi has 8
    assert motor.marcas([*artilheiro, _partida(3, 0, 1)]) == ["artilheiro"]
    penaltis = Disputa(nossas=[True] * 5, deles=[True, True, False, True])
    final_nos_penaltis = _partida(7, 1, 1, disputa=penaltis, venceu=True)
    assert motor.marcas([*vitorias, final_nos_penaltis]) == ["campeao", "nos-penaltis"]
    virada = [
        Gol(minuto=10, autor="Rival", nosso=False),
        Gol(minuto=60, autor="Alberi", nosso=True),
        Gol(minuto=80, autor="Alberi", nosso=True),
    ]
    assert motor.marcas([*vitorias, _partida(7, 2, 1, gols=virada)]) == [
        "campeao",
        "virada-na-final",
    ]
    perdeu_nos_penaltis = _partida(7, 0, 0, disputa=penaltis, venceu=False)
    assert motor.marcas([*vitorias, perdeu_nos_penaltis]) == ["caiu-na-final"]
