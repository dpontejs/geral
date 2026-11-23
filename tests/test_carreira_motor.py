from pathlib import Path
from statistics import mean

import pytest

from geral.games.carreira import regras
from geral.games.carreira.dados import PASTA, carregar
from geral.games.carreira.draft import JogadaInvalida, Roubo, oferta
from geral.games.carreira.motor import Craque, Entrada, jogar, simular

DRAFT = "d1"


def _roubos(ofertadas, melhor: bool | None = None, posicao="atacante") -> list[Roubo]:
    """Greedy draft: the most important attributes of the position first, each from the best
    (or worst) legend still free; `None` takes the offer in order."""
    if melhor is None:
        pares = list(zip(ofertadas, regras.ATRIBUTOS, strict=False))
        return [Roubo(lenda=lenda.nome, atributo=a) for lenda, a in pares]
    livres, roubos = list(ofertadas), []
    for atributo in sorted(regras.ATRIBUTOS, key=lambda a: -regras.PESOS[posicao][a]):
        lenda = (max if melhor else min)(livres, key=lambda x: x.notas[atributo])
        livres.remove(lenda)
        roubos.append(Roubo(lenda=lenda.nome, atributo=atributo))
    return roubos


def entrada(semente="s1", escolhas=(), melhor=None, posicao="atacante", clube="bahia", dados=None):
    ofertadas = oferta(dados or carregar(), "geral", DRAFT, clube)
    return Entrada(
        semente_draft=DRAFT,
        semente=semente,
        craque=Craque(nome="Zé", camisa=10, posicao=posicao, pe="direito", clube=clube),
        roubos=_roubos(ofertadas, melhor, posicao),
        escolhas=list(escolhas),
    )


def ate_o_fim(e: Entrada, dados=None, edicao="geral"):
    """Answer every question with option 0 until the career ends."""
    return jogar(dados or carregar(), edicao, e, lambda pendente: 0)


def test_same_input_gives_the_same_career() -> None:
    dados = carregar()

    assert simular(dados, "geral", entrada()) == simular(dados, "geral", entrada())
    assert simular(dados, "geral", entrada()) != simular(dados, "geral", entrada("s2"))


def test_escolhas_em_prefixo_repetem_o_passado() -> None:
    dados = carregar()
    for semente in (f"p{i}" for i in range(40)):
        primeira = simular(dados, "geral", entrada(semente))
        if primeira.pendente is None:
            continue
        for opcao in range(len(primeira.pendente.opcoes)):
            depois = simular(dados, "geral", entrada(semente, [opcao]))
            assert depois.temporadas[: len(primeira.temporadas)] == primeira.temporadas
        return
    pytest.fail("nenhuma carreira com escolha em 40 sementes")


def test_better_draft_scores_higher_on_average() -> None:
    sementes = [f"b{i}" for i in range(200)]
    forte = [ate_o_fim(entrada(s, melhor=True))[0].final.nota for s in sementes]
    fraco = [ate_o_fim(entrada(s, melhor=False))[0].final.nota for s in sementes]

    assert mean(forte) > mean(fraco) + 10
    assert max(fraco) > min(forte)  # luck still matters: not always


def test_choices_change_the_story() -> None:
    dados = carregar()
    for semente in (f"c{i}" for i in range(300)):
        carreira = simular(dados, "geral", entrada(semente, melhor=True))
        if carreira.pendente and carreira.pendente.id == "proposta-europa":
            europa, ficar = (ate_o_fim(entrada(semente, [i], melhor=True))[0] for i in (0, 1))
            assert {t.clube for t in europa.temporadas} != {t.clube for t in ficar.temporadas}
            return
    pytest.fail("nenhuma proposta da Europa em 300 sementes")


def test_team_edition_starts_in_its_youth() -> None:
    dados = carregar()
    e = entrada(clube=None).model_copy(update={"semente_draft": "v1"})
    e = e.model_copy(update={"roubos": _roubos(oferta(dados, "vasco", "v1"))})

    primeira = simular(dados, "vasco", e).temporadas[0]

    assert (primeira.clube, primeira.idade, primeira.jogos) == ("Vasco", 16, 0)


def test_geral_comeca_no_clube_escolhido_e_recusa_clube_de_fora() -> None:
    dados = carregar()

    assert simular(dados, "geral", entrada()).temporadas[0].clube == "Bahia"
    for clube in ("real-madrid", "nao-existe", None):
        with pytest.raises(JogadaInvalida):
            simular(dados, "geral", entrada(clube=clube))


def test_escolha_fora_do_alcance_ou_sobrando_e_invalida() -> None:
    dados = carregar()
    _, completa = ate_o_fim(entrada("s9"))

    with pytest.raises(JogadaInvalida):
        simular(dados, "geral", completa.model_copy(update={"escolhas": [*completa.escolhas, 0]}))
    if completa.escolhas:
        with pytest.raises(JogadaInvalida):
            simular(dados, "geral", completa.model_copy(update={"escolhas": [99]}))


def _dados_fracos(tmp_path: Path):
    notas = ", ".join(f"{a} = 1" for a in regras.ATRIBUTOS)
    (tmp_path / "lendas.toml").write_text(
        "".join(
            f'[[lenda]]\nnome = "Perna {i}"\nwikidata = "Q{i}"\nedicoes = ["geral"]\n'
            f"notas = {{{notas}}}\n"
            for i in range(9)
        ),
        encoding="utf-8",
    )
    for nome in ("mundo.toml", "eventos.toml", "escolhas.toml", "finais.toml", "marcas.toml"):
        if (PASTA / nome).exists():
            (tmp_path / nome).write_text((PASTA / nome).read_text(encoding="utf-8"))
    return carregar(tmp_path)


@pytest.mark.parametrize("fraco", [False, True])
def test_toda_carreira_termina_entre_30_e_42(tmp_path, fraco) -> None:
    dados = _dados_fracos(tmp_path) if fraco else carregar()
    for i in range(250):
        carreira, _ = ate_o_fim(
            entrada(f"t{i}", posicao=regras.POSICOES[i % 5], dados=dados), dados
        )

        ultima = carreira.temporadas[-1]
        assert 30 <= ultima.idade <= 42
        assert any(t.idade >= 17 for t in carreira.temporadas)
