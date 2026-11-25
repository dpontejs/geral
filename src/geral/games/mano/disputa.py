"""Score of a Mano a Mano shootout: 5 kicks each, alternating, then sudden death."""

from dataclasses import dataclass, field

SERIE = 5


@dataclass
class Disputa:
    cobrancas: list[tuple[int, bool]] = field(default_factory=list)
    perdedor_wo: int | None = None

    def batedor(self) -> int:
        """Who kicks now: player 0 starts, then they alternate."""
        return len(self.cobrancas) % 2

    def placar(self) -> tuple[int, int]:
        gols = [0, 0]
        for jogador, gol in self.cobrancas:
            gols[jogador] += gol
        return gols[0], gols[1]

    def _batidas(self, jogador: int) -> int:
        return sum(1 for quem, _ in self.cobrancas if quem == jogador)

    def vencedor(self) -> int | None:
        if self.perdedor_wo is not None:
            return 1 - self.perdedor_wo
        gols = self.placar()
        if len(self.cobrancas) < 2 * SERIE:
            for jogador in (0, 1):
                restam = SERIE - self._batidas(jogador)
                if gols[jogador] + restam < gols[1 - jogador]:
                    return 1 - jogador
            return None
        if len(self.cobrancas) % 2 or gols[0] == gols[1]:
            return None
        return 0 if gols[0] > gols[1] else 1

    def acabou(self) -> bool:
        return self.vencedor() is not None

    def registrar(self, gol: bool) -> None:
        if self.acabou():
            raise ValueError("the shootout is over")
        self.cobrancas.append((self.batedor(), gol))

    def wo(self, perdedor: int) -> None:
        """End the shootout now: ``perdedor`` left, the other wins with the score so far."""
        if perdedor not in (0, 1):
            raise ValueError("perdedor must be 0 or 1")
        if self.acabou():
            raise ValueError("the shootout is over")
        self.perdedor_wo = perdedor
