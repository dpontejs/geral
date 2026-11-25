"""The Mano a Mano room: phases, privacy, deadlines, the bot, abandon and rematch.

The clock is injected: `Jogo.andar` moves it and runs the room's `avancar`, as the hub's loop.
"""

import json
import random
from datetime import UTC, datetime, timedelta

import pytest

from geral.games.mano import bot as bot_mod
from geral.games.mano.sala import (
    CORRIDA,
    FOLGA,
    JANELA,
    PRAZO_ESCOLHA,
    RESULTADO,
    ErroSala,
    Evento,
    Sala,
)

T0 = datetime(2026, 11, 25, 20, 0, tzinfo=UTC)
SALA = "abc234"
GOL_ESQUERDA = {"alvo": [150, 300], "barra": 500}  # left third, low: only "esquerda" saves it
SAIDA = {"alvo": [380, 300], "barra": 500}  # middle third near the left: "esquerda" + exit


def _s(td: timedelta) -> float:
    return td.total_seconds()


class Jogo:
    def __init__(self, modo: str = "penaltis", bot: str | None = None, seed: int = 1) -> None:
        self.t = 0.0
        self.sala = Sala(SALA, modo, bot, self.agora, random.Random(seed))
        self.eventos: list[Evento] = []
        jogador, self.token0, eventos = self.sala.entrar("Ana", self.agora)
        assert jogador == 0
        self.eventos += eventos + self.sala.conectou(0, self.agora)
        if bot is None:
            jogador, self.token1, eventos = self.sala.entrar("Bia", self.agora)
            assert jogador == 1
            self.eventos += eventos + self.sala.conectou(1, self.agora)

    @property
    def agora(self) -> datetime:
        return T0 + timedelta(seconds=self.t)

    def andar(self, segundos: float) -> list[Evento]:
        self.t += segundos
        eventos = self.sala.avancar(self.agora)
        self.eventos += eventos
        return eventos

    def agir(self, jogador: int, tipo: str, **campos) -> list[Evento]:
        eventos = self.sala.agir(jogador, {"tipo": tipo, **campos}, self.agora)
        self.eventos += eventos
        return eventos

    def foto(self, jogador: int) -> dict:
        return self.sala.foto(jogador, self.agora)

    def batedor(self) -> int:
        return 0 if self.foto(0)["papel"] == "batedor" else 1

    def cobrar(self, chute: dict, lado: str, saida: float | None = None) -> dict:
        """One kick by whoever kicks now; returns the `cobranca` event's data."""
        batedor = self.batedor()
        goleiro = 1 - batedor
        self.agir(batedor, "chute", **chute)
        self.agir(goleiro, "defesa", lado=lado)
        self.andar(_s(CORRIDA))
        if saida is not None:
            self.andar(saida)
            self.agir(goleiro, "saida")
        self.andar(_s(JANELA + FOLGA) - (saida or 0))
        cobrancas = [e for e in self.eventos if e.tipo == "cobranca"]
        return cobrancas[-1].dados

    def depois(self) -> list[Evento]:
        return self.andar(_s(RESULTADO))

    def jogar_3_a_0(self) -> None:
        """Ana scores three, Bia misses three: Bia can no longer catch up."""
        for _ in range(3):
            assert self.cobrar(GOL_ESQUERDA, "direita")["lance"]["resultado"] == "gol"
            self.depois()
            assert self.cobrar(GOL_ESQUERDA, "esquerda")["lance"]["resultado"] == "defesa"
            self.depois()


def _fins(eventos: list[Evento]) -> list[dict]:
    return [e.dados["sumula"] for e in eventos if e.tipo == "fim"]


def test_criar_e_entrar_comeca_a_disputa():
    jogo = Jogo()
    assert jogo.foto(0)["fase"] == "escolha"
    assert jogo.foto(0)["papel"] == "batedor"
    assert jogo.foto(1)["papel"] == "goleiro"
    assert [j["apelido"] for j in jogo.foto(1)["jogadores"]] == ["Ana", "Bia"]


def test_sozinho_espera():
    sala = Sala(SALA, "penaltis", None, T0, random.Random(1))
    sala.entrar("Ana", T0)
    assert sala.foto(0, T0)["fase"] == "espera"


def test_sala_cheia_409():
    jogo = Jogo()
    with pytest.raises(ErroSala) as erro:
        jogo.sala.entrar("Caio", jogo.agora)
    assert erro.value.status == 409


def test_contra_o_bot_nao_entra_ninguem():
    jogo = Jogo(bot="facil")
    with pytest.raises(ErroSala) as erro:
        jogo.sala.entrar("Caio", jogo.agora)
    assert erro.value.status == 409


@pytest.mark.parametrize("apelido", ["A", "x" * 17, "  "])
def test_apelido_invalido_422(apelido):
    sala = Sala(SALA, "penaltis", None, T0, random.Random(1))
    with pytest.raises(ErroSala) as erro:
        sala.entrar(apelido, T0)
    assert erro.value.status == 422


def test_apelido_repetido_422():
    sala = Sala(SALA, "penaltis", None, T0, random.Random(1))
    sala.entrar("Ana", T0)
    with pytest.raises(ErroSala) as erro:
        sala.entrar("ana", T0)
    assert erro.value.status == 422


def test_token_identifica_o_jogador():
    jogo = Jogo()
    assert jogo.sala.jogador(jogo.token0) == 0
    assert jogo.sala.jogador(jogo.token1) == 1
    with pytest.raises(ErroSala) as erro:
        jogo.sala.jogador("outro")
    assert erro.value.status == 403


def test_escolha_nunca_vaza():
    jogo = Jogo()
    jogo.eventos.clear()
    jogo.agir(0, "chute", alvo=[123, 456], barra=789)
    para_goleiro = [e for e in jogo.eventos if e.para in (None, 1)]
    assert para_goleiro, "the keeper must learn the kicker locked"
    texto = json.dumps([e.dados for e in para_goleiro])
    assert "123" not in texto and "789" not in texto and "alvo" not in texto
    foto = jogo.foto(1)
    assert foto["travou"] == {"voce": False, "outro": True}
    assert "alvo" not in json.dumps(foto) and "789" not in json.dumps(foto)
    jogo.agir(1, "defesa", lado="fica")
    jogo.andar(_s(CORRIDA))
    texto = json.dumps([e.dados for e in jogo.eventos if e.para in (None, 1)])
    assert "789" not in texto  # still nothing before `cobranca`
    jogo.andar(_s(JANELA + FOLGA))
    cobranca = [e for e in jogo.eventos if e.tipo == "cobranca"]
    assert cobranca[0].para is None
    assert cobranca[0].dados["lance"]["chute"]["alvo"] == [123, 456]


def test_reconectar_depois_de_travar_mostra_so_a_propria_escolha():
    jogo = Jogo()
    jogo.agir(0, "chute", alvo=[123, 456], barra=789)
    jogo.agir(1, "defesa", lado="direita")
    batedor, goleiro = jogo.foto(0), jogo.foto(1)
    assert batedor["travou"] == {"voce": True, "outro": True}
    assert batedor["escolha"]["alvo"] == [123, 456]
    assert "direita" not in json.dumps(batedor)
    assert goleiro["escolha"] == {"lado": "direita"}
    assert "789" not in json.dumps(goleiro)


def test_cobranca_inicio_marca_o_chute():
    jogo = Jogo()
    jogo.agir(0, "chute", **GOL_ESQUERDA)
    eventos = jogo.agir(1, "defesa", lado="direita")
    inicio = [e for e in eventos if e.tipo == "cobranca_inicio"]
    assert len(inicio) == 1 and inicio[0].para is None
    assert inicio[0].dados["chute_em"] == (jogo.agora + CORRIDA).isoformat()
    assert jogo.foto(0)["fase"] == "corrida"


def test_saida_dentro_da_janela_conta():
    jogo = Jogo()
    cobranca = jogo.cobrar(SAIDA, "esquerda", saida=0.1)
    assert cobranca["lance"]["defesa"]["saida"] is True
    assert cobranca["lance"]["resultado"] == "defesa"


def test_saida_no_fim_da_folga_ainda_conta():
    jogo = Jogo()
    jogo.agir(0, "chute", **SAIDA)
    jogo.agir(1, "defesa", lado="esquerda")
    jogo.andar(_s(CORRIDA))
    jogo.t += _s(JANELA + FOLGA)  # arrives right at the edge, before the loop resolves
    jogo.agir(1, "saida")
    jogo.andar(0)
    cobranca = [e for e in jogo.eventos if e.tipo == "cobranca"][0].dados
    assert cobranca["lance"]["defesa"]["saida"] is True


def test_saida_fora_da_janela_nao_conta():
    jogo = Jogo()
    jogo.agir(0, "chute", **SAIDA)
    jogo.agir(1, "defesa", lado="esquerda")
    jogo.andar(_s(CORRIDA))
    jogo.t += _s(JANELA + FOLGA) + 0.01  # too late, the loop has not resolved yet
    assert jogo.agir(1, "saida") == []
    jogo.andar(0)
    cobranca = [e for e in jogo.eventos if e.tipo == "cobranca"][0].dados
    assert cobranca["lance"]["defesa"]["saida"] is False
    assert cobranca["lance"]["resultado"] == "gol"


def test_saida_antes_do_chute_nao_conta_e_gasta_a_vez():
    jogo = Jogo()
    jogo.agir(0, "chute", **SAIDA)
    jogo.agir(1, "defesa", lado="esquerda")
    jogo.andar(_s(CORRIDA) - 0.5)
    assert jogo.agir(1, "saida") == []  # too early: the first press decides
    jogo.andar(0.6)  # now inside the window
    assert jogo.agir(1, "saida") == []
    jogo.andar(_s(JANELA + FOLGA))
    cobranca = [e for e in jogo.eventos if e.tipo == "cobranca"][0].dados
    assert cobranca["lance"]["defesa"]["saida"] is False


def test_saida_repetida_vale_a_primeira():
    jogo = Jogo()
    jogo.agir(0, "chute", **SAIDA)
    jogo.agir(1, "defesa", lado="esquerda")
    jogo.andar(_s(CORRIDA) + 0.1)
    jogo.agir(1, "saida")
    jogo.t += _s(JANELA + FOLGA)  # a second press, late: changes nothing
    assert jogo.agir(1, "saida") == []
    jogo.andar(0)
    cobranca = [e for e in jogo.eventos if e.tipo == "cobranca"][0].dados
    assert cobranca["lance"]["defesa"]["saida"] is True


def test_saida_do_batedor_409():
    jogo = Jogo()
    jogo.agir(0, "chute", **SAIDA)
    jogo.agir(1, "defesa", lado="esquerda")
    jogo.andar(_s(CORRIDA) + 0.1)
    with pytest.raises(ErroSala) as erro:
        jogo.agir(0, "saida")
    assert erro.value.status == 409


def test_prazo_estourado_escolhe_ao_acaso():
    jogo = Jogo()
    jogo.andar(_s(PRAZO_ESCOLHA))
    assert jogo.foto(0)["fase"] == "corrida"
    jogo.andar(_s(CORRIDA + JANELA + FOLGA))
    cobranca = [e for e in jogo.eventos if e.tipo == "cobranca"][0].dados
    chute = cobranca["lance"]["chute"]
    assert all(0 <= c <= 1000 for c in [*chute["alvo"], chute["barra"]])
    assert cobranca["lance"]["defesa"]["lado"] in ("esquerda", "fica", "direita")
    assert cobranca["placar"] == list(jogo.foto(0)["placar"])


def test_prazo_estourado_so_preenche_quem_nao_travou():
    jogo = Jogo()
    jogo.agir(0, "chute", alvo=[123, 456], barra=500)
    jogo.andar(_s(PRAZO_ESCOLHA))
    jogo.andar(_s(CORRIDA + JANELA + FOLGA))
    cobranca = [e for e in jogo.eventos if e.tipo == "cobranca"][0].dados
    assert cobranca["lance"]["chute"]["alvo"] == [123, 456]


def test_papel_errado_409():
    jogo = Jogo()
    for jogador, tipo, campos in [
        (1, "chute", GOL_ESQUERDA),
        (0, "defesa", {"lado": "fica"}),
    ]:
        with pytest.raises(ErroSala) as erro:
            jogo.agir(jogador, tipo, **campos)
        assert erro.value.status == 409


def test_acao_fora_da_fase_409():
    jogo = Jogo()
    casos = [
        (1, "barreira", {"n": 3, "x": 500}),  # a penalty has no wall
        (0, "revanche", {}),  # the match is not over
    ]
    for jogador, tipo, campos in casos:
        with pytest.raises(ErroSala) as erro:
            jogo.agir(jogador, tipo, **campos)
        assert erro.value.status == 409
    jogo.andar(0.5)
    jogo.agir(0, "chute", **GOL_ESQUERDA)
    jogo.andar(0.5)
    with pytest.raises(ErroSala) as erro:  # already locked
        jogo.agir(0, "chute", **GOL_ESQUERDA)
    assert erro.value.status == 409
    jogo.agir(1, "defesa", lado="fica")
    jogo.andar(0.5)
    with pytest.raises(ErroSala) as erro:  # the run-up started
        jogo.agir(1, "defesa", lado="direita")
    assert erro.value.status == 409


def test_acao_desconhecida_422():
    jogo = Jogo()
    with pytest.raises(ErroSala) as erro:
        jogo.agir(0, "danca")
    assert erro.value.status == 422


def test_chute_invalido_422():
    jogo = Jogo()
    with pytest.raises(ErroSala) as erro:
        jogo.agir(0, "chute", alvo=[1200, 0], barra=500)
    assert erro.value.status == 422


def test_limite_de_acoes_429():
    jogo = Jogo()
    jogo.agir(0, "chute", **GOL_ESQUERDA)
    with pytest.raises(ErroSala) as erro:
        jogo.agir(0, "chute", **GOL_ESQUERDA)
    assert erro.value.status == 429
    jogo.agir(1, "defesa", lado="fica")  # the other player has their own limit


def test_penalti_descarta_trajetoria():
    jogo = Jogo()
    jogo.agir(0, "chute", alvo=[150, 300], barra=500, trajetoria="por_cima", curva=0.7)
    jogo.agir(1, "defesa", lado="direita")
    jogo.andar(_s(CORRIDA + JANELA + FOLGA))
    chute = [e for e in jogo.eventos if e.tipo == "cobranca"][0].dados["lance"]["chute"]
    assert chute["trajetoria"] is None and chute["curva"] == 0


def test_falta_tem_posicao_e_barreira_antes_da_escolha():
    jogo = Jogo(modo="faltas")
    batedor, goleiro = jogo.foto(0), jogo.foto(1)
    assert batedor["fase"] == goleiro["fase"] == "barreira"
    assert batedor["posicao"] == goleiro["posicao"]
    assert batedor["posicao"]["nome"] in ("meia_lua", "entrada_esquerda", "entrada_direita")
    assert -80 <= batedor["posicao"]["desvio"] <= 80
    with pytest.raises(ErroSala) as erro:  # the kicker waits for the wall
        jogo.agir(0, "chute", trajetoria="rasteira", **GOL_ESQUERDA)
    assert erro.value.status == 409
    jogo.agir(1, "barreira", n=4, x=600)
    assert jogo.foto(0)["fase"] == "escolha"
    assert jogo.foto(0)["barreira"] == {"n": 4, "x": 600}
    jogo.andar(0.5)
    with pytest.raises(ErroSala) as erro:  # a free kick needs its trajectory
        jogo.agir(0, "chute", **GOL_ESQUERDA)
    assert erro.value.status == 422
    jogo.andar(0.5)
    jogo.agir(0, "chute", trajetoria="rasteira", curva=0.2, **GOL_ESQUERDA)
    jogo.agir(1, "defesa", lado="direita")
    jogo.andar(_s(CORRIDA + JANELA + FOLGA))
    lance = [e for e in jogo.eventos if e.tipo == "cobranca"][0].dados["lance"]
    assert lance["barreira"] == {"n": 4, "x": 600}
    assert lance["posicao"] == batedor["posicao"]
    assert lance["chute"]["trajetoria"] == "rasteira"


def test_barreira_invalida_422():
    jogo = Jogo(modo="faltas")
    with pytest.raises(ErroSala) as erro:
        jogo.agir(1, "barreira", n=7, x=600)
    assert erro.value.status == 422


def test_barreira_no_prazo_estourado_e_ao_acaso():
    jogo = Jogo(modo="faltas")
    jogo.andar(_s(PRAZO_ESCOLHA))
    barreira = jogo.foto(0)["barreira"]
    assert jogo.foto(0)["fase"] == "escolha"
    assert 2 <= barreira["n"] <= 5 and 0 <= barreira["x"] <= 1000
    jogo.andar(_s(PRAZO_ESCOLHA))
    jogo.andar(_s(CORRIDA + JANELA + FOLGA))
    lance = [e for e in jogo.eventos if e.tipo == "cobranca"][0].dados["lance"]
    assert lance["chute"]["trajetoria"] in ("rasteira", "por_cima", "pelo_lado")


def test_papeis_alternam_e_o_placar_anda():
    jogo = Jogo()
    cobranca = jogo.cobrar(GOL_ESQUERDA, "direita")
    assert cobranca["placar"] == [1, 0]
    assert jogo.foto(0)["fase"] == "resultado"
    jogo.depois()
    assert jogo.foto(0)["papel"] == "goleiro" and jogo.foto(1)["papel"] == "batedor"
    assert jogo.foto(1)["serie"] == [[True], []]


def test_disputa_acaba_quando_nao_da_mais_para_alcancar():
    jogo = Jogo()
    jogo.jogar_3_a_0()
    assert jogo.foto(0)["fase"] == "fim"
    (sumula,) = _fins(jogo.eventos)
    assert sumula["id"] == f"{SALA}-1"
    assert sumula["placar"] == [3, 0]
    assert sumula["vencedor"] == 0
    assert sumula["wo"] is False
    assert len(sumula["cobrancas"]) == 6
    assert jogo.sala.sumula() == sumula


def test_fim_so_depois_do_replay():
    jogo = Jogo()
    for _ in range(2):
        jogo.cobrar(GOL_ESQUERDA, "direita")
        jogo.depois()
        jogo.cobrar(GOL_ESQUERDA, "esquerda")
        jogo.depois()
    jogo.cobrar(GOL_ESQUERDA, "direita")
    jogo.depois()
    jogo.cobrar(GOL_ESQUERDA, "esquerda")
    assert _fins(jogo.eventos) == [] and jogo.foto(0)["fase"] == "resultado"
    jogo.depois()
    assert len(_fins(jogo.eventos)) == 1


def test_quem_sai_perde_por_wo():
    jogo = Jogo()
    jogo.cobrar(GOL_ESQUERDA, "direita")
    jogo.depois()
    eventos = jogo.agir(0, "sair")
    (sumula,) = _fins(eventos)
    assert sumula["wo"] is True
    assert sumula["vencedor"] == 1
    assert sumula["placar"] == [1, 0]
    assert not jogo.sala.esta(0)
    assert jogo.foto(1)["fase"] == "fim"


def test_ausente_30s_perde_por_wo():
    jogo = Jogo()
    jogo.sala.desconectou(1, jogo.agora)
    jogo.andar(5)
    jogo.sala.conectou(0, jogo.agora)
    jogo.andar(24.9)
    assert _fins(jogo.eventos) == []
    jogo.andar(0.2)
    (sumula,) = _fins(jogo.eventos)
    assert sumula["wo"] is True and sumula["vencedor"] == 0


def test_voltar_antes_de_30s_nao_perde():
    jogo = Jogo()
    jogo.sala.desconectou(1, jogo.agora)
    jogo.andar(20)
    jogo.sala.conectou(1, jogo.agora)
    jogo.andar(20)
    assert _fins(jogo.eventos) == []


def test_contra_o_bot_ele_escolhe_sozinho():
    jogo = Jogo(bot="dificil", seed=3)
    assert jogo.foto(0)["jogadores"][1]["bot"] is True
    for _ in range(60):
        foto = jogo.foto(0)
        if foto["fase"] == "fim":
            break
        assert foto["fase"] == "escolha"
        if foto["papel"] == "batedor":
            jogo.agir(0, "chute", **GOL_ESQUERDA)
        else:
            jogo.agir(0, "defesa", lado="fica")
        jogo.andar(_s(CORRIDA + JANELA + FOLGA))
        jogo.depois()
    assert jogo.foto(0)["fase"] == "fim"
    (sumula,) = _fins(jogo.eventos)
    assert sumula["jogadores"][1]["bot"] is True


def test_bot_arma_a_barreira_sozinho():
    jogo = Jogo(modo="faltas", bot="medio", seed=3)
    jogo.agir(0, "chute", trajetoria="por_cima", **GOL_ESQUERDA)
    jogo.andar(_s(CORRIDA + JANELA + FOLGA))
    jogo.depois()
    foto = jogo.foto(0)  # the bot kicks now: the human arms the wall
    assert foto["papel"] == "goleiro" and foto["fase"] == "barreira"
    jogo.agir(0, "barreira", n=3, x=500)
    assert jogo.foto(0)["travou"]["outro"] is True


def test_revanche_zera_e_grava_sumula_de_cada_partida():
    jogo = Jogo()
    jogo.jogar_3_a_0()
    assert jogo.agir(0, "revanche")[-1].tipo == "estado"
    assert jogo.foto(1)["revanche"] == {"voce": False, "outro": True}
    assert jogo.foto(0)["fase"] == "fim"  # waits for the other one
    jogo.agir(1, "revanche")
    foto = jogo.foto(0)
    assert foto["fase"] == "escolha" and foto["partida"] == 2
    assert foto["placar"] == [0, 0]
    jogo.andar(0.5)
    jogo.jogar_3_a_0()
    assert [s["id"] for s in _fins(jogo.eventos)] == [f"{SALA}-1", f"{SALA}-2"]


def test_revanche_contra_o_bot_e_imediata_com_random_novo(monkeypatch):
    usados = []
    defender = bot_mod.defender

    def espia(nivel, historico, rng):
        usados.append(rng)
        return defender(nivel, historico, rng)

    monkeypatch.setattr(bot_mod, "defender", espia)
    jogo = Jogo(bot="medio")
    for _ in range(60):
        if jogo.foto(0)["fase"] == "fim":
            break
        if jogo.foto(0)["papel"] == "batedor":
            jogo.agir(0, "chute", alvo=[1000, 1000], barra=0)  # always out
        else:
            jogo.agir(0, "defesa", lado="fica")
        jogo.andar(_s(CORRIDA + JANELA + FOLGA))
        jogo.depois()
    jogo.agir(0, "revanche")
    assert jogo.foto(0)["fase"] == "escolha" and jogo.foto(0)["partida"] == 2
    assert usados[-1] is not usados[0]


def test_sair_no_fim_encerra_a_sala():
    jogo = Jogo()
    jogo.jogar_3_a_0()
    jogo.agir(1, "sair")
    assert jogo.sala.encerrada


def test_fim_sem_revanche_fecha_em_10_minutos():
    jogo = Jogo()
    jogo.jogar_3_a_0()
    jogo.andar(9 * 60)
    assert not jogo.sala.encerrada
    jogo.andar(61)
    assert jogo.sala.encerrada


def test_encerrar_no_meio_grava_sumula():
    jogo = Jogo()
    jogo.cobrar(GOL_ESQUERDA, "direita")
    (sumula,) = _fins(jogo.sala.encerrar(jogo.agora))
    assert sumula["placar"] == [1, 0] and sumula["vencedor"] is None
    assert jogo.sala.encerrada
    assert jogo.sala.encerrar(jogo.agora) == []


def test_encerrar_na_espera_nao_grava():
    sala = Sala(SALA, "penaltis", None, T0, random.Random(1))
    sala.entrar("Ana", T0)
    assert _fins(sala.encerrar(T0)) == []
    assert sala.encerrada


def test_saida_depois_de_resolvida_e_sem_efeito():
    jogo = Jogo()
    jogo.cobrar(SAIDA, "esquerda")
    assert jogo.foto(1)["fase"] == "resultado"
    assert jogo.agir(1, "saida") == []  # the late press of a slow network: 204, no effect


def test_os_dois_ausentes_perde_quem_saiu_primeiro():
    jogo = Jogo()
    jogo.sala.desconectou(1, jogo.agora)
    jogo.andar(5)
    jogo.sala.desconectou(0, jogo.agora)
    jogo.andar(40)
    (sumula,) = _fins(jogo.eventos)
    assert sumula["wo"] is True and sumula["vencedor"] == 0


def test_revanche_sem_o_outro_409():
    jogo = Jogo()
    jogo.agir(0, "sair")
    with pytest.raises(ErroSala) as erro:
        jogo.agir(1, "revanche")
    assert erro.value.status == 409


def test_bot_le_as_cobrancas_do_humano_no_papel_que_enfrenta(monkeypatch):
    lidos = {"defender": [], "chutar": []}
    defender, chutar = bot_mod.defender, bot_mod.chutar

    def espia_defender(nivel, historico, rng):
        lidos["defender"].append([lance.chute.alvo for lance in historico])
        return defender(nivel, historico, rng)

    def espia_chutar(nivel, historico, rng, **kw):
        lidos["chutar"].append([lance.defesa.lado for lance in historico])
        return chutar(nivel, historico, rng, **kw)

    monkeypatch.setattr(bot_mod, "defender", espia_defender)
    monkeypatch.setattr(bot_mod, "chutar", espia_chutar)
    jogo = Jogo(bot="dificil")
    jogo.agir(0, "chute", alvo=[1000, 1000], barra=0)  # the human kicks (out)
    jogo.andar(_s(CORRIDA + JANELA + FOLGA))
    jogo.depois()
    jogo.agir(0, "defesa", lado="direita")  # the human dives right
    jogo.andar(_s(CORRIDA + JANELA + FOLGA))
    jogo.depois()  # the human kicks again: the bot reads the first kick only
    assert lidos["defender"] == [[], [(1000, 1000)]]
    jogo.agir(0, "chute", alvo=[1000, 1000], barra=0)
    jogo.andar(_s(CORRIDA + JANELA + FOLGA))
    jogo.depois()  # the bot kicks again: it reads the human's dive only
    assert lidos["chutar"] == [[], ["direita"]]


def test_no_replay_cada_um_mantem_o_papel_do_lance():
    jogo = Jogo()
    jogo.cobrar(GOL_ESQUERDA, "direita")
    assert jogo.foto(0)["papel"] == "batedor" and jogo.foto(1)["papel"] == "goleiro"
    jogo.depois()
    assert jogo.foto(0)["papel"] == "goleiro"
