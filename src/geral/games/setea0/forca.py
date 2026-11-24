"""A player's strength (1-99): fame relative to the club, years there and the Seleção.

The constants are a first calibration; the dev may retune them (`docs/features/setea0.md`).
"""

from bisect import bisect_left

ANOS_DA_VELHA = 4  # all-time opponents have no years at the club


def percentis(famas: list[int]) -> list[float]:
    """Each fame's percentile inside its own club (0-1); ties share the lowest rank."""
    if len(famas) < 2:
        return [0.5] * len(famas)
    ordenadas = sorted(famas)
    return [bisect_left(ordenadas, fama) / (len(famas) - 1) for fama in famas]


def forca(percentil: float, anos: int | None, selecao: bool) -> int:
    anos = ANOS_DA_VELHA if anos is None else anos
    valor = 35 + 40 * percentil + 2.5 * min(anos, 8) + (6 if selecao else 0)
    return max(1, min(99, round(valor)))
