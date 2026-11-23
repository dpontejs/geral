"""The end of a career: the score, the label from `finais.toml` and the real player it recalls."""

from collections import Counter
from collections.abc import Iterable
from functools import cache

from pydantic import BaseModel

from geral.games.carreira.dados import Dados
from geral.games.velha.base import Base, load

EUROPA = 80
EXOTICAS = {"Arábia Saudita", "Japão", "Estados Unidos", "Turquia", "México"}
FAMILIA = {  # our positions -> the jogo da velha base's
    "zagueiro": "zagueiro",
    "lateral": "lateral",
    "volante": "meio-campo",
    "meia": "meio-campo",
    "atacante": "atacante",
}
CAMPOS = {
    "pico_min",
    "pico_max",
    "clubes_min",
    "clubes_max",
    "um_clube_min",
    "titulos_min",
    "gols_min",
    "selecao_min",
    "copa",
    "mundial",
    "europa_min",
    "exotico_min",
    "paises_min",
    "idade_fim_max",
    "copa_nordeste_min",
}


@cache
def base_real() -> Base:
    return load()


def numeros(temporadas: list) -> dict:
    """What the labels look at, from the professional seasons (17 and over)."""
    pro = [t for t in temporadas if t.idade >= 17] or temporadas
    por_clube = Counter(t.clube_id for t in pro)
    return {
        "pico": max(t.nota for t in temporadas),
        "clubes": len(por_clube),
        "um_clube": max(por_clube.values()),
        "titulos": sum(len(t.titulos) for t in temporadas),
        "gols": sum(t.gols for t in temporadas),
        "selecao": sum(t.selecao for t in temporadas),
        "copa": any(t.copa for t in temporadas),
        "mundial": any("Copa do Mundo" in t.titulos for t in temporadas),
        "europa": sum(t.liga_forca >= EUROPA for t in pro),
        "exotico": sum(t.pais in EXOTICAS for t in pro),
        "paises": len({t.pais for t in pro}),
        "idade_fim": temporadas[-1].idade,
        "copa_nordeste": sum("Copa do Nordeste" in t.titulos for t in temporadas),
    }


def _casa(condicao: dict, n: dict) -> bool:
    desconhecidos = set(condicao) - CAMPOS
    if desconhecidos:
        raise ValueError(f"finais.toml: unknown condicao {desconhecidos}")
    for campo, valor in condicao.items():
        if campo in ("copa", "mundial"):
            ok = n[campo] == valor
        elif campo.endswith("_min"):
            ok = n[campo.removesuffix("_min")] >= valor
        else:
            ok = n[campo.removesuffix("_max")] <= valor
        if not ok:
            return False
    return True


def rotular(dados: Dados, temporadas: list, marcas: Iterable[str] = ()) -> tuple[str, str]:
    """(label, description): the first entry of finais.toml whose condition matches and whose
    `requer` marks he won."""
    n, marcas = numeros(temporadas), set(marcas)
    for final in dados.finais:
        if set(final.get("requer", ())) <= marcas and _casa(final.get("condicao", {}), n):
            return final["rotulo"], final["descricao"]
    raise ValueError("finais.toml needs a last entry without condicao")


def nota(temporadas: list) -> int:
    """0-100: the peak, the trophies, the national team and above all a World Cup."""
    n = numeros(temporadas)
    valor = n["pico"] * 0.55 + min(30, 3 * n["titulos"]) + min(10, n["selecao"] / 10)
    valor += 8 * n["mundial"]
    return max(0, min(100, round(valor)))


def parecido(dados: Dados, base: Base, temporadas: list, posicao: str) -> str:
    """The real player of the same position whose path looks most like this one."""
    familia = FAMILIA[posicao]
    wikidata = {dados.clubes[t.clube_id].wikidata for t in temporadas} - {None}
    n, alvo = numeros(temporadas), nota(temporadas)

    def pontos(p) -> tuple[float, str]:
        valor = 3 * len(p.clubes & wikidata) + 2 * (p.selecao == (n["selecao"] > 0))
        valor += 2 * (p.copa == n["copa"]) - abs(min(p.fama, 100) - alvo) / 10
        return (-valor, p.nome)

    candidatos = [p for p in base.players.values() if familia in p.posicoes]
    return min(candidatos, key=pontos).nome if candidatos else ""


class Veredito(BaseModel):
    """What one club's fans say at the end: one per club, in the order he played for them."""

    clube: str
    clube_id: str
    temporadas: int
    jogos: int
    gols: int
    titulos: int
    veredito: str  # Traidor, Ídolo, Campeão, Passou em branco, Respeitado
    frase: str


FRASES = {
    "Traidor": "Na torcida {do_clube}, esse nome não se fala.",
    "Ídolo": "A torcida {do_clube} nunca vai esquecer.",
    "Campeão": "Deu título {ao_clube} e tem lugar na história.",
    "Passou em branco": "Na torcida {do_clube}, quase ninguém lembra.",
    "Respeitado": "Saiu {do_clube} de cabeça erguida.",
}


def vereditos(dados: Dados, temporadas: list) -> list[Veredito]:
    """Rules, the first that fits: left straight for the derby rival → Traidor; 5+ seasons with
    2+ titles or 60+ goals, or 3+ titles → Ídolo; a title → Campeão; under 25 games → Passou em
    branco; else Respeitado."""
    from geral.games.carreira.motor import artigos  # the engine imports this module

    traidos = {
        a.clube_id
        for a, b in zip(temporadas, temporadas[1:], strict=False)
        if a.clube_id != b.clube_id
        and not (b.chegada or "").startswith(("Emprestado", "Voltou do empréstimo"))  # loans
        and any(r.id == b.clube_id for _, r in dados.classicos_de(dados.clubes[a.clube_id]))
    }
    ordem = list(dict.fromkeys(t.clube_id for t in temporadas))
    saida = []
    for clube_id in ordem:
        dele = [t for t in temporadas if t.clube_id == clube_id]
        anos, jogos = len(dele), sum(t.jogos for t in dele)
        gols, titulos = sum(t.gols for t in dele), sum(len(t.titulos) for t in dele)
        if clube_id in traidos:
            veredito = "Traidor"
        elif (anos >= 5 and (titulos >= 2 or gols >= 60)) or titulos >= 3:
            veredito = "Ídolo"
        elif titulos:
            veredito = "Campeão"
        elif jogos < 25:
            veredito = "Passou em branco"
        else:
            veredito = "Respeitado"
        clube = dados.clubes[clube_id]
        saida.append(
            Veredito(
                clube=clube.nome,
                clube_id=clube_id,
                temporadas=anos,
                jogos=jogos,
                gols=gols,
                titulos=titulos,
                veredito=veredito,
                frase=FRASES[veredito].format_map(artigos("clube", clube)),
            )
        )
    return saida
