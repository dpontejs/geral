"""The 7a0 engine: pure and deterministic, replayed from the seed on every call.

Every function takes `dados` and recomputes from `semente`, like `carreira/motor.py`.
"""

import math
import weakref
from collections.abc import Callable
from random import Random

from geral.games.setea0.dados import chaves
from geral.games.setea0.modelos import (
    ESQUEMAS,
    MODOS,
    Campanha,
    Cobranca,
    Dados,
    Disputa,
    Escalado,
    Escolha,
    Gol,
    JogadaInvalida,
    Jogador,
    Partida,
    PedidoDePenalti,
    Posicao,
    Rodada,
)

MIN_DECADA = 8  # a decade needs this many players at the club to be drawn
TAMANHO_OFERTA = 10
RODADAS = 11

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


def _por_decada(dados: Dados, edicao: str) -> dict[int, list[Jogador]]:
    if edicao not in dados.clubes:
        raise JogadaInvalida(f"edição sem 7a0: {edicao}")

    def fazer() -> dict[int, list[Jogador]]:
        grupos: dict[int, list[Jogador]] = {}
        for jogador in dados.clubes[edicao].jogadores:
            for decada in sorted(jogador.decadas()):
                grupos.setdefault(decada, []).append(jogador)
        return grupos

    return _memo(dados, ("decadas", edicao), fazer)


def decadas(dados: Dados, edicao: str) -> list[int]:
    """The club's decades with at least `MIN_DECADA` players, in order."""
    grupos = _por_decada(dados, edicao)
    return list(
        _memo(
            dados,
            ("lista", edicao),
            lambda: sorted(d for d, js in grupos.items() if len(js) >= MIN_DECADA),
        )
    )


def oferta(
    dados: Dados, edicao: str, semente: str, rodada: int, troca: int, modo: str = "classico"
) -> Rodada:
    """The decade drawn for this round and reroll, with up to 10 of its players."""
    if modo not in MODOS:
        raise JogadaInvalida(f"modo desconhecido: {modo}")
    if not 0 <= rodada < RODADAS or not 0 <= troca <= MODOS[modo]:
        raise JogadaInvalida(f"rodada {rodada} ou troca {troca} fora do jogo")
    rng = Random(f"{semente}:{rodada}:{troca}")
    decada = rng.choice(decadas(dados, edicao))
    da_decada = list(_por_decada(dados, edicao)[decada])
    rng.shuffle(da_decada)
    escolhidos: list[Jogador] = []
    ids: set[str] = set()
    for linha in ("GOL", "DEF", "MEI", "ATA"):  # one of each line when the decade has one
        for j in da_decada:
            if j.id not in ids and any(LINHA[p] == linha for p in j.posicoes):
                escolhidos.append(j)
                ids.add(j.id)
                break
    for jogador in da_decada:
        if len(escolhidos) >= TAMANHO_OFERTA:
            break
        if jogador.id not in ids:
            escolhidos.append(jogador)
            ids.add(jogador.id)
    escolhidos.sort(key=lambda j: -j.forca)
    return Rodada.model_construct(  # built from validated parts; mass tests draw thousands
        rodada=rodada,
        troca=troca,
        decada=decada,
        jogadores=escolhidos,
        trocas_restantes=MODOS[modo] - troca,
    )


def _encaixe_de(posicao: Posicao, vaga: Posicao) -> float:
    if posicao == vaga:
        return 1.0
    if frozenset((posicao, vaga)) in VIZINHAS:
        return 0.85
    if "GOL" in (posicao, vaga):
        return 0.3
    return 0.6


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
        escalados.append(Escalado(jogador=jogador, decada=rodada.decada, vaga=escolha.vaga))
    return sorted(escalados, key=lambda e: e.vaga)


# --- matches -------------------------------------------------------------------------------

# Opponent strength relative to the club's own all-time XI, games 1-6; the final adds the derby
# bonus. Relative, so a club of stars and a club of 60s face the same climb.
FATORES = (0.74, 0.755, 0.77, 0.785, 0.80, 0.815)
BONUS_CLASSICO = 0.03
LAMBDA = 1.35  # goals per side when the teams are level
K = 3.0  # how hard the strength ratio bends the scoring
PESO_GOL: dict[Posicao, int] = {"ATA": 5, "MEI": 3, "LAT": 1, "ZAG": 1, "GOL": 0}
# Shootout strengths are rescaled so every club's all-time XI averages this: a club of 99s
# and one of 85s take penalties alike, as they play alike (relative strength).
PADRAO_PENALTI = 85.0
COBRANCAS_REGULARES = 5
MAX_COBRANCAS = 20
JOGOS = 7
ESQUEMA_ADVERSARIO = "4-4-2"


def forca_do_time(escalados: list[Escalado], esquema: str) -> float:
    vagas = ESQUEMAS[esquema]
    return sum(e.jogador.forca * encaixe(e.jogador, vagas[e.vaga]) for e in escalados) / len(
        escalados
    )


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
    return [Escalado(jogador=j, decada=0, vaga=i) for i, j in enumerate(time)]


def adversarios(dados: Dados, edicao: str) -> list[str]:
    """The 7 opponents of an edition, the derby last."""
    chave = chaves()["edicao"].get(edicao)
    if chave is None:
        raise JogadaInvalida(f"edição sem 7a0: {edicao}")
    return [*chave["adversarios"], chave["final"]]


def referencia(dados: Dados, edicao: str) -> float:
    """The club's own all-time XI, the yardstick its opponents are measured against."""

    def fazer() -> float:
        time = _escalados_do_adversario(adversario(dados, edicao))
        return forca_do_time(time, ESQUEMA_ADVERSARIO)

    return _memo(dados, ("referencia", edicao), fazer)


def fator(n: int) -> float:
    return FATORES[n - 1] if n < JOGOS else FATORES[-1] + BONUS_CLASSICO


def forca_do_adversario(dados: Dados, edicao: str, n: int) -> float:
    return referencia(dados, edicao) * fator(n)


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


class _Contexto:
    """What every match of one campaign shares, computed once."""

    def __init__(self, dados, edicao, semente, modo, esquema, escolhas) -> None:
        self.dados, self.edicao, self.semente, self.esquema = dados, edicao, semente, esquema
        self.escalados = escalar(dados, edicao, semente, modo, esquema, escolhas)
        self.slugs = adversarios(dados, edicao)
        self.ref = referencia(dados, edicao)
        self.escala = PADRAO_PENALTI / self.ref
        self.nossa = forca_do_time(self.escalados, esquema) / self.ref
        self.cobradores = _cobradores(self.escalados, esquema)
        self.goleiro = _goleiro(self.escalados, esquema)

    def partida(self, n: int, cobrancas: list[Cobranca]) -> Partida | PedidoDePenalti:
        rng = Random(f"{self.semente}:jogo:{n}")
        slug = self.slugs[n - 1]
        time_deles = _escalados_do_adversario(adversario(self.dados, slug))
        razao = self.nossa / fator(n)
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
                chance_deles(self.goleiro * self.escala),
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
        marcas=[],
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
