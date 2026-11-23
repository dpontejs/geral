"""Print sample careers as text, to read the game's variety by eye.

    uv run python scripts/carreira_amostra.py 20 [--modo completa] [--edicao geral] [--posicao meia]

Each career gets a random draft order, starting club (in 'geral') and answers.
"""

import argparse
import random

from geral.games.carreira import regras
from geral.games.carreira.dados import carregar
from geral.games.carreira.draft import Roubo, oferta
from geral.games.carreira.motor import Craque, Entrada, simular


def carreira(
    dados,
    edicao: str,
    posicao: str | None,
    n: int,
    clube: str | None = None,
    modo: str = "rapida",
) -> str:
    rng = random.Random(f"amostra:{n}")
    posicao = posicao or rng.choice(regras.POSICOES)
    inicio = clube or rng.choice(
        sorted(c.id for c in dados.clubes.values() if dados.ligas[c.liga].pais == "Brasil")
    )
    lendas = oferta(dados, edicao, f"a{n}", inicio)[:8]
    atributos = list(regras.ATRIBUTOS)
    rng.shuffle(atributos)
    entrada = Entrada(
        semente_draft=f"a{n}",
        semente=f"s{n}",
        craque=Craque(
            nome=f"Craque {n}",
            camisa=rng.randint(2, 99),
            posicao=posicao,
            pe="direito",
            clube=inicio,
        ),
        roubos=[Roubo(lenda=x.nome, atributo=a) for x, a in zip(lendas, atributos, strict=True)],
        modo=modo,
    )
    linhas = [f"== {entrada.craque.nome} ({posicao})"]
    linhas += [f"   roubou {r.atributo} de {r.lenda}" for r in entrada.roubos]
    while (resultado := simular(dados, edicao, entrada)).final is None:
        pergunta = resultado.pendente
        resposta = rng.randrange(len(pergunta.opcoes))
        if pergunta.tipo != "dia":  # the day-to-day is told in the season's line
            info = pergunta.info[resposta] if pergunta.info else None
            risco = ""
            if info and info.chance:
                risco = f" [{info.chance}%{' arriscada' if info.arriscada else ''}]"
            linhas.append(f"   ? {pergunta.pergunta} -> {pergunta.opcoes[resposta]}{risco}")
        entrada = entrada.model_copy(update={"escolhas": [*entrada.escolhas, resposta]})
    for t in resultado.temporadas:
        taças = f" 🏆 {', '.join(t.titulos)}" if t.titulos else ""
        numeros = f"{t.idade} {t.clube:<22} {t.jogos:>2}j {t.gols:>2}g nota {t.nota}"
        linhas.append(f"   {numeros}{taças} | {t.manchete}")
        linhas += [f"      * {m}" for m in t.marcas]
    f = resultado.final
    linhas.append(f"   >> {f.rotulo} ({f.nota}) — {f.descricao} Lembra: {f.parecido}.")
    if f.marcas:
        linhas.append(f"   >> marcas: {', '.join(f.marcas)} · posição final: {f.posicao}")
    return "\n".join(linhas)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("n", type=int)
    parser.add_argument("--edicao", default="geral")
    parser.add_argument("--posicao", choices=regras.POSICOES)
    parser.add_argument("--clube")
    parser.add_argument("--modo", choices=("rapida", "completa"), default="rapida")
    args = parser.parse_args()
    dados = carregar()
    for n in range(args.n):
        print(carreira(dados, args.edicao, args.posicao, n, args.clube, args.modo), end="\n\n")


if __name__ == "__main__":
    main()
