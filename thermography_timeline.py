"""Regras puras da timeline comparativa de termografia."""

from __future__ import annotations

from datetime import date
from typing import Literal


TimelineKey = tuple[date, int]
TimelineRole = Literal["t0", "ti"]


def valid_timeline_selection(
    selected: TimelineKey,
    other: TimelineKey | None,
    role: TimelineRole,
) -> bool:
    """Garante a ordem temporal T0 <= Ti, usando a sequência como desempate."""
    if other is None:
        return True
    if role == "t0":
        return selected <= other
    if role == "ti":
        return selected >= other
    raise ValueError("O papel da coleta deve ser 't0' ou 'ti'.")
