"""Estatísticas compartilhadas pelos gráficos temporais."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from statistics import fmean, pstdev


def daily_statistics(
    records: list[dict[str, object]],
    value_getter: Callable[[dict[str, object]], float | None],
) -> tuple[list[object], list[float], list[float]]:
    """Retorna datas, médias e desvios populacionais calculados por data."""
    grouped: dict[object, list[float]] = defaultdict(list)
    for record in records:
        value = value_getter(record)
        if value is not None:
            grouped[record["data_coleta"]].append(value)

    dates = sorted(grouped)
    means = [fmean(grouped[collection_date]) for collection_date in dates]
    deviations = [pstdev(grouped[collection_date]) for collection_date in dates]
    return dates, means, deviations
