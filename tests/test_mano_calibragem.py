from random import Random

import pytest

from geral.games.mano.regras import faixa_boa, resolver
from geral.games.mano.tipos import Barreira, Chute, Defesa, Posicao

LANCES = 10_000
P_CAVADINHA_ALEATORIA = 0.05  # the random kicker chips one kick in twenty (dev, 2026-11-26)
POSICOES = ("meia_lua", "entrada_esquerda", "entrada_direita")


def _lance_aleatorio(modo: str, rng: Random):
    chute = Chute(alvo=(rng.randint(0, 1000), rng.randint(0, 1000)), barra=rng.randint(0, 1000))
    defesa = Defesa(lado=rng.choice(("esquerda", "fica", "direita")), saida=rng.random() < 0.5)
    if modo == "penaltis":
        if rng.random() < P_CAVADINHA_ALEATORIA:
            chute = chute.model_copy(update={"alvo": (500, 500), "cavadinha": True})
        return resolver(chute, defesa, rng)
    chute = chute.model_copy(
        update={
            "trajetoria": rng.choice(("rasteira", "por_cima", "pelo_lado")),
            "curva": rng.uniform(-1, 1),
        }
    )
    barreira = Barreira(n=rng.randint(2, 5), x=rng.randint(0, 1000))
    posicao = Posicao(nome=rng.choice(POSICOES), desvio=rng.randint(-80, 80))
    return resolver(chute, defesa, rng, barreira=barreira, posicao=posicao)


# the dev chose free kicks harder than penalties, with the same keeper (2026-11-25), then the
# penalty harder for the kicker (2026-11-26): 50-60% instead of 55-65%
FAIXAS = {"penaltis": (0.50, 0.60), "faltas": (0.45, 0.50)}


@pytest.mark.parametrize("modo", ["penaltis", "faltas"])
def test_calibragem(modo):
    rng = Random(2026)
    resultados = [_lance_aleatorio(modo, rng).resultado for _ in range(LANCES)]
    taxas = {r: resultados.count(r) / LANCES for r in sorted(set(resultados))}
    print(modo, taxas)
    minimo, maximo = FAIXAS[modo]
    assert minimo <= taxas["gol"] <= maximo


def test_quem_acerta_a_barra_no_canto_ainda_perde_alguns():
    """A good human: corner aims, the bar near the band's centre, against a keeper who guesses
    the side half the time. The rate goes in the PR; here only a sanity range."""
    rng = Random(7)
    gols = erros_de_barra = 0
    for _ in range(LANCES):
        x = rng.choice((90, 910))
        alvo = (x, rng.randint(80, 450))
        barra = min(1000, max(0, round(rng.gauss(500, 60))))
        certo = "esquerda" if x < 500 else "direita"
        outros = [lado for lado in ("esquerda", "fica", "direita") if lado != certo]
        lado = certo if rng.random() < 0.5 else rng.choice(outros)
        defesa = Defesa(lado=lado, saida=rng.random() < 0.5)
        gols += resolver(Chute(alvo=alvo, barra=barra), defesa, rng).resultado == "gol"
        erros_de_barra += abs(barra - 500) > faixa_boa(alvo, False) / 2
    taxa = gols / LANCES
    print("humano no canto", taxa, "erros de barra", erros_de_barra / LANCES)
    assert 0.35 <= taxa <= 0.60
    assert erros_de_barra / LANCES > 0.05  # in the corner the bar must matter (dev, 2026-11-26)
