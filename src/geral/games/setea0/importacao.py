"""Pure steps of the 7a0 import: positions, stays at the club, raw players, the final data.

`scripts/import_setea0.py` downloads the pages and calls these; nothing here touches the network.
A raw player is a dict (`id`, `nome`, `posicoes`, `passagens`, `fama`, `selecao`); `montar`
turns the raw squads into `Dados`, with the strength of each player.
"""

import hashlib
import json
import re
import unicodedata
from datetime import date

from geral.games import ptwiki
from geral.games.ptwiki import Stint
from geral.games.setea0.dados import chaves
from geral.games.setea0.forca import forca, percentis
from geral.games.setea0.modelos import Clube, Dados, Jogador, Posicao
from geral.games.velha.base import Base

# First word of each part of the infobox field -> position; order matters ("ponta-de-lança").
PALAVRAS: list[tuple[str, Posicao]] = [
    ("goleiro", "GOL"),
    ("guarda-redes", "GOL"),
    ("quarto-zagueiro", "ZAG"),
    ("zagueiro", "ZAG"),
    ("libero", "ZAG"),
    ("beque", "ZAG"),
    ("defensor", "ZAG"),
    ("defesa", "ZAG"),
    ("lateral", "LAT"),
    ("ala", "LAT"),
    ("ponta-de-lanca", "MEI"),
    ("volante", "MEI"),
    ("meia", "MEI"),
    ("meio", "MEI"),
    ("medio", "MEI"),
    ("atacante", "ATA"),
    ("centroavante", "ATA"),
    ("centro-avante", "ATA"),
    ("ponta", "ATA"),
    ("avancado", "ATA"),
]
PARTES = re.compile(r",|;|/|\s+e\s+|\s+ou\s+")
SELECAO = "Seleção Brasileira de Futebol"
ARQUIVO = re.compile(r"\[\[(?:Ficheiro|Arquivo|Imagem|File|Image):[^\]]*\]\]", re.IGNORECASE)
BASE_OU_OLIMPICA = re.compile(r"sub[- ]?\d|ol[ií]mpic", re.IGNORECASE)
VELHA: dict[str, Posicao] = {
    "goleiro": "GOL",
    "zagueiro": "ZAG",
    "lateral": "LAT",
    "meio-campo": "MEI",
    "atacante": "ATA",
}


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def posicoes(texto: str) -> list[Posicao]:
    """The positions an infobox `posição` names, in order and without repeats."""
    achadas: list[Posicao] = []
    texto = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", texto)  # "[[Meio-campo#Meia|meia]]"
    texto = re.sub(r"<[^>]*>?", " ", texto)  # "<small>volante< e small>"
    for parte in PARTES.split(_sem_acento(ptwiki.plain(texto))):
        parte = parte.strip()  # "meiaatacante", "lateral-direito": the first word decides
        for palavra, posicao in PALAVRAS:
            if parte.startswith(palavra):
                if posicao not in achadas:
                    achadas.append(posicao)
                break
    return achadas


def passagens(stints: list[Stint], clube_qid: str) -> list[tuple[int, int]]:
    """The stays at the club (stint targets already Wikidata ids), consecutive ones merged."""
    lidas = [
        (s.start, s.end if s.end is not None else date.today().year)  # still there: this year
        for s in stints
        if s.target == clube_qid and s.start is not None
    ]
    anos = sorted((inicio, fim) for inicio, fim in lidas if inicio <= fim)  # "1999–1997": a typo
    fundidas: list[tuple[int, int]] = []
    for inicio, fim in anos:
        if fundidas and inicio <= fundidas[-1][1] + 1:
            fundidas[-1] = (fundidas[-1][0], max(fim, fundidas[-1][1]))
        else:
            fundidas.append((inicio, fim))
    return fundidas


def _selecao(campo: str) -> bool:
    for linha in ptwiki.LINE.split(campo):
        alvos = [m.group(1).strip() for m in ptwiki.LINK.finditer(linha)]
        if SELECAO in alvos and not BASE_OU_OLIMPICA.search(linha):
            return True
    return False


def colunas(params: dict[str, str]) -> tuple[str, str] | None:
    """The years and clubs columns of an infobox: `ano`/`clubes`, or numbered `anoN`/`clubeN`
    ({{Info/Futebol}}) joined line by line; None when the infobox has no career."""
    if "clubes" in params:
        return params.get("ano", ""), params["clubes"]
    numeros = sorted(int(k[5:]) for k in params if re.fullmatch(r"clube\d+", k))
    if not numeros:
        return None
    anos = "<br />".join(params.get(f"ano{n}", "") for n in numeros)
    return anos, "<br />".join(params[f"clube{n}"] for n in numeros)


def jogador_ptwiki(pagina: dict, clube_qid: str, fama: int) -> tuple[dict | None, str | None]:
    """The raw player of a page, or why it is left out (for the report).

    `pagina`: {"titulo", "qid", "text", "clubes" (the expanded `colunas` clubs), "ids" (club page
    title -> Wikidata id)}.
    """
    params = ptwiki.infobox(pagina["text"])
    carreira = colunas(params)
    if carreira is None:
        return None, "sem infobox"
    clubes = ARQUIVO.sub("", pagina["clubes"])  # a flag before the club would be read as it
    stints = ptwiki.parse_career(carreira[0], clubes)
    if stints is None:
        return None, "anos e clubes não batem"
    ids = pagina["ids"]
    resolvidos = [Stint(s.start, s.end, ids[s.target]) for s in stints if s.target in ids]
    anos = passagens(resolvidos, clube_qid)
    if not anos:
        return None, "sem anos no clube"
    achadas = posicoes(ptwiki.position(params.get("posição", "")))
    if not achadas:
        return None, "sem posição"
    nome = ptwiki.plain(params.get("nome", "")) or re.sub(r"\s*\(.*\)$", "", pagina["titulo"])
    return {
        "id": pagina["qid"],
        "nome": nome,
        "posicoes": achadas,
        "passagens": anos,
        "fama": fama,
        "selecao": _selecao(params.get("selecaonacional", "")),
    }, None


def jogadores_velha(base: Base, clube_qid: str) -> list[dict]:
    """The all-time players of an opponent club from the jogo da velha base (no years)."""
    jogadores = []
    for player in base.players.values():
        achadas = [VELHA[p] for p in player.posicoes if p in VELHA]
        if clube_qid in player.clubes and achadas:
            jogadores.append(
                {
                    "id": player.id,
                    "nome": player.nome,
                    "posicoes": achadas,
                    "passagens": [],
                    "fama": player.fama,
                    "selecao": player.selecao,
                }
            )
    return jogadores


def _anos(passagens_: list) -> int | None:
    return sum(fim - inicio + 1 for inicio, fim in passagens_) if passagens_ else None


def montar(brutos: dict[str, list[dict]], idolos: dict[str, dict[str, int]]) -> Dados:
    """The 7a0 data: each raw squad with its strengths; idols keep their hand-set strength."""
    for slug, fixas in idolos.items():
        ids = {j["id"] for j in brutos.get(slug, [])}
        if faltando := sorted(set(fixas) - ids):
            raise ValueError(f"ídolos de {slug} fora do elenco: {', '.join(faltando)}")
    clubes = {}
    for slug, jogadores in brutos.items():
        fixas = idolos.get(slug, {})
        ranks = percentis([j["fama"] for j in jogadores])
        clubes[slug] = Clube(
            nome=chaves()["clube"][slug]["nome"],
            jogadores=[
                Jogador(
                    id=j["id"],
                    nome=j["nome"],
                    posicoes=j["posicoes"],
                    passagens=[tuple(p) for p in j["passagens"]],
                    forca=fixas.get(j["id"], forca(rank, _anos(j["passagens"]), j["selecao"])),
                )
                for j, rank in zip(jogadores, ranks, strict=True)
            ],
        )
    conteudo = json.dumps(
        {slug: clube.model_dump(mode="json") for slug, clube in clubes.items()},
        sort_keys=True,
        ensure_ascii=False,
    )
    versao = hashlib.sha256(conteudo.encode()).hexdigest()[:12]
    return Dados(versao=versao, clubes=clubes)
