"""The career engine: one seed, the draft and the answers so far give the same career, always.

The seed's random stream is consumed in chronological order only, so a new answer never
changes a season that came before it: the career grows in front of the fan, it never shifts.
"""

import random
from dataclasses import dataclass, field, replace
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from geral.games.carreira import final
from geral.games.carreira.dados import (
    COM_CLUBE,
    Clube,
    Condicao,
    Dados,
    Decisao,
    Efeito,
    Evento,
    Opcao,
    OpcaoRotina,
)
from geral.games.carreira.draft import JogadaInvalida, Roubo, montar, oferta
from geral.games.carreira.regras import NOMES, POSICOES, geral

PRIMEIRO_ANO = 2027
IDADE_INICIAL, IDADE_MAXIMA = 16, 42
RISCO = 8  # taken off every risky day-to-day chance: daring has to cost something
MAX_ESCOLHAS = {"rapida": 5, "completa": 8}  # drawn decision questions per career
ARCO_TENTATIVAS = 2  # seasons an arc's next step waits for its condition before it dies
MAX_LANCES = 4  # penalties per career, one a season at most
MAX_RESPOSTAS = 60 + MAX_LANCES  # every answer of a Completa career: day-to-day, market, penalties
CHANCE_ESCOLHA = 0.4  # per season, when one fits
ARRISCADA = 25  # an option with this chance or less is shown as a long shot
COPA_DO_NORDESTE = "Copa do Nordeste"
REALIZACAO = 0.0  # points the ceiling sits from the draft's rating, on average
REALIZACAO_DESVIO = 9.0  # how much careers differ in it: both busts and stars come from here
FORMA = 4  # spread of a season's form (rating points, up or down)
FORMA_RUIM = -7  # from here down the season is told as one to forget
TEMPORADA_RUIM = "temporada-ruim"
GIGANTE_CEDO = 14  # a club this far above a boy of 21 or less slows his growth
SALTO = 18  # the biggest jump in level of a move up
EUROPA = 80  # league strength from which a league counts as the top of Europe
EXOTICAS = ("ara", "jap", "eua", "tur", "mex")
GOL = {"atacante": 0.5, "meia": 0.24, "volante": 0.07, "lateral": 0.06, "zagueiro": 0.05}
LANCES = ("gol", "defesa", "fora", "trave", "motor")  # the penalty's answers; "motor" rolls it
TIPOS_LANCE = ("jogo", "classico", "final")  # the match of a penalty: what is at stake
CHANCE_PENALTI = (0.2, 0.08)  # per season on the pitch, before his first penalty and after
CLASSICO_PENALTI = 0.5  # of those, the share that falls in a derby (where the club has one)
JOGOS_PENALTI = 5  # a season with fewer games has no penalty to take
MINUTO_FINAL = "90+4'"
MARCA_GOL, MARCA_ERRO = "frio-nas-decisoes", "perdeu-o-penalti"
ASSIST = {"atacante": 0.16, "meia": 0.26, "volante": 0.09, "lateral": 0.13, "zagueiro": 0.03}


class Craque(BaseModel):
    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=24)]
    camisa: int = Field(ge=1, le=99)
    posicao: Literal[POSICOES]
    pe: Literal["direito", "esquerdo", "ambos"]
    clube: str | None = Field(default=None, max_length=40)  # the 'geral' edition's start


class Entrada(BaseModel):
    semente_draft: str = Field(min_length=1, max_length=40)
    semente: str = Field(min_length=1, max_length=40)
    craque: Craque
    roubos: list[Roubo] = Field(max_length=9)
    escolhas: list[int] = Field(default=[], max_length=MAX_RESPOSTAS)
    modo: Literal["rapida", "completa"] = "rapida"
    minijogos: bool = False  # a penalty is played on screen; else the engine rolls it


class Temporada(BaseModel):
    ano: int
    idade: int
    clube: str
    clube_id: str
    pais: str
    liga_forca: int
    jogos: int
    gols: int
    assistencias: int
    nota: int
    titulos: list[str]
    selecao: int  # games for the national team
    copa: bool  # played a World Cup
    manchete: str
    eventos: list[str]
    forma: int = 0  # how the season went against his level, -10..10
    chegada: str | None = None  # "Chegou do Vasco": every change of club says so
    rotina: "ResultadoRotina | None" = None  # the day-to-day choice before this season
    marcas: list[str] = []  # the marks won since the last season, told: "Zé ganha a braçadeira"
    lance: "ResultadoLance | None" = None  # his penalty, when this season had one


class ResultadoLance(BaseModel):
    resultado: Literal["gol", "defesa", "fora", "trave"]
    adversario: str
    manchete: str
    copa: str = ""  # the cup, when it was the final
    tipo: Literal[TIPOS_LANCE] = "final"
    minuto: str = MINUTO_FINAL
    competicao: str = ""  # the league, the derby's name or the cup


class Lance(BaseModel):
    """The scoreboard of a penalty on screen: the club against whom, at which minute, in which
    match: a league game, a derby or a cup final."""

    clube: str
    adversario: str
    tipo: Literal[TIPOS_LANCE]
    minuto: str
    competicao: str  # the league, the derby's name or the cup
    copa: str = ""  # the cup, when it is the final


class ResultadoRotina(BaseModel):
    situacao: str
    escolha: str
    deu_certo: bool
    efeito: str  # "+3 finalização", "" when nothing changed


class InfoOpcao(BaseModel):
    chance: int | None = None  # % of it going well; None when there is no risk
    efeitos: str = ""  # "certo: +3 finalização · errado: lesão leve"
    arriscada: bool = False  # a long shot: chance of ARRISCADA or less


class Escolha(BaseModel):
    id: str
    tipo: Literal["dia", "mercado", "decisao", "lance"] = "decisao"
    pergunta: str
    opcoes: list[str]
    info: list[InfoOpcao] = []  # chance and effects of each option (day-to-day, risky decisions)
    destinos: list[str]  # the kind of each option (ficar, europa, aposentar…)
    clubes: list[str | None]  # the club each option moves to, None when it stays put
    lance: Lance | None = None  # a penalty's scoreboard (tipo "lance")


class Final(BaseModel):
    nota: int  # 0-100
    rotulo: str
    descricao: str
    titulos: dict[str, int]
    clubes: list[str]  # in the order he played for them
    jogos: int
    gols: int
    selecao: int
    copa: bool
    parecido: str  # "your career recalls ___"
    perguntas: list[str]  # ids of the questions asked
    posicao: str = ""  # where he ended up playing ("virou meia")
    marcas: list[str] = []  # the names of the marks he won, in order
    vereditos: list[final.Veredito] = []  # what each club's fans say


class Carreira(BaseModel):
    temporadas: list[Temporada]
    pendente: Escolha | None = None
    final: Final | None = None


def chance_de(opcao: OpcaoRotina, notas: dict[str, int]) -> int:
    """The % shown to the fan and rolled by the engine: one source for both."""
    if opcao.chance >= 100:
        return 100
    bonus = (notas[opcao.bonus] - 70) // 2 if opcao.bonus else 0
    return max(5, min(95, opcao.chance + bonus - RISCO))


def chance_penalti(finalizacao: int) -> float:
    """The engine's penalty: a goal this often, by the player's finishing."""
    return max(0.35, min(0.85, 0.45 + (finalizacao - 60) / 100))


def _minuto(minuto: int) -> str:
    """70 -> "70'", 94 -> "90+4'": how the scoreboard tells the minute."""
    return f"{minuto}'" if minuto <= 90 else f"90+{minuto - 90}'"


def descrever(efeito: Efeito) -> str:
    partes = [
        f"{'+' if d > 0 else '−'}{abs(d)} {NOMES[a].lower()}" for a, d in efeito.atributos.items()
    ]
    if efeito.nota:
        partes.append(f"{'+' if efeito.nota > 0 else '−'}{abs(efeito.nota)} de forma")
    if efeito.teto:
        partes.append(f"{'+' if efeito.teto > 0 else '−'}{abs(efeito.teto)} de potencial")
    if efeito.jogos < 1:
        partes.append("lesão: perde parte da temporada" if efeito.jogos <= 0.7 else "lesão leve")
    if efeito.saida > 0:
        partes.append("mais chance de proposta")
    elif efeito.saida < 0:
        partes.append("mais chance de ficar")
    if efeito.selecao:
        partes.append("olho da Seleção")
    return ", ".join(partes)


def _info(opcao: OpcaoRotina, notas: dict[str, int], dados: Dados | None = None) -> InfoOpcao:
    chance = chance_de(opcao, notas)

    def lado(efeito: Efeito, marca: str) -> str:
        partes = [descrever(efeito)]
        if dados and marca in dados.marcas:
            partes.append(f"vira {dados.marcas[marca].nome}")
        return ", ".join(p for p in partes if p)

    certo, errado = lado(opcao.sucesso, opcao.marca), lado(opcao.fracasso, opcao.marca_fracasso)
    if chance >= 100:
        return InfoOpcao(chance=None, efeitos=certo or "nada muda")
    return InfoOpcao(
        chance=chance,
        efeitos=f"certo: {certo or 'nada muda'} · errado: {errado or 'nada muda'}",
        arriscada=chance <= ARRISCADA,
    )


def _com_risco(opcao: OpcaoRotina) -> bool:
    """An option worth explaining: it has a chance, an effect or a mark."""
    return (
        opcao.chance < 100
        or opcao.sucesso != Efeito()
        or opcao.fracasso != Efeito()
        or bool(opcao.marca or opcao.marca_fracasso)
    )


def clube_inicial(dados: Dados, edicao: str, escolhido: str | None) -> Clube:
    """A team edition starts in the team's youth; 'geral' in the Brazilian club the fan chose."""
    if edicao != "geral":
        for clube in dados.clubes.values():
            if clube.time == edicao:
                return clube
        raise JogadaInvalida("essa edição não tem clube de partida")
    clube = dados.clubes.get(escolhido or "")
    if clube is None or dados.ligas[clube.liga].pais != "Brasil":
        raise JogadaInvalida("escolha um clube brasileiro para começar")
    return clube


def simular(dados: Dados, edicao: str, entrada: Entrada) -> Carreira:
    ofertadas = oferta(dados, edicao, entrada.semente_draft, entrada.craque.clube)
    notas = montar(ofertadas, entrada.roubos)
    inicio = clube_inicial(dados, edicao, entrada.craque.clube)
    return _Simulacao(dados, entrada, notas, inicio).rodar()


def artigos(campo: str, clube: Clube | None) -> dict[str, str]:
    """`{campo}` plus its articled forms for the texts: {o_clube}, {do_clube}, {no_clube}…"""
    nome = clube.nome if clube else ""
    f = clube is not None and clube.genero == "f"
    formas = {
        "o": "a" if f else "o",
        "O": "A" if f else "O",
        "do": "da" if f else "do",
        "no": "na" if f else "no",
        "pelo": "pela" if f else "pelo",
        "ao": "à" if f else "ao",
        "para_o": "para a" if f else "para o",
    }
    return {campo: nome} | {f"{k}_{campo}": f"{v} {nome}" for k, v in formas.items()}


def _fase(idade: int) -> str:
    return "inicio" if idade < 21 else "auge" if idade <= 30 else "fim"


@dataclass
class _Contexto:
    """What conditions look at: the player now and, after the numbers, this season."""

    idade: int
    nota: int
    forca: int
    posicao: str
    historico: set[str]
    no_clube_inicial: bool
    pais: str = ""
    regiao: str = ""
    classico: bool = False
    gols: int = 0
    jogos: int = 0
    titulo: bool = False
    selecao: bool = False
    copa: bool = False
    mundial: bool = False
    chegou_de_fora: bool = False

    def casa(self, c: Condicao) -> bool:
        return (
            c.idade_min <= self.idade <= c.idade_max
            and c.nota_min <= self.nota <= c.nota_max
            and c.forca_min <= self.forca <= c.forca_max
            and (not c.posicoes or self.posicao in c.posicoes)
            and (not c.fases or _fase(self.idade) in c.fases)
            and all(r in self.historico for r in c.requer)
            and not any(x in self.historico for x in c.exclui)
            and c.gols_min <= self.gols <= c.gols_max
            and c.jogos_min <= self.jogos <= c.jogos_max
            and (c.titulo is None or c.titulo == self.titulo)
            and (c.no_clube_inicial is None or c.no_clube_inicial == self.no_clube_inicial)
            and (c.selecao is None or c.selecao == self.selecao)
            and (c.copa is None or c.copa == self.copa)
            and (c.mundial is None or c.mundial == self.mundial)
            and (not c.paises or self.pais in c.paises)
            and (not c.regioes or self.regiao in c.regioes)
            and (c.classico is None or c.classico == self.classico)
            and (c.chegou_de_fora is None or c.chegou_de_fora == self.chegou_de_fora)
        )


@dataclass
class _Simulacao:
    dados: Dados
    entrada: Entrada
    notas: dict[str, int]
    inicio: Clube
    temporadas: list[Temporada] = field(default_factory=list)
    historico: set[str] = field(default_factory=set)
    perguntadas: list[str] = field(default_factory=list)
    passos: int = 0  # how many of `perguntadas` were arc steps (outside the cap)
    # open arcs, oldest first: (the mark, tries left, the club it happens at)
    arcos: list[tuple[str, int, str]] = field(default_factory=list)
    marcas_ganhas: list[str] = field(default_factory=list)  # mark ids, in order
    onde_marcou: dict[str, str] = field(default_factory=dict)  # mark id -> club it was won at
    manchetes_usadas: set[str] = field(default_factory=set)  # headline templates told
    respondidas: int = 0
    emprestado_de: Clube | None = None
    aposentou: bool = False
    chegada: str | None = None  # how he got to the current club, for the next season
    veio_de: Clube | None = None  # the club he left, while `chegada` is told
    efeito: Efeito = Efeito()  # the day-to-day result, for the next season
    resultado: ResultadoRotina | None = None
    rotinas_vistas: list[str] = field(default_factory=list)
    marcas_novas: list[str] = field(default_factory=list)  # told in the next season
    saida_extra: float = 0.0  # a decision's push towards the door, for this winter's market
    lances: int = 0  # penalties he took

    def __post_init__(self) -> None:
        self.rng = random.Random(f"carreira:{self.entrada.semente}")
        self.posicao = self.entrada.craque.posicao
        base = geral(self.notas, self.posicao)
        # The draft is potential: how much of it comes true is drawn once per career.
        realizacao = self.rng.gauss(REALIZACAO, REALIZACAO_DESVIO)  # rating points, ±
        self.teto = max(35, min(99, round(base + realizacao)))
        self.parte, self.forma, self.nivel_atual = 1.0, 0, 0.0
        self.nota = max(30, self.teto - 25)
        self.aposenta_aos = self.rng.randint(33, 38) + (2 if self.notas["fisico"] >= 85 else 0)
        self.idade, self.ano, self.clube = IDADE_INICIAL, PRIMEIRO_ANO, self.inicio
        self.completa = self.entrada.modo == "completa"
        self.minijogos = self.completa and self.entrada.minijogos  # Rápida never asks a penalty
        self._pesos_estado: dict[str, int] = {}
        self._peso_nordeste = 1
        for clube in self.dados.clubes.values():
            if clube.estado:
                self._pesos_estado[clube.estado] = (
                    self._pesos_estado.get(clube.estado, 0) + clube.prestigio**2
                )
                if self.dados.regiao(clube) == "nordeste":
                    self._peso_nordeste += clube.prestigio**2

    # -- the loop --------------------------------------------------------------------------

    def rodar(self) -> Carreira:
        while True:
            if self.completa and self.idade > IDADE_INICIAL:
                pendente = self._dia_a_dia()
                if pendente:
                    return Carreira(temporadas=self.temporadas, pendente=pendente)
            jogada = self._temporada()
            if isinstance(jogada, Escolha):  # the cup final's penalty, before the season ends
                return Carreira(temporadas=self.temporadas, pendente=jogada)
            temporada, saida = jogada
            self.temporadas.append(temporada)
            if not self._encerra():
                pendente, decidiu = self._pergunta(temporada)
                if pendente:
                    return Carreira(temporadas=self.temporadas, pendente=pendente)
                if not (self.aposentou or decidiu):  # a market answer holds this winter
                    pendente = self._mercado(saida + self.saida_extra)
                    if pendente:
                        return Carreira(temporadas=self.temporadas, pendente=pendente)
            if self.aposentou or self._encerra():
                break
            self.idade, self.ano = self.idade + 1, self.ano + 1
            self._evoluir()
        if self.respondidas < len(self.entrada.escolhas):
            raise JogadaInvalida("a carreira já terminou: escolhas demais")
        return Carreira(temporadas=self.temporadas, final=self._final())

    def _encerra(self) -> bool:
        return (
            self.idade >= IDADE_MAXIMA
            or self.idade >= self.aposenta_aos
            or (self.idade >= 30 and self.nota < 40)
        )

    def _evoluir(self) -> None:
        if self.idade <= 26:
            # Growth needs games and form; a giant club too early holds the boy back.
            fator = 0.4 + 0.8 * min(1.0, self.parte) + self.forma / 15
            if self.idade <= 21 and self.nivel_atual - self.nota > GIGANTE_CEDO:
                fator *= 0.5
            ganho = round(self.rng.randint(2, 6) * max(0.0, fator))
            self.nota += min(max(0, self.teto - self.nota), ganho)
        elif self.idade <= 30:
            self.nota += self.rng.choice((-1, 0, 0, 1))
        else:
            self.nota -= self.rng.randint(1, 3) + (2 if self.idade >= 34 else 0)
        self.nota = max(20, min(99, self.nota))

    # -- one season ------------------------------------------------------------------------

    def _nivel(self, clube: Clube) -> float:
        return (self.dados.ligas[clube.liga].forca + clube.prestigio) / 2

    def _campos_classico(self) -> dict[str, str]:
        """{classico} and {rival} for the texts: the derby turns by year, without the dice."""
        todos = self.dados.classicos_de(self.clube)
        nome, rival = todos[self.ano % len(todos)] if todos else ("clássico", None)
        return {"classico": nome} | artigos("rival", rival)

    def _regionais(self, participacao: float) -> list[str]:
        """The state cup and, for a club of the Northeast, the Copa do Nordeste: a club's chance is
        its weight (prestige squared) among the clubs that play it."""
        estado = self.dados.estados.get(self.clube.estado or "")
        if estado is None:
            return []
        ganhos = []
        peso = self.clube.prestigio**2
        rivais = self._pesos_estado.get(estado.uf, peso)
        if self.rng.random() < min(0.75, 1.1 * peso / rivais) * participacao:
            ganhos.append(estado.campeonato)
        if estado.regiao == "nordeste":
            chance = min(0.3, 2.2 * peso / self._peso_nordeste) * participacao
            if self.rng.random() < chance:
                ganhos.append(COPA_DO_NORDESTE)
        return ganhos

    def _contexto(self) -> _Contexto:
        return _Contexto(
            idade=self.idade,
            nota=self.nota,
            forca=self.dados.ligas[self.clube.liga].forca,
            pais=self.dados.ligas[self.clube.liga].pais,
            posicao=self.posicao,
            historico=self.historico,
            no_clube_inicial=self.clube.id == self.inicio.id,
            regiao=self.dados.regiao(self.clube) or "",
            classico=bool(self.dados.classicos_de(self.clube)),
            chegou_de_fora=self.chegada is not None
            and self.veio_de is not None
            and self.dados.regiao(self.veio_de) != self.dados.regiao(self.clube),
        )

    def _sortear_eventos(self, momento: str, ctx: _Contexto) -> list[Evento]:
        cabem = [
            e
            for e in self.dados.eventos
            if e.momento == momento
            and e.peso > 0  # weight 0: only the engine picks it
            and not (e.unico and e.id in self.historico)
            and ctx.casa(e.condicao)
        ]
        if not cabem:
            return []
        if momento == "antes":
            if self.rng.random() >= 0.35:
                return []
            return [self.rng.choices(cabem, weights=[e.peso for e in cabem])[0]]
        primeiro = self.rng.choices(cabem, weights=[e.peso for e in cabem])[0]
        outros = [e for e in cabem if e is not primeiro and e.id != "temporada-comum"]
        if outros and self.rng.random() < 0.3:
            return [primeiro, self.rng.choices(outros, weights=[e.peso for e in outros])[0]]
        return [primeiro]

    def _temporada(self) -> tuple[Temporada, float] | Escolha:
        liga = self.dados.ligas[self.clube.liga]
        nivel = self._nivel(self.clube)
        antes = self._sortear_eventos("antes", self._contexto())
        efeito_jogos = min([e.efeito.jogos for e in antes] + [self.efeito.jogos])
        jogos = gols = assist = selecao = 0
        titulos: list[str] = []
        copa = False
        forma = 0
        lance: ResultadoLance | None = None
        evento_lance: Evento | None = None
        adversario: Clube | None = None
        if self.idade > IDADE_INICIAL:
            forma = max(-10, min(10, round(self.rng.gauss(0, FORMA))))
            em_campo = self.nota + forma  # the rating this season actually played at
            parte = max(0.03, min(1.0, 0.5 + (em_campo - nivel) / 25)) * efeito_jogos
            jogos = round(self.rng.randint(36, 52) * parte)
            ritmo = 0.7 + 0.6 * max(0.0, min(1.0, (em_campo - nivel + 20) / 40))
            taxa_gol = GOL[self.posicao] * (self.notas["finalizacao"] / 75) ** 1.6 * ritmo
            taxa_assist = ASSIST[self.posicao] * (self.notas["passe"] / 75) ** 1.4 * ritmo
            gols = sum(self.rng.random() < taxa_gol for _ in range(jogos))
            assist = sum(self.rng.random() < taxa_assist for _ in range(jogos))
            peso = 0.6 + 0.4 * min(1.0, parte * 1.5)
            chance = max(
                0.01, min(0.55, (self.clube.prestigio - 55) / 90 + (em_campo - nivel) / 250)
            )
            chance *= peso * min(1.0, jogos / 15)  # a title needs the player on the pitch
            if self.rng.random() < chance:
                titulos.append(liga.campeonato)
            pode = self.lances < MAX_LANCES and jogos >= JOGOS_PENALTI
            partida = None  # the match of this season's penalty, if any
            if liga.copa:
                sorte = self.rng.random()
                # A final that goes to his penalty is a title only when it goes in: the final
                # comes as much more often as he misses, so the cups won stay what they were.
                final = min(0.9, chance * 0.6 / chance_penalti(self.notas["finalizacao"]))
                if pode and sorte < final:
                    partida = "final"
                elif sorte < chance * 0.6:
                    titulos.append(liga.copa)
            if partida is None and pode and self.rng.random() < CHANCE_PENALTI[self.lances > 0]:
                classico = self.dados.classicos_de(self.clube)
                partida = (
                    "classico" if classico and self.rng.random() < CLASSICO_PENALTI else "jogo"
                )
            if partida:
                jogada = self._lance(partida, liga)
                if isinstance(jogada, Escolha):
                    return jogada
                lance, evento_lance, adversario = jogada
                if lance.resultado == "gol" and partida == "final":
                    titulos.append(liga.copa)
                elif lance.resultado == "gol":
                    gols += 1  # a league game or a derby: one more goal, no title
            if (
                liga.continental
                and self.clube.prestigio >= 68
                and self.rng.random() < chance * 0.35
            ):
                titulos.append(liga.continental)
            titulos += self._regionais(peso * min(1.0, jogos / 10))
            convocado = any(e.efeito.selecao for e in antes) or self.efeito.selecao
            if 18 <= self.idade <= 35 and self.nota >= 78 and parte > 0.4:
                convocado = convocado or self.rng.random() < min(0.95, (self.nota - 76) / 14)
            if convocado:
                selecao = self.rng.randint(3, 10)
                if self.ano % 4 == 2 and self.nota >= 82 and self.rng.random() < 0.7:
                    copa, selecao = True, selecao + self.rng.randint(2, 7)
                    if self.rng.random() < 0.12:
                        titulos.append("Copa do Mundo")
        ctx = self._contexto()
        ctx.gols, ctx.jogos, ctx.titulo, ctx.selecao = gols, jogos, bool(titulos), selecao > 0
        ctx.copa, ctx.mundial = copa, "Copa do Mundo" in titulos
        depois = self._sortear_eventos("depois", ctx)
        ruim = next((e for e in self.dados.eventos if e.id == TEMPORADA_RUIM), None)
        if forma <= FORMA_RUIM and ruim:  # a season to forget is told as one
            depois = [ruim, *[e for e in depois if e is not ruim][:1]]
        if lance:
            # The penalty's own headline tells this season: an event of the cold-blood mark
            # ("sangue frio", a goal at the death) would tell it twice, so it waits for another one.
            depois = [e for e in depois if MARCA_GOL not in e.condicao.requer]
            marca = MARCA_GOL if lance.resultado == "gol" else MARCA_ERRO
            # a final or a derby makes a mark; a league game only the headline
            if lance.tipo != "jogo" and marca in self.dados.marcas:  # a test world may lack it
                self._marcar(marca)
        if evento_lance:  # the penalty is the season's headline
            depois = [evento_lance, *depois]
        eventos = antes + depois
        if self.idade > IDADE_INICIAL:
            self.parte, self.forma, self.nivel_atual = jogos / 44, forma, nivel
        for e in eventos:
            self.historico.add(e.id)
            self.nota = max(20, min(99, self.nota + e.efeito.nota))
            self.teto = max(35, self.teto + e.efeito.teto)
            if e.efeito.titulo:
                titulos.append(e.efeito.titulo)
        principal = (depois or antes)[0] if eventos else None
        campos = (
            artigos("clube", self.clube)
            | self._campos_classico()
            | {
                "nome": self.entrada.craque.nome,
                "camisa": self.entrada.craque.camisa,
                "liga": liga.pais,
                "campeonato": liga.campeonato,
                "gols": gols,
                "jogos": jogos,
                "idade": self.idade,
            }
        )
        if lance:
            campos |= artigos("adversario", adversario) | {
                "minuto": lance.minuto,
                "competicao": lance.competicao,
            }
        manchete = ""
        if principal:
            novas = [m for m in principal.manchetes if m not in self.manchetes_usadas]
            # Its own stream: adding or editing headlines never reshuffles the careers.
            sorteio = random.Random(f"manchete:{self.entrada.semente}:{self.ano}")
            modelo = sorteio.choice(novas or principal.manchetes)
            self.manchetes_usadas.add(modelo)
            manchete = modelo.format_map(campos)
        if lance:
            lance.manchete = manchete
        temporada = Temporada(
            ano=self.ano,
            idade=self.idade,
            clube=self.clube.nome,
            clube_id=self.clube.id,
            pais=liga.pais,
            liga_forca=liga.forca,
            jogos=jogos,
            gols=gols,
            assistencias=assist,
            nota=self.nota,
            titulos=titulos,
            selecao=selecao,
            copa=copa,
            manchete=manchete,
            eventos=[e.id for e in eventos],
            forma=forma,
            chegada=self.chegada,
            rotina=self.resultado,
            marcas=self.marcas_novas,
            lance=lance,
        )
        saida = sum(e.efeito.saida for e in eventos) + self.efeito.saida + self._saida_das_marcas()
        self.chegada, self.veio_de, self.efeito, self.resultado = None, None, Efeito(), None
        self.marcas_novas, self.saida_extra = [], 0.0
        return temporada, saida

    def _lance(self, tipo: str, liga) -> tuple[ResultadoLance, Evento | None, Clube] | Escolha:
        """His penalty in a match of this kind: the fan kicks it (minijogos) or the engine rolls
        it by his finishing. Who, when and the roll are drawn either way, in this order, so the
        rest of the career never depends on how the penalty was taken; only on whether it went
        in."""
        finalizacao = self.notas["finalizacao"]
        copa = liga.copa if tipo == "final" else ""
        if tipo == "final":
            adversario, competicao, minuto = self._adversario(liga.copa), liga.copa, MINUTO_FINAL
        else:
            if tipo == "classico":
                competicao, adversario = self._rival()
            else:
                competicao, adversario = liga.campeonato, self._da_liga()
            minuto = _minuto(self.rng.randint(70, 94))
        sorte = self.rng.random()
        resposta = self._resposta(len(LANCES)) if self.minijogos else None
        if self.minijogos and resposta is None:
            return Escolha(
                id=f"penalti-{tipo}",
                tipo="lance",
                pergunta=self._frase_do_lance(tipo, competicao, minuto, adversario),
                opcoes=list(LANCES),
                info=[InfoOpcao(chance=finalizacao)] + [InfoOpcao() for _ in LANCES[1:]],
                destinos=["ficar"] * len(LANCES),
                clubes=[None] * len(LANCES),
                lance=Lance(
                    clube=self.clube.nome,
                    adversario=adversario.nome,
                    tipo=tipo,
                    minuto=minuto,
                    competicao=competicao,
                    copa=copa,
                ),
            )
        self.lances += 1
        if resposta is not None and resposta < len(LANCES) - 1:
            resultado = LANCES[resposta]
        else:
            p = chance_penalti(finalizacao)
            # a miss is told from the same roll: most are saved, some go wide, a few hit the post
            erro = (sorte - p) / (1 - p)
            resultado = (
                "gol"
                if sorte < p
                else "defesa"
                if erro < 0.55
                else "fora"
                if erro < 0.85
                else "trave"
            )
        fim = "gol" if resultado == "gol" else "erro"
        evento_id = f"penalti-{fim}" if tipo == "final" else f"penalti-{tipo}-{fim}"
        evento = next((e for e in self.dados.eventos if e.id == evento_id), None)
        lance = ResultadoLance(
            resultado=resultado,
            adversario=adversario.nome,
            manchete="",
            copa=copa,
            tipo=tipo,
            minuto=minuto,
            competicao=competicao,
        )
        return lance, evento, adversario

    def _frase_do_lance(self, tipo: str, competicao: str, minuto: str, adversario: Clube) -> str:
        """The question's line, by what is at stake."""
        o_clube, nome = artigos("c", self.clube)["o_c"], self.entrada.craque.nome
        contra = artigos("a", adversario)["o_a"]
        if tipo == "final":
            return f"Final da {competicao}, {minuto}: pênalti para {o_clube}. {nome} pega a bola."
        if tipo == "classico":
            return (
                f"{competicao}, {minuto}: pênalti para {o_clube} contra {contra}. "
                f"A torcida rival vaia, e {nome} pega a bola."
            )
        return f"{competicao}, {minuto}: pênalti para {o_clube} contra {contra}. {nome} vai bater."

    def _adversario(self, copa: str) -> Clube:
        """The other finalist, with no dice: one of the strongest clubs that play this cup, by
        year."""
        outros = sorted(
            (
                c
                for c in self.dados.clubes.values()
                if c.id != self.clube.id and self.dados.ligas[c.liga].copa == copa
            ),
            key=lambda c: (-c.prestigio, c.id),
        )[:6]
        return outros[self.ano % len(outros)] if outros else self.clube

    def _rival(self) -> tuple[str, Clube]:
        """The derby of this year, the one the texts tell ({classico}, {rival})."""
        todos = self.dados.classicos_de(self.clube)
        return todos[self.ano % len(todos)]

    def _da_liga(self) -> Clube:
        """A league opponent, drawn."""
        outros = sorted(
            (c for c in self.dados.clubes.values() if c.liga == self.clube.liga),
            key=lambda c: c.id,
        )
        outros = [c for c in outros if c.id != self.clube.id]
        return self.rng.choice(outros) if outros else self.clube

    # -- between seasons -------------------------------------------------------------------

    def _destino(self, tipo: str) -> Clube | None:
        """A club for a move of this kind, or None when the world has no fit."""
        atual, nota = self._nivel(self.clube), self.nota
        clubes = [c for c in self.dados.clubes.values() if c.id != self.clube.id]
        forca = {c.id: self.dados.ligas[c.liga].forca for c in clubes}
        if tipo == "casa":
            return self.inicio if self.clube.id != self.inicio.id else None
        filtros = {
            "europa": lambda c: forca[c.id] >= EUROPA and nota - 14 <= self._nivel(c) <= nota + 4,
            # a step up, not a leap: the ABC boy goes through Sport or Bahia before Europe
            "maior": lambda c: atual + 3 < self._nivel(c) <= min(nota + 4, atual + SALTO),
            "menor": lambda c: nota - 18 <= self._nivel(c) <= min(atual - 2, nota - 2),
            "emprestimo": lambda c: nota - 16 <= self._nivel(c) <= nota - 3,
            "lado": lambda c: abs(self._nivel(c) - atual) <= 6,
            "arabia": lambda c: c.liga == "ara" and self._nivel(c) <= nota + 8,
            "exotico": lambda c: (
                c.liga in EXOTICAS and c.liga != self.clube.liga and self._nivel(c) <= nota + 8
            ),
        }
        cabem = sorted((c for c in clubes if filtros[tipo](c)), key=lambda c: c.id)
        if tipo in ("menor", "lado", "emprestimo", "maior"):
            pais = self.dados.ligas[self.clube.liga].pais
            perto = [c for c in cabem if self.dados.ligas[c.liga].pais == pais]
            if perto and self.rng.random() < 0.65:  # most moves stay in the country
                cabem = perto
                regiao = self.dados.regiao(self.clube)
                vizinhos = [c for c in cabem if regiao and self.dados.regiao(c) == regiao]
                if vizinhos and self.rng.random() < 0.5:  # and in Brazil, half in the region
                    cabem = vizinhos
        return self.rng.choice(cabem) if cabem else None

    def _mudar(
        self, clube: Clube | None, emprestimo: bool = False, motivo: str | None = None
    ) -> None:
        if clube is None:
            return
        if motivo is None:
            de = artigos("c", self.clube)
            motivo = f"Emprestado {de['pelo_c']}" if emprestimo else f"Chegou {de['do_c']}"
        self.emprestado_de = (self.emprestado_de or self.clube) if emprestimo else None
        self.clube, self.chegada, self.veio_de = clube, motivo, self.clube

    def _mercado(self, saida: float) -> Escolha | None:
        """The winter's market. Rápida moves him by itself; Completa asks, save for the end of a
        loan and a release (both told in the next season's line)."""
        if self.emprestado_de:
            de = artigos("c", self.clube)["ao_c"]
            self._mudar(self.emprestado_de, motivo=f"Voltou do empréstimo {de}")
            return None
        diff = self.nota - self._nivel(self.clube)
        sorte = self.rng.random()
        if self.clube.id == self.inicio.id and self.idade <= 19:
            sorte = 1 - (1 - sorte) * 0.4  # the boy rarely leaves the club that raised him
        destino = None
        if self.idade >= 31 and sorte < 0.08 + saida / 2:
            destino = self._destino(self.rng.choice(("exotico", "casa", "menor")))
        elif diff >= 8 and sorte < 0.35 + saida:
            destino = self._destino("maior")
        elif diff <= -10 and sorte < (0.85 if diff <= -18 else 0.5) + saida:
            destino = self._destino("menor")
            if self.completa and diff <= -18 and destino:  # no room: released, no question
                saiu = artigos("c", self.clube)["pelo_c"]
                self._mudar(destino, motivo=f"Dispensado {saiu}")
                return None
        elif sorte < 0.08 + saida:
            destino = self._destino("lado")
        if destino is None:
            return None
        if not self.completa:
            self._mudar(destino)
            return None
        return self._proposta(destino)

    def _proposta(self, destino: Clube) -> Escolha | None:
        campos = artigos("clube", self.clube) | artigos("destino", destino)
        campos |= {"nome": self.entrada.craque.nome, "idade": self.idade}
        pais = self.dados.ligas[destino.liga].pais
        onde = "" if pais == self.dados.ligas[self.clube.liga].pais else f" ({pais})"
        escolha = Escolha(
            id="proposta",
            tipo="mercado",
            pergunta="{O_destino}{onde} faz uma proposta por {nome}.".format_map(
                campos | {"onde": onde}
            ),
            opcoes=[
                "Aceitar e ir {para_o_destino}".format_map(campos),
                "Ficar {no_clube}".format_map(campos),
            ],
            destinos=["maior", "ficar"],
            clubes=[destino.id, None],
        )
        resposta = self._resposta(len(escolha.opcoes))
        if resposta is None:
            return escolha
        if resposta == 0:
            self._mudar(destino)
        return None

    def _resposta(self, opcoes: int) -> int | None:
        """The fan's next answer, or None when the career waits for it."""
        if self.respondidas >= len(self.entrada.escolhas):
            return None
        resposta = self.entrada.escolhas[self.respondidas]
        self.respondidas += 1
        if not 0 <= resposta < opcoes:
            raise JogadaInvalida("essa opção não existe")
        return resposta

    def _dia_a_dia(self) -> Escolha | None:
        """Completa: the season's day-to-day situation; its result counts for this season."""
        ctx = self._contexto()
        if self.temporadas:
            ctx.gols, ctx.jogos = self.temporadas[-1].gols, self.temporadas[-1].jogos
        cabem = [r for r in self.dados.rotinas if ctx.casa(r.condicao)]
        novas = [r for r in cabem if r.id not in self.rotinas_vistas] or cabem
        if not novas:
            return None
        rotina = self.rng.choices(novas, weights=[r.peso for r in novas])[0]
        self.rotinas_vistas.append(rotina.id)
        campos = (
            artigos("clube", self.clube)
            | self._campos_classico()
            | {
                "nome": self.entrada.craque.nome,
                "idade": self.idade,
            }
        )
        texto = rotina.texto.format_map(campos)
        resposta = self._resposta(len(rotina.opcoes))
        if resposta is None:
            return Escolha(
                id=rotina.id,
                tipo="dia",
                pergunta=texto,
                opcoes=[o.texto.format_map(campos) for o in rotina.opcoes],
                info=[_info(o, self.notas, self.dados) for o in rotina.opcoes],
                destinos=["ficar"] * len(rotina.opcoes),
                clubes=[None] * len(rotina.opcoes),
            )
        opcao = rotina.opcoes[resposta]
        deu_certo, efeito = self._aplicar(opcao)
        self.resultado = ResultadoRotina(
            situacao=texto,
            escolha=opcao.texto.format_map(campos),
            deu_certo=deu_certo,
            efeito=descrever(efeito),
        )
        return None

    def _aplicar(self, opcao: OpcaoRotina) -> tuple[bool, Efeito]:
        """Roll the option's chance and apply what came of it: ratings, form and ceiling now; games,
        national team and the push to leave on the next season; the mark it gives."""
        chance = chance_de(opcao, self.notas)
        if isinstance(opcao, Opcao) and chance >= 100:
            deu_certo = True  # a sure decision rolls no dice: older careers keep their stream
        else:
            deu_certo = self.rng.random() * 100 < chance
        efeito = opcao.sucesso if deu_certo else opcao.fracasso
        self._efeito_agora(efeito)
        self.efeito = Efeito(
            nota=self.efeito.nota + efeito.nota,
            saida=self.efeito.saida + efeito.saida,
            jogos=min(self.efeito.jogos, efeito.jogos),
            selecao=self.efeito.selecao or efeito.selecao,
        )
        marca = opcao.marca if deu_certo else opcao.marca_fracasso
        if marca:
            self._marcar(marca)
        return deu_certo, efeito

    def _efeito_agora(self, efeito: Efeito) -> None:
        if efeito.posicao and efeito.posicao != self.posicao:
            # a new position: the same ratings weigh differently from now on
            delta = geral(self.notas, efeito.posicao) - geral(self.notas, self.posicao)
            self.posicao = efeito.posicao
            self.nota = max(20, min(99, self.nota + delta))
            self.teto = max(35, min(99, self.teto + delta))
        antes = geral(self.notas, self.posicao)
        for atributo, delta in efeito.atributos.items():
            self.notas[atributo] = max(1, min(99, self.notas[atributo] + delta))
        ganho = geral(self.notas, self.posicao) - antes + efeito.nota
        self.nota = max(20, min(99, self.nota + ganho))
        self.teto = max(
            35, min(99, self.teto + geral(self.notas, self.posicao) - antes + efeito.teto)
        )

    def _marcar(self, marca_id: str) -> None:
        """Win a mark: once per career, its effect applied then, told in the next season."""
        if marca_id in self.historico:
            return
        self.historico.add(marca_id)
        self.marcas_ganhas.append(marca_id)
        self.onde_marcou[marca_id] = self.clube.id
        marca = self.dados.marcas[marca_id]
        self._efeito_agora(marca.efeito)
        self.saida_extra += marca.efeito.saida  # this winter too; `_saida_das_marcas` from then on
        self.marcas_novas.append(marca.texto.format_map({"nome": self.entrada.craque.nome}))
        if any(
            d.continua and marca_id in d.condicao.requer and d.id not in self.perguntadas
            for d in self.dados.decisoes
        ):
            # its next step comes next winter, at this club, after any arc already open
            self.arcos.append((marca_id, ARCO_TENTATIVAS, self.clube.id))

    def _saida_das_marcas(self) -> float:
        """A mark's push to leave (a vow to the club, a fan base fed up) counts every winter while
        he is at the club where he won it."""
        return sum(
            self.dados.marcas[m].efeito.saida
            for m, clube in self.onde_marcou.items()
            if clube == self.clube.id
        )

    def _pergunta(self, temporada: Temporada) -> tuple[Escolha | None, bool]:
        """Maybe a question this season: (pending question, the fan settled this winter)."""
        ctx = self._contexto()
        ctx.gols, ctx.jogos = temporada.gols, temporada.jogos
        ctx.titulo, ctx.selecao = bool(temporada.titulos), temporada.selecao > 0
        ctx.copa, ctx.mundial = temporada.copa, "Copa do Mundo" in temporada.titulos
        decisao, destinos = self._passo_do_arco(ctx)
        if decisao is not None:
            self.passos += 1  # an arc's step is always asked and never counts in the cap
        else:
            sorteadas = len(self.perguntadas) - self.passos
            if sorteadas >= MAX_ESCOLHAS[self.entrada.modo] or self.rng.random() >= CHANCE_ESCOLHA:
                return None, False
            cabem = [
                d
                for d in self.dados.decisoes
                if not d.continua and d.id not in self.perguntadas and ctx.casa(d.condicao)
            ]
            if not cabem:
                return None, False
            decisao = self.rng.choices(cabem, weights=[d.peso for d in cabem])[0]
            destinos = self._destinos(decisao)
            if any(clube is None for clube in destinos.values()):
                return None, False
        self.perguntadas.append(decisao.id)
        resposta = self._resposta(len(decisao.opcoes))
        if resposta is None:
            return self._escolha(decisao, destinos), False
        self.historico.add(decisao.id)  # an answered question can open others (`requer`)
        opcao = decisao.opcoes[resposta]
        saida = self.efeito.saida
        self._aplicar(opcao)
        # the push to leave of a winter's decision counts in this winter's market
        self.saida_extra += self.efeito.saida - saida
        self.efeito = replace(self.efeito, saida=saida)
        destino = opcao.destino
        if destino == "aposentar":
            self.aposentou = True
        elif destino == "mais_um":
            self.aposenta_aos = min(IDADE_MAXIMA, max(self.aposenta_aos, self.idade + 2))
        elif destino in destinos:
            self._mudar(destinos[destino], emprestimo=destino == "emprestimo")
        # A market question holds the winter whatever the answer; one off the market lets it run.
        return None, bool(destinos) or self.aposentou

    def _destinos(self, decisao: Decisao) -> dict[str, Clube | None]:
        return {
            o.destino: self._destino(o.destino) for o in decisao.opcoes if o.destino in COM_CLUBE
        }

    def _passo_do_arco(self, ctx: _Contexto) -> tuple[Decisao | None, dict[str, Clube | None]]:
        """The oldest open arc's next step, when its condition fits this winter; else that arc
        has one try less. Arcs opened meanwhile wait their turn."""
        while self.arcos:
            marca, restantes, clube = self.arcos[0]
            if clube != self.clube.id:  # a new club: the story of the old one is over
                self.arcos.pop(0)
                continue
            for decisao in self.dados.decisoes:
                if (
                    decisao.continua
                    and decisao.id not in self.perguntadas
                    and marca in decisao.condicao.requer
                    and ctx.casa(decisao.condicao)
                ):
                    destinos = self._destinos(decisao)
                    if all(destinos.values()):
                        self.arcos.pop(0)
                        return decisao, destinos
            if restantes > 1:
                self.arcos[0] = (marca, restantes - 1, clube)
            else:
                self.arcos.pop(0)
            break
        return None, {}

    def _escolha(self, decisao: Decisao, destinos: dict[str, Clube | None]) -> Escolha:
        alvos = [c for c in destinos.values() if c]
        clubes = [destinos.get(o.destino) for o in decisao.opcoes]
        pais = lambda c: self.dados.ligas[c.liga].pais if c else ""  # noqa: E731
        campos = artigos("clube", self.clube) | {
            "nome": self.entrada.craque.nome,
            "idade": self.idade,
        }
        # {destino} in the question is the first club on offer, {outro} the second; in an option,
        # {destino} is that option's own club.
        primeiro = alvos[0] if alvos else None
        segundo = alvos[1] if len(alvos) > 1 else None
        geral_ = campos | artigos("destino", primeiro) | artigos("outro", segundo)
        geral_ |= {"pais_destino": pais(primeiro), "pais_outro": pais(segundo)}

        def opcao(texto: str, clube: Clube | None) -> str:
            proprio = clube or primeiro
            return texto.format_map(
                campos | artigos("destino", proprio) | {"pais_destino": pais(proprio)}
            )

        return Escolha(
            id=decisao.id,
            pergunta=decisao.pergunta.format_map(geral_),
            opcoes=[opcao(o.texto, c) for o, c in zip(decisao.opcoes, clubes, strict=True)],
            info=(
                [_info(o, self.notas, self.dados) for o in decisao.opcoes]
                if any(_com_risco(o) for o in decisao.opcoes)
                else []
            ),
            destinos=[o.destino for o in decisao.opcoes],
            clubes=[c.id if c else None for c in clubes],
        )

    # -- the end ---------------------------------------------------------------------------

    def _final(self) -> Final:
        titulos: dict[str, int] = {}
        for t in self.temporadas:
            for nome in t.titulos:
                titulos[nome] = titulos.get(nome, 0) + 1
        rotulo, descricao = final.rotular(self.dados, self.temporadas, self.marcas_ganhas)
        return Final(
            nota=final.nota(self.temporadas),
            rotulo=rotulo,
            descricao=descricao,
            titulos=titulos,
            clubes=list(dict.fromkeys(t.clube for t in self.temporadas)),
            jogos=sum(t.jogos for t in self.temporadas),
            gols=sum(t.gols for t in self.temporadas),
            selecao=sum(t.selecao for t in self.temporadas),
            copa=any(t.copa for t in self.temporadas),
            parecido=final.parecido(self.dados, final.base_real(), self.temporadas, self.posicao),
            perguntas=list(self.perguntadas),
            posicao=self.posicao,
            marcas=[self.dados.marcas[m].nome for m in self.marcas_ganhas],
            vereditos=final.vereditos(self.dados, self.temporadas),
        )


Temporada.model_rebuild()
