"""Helpers the Central templates use: band colours and short pt-BR dates."""

from datetime import datetime
from zoneinfo import ZoneInfo

BRASILIA = ZoneInfo("America/Sao_Paulo")
# The Geral's palette by the band's place in ge's list; relegation is always red. ge's own blues
# and cyans stay out (docs/features/central.md).
PALETTE = ("#1F7A3D", "#7DBE8A", "#E3B23C", "#8C8778", "#5E7FA8")
RELEGATION = "#B83A2E"
WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def band_colors(bands: list[str]) -> dict[str, str]:
    colors, others = {}, iter(PALETTE)
    for band in bands:
        colors[band] = RELEGATION if band.startswith("Rebaixados") else next(others, PALETTE[-1])
    return colors


def short_day(moment: datetime) -> str:
    """'sáb 22/11'"""
    local = moment.astimezone(BRASILIA)
    return f"{WEEKDAYS[local.weekday()]} {local:%d/%m}"


def short_time(moment: datetime) -> str:
    """'16h' or '21h30'"""
    local = moment.astimezone(BRASILIA)
    return f"{local:%H}h" + (f"{local:%M}" if local.minute else "")
