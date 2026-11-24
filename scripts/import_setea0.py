"""Build `setea0.json`, the 7a0 squads, from Portuguese Wikipedia, Wikidata and the velha base.

The clubs with years at the club (`origem = "ptwiki"` in `chaves.toml`) come from the category
"Futebolistas do <clube>" and its subcategories (the goalkeepers live in one), reviewed by
hand in `elencos/<slug>.toml`; the all-time opponents come from the jogo da velha base.
`idolos.toml` fixes the strength of the idols.

Usage:
  uv run python scripts/import_setea0.py                  # download, write setea0.json, report
  uv run python scripts/import_setea0.py --cache          # rebuild from the last download
  uv run python scripts/import_setea0.py --sugerir abc    # write elencos/abc.toml to review
      # (an existing list only gets the new pages, at the end; its review stays)
"""

import json
import re
import sys
import tomllib
from collections import Counter
from datetime import date
from pathlib import Path

import httpx

from geral.games import ptwiki
from geral.games.onde_jogou import HERE as GAMES
from geral.games.setea0 import dados
from geral.games.setea0.importacao import colunas, jogador_ptwiki, jogadores_velha, montar
from geral.games.setea0.modelos import Dados, epocas
from geral.games.velha import base as velha

CACHE = Path.home() / ".cache" / "geral" / "setea0.json"
PARCIAL = CACHE.with_name("setea0-paginas.json")  # removed once the download ends
ELENCOS = dados.HERE / "elencos"
IDOLOS = dados.HERE / "idolos.toml"
JOGADORES_PT = GAMES / "jogadores_pt.toml"
# Subcategories of a club's players left out: other teams of the club, not its football.
FORA = re.compile(r"\(feminino\)|futebol de areia|showbol", re.IGNORECASE)
REVISADOS = ("abc", "nautico")  # already reviewed in jogadores_pt.toml


def ptwiki_slugs() -> list[str]:
    clubes = dados.chaves()["clube"]
    return [slug for slug, clube in clubes.items() if clube["origem"] == "ptwiki"]


def revisados(slug: str) -> dict[str, str]:
    """Page -> name of the players of `jogadores_pt.toml` for an edition."""
    jogadores = tomllib.loads(JOGADORES_PT.read_text(encoding="utf-8"))["jogador"]
    return {j["pagina"]: j["nome"] for j in jogadores if j["edicao"] == slug}


def download() -> dict:
    """Every page of the ptwiki clubs, their clubs' Wikidata ids and the players' fame.

    The pages (the slow part) are kept in `PARCIAL` once expanded, so a failure after them
    resumes from there.
    """
    clubes = dados.chaves()["clube"]
    with httpx.Client(headers=ptwiki.HEADERS, timeout=60) as client:
        if PARCIAL.exists():
            titulos, pages = json.loads(PARCIAL.read_text(encoding="utf-8")).values()
        else:
            titulos, pages = baixar_paginas(client, clubes)
        nomes = {t for page in pages.values() for t in ptwiki.shown_names(page["clubes"])}
        ids = ptwiki.page_ids(client, sorted(nomes))
        fama = ptwiki.sitelinks(client, sorted({page["qid"] for page in pages.values()}))
    ano = date.today().year  # a stay still open ends here: the same download, the same json
    return {"titulos": titulos, "pages": pages, "ids": ids, "fama": fama, "ano": ano}


def baixar_paginas(client: httpx.Client, clubes: dict) -> tuple[dict, dict]:
    titulos: dict[str, list[str]] = {}
    for slug in ptwiki_slugs():
        membros = ptwiki.category_tree(client, clubes[slug]["categoria"], FORA)
        extras = [t for t in revisados(slug) if t not in membros]
        titulos[slug] = membros + extras
        print(f"{slug}: {len(titulos[slug])} páginas", file=sys.stderr)
    todas = sorted({t for lista in titulos.values() for t in lista})
    pages = ptwiki.fetch_pages(client, todas)
    clubes_ = [(colunas(ptwiki.infobox(p["text"])) or ("", ""))[1] for p in pages.values()]
    for page, coluna in zip(pages.values(), ptwiki.expand_many(client, clubes_), strict=True):
        page["clubes"] = coluna
    PARCIAL.parent.mkdir(parents=True, exist_ok=True)
    PARCIAL.write_text(json.dumps({"titulos": titulos, "pages": pages}), encoding="utf-8")
    return titulos, pages


def avaliar(raw: dict, slug: str, titulo: str) -> tuple[dict | None, str | None]:
    page = raw["pages"].get(titulo)
    if page is None:
        return None, "página não encontrada"
    pagina = {**page, "titulo": titulo, "ids": raw["ids"]}
    clube_qid = dados.chaves()["clube"][slug]["wikidata"]
    return jogador_ptwiki(pagina, clube_qid, raw["fama"].get(page["qid"], 0), raw["ano"])


def _toml(texto: str) -> str:
    return json.dumps(texto, ensure_ascii=False)


def _entradas(
    raw: dict, slug: str, titulos: list[str], ja: dict[str, str], so_revisados: bool = True
) -> list[str]:
    """The TOML entries of the pages, cut (`incluir = false`) with the reason.

    `so_revisados`: a page missing from `jogadores_pt.toml` is cut (a first list); pages added
    to an existing list were never reviewed there, so only the automatic cuts apply.
    """
    linhas: list[str] = []
    for titulo in titulos:
        jogador, motivo = avaliar(raw, slug, titulo)
        if so_revisados and ja and titulo not in ja and not motivo:
            motivo = "fora de jogadores_pt.toml (não revisado)"
        nome = ja.get(titulo) or (jogador or {}).get("nome") or re.sub(r"\s*\(.*\)$", "", titulo)
        incluir = "false  # " + motivo if motivo else "true"
        linhas += ["[[jogador]]", f"pagina = {_toml(titulo)}", f"nome = {_toml(nome)}"]
        linhas += [f"incluir = {incluir}", ""]
    return linhas


def sugerir(raw: dict, slug: str) -> None:
    """Write `elencos/<slug>.toml` with every page; when it exists, add only the new pages at
    the end, so the review already done stays as it is."""
    destino = ELENCOS / f"{slug}.toml"
    clube = dados.chaves()["clube"][slug]
    ja = revisados(slug) if slug in REVISADOS else {}
    if destino.exists():
        texto = destino.read_text(encoding="utf-8")
        listadas = {j["pagina"] for j in tomllib.loads(texto).get("jogador", [])}
        novas = [t for t in raw["titulos"][slug] if t not in listadas]
        if not novas:
            print(f"{destino}: nenhuma página nova")
            return
        linhas = [f"# Goleiros e subcategorias ({date.today().isoformat()})", ""]
        linhas += _entradas(raw, slug, novas, ja, so_revisados=False)
        separador = "" if texto.endswith("\n\n") else "\n" if texto.endswith("\n") else "\n\n"
        destino.write_text(texto + separador + "\n".join(linhas), encoding="utf-8")
        print(f"{destino}: {len(novas)} páginas novas, {linhas.count('incluir = true')} incluídas")
        return
    linhas = [
        f'# {clube["nome"]}: jogadores de "{clube["categoria"]}" (Wikipédia pt), sugeridos por',
        f"# `scripts/import_setea0.py --sugerir {slug}`. A revisão é humana:",
        "# `incluir = false` tira o jogador do 7a0; o comentário diz por que a sugestão o cortou.",
        "",
    ]
    if ja:
        linhas[2:2] = [
            "# Os nomes vêm de jogadores_pt.toml, já revisado; quem não está lá entra cortado."
        ]
    linhas += _entradas(raw, slug, raw["titulos"][slug], ja)
    ELENCOS.mkdir(exist_ok=True)
    destino.write_text("\n".join(linhas), encoding="utf-8")
    print(f"{destino}: {linhas.count('incluir = true')} incluídos")


def brutos_ptwiki(raw: dict, slug: str, relatorio: list[str]) -> list[dict]:
    lista = tomllib.loads((ELENCOS / f"{slug}.toml").read_text(encoding="utf-8"))["jogador"]
    jogadores: dict[str, dict] = {}
    motivos: Counter[str] = Counter()
    for entrada in lista:
        jogador, motivo = avaliar(raw, slug, entrada["pagina"])
        if not entrada["incluir"]:
            motivos[motivo or "cortado na revisão"] += 1
            continue
        if motivo:
            motivos[motivo] += 1
            relatorio.append(f"  {slug}: {entrada['pagina']}: {motivo}")
            continue
        jogadores.setdefault(jogador["id"], {**jogador, "nome": entrada["nome"]})
    cortes = ", ".join(f"{n} {m}" for m, n in motivos.most_common()) or "nenhum"
    relatorio.insert(0, f"{slug}: {len(jogadores)} jogadores; fora: {cortes}")
    return list(jogadores.values())


def eras(dados_: Dados) -> list[str]:
    """Each edition's eras with their player count, as the die draws them."""
    linhas = []
    for slug, edicao in dados.chaves()["edicao"].items():
        jogadores = dados_.clubes[slug].jogadores
        partes = [
            f"{epoca.rotulo} ({sum(epoca.contem(j) for j in jogadores)})"
            for epoca in epocas(jogadores)
        ]
        linhas.append(f"{edicao['nome']}: {', '.join(partes)}")
    return linhas


def main() -> None:
    if "--cache" in sys.argv or ("--sugerir" in sys.argv and CACHE.exists()):
        raw = json.loads(CACHE.read_text(encoding="utf-8"))
    else:
        raw = download()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        PARCIAL.unlink(missing_ok=True)
    if "--sugerir" in sys.argv:
        sugerir(raw, sys.argv[sys.argv.index("--sugerir") + 1])
        return
    relatorio: list[str] = []
    brutos: dict[str, list[dict]] = {}
    for slug in ptwiki_slugs():
        do_clube: list[str] = []
        brutos[slug] = brutos_ptwiki(raw, slug, do_clube)
        relatorio += do_clube
    base = velha.load()
    for slug, clube in dados.chaves()["clube"].items():
        if clube["origem"] == "velha":
            brutos[slug] = jogadores_velha(base, clube["wikidata"])
            relatorio.append(f"{slug}: {len(brutos[slug])} jogadores (base da velha)")
    idolos = {
        slug: {qid: int(forca) for qid, forca in notas.items()}
        for slug, notas in tomllib.loads(IDOLOS.read_text(encoding="utf-8")).items()
    }
    faltando = [
        f"{slug}: {qid}"
        for slug, notas in idolos.items()
        for qid in notas
        if qid not in {j["id"] for j in brutos.get(slug, [])}
    ]
    resultado = montar(brutos, idolos) if not faltando else None
    for linha in relatorio:
        print(linha)
    if resultado is None:
        print("ídolos fora do elenco:\n  " + "\n  ".join(faltando))
        sys.exit(1)
    for linha in eras(resultado):
        print(linha)
    dados.DADOS.write_text(resultado.model_dump_json(indent=1) + "\n", encoding="utf-8")
    print(f"versão {resultado.versao} em {dados.DADOS.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
