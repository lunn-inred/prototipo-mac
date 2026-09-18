"""Persistência transacional das coletas de termografia."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from math import isfinite
from typing import Callable, ContextManager, Mapping

from psycopg2.extensions import connection

from database import database_write_connection


THERMOGRAPHY_GROUP = "termografia"
IMAGE_MEASURES = frozenset({
    "MASSA",
    "EVA_DOR",
    "OBSERVACOES",
    "PERNA_DIREITA_FRENTE",
    "PERNA_DIREITA_VERSO",
    "PERNA_ESQUERDA_FRENTE",
    "PERNA_ESQUERDA_VERSO",
    "SOMA_FRENTE",
    "SOMA_VERSO",
})
LEGACY_MEASURES = frozenset({
    "MASSA",
    "EVA_DOR",
    "OBSERVACOES",
    "SOMA_FRENTE",
    "SOMA_VERSO",
})

ConnectionFactory = Callable[[], ContextManager[connection]]


class DuplicateThermographyError(ValueError):
    """Indica que o atleta já possui termografia na data informada."""


@dataclass(frozen=True)
class LegacyThermographyRecord:
    athlete_id: int
    collected_at: date | datetime
    mass: float
    pain_score: int
    front: int
    back: int
    observations: str | None = None


def _timestamp(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    raise ValueError("Data da coleta é obrigatória.")


def _positive_number(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} deve ser um número válido.") from error
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{label} deve ser maior que zero.")
    return number


def _pain_score(value: object) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("EVA Dor deve ser um número entre 0 e 10.") from error
    if not isfinite(number) or not number.is_integer() or not 0 <= number <= 10:
        raise ValueError("EVA Dor deve ser um número inteiro entre 0 e 10.")
    return int(number)


def _pixel_count(value: object, label: str) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} deve ser uma contagem válida.") from error
    if not isfinite(number) or not number.is_integer() or number < 0:
        raise ValueError(f"{label} deve ser um número inteiro não negativo.")
    return int(number)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def image_measurements(
    *,
    mass: object,
    pain_score: object,
    front_right: object,
    front_left: object,
    back_right: object,
    back_left: object,
    observations: object = None,
) -> dict[str, float | int | str]:
    """Valida e organiza todas as medidas extraídas das duas imagens."""
    right_front = _pixel_count(front_right, "Perna direita — frente")
    left_front = _pixel_count(front_left, "Perna esquerda — frente")
    right_back = _pixel_count(back_right, "Perna direita — verso")
    left_back = _pixel_count(back_left, "Perna esquerda — verso")
    result: dict[str, float | int | str] = {
        "MASSA": _positive_number(mass, "Massa"),
        "EVA_DOR": _pain_score(pain_score),
        "PERNA_DIREITA_FRENTE": right_front,
        "PERNA_DIREITA_VERSO": right_back,
        "PERNA_ESQUERDA_FRENTE": left_front,
        "PERNA_ESQUERDA_VERSO": left_back,
        "SOMA_FRENTE": right_front + left_front,
        "SOMA_VERSO": right_back + left_back,
    }
    text = _optional_text(observations)
    if text is not None:
        result["OBSERVACOES"] = text
    return result


def legacy_measurements(record: LegacyThermographyRecord) -> dict[str, float | int | str]:
    """Valida uma linha legada, que possui somente as somas por vista."""
    result: dict[str, float | int | str] = {
        "MASSA": _positive_number(record.mass, "Massa"),
        "EVA_DOR": _pain_score(record.pain_score),
        "SOMA_FRENTE": _pixel_count(record.front, "Frente"),
        "SOMA_VERSO": _pixel_count(record.back, "Verso"),
    }
    text = _optional_text(record.observations)
    if text is not None:
        result["OBSERVACOES"] = text
    return result


def _insert_collection(
    cursor: object,
    *,
    athlete_id: int,
    collected_at: date | datetime,
    measurements: Mapping[str, float | int | str],
    required_measures: frozenset[str],
) -> int:
    athlete_id = int(athlete_id)
    timestamp = _timestamp(collected_at)

    # O bloqueio da linha do atleta serializa coletas simultâneas desse atleta.
    cursor.execute(
        "SELECT id_atleta FROM public.atleta WHERE id_atleta = %s FOR UPDATE",
        (athlete_id,),
    )
    if cursor.fetchone() is None:
        raise ValueError("Jogador não encontrado no banco.")

    cursor.execute(
        """
        SELECT m.id_medida, UPPER(TRIM(m.nome))
        FROM public.medida AS m
        JOIN public.grupo_medida AS gm
          ON gm.id_grupo_medida = m.id_grupo_medida
        WHERE LOWER(TRIM(gm.nome)) = %s
        """,
        (THERMOGRAPHY_GROUP,),
    )
    measure_ids = {str(name): int(measure_id) for measure_id, name in cursor.fetchall()}
    missing = sorted(required_measures - set(measure_ids))
    if missing:
        raise RuntimeError(
            "Medidas de termografia ausentes no banco: " + ", ".join(missing)
        )

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM public.medida_valor AS mv
        JOIN public.medida AS m ON m.id_medida = mv.id_medida
        JOIN public.grupo_medida AS gm
          ON gm.id_grupo_medida = m.id_grupo_medida
        WHERE mv.id_atleta = %s
          AND mv.data = %s
          AND LOWER(TRIM(gm.nome)) = %s
        """,
        (athlete_id, timestamp, THERMOGRAPHY_GROUP),
    )
    if int(cursor.fetchone()[0]) > 0:
        raise DuplicateThermographyError(
            "Já existe uma coleta de termografia para esse jogador nessa data."
        )

    values = []
    for name, value in measurements.items():
        if name not in measure_ids:
            raise RuntimeError(f"Medida de termografia não configurada: {name}.")
        numeric_value = None if isinstance(value, str) else float(value)
        text_value = value if isinstance(value, str) else None
        values.append(
            (athlete_id, None, measure_ids[name], numeric_value, text_value, timestamp)
        )
    cursor.executemany(
        """
        INSERT INTO public.medida_valor
            (id_atleta, id_partida, id_medida, valor, valor_texto, data)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        values,
    )
    return len(values)


def save_image_thermography(
    *,
    athlete_id: int,
    collected_at: date | datetime,
    mass: object,
    pain_score: object,
    front_right: object,
    front_left: object,
    back_right: object,
    back_left: object,
    observations: object = None,
    connection_factory: ConnectionFactory = database_write_connection,
) -> int:
    """Grava atomicamente uma coleta obtida das imagens de frente e verso."""
    measurements = image_measurements(
        mass=mass,
        pain_score=pain_score,
        front_right=front_right,
        front_left=front_left,
        back_right=back_right,
        back_left=back_left,
        observations=observations,
    )
    with connection_factory() as database, database.cursor() as cursor:
        return _insert_collection(
            cursor,
            athlete_id=athlete_id,
            collected_at=collected_at,
            measurements=measurements,
            required_measures=IMAGE_MEASURES,
        )


def save_legacy_thermography(
    records: list[LegacyThermographyRecord],
    *,
    connection_factory: ConnectionFactory = database_write_connection,
) -> int:
    """Grava um lote legado em uma única transação, sem dados parciais."""
    if not records:
        raise ValueError("Não há registros legados para salvar.")
    prepared = [(record, legacy_measurements(record)) for record in records]
    keys = [(int(record.athlete_id), _timestamp(record.collected_at)) for record in records]
    if len(keys) != len(set(keys)):
        raise ValueError("O lote contém o mesmo jogador e data mais de uma vez.")

    inserted = 0
    with connection_factory() as database, database.cursor() as cursor:
        for record, measurements in prepared:
            inserted += _insert_collection(
                cursor,
                athlete_id=record.athlete_id,
                collected_at=record.collected_at,
                measurements=measurements,
                required_measures=LEGACY_MEASURES,
            )
    return inserted
