import base64
import zlib

import pytest
from test_carreira_motor import _roubos, ate_o_fim, entrada

from geral.games.carreira.codigo import (
    CodigoInvalido,
    Resumo,
    codificar,
    decodificar,
    resumir,
)
from geral.games.carreira.dados import carregar
from geral.games.carreira.draft import oferta
from geral.games.carreira.motor import simular


def test_career_code_reopens_the_exact_career() -> None:
    dados = carregar()
    carreira, e = ate_o_fim(entrada("k1"))

    codigo = codificar(dados.versao, "geral", e, resumir(e, carreira))
    aberto = decodificar(codigo)

    assert aberto.versao == dados.versao and aberto.edicao == "geral"
    assert simular(dados, "geral", aberto.entrada) == carreira
    assert len(codigo) < 2000 and "=" not in codigo


def test_old_code_after_data_change_shows_the_card_summary() -> None:
    carreira, e = ate_o_fim(entrada("k2"))
    resumo = resumir(e, carreira)

    aberto = decodificar(codificar("00000000", "geral", e, resumo))

    assert aberto.versao != carregar().versao
    assert (
        aberto.resumo
        == resumo
        == Resumo(
            nome="Zé",
            posicao="atacante",
            rotulo=carreira.final.rotulo,
            nota=carreira.final.nota,
            titulos=sum(carreira.final.titulos.values()),
            clubes=carreira.final.clubes,
        )
    )


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@pytest.mark.parametrize(
    "codigo",
    [
        "",
        "%%%não é base64%%%",
        _b64(b"lixo sem zlib"),
        _b64(zlib.compress(b'{"v": "1", "e": ')),  # JSON truncado
        _b64(zlib.compress(b'{"v": "1"}')),  # campos faltando
        "A" * 2001,
    ],
)
def test_codigo_adulterado_e_codigo_invalido(codigo) -> None:
    with pytest.raises(CodigoInvalido):
        decodificar(codigo)


def test_codigo_aninhado_demais_ou_bomba_e_codigo_invalido() -> None:
    for bruto in (b"[" * 200_000, b'{"v": "' + b"a" * 1_000_000 + b'"}'):
        codigo = _b64(zlib.compress(bruto, 9))
        assert len(codigo) <= 2000
        with pytest.raises(CodigoInvalido):
            decodificar(codigo)


# A link made by the first format (JSON + zlib), before the short one: it has to keep opening.
LINK_ANTIGO = (
    "eNptks9uE0EMxl9lNedFapDaSrltEFChcqGIA6hCzoyTtTozDp6ZHhLlaTj1OfJi2Eskui3ay_jbn__Inw_uEaUAu6Xz"
    "V28Xi-tw6XqHgfykbVEgmpCrQAC3PLiCSSP8GQQ2VZGw0P9nUcMHC73Ar4ZGZ06mfj89mQyJihZZXPRux-XcAyp4sGQV"
    "jQ0kSJWNj21tyhpGAnfsnXBbc3HLHwcXMds8bsgFY-LuCyTOmgNVaN2qFX7EyJ4CBNTcfxlfUabqz8gNZYi0BxvoOToE"
    "TCRdwO4zZtxjmaftoJR57W-QA-XxRfmgrzgHP7FssbtttJ-jCcS_GuPj6UkK5-6Og0yLnI2ue5zj70MDCdzdQRlhTntY"
    "o0ea8zctPsyxSEGNz16Xfq_mF89xBNv7RT99KiYORgrsdMOTN1ha4lee_9dn4dqiaYNUiiOScJdhciVz1Zkur3tXySDt"
    "enW-BBvAraZb6N07SDvKqO5rsJJW7OB6d8tZt52N-ABJTfWn31Z2iG-GMdLf1w3F6apX2mvDW3b3x-MfRP8DXg"
)


def test_link_antigo_continua_abrindo() -> None:
    aberto = decodificar(LINK_ANTIGO)

    assert aberto.versao == "c62117d5" and aberto.edicao == "geral"
    assert aberto.entrada.semente_draft == "d1" and aberto.entrada.semente == "k1"
    assert aberto.entrada.craque.clube == "bahia" and aberto.entrada.escolhas == [0, 0, 0, 0]
    assert [r.lenda for r in aberto.entrada.roubos][:2] == ["Anselmo Ramon", "Terto"]
    assert aberto.resumo == Resumo(
        nome="Zé",
        posicao="atacante",
        rotulo="Artilheiro nato",
        nota=57,
        titulos=6,
        clubes=[
            "Bahia",
            "Campinense",
            "Brusque",
            "Londrina",
            "Famalicão",
            "Al-Ahli",
            "Al-Hilal",
            "Botafogo",
        ],
    )


TOKEN_DRAFT, TOKEN_CARREIRA = "q9Zx_4Lm-0A", "Bv3-tRk2_Yw"  # what secrets.token_urlsafe(8) gives


def _carreira(modo: str, nome="Zé", semente_draft=TOKEN_DRAFT, semente=TOKEN_CARREIRA):
    dados = carregar()
    e = entrada(semente).model_copy(
        update={
            "semente_draft": semente_draft,
            "modo": modo,
            "roubos": _roubos(oferta(dados, "geral", semente_draft, "bahia")),
        }
    )
    e = e.model_copy(update={"craque": e.craque.model_copy(update={"nome": nome})})
    return ate_o_fim(e)


@pytest.mark.parametrize("modo", ["rapida", "completa"])
@pytest.mark.parametrize(
    "sementes", [(TOKEN_DRAFT, TOKEN_CARREIRA), ("d1", "uma semente qualquer")]
)
def test_codigo_curto_reabre_a_carreira_nos_dois_modos(modo, sementes) -> None:
    dados = carregar()
    carreira, e = _carreira(modo, semente_draft=sementes[0], semente=sementes[1])
    resumo = resumir(e, carreira)

    aberto = decodificar(codificar(dados.versao, "geral", e, resumo))

    assert (aberto.versao, aberto.edicao, aberto.entrada, aberto.resumo) == (
        dados.versao,
        "geral",
        e,
        resumo,
    )
    assert simular(dados, "geral", aberto.entrada) == carreira


def test_carreira_completa_com_nome_de_24_letras_cabe_em_100_caracteres() -> None:
    dados = carregar()
    carreira, e = _carreira("completa", nome="Maximiliano Albuquerqueh")
    assert len(e.craque.nome) == 24 and len(e.escolhas) > 20
    resumo = resumir(e, carreira)
    tipica = resumo.model_copy(update={"clubes": resumo.clubes[:6]})  # ~5 clubs on average

    codigo = codificar(dados.versao, "geral", e, tipica)
    rodada = codificar(dados.versao, "geral", e, resumo)  # every club this one played for

    assert len(codigo) <= 100 and len(rodada) <= 110 and "=" not in codigo
    assert set(codigo) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_resumo_com_nomes_que_os_dados_nao_conhecem_vai_por_extenso() -> None:
    carreira, e = _carreira("rapida", nome="Zé Ñandú")
    resumo = resumir(e, carreira).model_copy(
        update={"rotulo": "Um rótulo que saiu", "clubes": ["Bahia", "Clube Que Fechou"], "nota": 0}
    )

    assert decodificar(codificar("00000000", "geral", e, resumo)).resumo == resumo


def test_draft_que_mudou_nao_reconstroi_roubos_errados(monkeypatch) -> None:
    from geral.games.carreira import codigo as modulo

    carreira, e = _carreira("rapida")
    codigo = codificar(carregar().versao, "geral", e, resumir(e, carreira))
    oferta_de_hoje = modulo.oferta
    monkeypatch.setattr(modulo, "oferta", lambda *a: list(reversed(oferta_de_hoje(*a))))

    aberto = decodificar(codigo)

    assert aberto.entrada.roubos == [] and aberto.resumo == resumir(e, carreira)


def test_codigo_curto_corrompido_e_codigo_invalido() -> None:
    carreira, e = _carreira("completa")
    codigo = codificar(carregar().versao, "geral", e, resumir(e, carreira))
    bruto = base64.urlsafe_b64decode(codigo + "=" * (-len(codigo) % 4))

    for n in range(1, len(bruto)):
        with pytest.raises(CodigoInvalido):
            decodificar(_b64(bruto[:n]))
    # 0x03: no such format (0x01 and 0x02 are short codes)
    for ruim in (bruto + b"\0", b"\x03" + bruto[1:], b"\x01", b"\x01" + b"\xff" * 80):
        with pytest.raises(CodigoInvalido):
            decodificar(_b64(ruim))


def test_link_guarda_a_posicao_final_do_card() -> None:
    carreira, e = _carreira("completa")
    resumo = resumir(e, carreira).model_copy(update={"posicao": "meia"})
    assert e.craque.posicao != "meia"
    aberto = decodificar(codificar(carregar().versao, "geral", e, resumo))
    assert aberto.resumo.posicao == "meia" and aberto.entrada.craque.posicao == e.craque.posicao
