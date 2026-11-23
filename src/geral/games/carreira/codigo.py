"""The share link of a finished career: everything needed to replay it, nothing stored.

The code also carries the card's summary, so a link made before the data changed still shows
the card that was shared (the career itself would come out different with the new data).

Two formats open. The first one (JSON + zlib, ~600 characters) is only read now. New links are
a packed bit string (~90 characters) whose first byte is the format (`FORMATOS`); it leans on a
few things staying put, or old links stop opening right:

- the order of `regras.ATRIBUTOS`, `regras.POSICOES`, `PES` and `MODOS`;
- the data's version goes as its first 16 bits: a link replays when they match today's;
- clubs go as a hash of their id and the card's label as a hash of its text, resolved against
  today's data. A club that later leaves the data drops from the card, a label that does
  becomes `ROTULO_PERDIDO`. Whatever the data does not know, or knows under a shared hash,
  goes in full;
- the stolen attributes go as positions in the draft's offer, plus a checksum of the offer: if
  the draft changes, the roubos come back empty (the career no longer replays, the card shows).
"""

import base64
import binascii
import hashlib
import json
import math
import re
import zlib

from pydantic import BaseModel, ValidationError

from geral.games.carreira.dados import Dados, carregar
from geral.games.carreira.draft import OFERTA, Roubo, oferta
from geral.games.carreira.motor import Carreira, Craque, Entrada
from geral.games.carreira.regras import ATRIBUTOS, POSICOES

LIMITE = 2000  # characters
MAX_JSON = 8192  # bytes once decompressed: a real career is ~1.5 KB
FORMATO = 4  # first byte of a short code; an old one starts with zlib's 0x78
# 2 adds the card's final position (a career can change it), 3 the minijogos switch, 4 counts the
# answers in 7 bits (up to 4 penalties take a career past 63); older still open
FORMATOS = (1, 2, 3, 4)
RESPOSTAS = {1: 6, 2: 6, 3: 6, 4: 7}  # bits of the answer count, by format
PES = ("direito", "esquerdo", "ambos")
MODOS = ("rapida", "completa")
TOKEN = 8  # bytes behind a secrets.token_urlsafe(8) seed
VERSAO, CLUBE, ROTULO, CONFERE = 16, 12, 10, 12  # bits of each hash
ROTULO_PERDIDO = "Carreira encerrada"
ROUBOS = math.perm(OFERTA, len(ATRIBUTOS))  # ways to steal: positions in the offer, in order
ASCII, LATIN1, UTF8 = 0, 1, 2  # how a text goes


class CodigoInvalido(ValueError):
    pass


class Resumo(BaseModel):
    nome: str
    posicao: str
    rotulo: str
    nota: int
    titulos: int
    clubes: list[str]


class Compartilhado(BaseModel):
    versao: str
    edicao: str
    entrada: Entrada
    resumo: Resumo


def resumir(entrada: Entrada, carreira: Carreira) -> Resumo:
    final = carreira.final
    if final is None:
        raise ValueError("only a finished career has a card")
    return Resumo(
        nome=entrada.craque.nome,
        posicao=final.posicao or entrada.craque.posicao,  # where he ended up ("virou meia")
        rotulo=final.rotulo,
        nota=final.nota,
        titulos=sum(final.titulos.values()),
        clubes=final.clubes,
    )


def codificar(
    versao: str, edicao: str, entrada: Entrada, resumo: Resumo, dados: Dados | None = None
) -> str:
    dados = dados or carregar()
    craque = entrada.craque
    if resumo.nome != craque.nome:  # the position may have changed along the career
        raise ValueError("the card is of another player")
    v = _Vocabulario(dados)
    b = _Escrita()
    b.put(FORMATO, 8)
    _versao_put(b, versao)
    b.put(edicao == "geral", 1)
    if edicao != "geral":
        b.texto(edicao)
    b.put(MODOS.index(entrada.modo), 1)
    b.put(entrada.minijogos, 1)
    b.put(POSICOES.index(craque.posicao), 3)
    b.put(PES.index(craque.pe), 2)
    b.put(craque.camisa, 7)
    b.texto(craque.nome)
    b.put(craque.clube is not None, 1)
    if craque.clube is not None:
        v.clube_put(b, craque.clube)
    _semente_put(b, entrada.semente_draft)
    _semente_put(b, entrada.semente)
    _roubos_put(b, entrada.roubos, oferta(dados, edicao, entrada.semente_draft, craque.clube))
    _escolhas_put(b, entrada.escolhas, RESPOSTAS[FORMATO])
    b.put(min(resumo.nota, 127), 7)
    b.put(min(resumo.titulos, 255), 8)
    v.rotulo_put(b, resumo.rotulo)
    _clubes_put(b, v, resumo.clubes, craque.clube)
    mudou = resumo.posicao != craque.posicao
    b.put(mudou, 1)
    if mudou:
        b.put(POSICOES.index(resumo.posicao), 3)
    return base64.urlsafe_b64encode(b.bytes()).decode().rstrip("=")


def decodificar(codigo: str, dados: Dados | None = None) -> Compartilhado:
    if not codigo or len(codigo) > LIMITE:
        raise CodigoInvalido("código vazio ou grande demais")
    try:
        bruto = base64.urlsafe_b64decode(codigo + "=" * (-len(codigo) % 4))
        if bruto[:1] and bruto[0] in FORMATOS:
            return _curto(bruto, dados or carregar())
        return _antigo(bruto)
    except (
        binascii.Error,
        ValueError,
        IndexError,
        zlib.error,
        ValidationError,
        RecursionError,
    ) as erro:
        raise CodigoInvalido("código de carreira inválido") from erro


def _antigo(bruto: bytes) -> Compartilhado:
    descompressor = zlib.decompressobj()
    texto = descompressor.decompress(bruto, MAX_JSON)
    if descompressor.unconsumed_tail:
        raise CodigoInvalido("código grande demais")
    return Compartilhado.model_validate(json.loads(texto))


def _curto(bruto: bytes, dados: Dados) -> Compartilhado:
    v = _Vocabulario(dados)
    b = _Leitura(bruto)
    formato = b.get(8)
    versao = _versao_get(b, dados.versao)
    edicao = "geral" if b.get(1) else b.texto()
    modo = MODOS[b.get(1)]
    minijogos = formato >= 3 and bool(b.get(1))
    posicao, pe = POSICOES[b.get(3)], PES[b.get(2)]
    camisa, nome = b.get(7), b.texto()
    clube = v.clube_get(b) if b.get(1) else None
    semente_draft, semente = _semente_get(b), _semente_get(b)
    roubos = _roubos_get(b, oferta(dados, edicao, semente_draft, clube))
    escolhas = _escolhas_get(b, RESPOSTAS[formato])
    nota, titulos = b.get(7), b.get(8)
    rotulo = v.rotulo_get(b) or ROTULO_PERDIDO
    clubes = _clubes_get(b, v, clube)
    final = POSICOES[b.get(3)] if formato >= 2 and b.get(1) else posicao
    b.fim()
    craque = Craque(nome=nome, camisa=camisa, posicao=posicao, pe=pe, clube=clube)
    return Compartilhado(
        versao=versao,
        edicao=edicao,
        entrada=Entrada(
            semente_draft=semente_draft,
            semente=semente,
            craque=craque,
            roubos=roubos,
            escolhas=escolhas,
            modo=modo,
            minijogos=minijogos,
        ),
        resumo=Resumo(
            nome=craque.nome,
            posicao=final,
            rotulo=rotulo,
            nota=nota,
            titulos=titulos,
            clubes=clubes,
        ),
    )


class _Escrita:
    """Bits, most significant first; the last byte is padded with zeros."""

    def __init__(self) -> None:
        self.valor = self.tamanho = 0

    def put(self, valor: int, bits: int) -> None:
        if not 0 <= valor < 1 << bits:
            raise ValueError(f"{valor} does not fit in {bits} bits")
        self.valor = self.valor << bits | valor
        self.tamanho += bits

    def bruto(self, dados: bytes, bits: int = 8) -> None:
        for byte in dados:
            self.put(byte, bits)

    def texto(self, texto: str) -> None:
        """7 bits a character when ASCII, 8 when Latin-1 (most Brazilian names), else UTF-8."""
        if texto.isascii():
            modo, dados, bits = ASCII, texto.encode(), 7
        else:
            try:
                modo, dados, bits = LATIN1, texto.encode("latin-1"), 8
            except UnicodeEncodeError:
                modo, dados, bits = UTF8, texto.encode(), 8
        self.put(modo, 2)
        self.put(len(dados), 8)
        self.bruto(dados, bits)

    def bytes(self) -> bytes:
        sobra = -self.tamanho % 8
        return (self.valor << sobra).to_bytes((self.tamanho + sobra) // 8, "big")


class _Leitura:
    def __init__(self, dados: bytes) -> None:
        self.valor = int.from_bytes(dados, "big")
        self.resta = len(dados) * 8

    def get(self, bits: int) -> int:
        if bits > self.resta:
            raise ValueError("the code ends too soon")
        self.resta -= bits
        return self.valor >> self.resta & ((1 << bits) - 1)

    def bruto(self, n: int, bits: int = 8) -> bytes:
        return bytes(self.get(bits) for _ in range(n))

    def texto(self) -> str:
        modo = self.get(2)
        n = self.get(8)
        if modo == ASCII:
            return self.bruto(n, 7).decode("ascii")
        if modo == LATIN1:
            return self.bruto(n).decode("latin-1")
        if modo == UTF8:
            return self.bruto(n).decode()
        raise ValueError("unknown text encoding")

    def fim(self) -> None:
        """Only the zero padding of the last byte may be left: one code per career."""
        if self.resta >= 8 or self.valor & ((1 << self.resta) - 1):
            raise ValueError("the code goes on after the career")


def _hash(texto: str, bits: int) -> int:
    digest = hashlib.blake2s(texto.encode(), digest_size=4).digest()
    return int.from_bytes(digest, "big") >> (32 - bits)


class _Vocabulario:
    """Today's club ids and card labels by hash; a hash two of them share is never used."""

    def __init__(self, dados: Dados) -> None:
        self.dados = dados
        self.clubes = _por_hash(dados.clubes, CLUBE)
        self.rotulos = _por_hash({f["rotulo"] for f in dados.finais}, ROTULO)
        nomes: dict[str, list[str]] = {}
        for clube in dados.clubes.values():
            nomes.setdefault(clube.nome, []).append(clube.id)
        self.ids = {nome: ids[0] for nome, ids in nomes.items() if len(ids) == 1}

    def clube_put(self, b: _Escrita, clube_id: str) -> None:
        _nome_put(b, clube_id, self.clubes, CLUBE)

    def clube_get(self, b: _Leitura) -> str | None:
        return _nome_get(b, self.clubes, CLUBE)

    def nome_put(self, b: _Escrita, nome: str) -> None:
        """A club of the card: by its id when the name is known, else the name in full."""
        clube_id = self.ids.get(nome)
        curto = clube_id is not None and self.clubes.get(_hash(clube_id, CLUBE)) == clube_id
        b.put(curto, 1)
        if curto:
            b.put(_hash(clube_id, CLUBE), CLUBE)
        else:
            b.texto(nome)

    def nome_get(self, b: _Leitura) -> str | None:
        if not b.get(1):
            return b.texto()
        clube = self.dados.clubes.get(self.clubes.get(b.get(CLUBE), ""))
        return clube.nome if clube else None

    def rotulo_put(self, b: _Escrita, rotulo: str) -> None:
        _nome_put(b, rotulo, self.rotulos, ROTULO)

    def rotulo_get(self, b: _Leitura) -> str | None:
        return _nome_get(b, self.rotulos, ROTULO)


def _por_hash(textos, bits: int) -> dict[int, str]:
    vistos: dict[int, list[str]] = {}
    for texto in textos:
        vistos.setdefault(_hash(texto, bits), []).append(texto)
    return {h: t[0] for h, t in vistos.items() if len(t) == 1}


def _nome_put(b: _Escrita, texto: str, vocabulario: dict[int, str], bits: int) -> None:
    curto = vocabulario.get(_hash(texto, bits)) == texto
    b.put(curto, 1)
    if curto:
        b.put(_hash(texto, bits), bits)
    else:
        b.texto(texto)


def _nome_get(b: _Leitura, vocabulario: dict[int, str], bits: int) -> str | None:
    """The text, or None when today's data no longer knows that hash."""
    return vocabulario.get(b.get(bits)) if b.get(1) else b.texto()


def _versao_put(b: _Escrita, versao: str) -> None:
    """`dados.versao` (8 hex digits) by its first 16 bits; anything else in full."""
    hexa = re.fullmatch("[0-9a-f]{8}", versao) is not None
    b.put(hexa, 1)
    if hexa:
        b.put(int(versao, 16) >> (32 - VERSAO), VERSAO)
    else:
        b.texto(versao)


def _versao_get(b: _Leitura, hoje: str) -> str:
    """Today's version when the bits match it; else only the prefix (never equal to today's)."""
    if not b.get(1):
        return b.texto()
    prefixo = f"{b.get(VERSAO):0{VERSAO // 4}x}"
    return hoje if hoje.startswith(prefixo) else prefixo


def _semente_put(b: _Escrita, semente: str) -> None:
    """A server seed (token_urlsafe(8): 11 characters) as its 8 bytes; any other in full."""
    try:
        cru = base64.urlsafe_b64decode(semente + "=")
    except (binascii.Error, ValueError):
        cru = b""
    token = len(cru) == TOKEN and _token(cru) == semente
    b.put(token, 1)
    if token:
        b.bruto(cru)
    else:
        b.texto(semente)


def _token(cru: bytes) -> str:
    return base64.urlsafe_b64encode(cru).decode().rstrip("=")


def _semente_get(b: _Leitura) -> str:
    return _token(b.bruto(TOKEN)) if b.get(1) else b.texto()


def _conferir(ofertadas: list) -> int:
    """A few bits of the offer: a link of an older draft must not replay other legends."""
    return _hash("\0".join(x.nome for x in ofertadas), CONFERE)


def _roubos_put(b: _Escrita, roubos: list[Roubo], ofertadas: list) -> None:
    """Who each attribute (in `ATRIBUTOS` order) was stolen from, as one number: the position
    in the offer among the legends still free (a permutation's Lehmer code)."""
    por_atributo = {r.atributo: r.lenda for r in roubos}
    if len(roubos) != len(ATRIBUTOS) or set(por_atributo) != set(ATRIBUTOS):
        raise ValueError("a finished career steals each attribute once")
    livres = [x.nome for x in ofertadas]
    numero = 0
    for atributo in ATRIBUTOS:
        posicao = livres.index(por_atributo[atributo])  # ValueError when not on offer
        numero = numero * len(livres) + posicao
        livres.pop(posicao)
    b.put(_conferir(ofertadas), CONFERE)
    b.put(numero, ROUBOS.bit_length())


def _roubos_get(b: _Leitura, ofertadas: list) -> list[Roubo]:
    """The roubos, or none when today's offer is not the one the link was made with."""
    conferencia, numero = b.get(CONFERE), b.get(ROUBOS.bit_length())
    if numero >= ROUBOS:
        raise ValueError("no such draft")
    posicoes = []
    for livres in range(OFERTA - len(ATRIBUTOS) + 1, OFERTA + 1):
        numero, posicao = divmod(numero, livres)
        posicoes.append(posicao)
    if conferencia != _conferir(ofertadas) or len(ofertadas) != OFERTA:
        return []
    livres = [x.nome for x in ofertadas]
    return [
        Roubo(lenda=livres.pop(p), atributo=a)
        for p, a in zip(reversed(posicoes), ATRIBUTOS, strict=True)
    ]


def _escolhas_put(b: _Escrita, escolhas: list[int], contador: int) -> None:
    """The answers as one number in base (largest answer + 1)."""
    base = max(escolhas, default=0) + 1
    if base > 17 or min(escolhas, default=0) < 0:
        raise ValueError("an answer out of range")
    base = max(base, 2)
    numero = 0
    for escolha in escolhas:
        numero = numero * base + escolha
    b.put(len(escolhas), contador)
    b.put(base - 2, 4)
    b.put(numero, (base ** len(escolhas) - 1).bit_length())


def _escolhas_get(b: _Leitura, contador: int) -> list[int]:
    quantas, base = b.get(contador), b.get(4) + 2
    numero = b.get((base**quantas - 1).bit_length())
    escolhas = []
    for _ in range(quantas):
        numero, escolha = divmod(numero, base)
        escolhas.append(escolha)
    if numero:
        raise ValueError("answers left over")
    return escolhas[::-1]


def _clubes_put(b: _Escrita, v: _Vocabulario, clubes: list[str], inicio: str | None) -> None:
    """The card's clubs; the first one is nearly always where he started, told in one bit."""
    b.put(len(clubes), 5)
    primeiro = inicio is not None and inicio in v.dados.clubes
    primeiro = primeiro and bool(clubes) and clubes[0] == v.dados.clubes[inicio].nome
    b.put(primeiro, 1)
    for nome in clubes[1:] if primeiro else clubes:
        v.nome_put(b, nome)


def _clubes_get(b: _Leitura, v: _Vocabulario, inicio: str | None) -> list[str]:
    quantos, primeiro = b.get(5), b.get(1)
    if primeiro and not quantos:
        raise ValueError("a first club of none")
    clubes = []
    if primeiro:
        clube = v.dados.clubes.get(inicio or "")
        clubes.append(clube.nome if clube else None)
    clubes += [v.nome_get(b) for _ in range(quantos - primeiro)]
    return [c for c in clubes if c is not None]
