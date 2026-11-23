"""`jogar` plays a career in one pass, answering as it goes. It must give exactly the career the
site rebuilds answer by answer (`simular` over the growing list of answers)."""

import random

from test_carreira_motor import entrada

from geral.games.carreira.dados import carregar
from geral.games.carreira.motor import jogar, simular


def _ao_acaso(rng: random.Random):
    return lambda pendente: rng.randrange(len(pendente.opcoes))


def test_jogar_da_a_mesma_carreira_que_refazer_resposta_por_resposta() -> None:
    dados = carregar()
    for i in range(12):
        e = entrada(f"j{i}").model_copy(
            update={"modo": "completa", "minijogos": bool(i % 2), "escolhas": []}
        )
        vistas: list = []
        sorteio = _ao_acaso(random.Random(i))

        def responder(pendente, vistas=vistas, sorteio=sorteio):
            vistas.append(pendente)
            return sorteio(pendente)

        carreira, final = jogar(dados, "geral", e, responder)
        assert carreira.final is not None and len(final.escolhas) == len(vistas)

        passo = e
        for n, resposta in enumerate(final.escolhas):  # the site's way: replay from scratch
            pendente = simular(dados, "geral", passo).pendente
            assert pendente == vistas[n], (i, n)
            passo = passo.model_copy(update={"escolhas": [*passo.escolhas, resposta]})
        assert simular(dados, "geral", passo) == carreira


def test_jogar_respeita_as_respostas_que_ja_vieram() -> None:
    dados = carregar()
    e = entrada("ja").model_copy(update={"modo": "completa", "escolhas": [1, 0]})
    carreira, final = jogar(dados, "geral", e, _ao_acaso(random.Random(3)))
    assert final.escolhas[:2] == [1, 0]
    assert simular(dados, "geral", final) == carreira
