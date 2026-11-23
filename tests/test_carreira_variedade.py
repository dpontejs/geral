import random
from collections import Counter

from test_carreira_motor import ate_o_fim, entrada
from velha_fakes import base, player

from geral.games.carreira import regras
from geral.games.carreira.dados import carregar
from geral.games.carreira.final import parecido, rotular
from geral.games.carreira.motor import Temporada, artigos, jogar, simular


def test_careers_vary() -> None:
    carreiras = [ate_o_fim(entrada(f"v{i}"))[0] for i in range(500)]

    rotulos = Counter(c.final.rotulo for c in carreiras)
    clubes = {t.clube for c in carreiras for t in c.temporadas}
    historias = Counter(tuple(t.manchete for t in c.temporadas) for c in carreiras)

    assert len(rotulos) >= 8, rotulos
    assert len(clubes) >= 40
    assert historias.most_common(1)[0][1] <= 10  # no story in more than 2% of careers


def _ao_acaso(semente: str, posicao: str):
    """A career with the answers drawn from the seed, a draft drawn from it too."""
    dados = carregar()
    rng = random.Random(semente)
    melhor = rng.choice((True, False, None))
    e = entrada(semente, posicao=posicao, melhor=melhor, clube=rng.choice(BR))
    return jogar(dados, "geral", e, lambda pendente: rng.randrange(len(pendente.opcoes)))


BR = sorted(c.id for c in carregar().clubes.values() if carregar().ligas[c.liga].pais == "Brasil")


def test_every_event_and_choice_in_toml_is_reachable_and_headlines_are_whole() -> None:
    dados = carregar()
    vistos: set[str] = set()
    for i in range(2000):
        carreira, _ = _ao_acaso(f"r{i}", regras.POSICOES[i % 5])
        vistos |= {ev for t in carreira.temporadas for ev in t.eventos}
        vistos |= set(carreira.final.perguntas) | {f"final:{carreira.final.rotulo}"}
        assert all("{" not in t.manchete and "}" not in t.manchete for t in carreira.temporadas)
        assert all(t.manchete for t in carreira.temporadas)

    todos = {e.id for e in dados.eventos} | {d.id for d in dados.decisoes}
    todos |= {f"final:{r['rotulo']}" for r in dados.finais}
    assert todos - vistos == set()


def _temporada(idade: int, clube: str, clube_id: str, **extra) -> Temporada:
    campos = {
        "ano": 2027 + idade - 16,
        "idade": idade,
        "clube": clube,
        "clube_id": clube_id,
        "pais": "Brasil",
        "liga_forca": 72,
        "jogos": 40,
        "gols": 10,
        "assistencias": 5,
        "nota": 75,
        "titulos": [],
        "selecao": 0,
        "copa": False,
        "manchete": "x",
        "eventos": [],
    }
    return Temporada(**(campos | extra))


def test_rotulo_bandeira_para_quem_ficou_no_mesmo_clube() -> None:
    temporadas = [_temporada(i, "Vasco", "vasco") for i in range(16, 35)]

    rotulo, _ = rotular(carregar(), temporadas)

    assert rotulo == "Bandeira"


def test_rotulo_cigano_para_quem_rodou() -> None:
    clubes = ["bahia", "sport", "ceara", "goias", "remo", "vitoria", "guarani", "abc", "csa"]
    temporadas = [_temporada(16 + i * 2, c.title(), c, nota=60) for i, c in enumerate(clubes)]

    rotulo, _ = rotular(carregar(), temporadas)

    assert rotulo == "Cigano da bola"


def test_parecido_prefere_quem_passou_pelos_mesmos_clubes() -> None:
    vasco, gremio = "Q5014111", "Q221695"
    b = base(
        player("Q1", "Do Vasco", clubes=(vasco, gremio), posicoes=("atacante",), fama=40),
        player("Q2", "Do Flamengo", clubes=("Q17479",), posicoes=("atacante",), fama=75),
        player("Q3", "Zagueiro do Vasco", clubes=(vasco, gremio), posicoes=("zagueiro",)),
    )
    temporadas = [
        _temporada(20, "Vasco", "vasco"),
        _temporada(24, "Grêmio", "gremio"),
    ]

    assert parecido(carregar(), b, temporadas, "atacante") == "Do Vasco"


def test_manchetes_concordam_com_clube_e_campeonato_femininos() -> None:
    dados = carregar()
    femininos = [c.nome for c in dados.clubes.values() if c.genero == "f"]
    assert {"Ponte Preta", "Lazio", "Juventus"} <= set(femininos)
    erradas = [
        f"{artigo} {nome}" for nome in femininos for artigo in ("do", "no", "pelo", "o", "O")
    ] + ["o Bundesliga", "do Bundesliga", "do Premier League", "do La Liga", "do MLS"]
    for i in range(400):
        carreira, _ = _ao_acaso(f"g{i}", regras.POSICOES[i % 5])
        for t in carreira.temporadas:
            assert not any(e in t.manchete for e in erradas), t.manchete


def test_mudanca_escolhida_vale_na_temporada_seguinte() -> None:
    dados = carregar()
    vistas = 0
    for i in range(300):
        rng = random.Random(f"m{i}")
        e = entrada(f"m{i}", posicao=regras.POSICOES[i % 5], melhor=rng.choice((True, None)))
        while (carreira := simular(dados, "geral", e)).final is None:
            pergunta = carreira.pendente
            resposta = rng.randrange(len(pergunta.opcoes))
            e = e.model_copy(update={"escolhas": [*e.escolhas, resposta]})
            alvo, tipo = pergunta.clubes[resposta], pergunta.destinos[resposta]
            if alvo is None:
                continue
            depois = simular(dados, "geral", e).temporadas[len(carreira.temporadas)]
            assert depois.clube_id == alvo, (pergunta.id, tipo)
            if tipo == "exotico":
                assert depois.pais != carreira.temporadas[-1].pais
            vistas += 1
    assert vistas > 100


def test_todo_evento_frequente_tem_quatro_manchetes() -> None:
    dados = carregar()
    poucas = {e.id: len(e.manchetes) for e in dados.eventos if e.peso >= 1 and len(e.manchetes) < 4}
    assert poucas == {}

    for clube, rival in (("vasco", "flamengo"), ("lazio", "roma")):
        campos = (
            artigos("clube", dados.clubes[clube])
            | {"classico": "Clássico"}
            | artigos("rival", dados.clubes.get(rival))
            | artigos("adversario", dados.clubes["bahia"])  # a penalty's (motor.py, `_lance`)
            | {"minuto": "87'", "competicao": "Brasileirão"}
            | {
                "nome": "Fulano",
                "camisa": 10,
                "liga": "Brasil",
                "campeonato": "Brasileirão",
                "gols": 12,
                "jogos": 38,
                "idade": 24,
            }
        )
        for e in dados.eventos:
            assert len(set(e.manchetes)) == len(e.manchetes), e.id
            for m in e.manchetes:
                texto = m.format_map(campos)
                assert "{" not in texto and "}" not in texto, (e.id, m)


def test_mexer_nas_manchetes_nao_muda_a_carreira() -> None:
    """Headlines are drawn apart from the simulation: editing texts never reshuffles careers."""
    from dataclasses import replace

    dados = carregar()
    outra = replace(
        dados,
        eventos=tuple(
            replace(e, manchetes=(*e.manchetes, "{nome} em manchete extra")) for e in dados.eventos
        ),
    )

    def numeros(carreira):
        return [(t.clube_id, t.jogos, t.gols, t.nota, t.titulos) for t in carreira.temporadas]

    for i in range(20):
        e = entrada(f"m{i}")
        antes, respostas = ate_o_fim(e, dados)
        depois = simular(outra, "geral", respostas)
        assert depois.final is not None
        assert numeros(depois) == numeros(antes), i
