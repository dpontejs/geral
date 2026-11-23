import random
import statistics

from geral.games.carreira import regras
from geral.games.carreira.dados import carregar
from geral.games.carreira.draft import OFERTA, Roubo, montar, oferta
from geral.games.carreira.jogadores import (
    CORTE_FAMA,
    CORTE_NORDESTE,
    CORTE_SELECAO,
    conhecido,
    jogadores_da_base,
    notas_do_jogador,
)
from geral.games.carreira.motor import Craque, Entrada, simular
from geral.games.velha.base import Player, load


def _player(pid="Q1", posicao="atacante", fama=10) -> Player:
    return Player(pid, "Fulano", "2001–2015", (posicao,), (), fama, frozenset(), False, False)


def test_oferta_tem_uma_lenda_e_nove_jogadores_reais() -> None:
    dados = carregar()
    for i in range(50):
        nomes = oferta(dados, "geral", f"o{i}", "flamengo")
        assert OFERTA == len(nomes) == 10 and len({x.nome for x in nomes}) == 10
        assert sum(x.tipo == "lenda" for x in nomes) == 1
        assert all(x.resumo for x in nomes if x.tipo == "jogador")
    curadas = {x.wikidata for x in dados.lendas}
    assert not curadas & {x.wikidata for x in jogadores_da_base(dados)}


def _conhecido(p: Player, nordeste: bool) -> bool:
    return (not p.paises or p.selecao) and (
        p.fama >= CORTE_FAMA
        or (p.selecao and p.fama >= CORTE_SELECAO)
        or (nordeste and p.fama >= CORTE_NORDESTE)
    )


def test_os_jogadores_do_draft_sao_conhecidos() -> None:
    dados = carregar()
    base = load().players
    pool = jogadores_da_base(dados)
    assert all(_conhecido(base[x.wikidata], x.regiao == "nordeste") for x in pool)
    assert 300 <= len(pool) <= 500, len(pool)
    assert CORTE_NORDESTE < CORTE_FAMA
    for i in range(50):
        for clube in ("flamengo", "abc"):
            for x in oferta(dados, "geral", f"c{i}", clube):
                if x.tipo == "jogador":
                    assert _conhecido(base[x.wikidata], x.regiao == "nordeste"), x.nome


def test_estrangeiro_e_desconhecido_ficam_fora() -> None:
    def p(pid, paises=(), fama=100, selecao=False):
        return Player(pid, "X", "", ("atacante",), paises, fama, frozenset(), selecao, False)

    assert conhecido(p("Q1"), nordeste=False)
    assert not conhecido(p("Q2", paises=("Q739",)), nordeste=False)  # Colombia, say
    assert conhecido(p("Q8", paises=("Q29",), selecao=True), nordeste=False)  # Marcelo, Spain
    assert not conhecido(p("Q3", fama=CORTE_FAMA - 1), nordeste=False)
    assert conhecido(p("Q4", fama=CORTE_SELECAO, selecao=True), nordeste=False)
    assert not conhecido(p("Q5", fama=CORTE_SELECAO - 1, selecao=True), nordeste=False)
    assert conhecido(p("Q6", fama=CORTE_NORDESTE), nordeste=True)
    assert not conhecido(p("Q7", fama=CORTE_NORDESTE), nordeste=False)


def test_nota_de_jogador_da_base_segue_fama_e_posicao() -> None:
    atacante = notas_do_jogador(_player())
    assert atacante == notas_do_jogador(_player())  # the same player, the same ratings
    assert atacante["finalizacao"] > atacante["marcacao"] + 20
    zagueiro = notas_do_jogador(_player("Q2", "zagueiro"))
    assert zagueiro["marcacao"] > zagueiro["finalizacao"] + 20

    def nivel(fama: int) -> float:
        return statistics.mean(notas_do_jogador(_player(f"Q{fama}", "meio-campo", fama)).values())

    assert nivel(1) < nivel(10) < nivel(80)
    assert all(1 <= v <= 99 for v in notas_do_jogador(_player(fama=185)).values())


def test_quem_comeca_no_nordeste_ve_jogadores_da_regiao() -> None:
    dados = carregar()
    regionais = set()
    for i in range(50):
        nomes = oferta(dados, "geral", f"n{i}", "abc")
        assert nomes == oferta(dados, "geral", f"n{i}", "abc")
        assert [x.regiao for x in nomes if x.tipo == "lenda"] == ["nordeste"]
        daqui = {x.nome for x in nomes if x.regiao == "nordeste" and x.tipo == "jogador"}
        assert len(daqui) >= 3
        regionais |= daqui
    assert len(regionais) >= 60, len(regionais)  # not the same few every time


def roubos_humanos(dados, semente: str, posicao: str, clube: str = "flamengo") -> list[Roubo]:
    """One name at a time, the next unknown: the best free attribute for the position; the two
    re-rolls go to names whose best free attribute is poor."""
    nomes = oferta(dados, "geral", semente, clube)
    fila, reservas, livres, roubos = nomes[:8], nomes[8:], set(regras.ATRIBUTOS), []
    for lenda in fila:
        melhor = max(livres, key=lambda a: regras.PESOS[posicao][a] * lenda.notas[a])
        if reservas and lenda.notas[melhor] < 70:
            lenda = reservas.pop(0)
            melhor = max(livres, key=lambda a: regras.PESOS[posicao][a] * lenda.notas[a])
        roubos.append(Roubo(lenda=lenda.nome, atributo=melhor))
        livres.remove(melhor)
    return roubos


def draft_humano(dados, semente: str, posicao: str, clube: str = "flamengo") -> dict[str, int]:
    return montar(
        oferta(dados, "geral", semente, clube), roubos_humanos(dados, semente, posicao, clube)
    )


def carreira_humana(dados, i: int, modo: str = "rapida"):
    posicao = regras.POSICOES[i % 5]
    clube = ["flamengo", "abc", "sport", "palmeiras", "bahia", "goias"][i % 6]
    e = Entrada(
        semente_draft=f"d{i}",
        semente=f"c{i}",
        craque=Craque(nome="Zé", camisa=10, posicao=posicao, pe="direito", clube=clube),
        roubos=roubos_humanos(dados, f"d{i}", posicao, clube),
        modo=modo,
    )
    rng = random.Random(i)
    while (c := simular(dados, "geral", e)).final is None:
        e = e.model_copy(update={"escolhas": [*e.escolhas, rng.randrange(len(c.pendente.opcoes))]})
    return c


def test_draft_humano_tem_mediana_perto_de_70() -> None:
    dados = carregar()
    gerais = sorted(
        regras.geral(draft_humano(dados, f"h{i}", regras.POSICOES[i % 5]), regras.POSICOES[i % 5])
        for i in range(1000)
    )
    assert 66 <= gerais[500] <= 74, (gerais[100], gerais[500], gerais[900])


CARREIRAS = 400


def _carreiras():
    dados = carregar()
    return [carreira_humana(dados, i) for i in range(CARREIRAS)]


def test_distribuicao_equilibrada() -> None:
    carreiras = _carreiras()
    picos = [max(t.nota for t in c.temporadas) for c in carreiras]
    nao_decolou = sum(p < 65 for p in picos) / CARREIRAS
    craque = sum(p >= 80 for p in picos) / CARREIRAS
    lendas = sum(c.final.nota >= 90 for c in carreiras) / CARREIRAS

    assert 0.18 <= nao_decolou <= 0.32, nao_decolou
    assert 0.18 <= craque <= 0.35, craque
    assert 0 < lendas <= 0.08, lendas


def test_temporada_ruim_tem_manchete_de_temporada_ruim() -> None:
    ruins = [t for c in _carreiras()[:150] for t in c.temporadas if t.forma <= -7]
    assert ruins and all("temporada-ruim" in t.eventos for t in ruins)


def test_lesao_grave_baixa_o_teto() -> None:
    def pico_depois(c, idade):
        return max(t.nota for t in c.temporadas if t.idade >= idade)

    machucados, inteiros = [], []
    for c in _carreiras():
        cedo = [t for t in c.temporadas if 19 <= t.idade <= 22 and "lesao-grave" in t.eventos]
        (machucados if cedo else inteiros).append(pico_depois(c, 23))
    assert machucados and statistics.mean(machucados) < statistics.mean(inteiros) - 2
