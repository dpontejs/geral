from random import Random

import pytest

from geral.games.mano.regras import resolver
from geral.games.mano.tipos import Barreira, Chute, Defesa, Posicao

LANCES = 10_000
POSICOES = ("meia_lua", "entrada_esquerda", "entrada_direita")


def _lance_aleatorio(modo: str, rng: Random):
    chute = Chute(alvo=(rng.randint(0, 1000), rng.randint(0, 1000)), barra=rng.randint(0, 1000))
    defesa = Defesa(lado=rng.choice(("esquerda", "fica", "direita")), saida=rng.random() < 0.5)
    if modo == "penaltis":
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


@pytest.mark.parametrize("modo", ["penaltis", "faltas"])
def test_calibragem(modo):
    rng = Random(2026)
    resultados = [_lance_aleatorio(modo, rng).resultado for _ in range(LANCES)]
    taxas = {r: resultados.count(r) / LANCES for r in sorted(set(resultados))}
    print(modo, taxas)
    assert 0.55 <= taxas["gol"] <= 0.65
