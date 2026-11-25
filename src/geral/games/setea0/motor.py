"""The 7a0 engine: pure and deterministic, replayed from the seed on every call.

Every function takes `dados` and recomputes from `semente`, like `carreira/motor.py`.
"""

import math
import tomllib
import weakref
from collections.abc import Callable
from functools import cache
from pathlib import Path
from random import Random

from geral.games.setea0.dados import chaves
from geral.games.setea0.modelos import (
    ESQUEMAS,
    MODOS,
    Campanha,
    Cobranca,
    Dados,
    Disputa,
    Epoca,
    Escalado,
    Escolha,
    Gol,
    JogadaInvalida,
    Jogador,
    Partida,
    PedidoDePenalti,
    Posicao,
    Rodada,
    epocas,
)

TAMANHO_OFERTA = 10
RODADAS = 11
TODOS_OS_TEMPOS = Epoca(inicio=0, fim=0, rotulo="todos os tempos")  # all-time opponents

LINHA: dict[Posicao, str] = {"GOL": "GOL", "ZAG": "DEF", "LAT": "DEF", "MEI": "MEI", "ATA": "ATA"}
VIZINHAS = {frozenset(("LAT", "ZAG")), frozenset(("LAT", "MEI")), frozenset(("MEI", "ATA"))}


# Per-`Dados` memo (decade index, opponents' XIs): mass simulations replay thousands of games.
_MEMO: dict[int, tuple[weakref.ref, dict]] = {}


def _memo[T](dados: Dados, chave: tuple, fazer: Callable[[], T]) -> T:
    ident = id(dados)
    guardado = _MEMO.get(ident)
    if guardado is None or guardado[0]() is not dados:  # a dead `Dados` may leave its id behind
        guardado = (weakref.ref(dados, lambda _: _MEMO.pop(ident, None)), {})
        _MEMO[ident] = guardado
    if chave not in guardado[1]:
        guardado[1][chave] = fazer()
    return guardado[1][chave]


# The 7a0 da Geral (dev, 2026-11-24): the die draws a club and one of its eras among the
# published editions; the mixed team plays the grandes of `chaves.toml` `[geral]`.
GERAL = "geral"


def clubes_da_geral(dados: Dados) -> list[str]:
    """The clubs whose eras the Geral draws: the published editions that have a squad."""
    return [
        slug
        for slug, edicao in chaves()["edicao"].items()
        if edicao.get("publicado") and slug in dados.clubes
    ]


def _clubes(dados: Dados, edicao: str) -> list[str]:
    """The squads an edition picks from: its own, or every Geral club."""
    if edicao == GERAL:
        return clubes_da_geral(dados)
    if edicao not in dados.clubes:
        raise JogadaInvalida(f"edição sem 7a0: {edicao}")
    return [edicao]


def epocas_do_clube(dados: Dados, edicao: str) -> list[Epoca]:
    """The eras the die can draw for the edition, oldest first (club by club in the Geral)."""
    return [e for e, _ in _por_epoca(dados, edicao)]


def _por_epoca(dados: Dados, edicao: str) -> list[tuple[Epoca, list[Jogador]]]:
    clubes = _clubes(dados, edicao)

    def fazer() -> list[tuple[Epoca, list[Jogador]]]:
        feitas = []
        for slug in clubes:
            jogadores = dados.clubes[slug].jogadores
            for e in epocas(jogadores):
                if edicao == GERAL:
                    e = Epoca(inicio=e.inicio, fim=e.fim, rotulo=e.rotulo, clube=slug)
                feitas.append((e, [j for j in jogadores if e.contem(j)]))
        return feitas

    return _memo(dados, ("epocas", edicao, tuple(clubes)), fazer)


def _epoca_sorteada(eras: list[Epoca], semente: str, rodada: int, troca: int) -> tuple[int, Random]:
    """The index of the era of `(rodada, troca)` and the rng that drew it. A reroll never brings
    back an era shown in this round; with fewer eras than rerolls, only the last one is left out."""
    vistas: list[int] = []
    for t in range(troca + 1):
        rng = Random(f"{semente}:{rodada}:{t}")
        novas = [i for i in range(len(eras)) if i not in vistas]
        if not novas:
            novas = [i for i in range(len(eras)) if i != vistas[-1]] or list(range(len(eras)))
        vistas.append(rng.choice(novas))
    return vistas[-1], rng


def oferta(
    dados: Dados, edicao: str, semente: str, rodada: int, troca: int, modo: str = "classico"
) -> Rodada:
    """The era drawn for this round and reroll, with up to 10 of its players."""
    if modo not in MODOS:
        raise JogadaInvalida(f"modo desconhecido: {modo}")
    if not 0 <= rodada < RODADAS or not 0 <= troca <= MODOS[modo]:
        raise JogadaInvalida(f"rodada {rodada} ou troca {troca} fora do jogo")
    por_epoca = _por_epoca(dados, edicao)
    if not por_epoca:
        raise JogadaInvalida(f"{edicao} não tem jogadores com época")
    i, rng = _epoca_sorteada([e for e, _ in por_epoca], semente, rodada, troca)
    epoca, da_epoca = por_epoca[i][0], list(por_epoca[i][1])
    rng.shuffle(da_epoca)
    escolhidos: list[Jogador] = []
    ids: set[str] = set()
    for posicao in ("GOL", "LAT", "ZAG", "MEI", "ATA"):  # one of each when the era has one
        if any(posicao in j.posicoes for j in escolhidos):
            continue
        for j in da_epoca:
            if j.id not in ids and posicao in j.posicoes:
                escolhidos.append(j)
                ids.add(j.id)
                break
    for jogador in da_epoca:
        if len(escolhidos) >= TAMANHO_OFERTA:
            break
        if jogador.id not in ids:
            escolhidos.append(jogador)
            ids.add(jogador.id)
    escolhidos.sort(key=lambda j: -j.forca)
    return Rodada.model_construct(  # built from validated parts; mass tests draw thousands
        rodada=rodada,
        troca=troca,
        epoca=epoca,
        jogadores=escolhidos,
        trocas_restantes=MODOS[modo] - troca,
    )


def _encaixe_de(posicao: Posicao, vaga: Posicao) -> float:
    if posicao == vaga:
        return 1.0
    if frozenset((posicao, vaga)) in VIZINHAS:
        return 0.85
    if "GOL" in (posicao, vaga):  # a centre-back in goal, or a keeper up front: next to nothing
        return 0.1
    return 0.45


_ENCAIXES = {(p, v): _encaixe_de(p, v) for p in LINHA for v in LINHA}


def encaixe(jogador: Jogador, vaga: Posicao) -> float:
    """How well the player fits the slot: the best of his positions."""
    return max(_ENCAIXES[p, vaga] for p in jogador.posicoes)


def escalar(
    dados: Dados, edicao: str, semente: str, modo: str, esquema: str, escolhas: list[Escolha]
) -> list[Escalado]:
    """Checks the lineup against the draw; the 11 sorted by slot."""
    if esquema not in ESQUEMAS:
        raise JogadaInvalida(f"esquema desconhecido: {esquema}")
    if modo not in MODOS:
        raise JogadaInvalida(f"modo desconhecido: {modo}")
    if len(escolhas) != RODADAS:
        raise JogadaInvalida("a escalação tem 11 escolhas")
    ordem = sorted(escolhas, key=lambda e: e.rodada)
    if [e.rodada for e in ordem] != list(range(RODADAS)):
        raise JogadaInvalida("as rodadas vão de 0 a 10")
    if sorted(e.vaga for e in ordem) != list(range(len(ESQUEMAS[esquema]))):
        raise JogadaInvalida("vaga repetida ou fora do esquema")
    escalados = []
    usados: set[str] = set()
    troca = 0
    for escolha in ordem:
        if escolha.troca < troca or escolha.troca > MODOS[modo]:
            raise JogadaInvalida(f"troca inválida na rodada {escolha.rodada}")
        troca = escolha.troca
        rodada = oferta(dados, edicao, semente, escolha.rodada, escolha.troca, modo)
        jogador = next((j for j in rodada.jogadores if j.id == escolha.jogador), None)
        if jogador is None:
            raise JogadaInvalida(f"{escolha.jogador} não estava na rodada {escolha.rodada}")
        if jogador.id in usados:
            raise JogadaInvalida(f"{jogador.nome} já está no time")
        usados.add(jogador.id)
        escalados.append(Escalado(jogador=jogador, epoca=rodada.epoca, vaga=escolha.vaga))
    return sorted(escalados, key=lambda e: e.vaga)


# --- matches -------------------------------------------------------------------------------

# Opponent strength relative to the club's own all-time XI, games 1-6; the final adds the derby
# bonus. Relative, so a club of stars and a club of 60s face the same climb.
FATORES = (0.63, 0.65, 0.67, 0.69, 0.71, 0.73)
BONUS_CLASSICO = 0.03
# The Geral: no derby; the final is one more step of the ladder, and the whole ladder is scaled
# by FATOR_GERAL against the mean of its clubs' all-time XIs (`test_calibragem_da_geral`).
PASSO_FINAL_GERAL = 0.02
FATOR_GERAL = 1.05  # greedy: 21.6% on the test data (the fake ABC: 21%), 12.5% on the real
LAMBDA = 1.35  # goals per side when the teams are level
K = 1.5  # how hard the strength ratio bends the scoring
PESO_GOL: dict[Posicao, int] = {"ATA": 5, "MEI": 3, "LAT": 1, "ZAG": 1, "GOL": 0}
# Shootout strengths are rescaled so every club's all-time XI (and, for our keeper, the club's
# keepers) average this: a club of 99s and one of 85s take penalties alike (relative strength).
PADRAO_PENALTI = 85.0
COBRANCAS_REGULARES = 5
MAX_COBRANCAS = 20
JOGOS = 7
ESQUEMA_ADVERSARIO = "4-4-2"


# Without a real keeper the whole team sinks: its strength is multiplied by the goal slot's fit
# to this power (a centre-back in goal, 0.1 ** 0.2 = 0.63), on top of his own share.
EXPOENTE_GOLEIRO = 0.2


def forca_do_time(escalados: list[Escalado], esquema: str) -> float:
    vagas = ESQUEMAS[esquema]
    soma, goleiro = 0.0, 1.0
    for e in escalados:
        encaixado = encaixe(e.jogador, vagas[e.vaga])
        soma += e.jogador.forca * encaixado
        if vagas[e.vaga] == "GOL":
            goleiro = encaixado
    return soma / len(escalados) * goleiro**EXPOENTE_GOLEIRO


def adversario(dados: Dados, slug: str) -> list[Jogador]:
    """The club's 11 strongest in a 4-4-2, slot by slot; gaps filled by the best fit."""
    if slug not in dados.clubes:
        raise JogadaInvalida(f"clube sem elenco: {slug}")
    return list(_memo(dados, ("adversario", slug), lambda: _montar_adversario(dados, slug)))


def _montar_adversario(dados: Dados, slug: str) -> list[Jogador]:
    vagas = ESQUEMAS[ESQUEMA_ADVERSARIO]
    livres = sorted(dados.clubes[slug].jogadores, key=lambda j: -j.forca)
    time: list[Jogador | None] = [None] * len(vagas)
    for i, vaga in enumerate(vagas):
        achado = next((j for j in livres if vaga in j.posicoes), None)
        if achado is not None:
            time[i] = achado
            livres.remove(achado)
    for i, vaga in enumerate(vagas):
        if time[i] is None and livres:
            achado = max(livres, key=lambda j: j.forca * encaixe(j, vaga))
            time[i] = achado
            livres.remove(achado)
    if any(j is None for j in time):
        raise JogadaInvalida(f"{slug} não tem 11 jogadores")
    return [j for j in time if j is not None]


def _escalados_do_adversario(time: list[Jogador]) -> list[Escalado]:
    return [Escalado(jogador=j, epoca=TODOS_OS_TEMPOS, vaga=i) for i, j in enumerate(time)]


def adversarios(dados: Dados, edicao: str) -> list[str]:
    """The 7 opponents of an edition, the derby last; the Geral's grandes weakest first."""
    if edicao == GERAL:
        return _memo(dados, ("grandes",), lambda: _grandes_em_ordem(dados))
    chave = chaves()["edicao"].get(edicao)
    if chave is None:
        raise JogadaInvalida(f"edição sem 7a0: {edicao}")
    return [*chave["adversarios"], chave["final"]]


def _grandes_em_ordem(dados: Dados) -> list[str]:
    grandes = chaves()["geral"]["grandes"]
    return sorted(grandes, key=lambda slug: (referencia(dados, slug), slug))


def referencia(dados: Dados, edicao: str) -> float:
    """The club's own all-time XI, the yardstick its opponents are measured against; for the
    Geral, the mean of its clubs' ones."""
    if edicao == GERAL:
        clubes = clubes_da_geral(dados)
        if not clubes:
            raise JogadaInvalida("a Geral não tem clubes publicados")
        return sum(referencia(dados, slug) for slug in clubes) / len(clubes)

    def fazer() -> float:
        time = _escalados_do_adversario(adversario(dados, edicao))
        return forca_do_time(time, ESQUEMA_ADVERSARIO)

    return _memo(dados, ("referencia", edicao), fazer)


def fator(n: int, edicao: str = "") -> float:
    if edicao == GERAL:
        degrau = FATORES[n - 1] if n < JOGOS else FATORES[-1] + PASSO_FINAL_GERAL
        return degrau * FATOR_GERAL
    return FATORES[n - 1] if n < JOGOS else FATORES[-1] + BONUS_CLASSICO


def forca_do_adversario(dados: Dados, edicao: str, n: int) -> float:
    return referencia(dados, edicao) * fator(n, edicao)


def _poisson(rng: Random, lam: float) -> int:
    limite, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limite:
            return k
        k += 1


def _autor(rng: Random, escalados: list[Escalado], esquema: str) -> str:
    vagas = ESQUEMAS[esquema]
    pesos = [PESO_GOL[vagas[e.vaga]] * e.jogador.forca for e in escalados]
    return rng.choices(escalados, weights=pesos)[0].jogador.nome


def chance_penalti(forca: float) -> float:
    """Same formula as the Carreira's penalty."""
    return max(0.35, min(0.85, 0.45 + (forca - 60) / 100))


def chance_deles(goleiro: float) -> float:
    return max(0.55, min(0.9, 0.75 - (goleiro - 60) / 200))


def disputa(
    rng: Random,
    cobradores: list[Jogador],
    nossas: list[Cobranca],
    chance_deles: float,
    goleiros: tuple[float, float],
    escala: float = 1.0,
) -> tuple[Disputa, bool | None]:
    """A shootout, us first: 5 each, then sudden death, at most 20 each.

    Our kicks come from `nossas` (`"motor"` rolls the Carreira formula); when the list runs
    out before a decision the result is `None`, pending the fan's next kick. `escala` puts our
    kickers on the shared scale (see `PADRAO_PENALTI`). One roll per kick
    is drawn whatever the source, so the opponent's kicks never depend on how we kick.
    """
    feitas = Disputa(nossas=[], deles=[])

    def decidida() -> bool | None:
        a, b = sum(feitas.nossas), sum(feitas.deles)
        ca, cb = len(feitas.nossas), len(feitas.deles)
        if ca <= COBRANCAS_REGULARES and cb <= COBRANCAS_REGULARES:
            if a > b + COBRANCAS_REGULARES - cb:
                return True
            if b > a + COBRANCAS_REGULARES - ca:
                return False
            return None
        if ca == cb and a != b:
            return a > b
        return None

    for i in range(MAX_COBRANCAS):
        if i >= len(nossas):
            return feitas, None
        cobrador = cobradores[i % len(cobradores)]
        rolagem = rng.random()
        if nossas[i].resultado == "motor":
            feitas.nossas.append(rolagem < chance_penalti(cobrador.forca * escala))
        else:
            feitas.nossas.append(nossas[i].resultado == "gol")
        if (fim := decidida()) is not None:
            return feitas, fim
        feitas.deles.append(rng.random() < chance_deles)
        if (fim := decidida()) is not None:
            return feitas, fim
    nosso, deles = goleiros
    if nosso != deles:
        return feitas, nosso > deles
    return feitas, rng.random() < 0.5


def _cobradores(escalados: list[Escalado], esquema: str) -> list[Jogador]:
    vagas = ESQUEMAS[esquema]
    por_forca = sorted(escalados, key=lambda e: -e.jogador.forca)
    frente = [e.jogador for e in por_forca if vagas[e.vaga] in ("ATA", "MEI")][:5]
    return frente + [e.jogador for e in por_forca if e.jogador not in frente]


def _goleiro(escalados: list[Escalado], esquema: str) -> float:
    vagas = ESQUEMAS[esquema]
    e = next(e for e in escalados if vagas[e.vaga] == "GOL")
    return e.jogador.forca * encaixe(e.jogador, "GOL")


def _media_dos_goleiros(dados: Dados, edicao: str, reserva: float) -> float:
    """The club's keepers' mean strength: a keeper is judged against the club's other keepers."""

    def fazer() -> float:
        forcas = [
            j.forca
            for slug in _clubes(dados, edicao)
            for j in dados.clubes[slug].jogadores
            if "GOL" in j.posicoes
        ]
        return sum(forcas) / len(forcas) if forcas else reserva

    return _memo(dados, ("goleiros", edicao, tuple(_clubes(dados, edicao))), fazer)


class _Contexto:
    """What every match of one campaign shares, computed once."""

    def __init__(self, dados, edicao, semente, modo, esquema, escolhas) -> None:
        self.dados, self.edicao, self.semente, self.esquema = dados, edicao, semente, esquema
        self.escalados = escalar(dados, edicao, semente, modo, esquema, escolhas)
        self.slugs = adversarios(dados, edicao)
        self.ref = referencia(dados, edicao)
        self.escala = PADRAO_PENALTI / self.ref
        self.escala_goleiro = PADRAO_PENALTI / _media_dos_goleiros(dados, edicao, self.ref)
        self.nossa = forca_do_time(self.escalados, esquema) / self.ref
        self.cobradores = _cobradores(self.escalados, esquema)
        self.goleiro = _goleiro(self.escalados, esquema)

    def partida(self, n: int, cobrancas: list[Cobranca]) -> Partida | PedidoDePenalti:
        rng = Random(f"{self.semente}:jogo:{n}")
        slug = self.slugs[n - 1]
        time_deles = _escalados_do_adversario(adversario(self.dados, slug))
        razao = self.nossa / fator(n, self.edicao)
        nosso, deles = _poisson(rng, LAMBDA * razao**K), _poisson(rng, LAMBDA / razao**K)
        total = min(nosso + deles, 90)
        lados = [True] * nosso + [False] * deles
        rng.shuffle(lados)
        minutos = sorted(rng.sample(range(1, 91), total))
        gols = [
            Gol(
                minuto=m,
                autor=_autor(rng, self.escalados, self.esquema)
                if lado
                else _autor(rng, time_deles, ESQUEMA_ADVERSARIO),
                nosso=lado,
            )
            for m, lado in zip(minutos, lados, strict=False)
        ]
        nosso = sum(g.nosso for g in gols)
        deles = len(gols) - nosso
        resultado: Disputa | None = None
        venceu: bool | None = nosso > deles
        if nosso == deles:
            goleiro_deles = time_deles[0].jogador.forca * encaixe(time_deles[0].jogador, "GOL")
            resultado, venceu = disputa(
                rng,
                self.cobradores,
                cobrancas,
                chance_deles(self.goleiro * self.escala_goleiro),
                (self.goleiro / self.ref, goleiro_deles / referencia(self.dados, slug)),
                self.escala,
            )
            if venceu is None:
                cobrador = self.cobradores[len(resultado.nossas) % len(self.cobradores)]
                return PedidoDePenalti(
                    n=n,
                    adversario=slug,
                    nosso=nosso,
                    deles=deles,
                    disputa=resultado,
                    cobrador=cobrador.nome,
                    chance=min(99, round(cobrador.forca * self.escala)),
                    gols=gols,
                )
        return Partida(
            n=n,
            adversario=slug,
            gols=gols,
            nosso=nosso,
            deles=deles,
            disputa=resultado,
            venceu=bool(venceu),
        )

    def jogar(
        self, cobrancas: list[list[Cobranca]], ate: int, motor: bool
    ) -> list[Partida | PedidoDePenalti]:
        """Games 1..ate, stopping at an elimination or a pending shootout."""
        feitas: list[Partida | PedidoDePenalti] = []
        disputas = 0
        for n in range(1, ate + 1):
            if motor:
                minhas = [Cobranca(resultado="motor")] * MAX_COBRANCAS
            else:
                minhas = cobrancas[disputas] if disputas < len(cobrancas) else []
            p = self.partida(n, minhas)
            feitas.append(p)
            if isinstance(p, PedidoDePenalti) or not p.venceu:
                break
            if p.disputa is not None:
                disputas += 1
        return feitas


def jogo(
    dados: Dados,
    edicao: str,
    semente: str,
    modo: str,
    esquema: str,
    escolhas: list[Escolha],
    cobrancas: list[list[Cobranca]],
    n: int,
) -> Partida | PedidoDePenalti:
    """Game `n`, replaying 1..n; the k-th shootout of the campaign reads `cobrancas[k]`."""
    if not 1 <= n <= JOGOS:
        raise JogadaInvalida(f"jogo {n} não existe")
    feitas = _Contexto(dados, edicao, semente, modo, esquema, escolhas).jogar(cobrancas, n, False)
    ultima = feitas[-1]
    if isinstance(ultima, PedidoDePenalti) or ultima.n == n:
        return ultima
    raise JogadaInvalida(f"o time caiu no jogo {ultima.n}")


def _campanha(ctx: _Contexto, modo: str, feitas: list) -> Campanha:
    if any(isinstance(p, PedidoDePenalti) for p in feitas):
        raise JogadaInvalida("disputa de pênaltis pendente")
    campeao = len(feitas) == JOGOS and feitas[-1].venceu
    return Campanha(
        edicao=ctx.edicao,
        modo=modo,
        esquema=ctx.esquema,
        escalacao=ctx.escalados,
        partidas=feitas,
        campeao=campeao,
        marcas=marcas(feitas),
        versao=ctx.dados.versao,
    )


def campanha(
    dados: Dados,
    edicao: str,
    semente: str,
    modo: str,
    esquema: str,
    escolhas: list[Escolha],
    cobrancas: list[list[Cobranca]],
) -> Campanha:
    ctx = _Contexto(dados, edicao, semente, modo, esquema, escolhas)
    return _campanha(ctx, modo, ctx.jogar(cobrancas, JOGOS, False))


def campanha_motor(
    dados: Dados, edicao: str, semente: str, modo: str, esquema: str, escolhas: list[Escolha]
) -> Campanha:
    """The engine takes every penalty; what the mass tests run."""
    ctx = _Contexto(dados, edicao, semente, modo, esquema, escolhas)
    return _campanha(ctx, modo, ctx.jogar([], JOGOS, True))


# --- marks ---------------------------------------------------------------------------------

MARCAS = Path(__file__).parent / "marcas.toml"
GOLS_DO_ARTILHEIRO = 7
GOLS_DO_PAREDAO = 2


@cache
def textos_das_marcas() -> dict[str, dict[str, str]]:
    """`{id: {nome, texto}}`, in the card's order."""
    return tomllib.loads(MARCAS.read_text(encoding="utf-8"))


def _esteve_atras(partida: Partida) -> bool:
    saldo = 0
    for gol in partida.gols:
        saldo += 1 if gol.nosso else -1
        if saldo < 0:
            return True
    return False


def marcas(partidas: list[Partida]) -> list[str]:
    """The marks a (possibly unfinished) campaign earned, in `marcas.toml` order."""
    campeao = len(partidas) == JOGOS and all(p.venceu for p in partidas)
    final = partidas[-1] if partidas and partidas[-1].n == JOGOS else None
    artilharia: dict[str, int] = {}
    for p in partidas:
        for gol in p.gols:
            if gol.nosso:
                artilharia[gol.autor] = artilharia.get(gol.autor, 0) + 1
    regras = {
        "sete-a-zero": any(p.nosso >= 7 and p.deles == 0 for p in partidas),
        "campeao": campeao,
        "artilheiro": max(artilharia.values(), default=0) >= GOLS_DO_ARTILHEIRO,
        "nos-penaltis": campeao and final is not None and final.disputa is not None,
        "virada-na-final": campeao and final is not None and _esteve_atras(final),
        "paredao": campeao and sum(p.deles for p in partidas) <= GOLS_DO_PAREDAO,
        "caiu-na-final": final is not None and not final.venceu,
        "estreia-amarga": bool(partidas) and partidas[0].n == 1 and not partidas[0].venceu,
    }
    return [m for m in textos_das_marcas() if regras[m]]
