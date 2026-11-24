"""Rules of a Prancheta room: pure, synchronous, with the clock injected.

Every method receives `agora` and returns the events the hub must deliver. Privacy (who sees
the word, the choices, a near miss) is decided here; the hub only routes `para`/`exceto`.
"""

import random
import secrets
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from geral.games.prancheta.filtro import tem_palavrao
from geral.games.prancheta.tipos import Banco, Palavra, normalizar

MAX_JOGADORES = 10
TEMPO_ESCOLHA = timedelta(seconds=15)
TEMPO_DESENHO = timedelta(seconds=80)
TEMPO_INTERVALO = timedelta(seconds=6)
AUSENCIA = timedelta(seconds=30)
BASE = {"facil": 5, "media": 7, "dificil": 10}
PISO = 2
ASSISTENCIA = 2
PEDACO_MAX = 64
PONTOS_MAX = 20_000
CHUTE_MAX = 40
CHUTE_INTERVALO = timedelta(seconds=0.5)
PEDACOS_POR_SEGUNDO = 40
APELIDO_MIN, APELIDO_MAX = 2, 16
CORES = range(8)
ESPESSURAS = (1, 2, 3)
COORDENADAS = range(1001)
DIFICULDADES = ("facil", "media", "dificil")


@dataclass
class Evento:
    tipo: str  # estado | traco | desfazer | limpar | chute | acerto | trave | dica | fim
    dados: dict  # the contract's JSON, already with "seq"
    para: int | None = None
    exceto: int | None = None


class ErroSala(Exception):
    def __init__(self, status: int, motivo: str):
        super().__init__(motivo)
        self.status = status
        self.motivo = motivo


@dataclass
class _Jogador:
    id: int
    apelido: str
    token: str
    desde: datetime  # last time the player had no events connection (or joined)
    pontos: int = 0
    gols: int = 0
    assist: int = 0
    conexoes: int = 0
    presente: bool = True
    acertou: bool = False
    ultimo_chute: datetime | None = None
    pedacos: deque = field(default_factory=deque)


def _eh_int(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


class Sala:
    def __init__(
        self, id: str, rodadas: int, banco: Banco, rng: random.Random, agora: datetime
    ) -> None:
        self.id = id
        self.rodadas = rodadas
        self.criada_em = agora
        self.encerrada = False
        self._banco = banco
        self._rng = rng
        self._seq = 0
        self._jogadores: dict[int, _Jogador] = {}  # active players, in joining order
        self._tokens: dict[str, int] = {}
        self._proximo_id = 1
        self._anfitriao: int | None = None
        self._fase = "espera"
        self._rodada = 0
        self._fila: list[int] = []
        self._prazo: datetime | None = None
        self._usadas: set[str] = set()
        self._desenhista: int | None = None
        self._opcoes: list[Palavra] | None = None
        self._palavra: Palavra | None = None
        self._tracos: dict[int, dict] = {}
        self._total_pontos = 0
        self._dica: list[str | None] | None = None
        self._dicas_dadas = 0
        self._acertaram: list[int] = []

    # --- entrada e identidade ---

    def entrar(self, apelido: str, agora: datetime) -> tuple[int, str, list[Evento]]:
        if self.encerrada:
            raise ErroSala(409, "room is over")
        if len(self._jogadores) >= MAX_JOGADORES:
            raise ErroSala(409, "room is full")
        apelido = apelido.strip()
        if not APELIDO_MIN <= len(apelido) <= APELIDO_MAX:
            raise ErroSala(422, "nickname must have 2 to 16 characters")
        if tem_palavrao(apelido):
            raise ErroSala(422, "nickname not allowed")
        if normalizar(apelido) in {normalizar(j.apelido) for j in self._jogadores.values()}:
            raise ErroSala(422, "nickname already in the room")
        jogador = _Jogador(self._proximo_id, apelido, secrets.token_urlsafe(16), desde=agora)
        self._proximo_id += 1
        self._jogadores[jogador.id] = jogador
        self._tokens[jogador.token] = jogador.id
        if self._anfitriao is None:
            self._anfitriao = jogador.id
        if self._fase not in ("espera", "fim"):
            self._fila.append(jogador.id)
        return jogador.id, jogador.token, self._estados(agora)

    def jogador(self, token: str) -> int:
        try:
            return self._tokens[token]
        except KeyError:
            raise ErroSala(403, "invalid token") from None

    # --- ações ---

    def agir(self, jogador: int, acao: dict, agora: datetime) -> list[Evento]:
        if jogador not in self._jogadores:
            raise ErroSala(403, "player is not in the room")
        if self.encerrada:
            raise ErroSala(409, "room is over")
        tratar = {
            "comecar": self._comecar,
            "escolher": self._escolher,
            "traco": self._traco,
            "desfazer": self._desfazer,
            "limpar": self._limpar,
            "chute": self._chute,
        }.get(acao.get("tipo"))
        if tratar is None:
            raise ErroSala(422, "unknown action")
        return tratar(self._jogadores[jogador], acao, agora)

    def _comecar(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        if jogador.id != self._anfitriao:
            raise ErroSala(409, "only the host starts")
        if self._fase != "espera":
            raise ErroSala(409, "already started")
        if len(self._presentes()) < 2:
            raise ErroSala(409, "need two players")
        return self._proximo_lance(agora)

    def _escolher(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        self._exigir_desenhista(jogador, "escolha")
        indice = acao.get("indice")
        if not _eh_int(indice) or not 0 <= indice <= 2:
            raise ErroSala(422, "index must be 0 to 2")
        assert self._opcoes is not None
        return self._comecar_desenho(self._opcoes[indice], agora)

    def _traco(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        self._exigir_desenhista(jogador, "desenho")
        id_, cor, esp, pts, fim = (acao.get(k) for k in ("id", "cor", "esp", "pts", "fim"))
        valido = (
            _eh_int(id_)
            and _eh_int(cor)
            and cor in CORES
            and _eh_int(esp)
            and esp in ESPESSURAS
            and isinstance(fim, bool)
            and isinstance(pts, list)
            and len(pts) <= PEDACO_MAX
            and all(
                isinstance(p, list)
                and len(p) == 2
                and all(_eh_int(c) and c in COORDENADAS for c in p)
                for p in pts
            )
        )
        if not valido:
            raise ErroSala(422, "invalid stroke")
        if self._total_pontos + len(pts) > PONTOS_MAX:
            raise ErroSala(422, "drawing is too long")
        while jogador.pedacos and agora - jogador.pedacos[0] >= timedelta(seconds=1):
            jogador.pedacos.popleft()
        if len(jogador.pedacos) >= PEDACOS_POR_SEGUNDO:
            raise ErroSala(429, "too many stroke pieces")
        jogador.pedacos.append(agora)
        self._total_pontos += len(pts)
        atual = self._tracos.get(id_)
        if atual is None:
            self._tracos[id_] = {"id": id_, "cor": cor, "esp": esp, "pts": list(pts), "fim": fim}
        else:
            atual["pts"].extend(pts)
            atual["fim"] = fim
        dados = {"id": id_, "cor": cor, "esp": esp, "pts": pts, "fim": fim}
        return [self._evento("traco", dados, exceto=jogador.id)]

    def _desfazer(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        self._exigir_desenhista(jogador, "desenho")
        if not self._tracos:
            return []
        id_, traco = self._tracos.popitem()
        self._total_pontos -= len(traco["pts"])
        return [self._evento("desfazer", {"id": id_}, exceto=jogador.id)]

    def _limpar(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        self._exigir_desenhista(jogador, "desenho")
        self._tracos.clear()
        self._total_pontos = 0
        return [self._evento("limpar", {}, exceto=jogador.id)]

    def _chute(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        if self._fase != "desenho" or jogador.id == self._desenhista or jogador.acertou:
            raise ErroSala(409, "cannot guess now")
        cru = acao.get("texto")
        if not isinstance(cru, str) or not cru.strip() or len(cru.strip()) > CHUTE_MAX:
            raise ErroSala(422, "guess must have 1 to 40 characters")
        if jogador.ultimo_chute and agora - jogador.ultimo_chute < CHUTE_INTERVALO:
            raise ErroSala(429, "guessing too fast")
        jogador.ultimo_chute = agora
        assert self._palavra is not None
        veredito = self._banco.julgar(cru, self._palavra)
        texto = cru.strip()
        if veredito == "certo":
            return self._acerto(jogador, agora)
        if veredito == "trave":
            return [self._evento("trave", {"texto": texto}, para=jogador.id)]
        dados = {"jogador": jogador.id, "texto": texto}
        normal = normalizar(texto)
        entrega = tem_palavrao(texto) or any(
            normalizar(alvo) in normal for alvo in (self._palavra.texto, *self._palavra.aceita)
        )
        return [self._evento("chute", dados, para=jogador.id if entrega else None)]

    def _acerto(self, jogador: _Jogador, agora: datetime) -> list[Evento]:
        assert self._palavra is not None
        self._acertaram.append(jogador.id)
        pontos = max(BASE[self._palavra.dificuldade] - (len(self._acertaram) - 1), PISO)
        jogador.acertou = True
        jogador.pontos += pontos
        jogador.gols += 1
        desenhista = self._jogadores.get(self._desenhista or 0)
        if desenhista is not None:
            desenhista.pontos += ASSISTENCIA
            desenhista.assist += 1
        eventos = [self._evento("acerto", {"jogador": jogador.id, "pontos": pontos})]
        if self._todos_acertaram():
            eventos += self._ir_ao_intervalo(agora)
        return eventos

    def _todos_acertaram(self) -> bool:
        quem_chuta = [j for j in self._presentes() if j != self._desenhista]
        return all(self._jogadores[j].acertou for j in quem_chuta)

    def _exigir_desenhista(self, jogador: _Jogador, fase: str) -> None:
        if self._fase != fase or jogador.id != self._desenhista:
            raise ErroSala(409, "not your turn")

    # --- conexão e relógio ---

    def conectou(self, jogador: int, agora: datetime) -> list[Evento]:
        j = self._jogadores.get(jogador)
        if j is None:
            return []
        j.conexoes += 1
        return []

    def desconectou(self, jogador: int, agora: datetime) -> list[Evento]:
        j = self._jogadores.get(jogador)
        if j is None:
            return []
        j.conexoes = max(j.conexoes - 1, 0)
        if j.conexoes == 0:
            j.desde = agora
        return []

    def avancar(self, agora: datetime) -> list[Evento]:
        eventos: list[Evento] = []
        if self._fase == "desenho":
            eventos += self._dicas(agora)
        while not self.encerrada and self._prazo is not None and agora >= self._prazo:
            if self._fase == "escolha":
                assert self._opcoes is not None
                eventos += self._comecar_desenho(self._rng.choice(self._opcoes), agora)
            elif self._fase == "desenho":
                eventos += self._ir_ao_intervalo(agora)
            elif self._fase == "intervalo":
                eventos += self._proximo_lance(agora)
        return eventos

    # --- fases ---

    def _proximo_lance(self, agora: datetime) -> list[Evento]:
        while True:
            while self._fila:
                candidato = self._fila.pop(0)
                if candidato in self._presentes():
                    return self._iniciar_lance(candidato, agora)
            if self._rodada >= self.rodadas:
                return self._encerrar(agora)
            self._rodada += 1
            self._fila = list(self._presentes())

    def _dicas(self, agora: datetime) -> list[Evento]:
        """Lights one random unlit letter at 50% and at 75% of the drawing time."""
        assert self._prazo is not None and self._dica is not None
        inicio = self._prazo - TEMPO_DESENHO
        eventos = []
        for numero, marco in enumerate((0.5, 0.75), start=1):
            if self._dicas_dadas >= numero or agora < inicio + TEMPO_DESENHO * marco:
                continue
            self._dicas_dadas = numero
            assert self._palavra is not None
            letras = [i for i, c in enumerate(self._palavra.texto) if c.isalpha()]
            apagadas = [i for i in letras if self._dica[i] is None]
            if len(letras) - len(apagadas) >= len(letras) // 3:
                continue
            i = self._rng.choice(apagadas)
            self._dica[i] = self._palavra.texto[i]
            eventos.append(
                self._evento("dica", {"dica": list(self._dica)}, exceto=self._desenhista)
            )
        return eventos

    def _iniciar_lance(self, desenhista: int, agora: datetime) -> list[Evento]:
        self._fase = "escolha"
        self._desenhista = desenhista
        self._opcoes = self._banco.opcoes(self._rng, self._usadas)
        self._usadas.update(p.texto for p in self._opcoes)
        self._palavra = None
        self._dica = None
        self._dicas_dadas = 0
        self._acertaram = []
        self._tracos = {}
        self._total_pontos = 0
        self._prazo = agora + TEMPO_ESCOLHA
        for j in self._jogadores.values():
            j.acertou = False
        return self._estados(agora)

    def _comecar_desenho(self, palavra: Palavra, agora: datetime) -> list[Evento]:
        self._fase = "desenho"
        self._palavra = palavra
        self._dica = [None if c.isalpha() else c for c in palavra.texto]
        self._opcoes = None
        self._prazo = agora + TEMPO_DESENHO
        return self._estados(agora)

    def _ir_ao_intervalo(self, agora: datetime) -> list[Evento]:
        self._fase = "intervalo"
        self._opcoes = None
        self._prazo = agora + TEMPO_INTERVALO
        return self._estados(agora)

    def _encerrar(self, agora: datetime) -> list[Evento]:
        self._fase = "fim"
        self._prazo = None
        self._opcoes = None
        self.encerrada = True
        return self._estados(agora)

    # --- leitura ---

    def _presentes(self) -> list[int]:
        return [j.id for j in self._jogadores.values() if j.presente]

    def foto(self, jogador: int, agora: datetime) -> dict:
        desenha = jogador == self._desenhista
        ve_palavra = self._fase in ("intervalo", "fim") or (desenha and self._fase == "desenho")
        return {
            "seq": self._seq,
            "voce": jogador,
            "fase": self._fase,
            "rodada": self._rodada,
            "rodadas": self.rodadas,
            "prazo": self._prazo.isoformat() if self._prazo else None,
            "agora": agora.isoformat(),
            "desenhista": self._desenhista,
            "jogadores": [
                {
                    "id": j.id,
                    "apelido": j.apelido,
                    "pontos": j.pontos,
                    "gols": j.gols,
                    "assist": j.assist,
                    "presente": j.presente,
                    "anfitriao": j.id == self._anfitriao,
                    "acertou": j.acertou,
                }
                for j in self._jogadores.values()
            ],
            "dica": list(self._dica) if self._dica is not None else None,
            "opcoes": (
                [{"texto": p.texto, "dificuldade": p.dificuldade} for p in self._opcoes]
                if desenha and self._fase == "escolha" and self._opcoes
                else None
            ),
            "palavra": self._palavra.texto if ve_palavra and self._palavra else None,
            "tracos": [{**t, "pts": [list(p) for p in t["pts"]]} for t in self._tracos.values()],
        }

    def _estados(self, agora: datetime) -> list[Evento]:
        """One `estado` per active player (each sees their own view), all with the same seq."""
        self._seq += 1
        return [Evento("estado", self.foto(j, agora), para=j) for j in self._jogadores]

    def _evento(self, tipo: str, dados: dict, **destino) -> Evento:
        self._seq += 1
        return Evento(tipo, {**dados, "seq": self._seq}, **destino)
