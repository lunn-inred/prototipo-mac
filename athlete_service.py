"""Operações transacionais do CRUD de atletas."""

from __future__ import annotations

from datetime import date
from typing import Callable, ContextManager, Protocol

from psycopg2.extensions import connection

from database import database_write_connection


class AthleteInUseError(ValueError):
    """Indica que o atleta possui medições e não pode ser excluído."""


ConnectionFactory = Callable[[], ContextManager[connection]]


def _required_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("Nome é obrigatório.")
    return name


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def create_athlete(
    *,
    name: str,
    nickname: str | None = None,
    position: str | None = None,
    group: str | None = None,
    birth_date: date | None = None,
    connection_factory: ConnectionFactory = database_write_connection,
) -> int:
    """Cria um atleta e retorna seu ID."""
    query = """
        INSERT INTO public.atleta
            (nome, apelido, posicao, grupo, data_nascimento)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id_atleta
    """
    values = (
        _required_name(name),
        _optional_text(nickname),
        _optional_text(position),
        _optional_text(group),
        birth_date,
    )
    with connection_factory() as database, database.cursor() as cursor:
        cursor.execute(query, values)
        return int(cursor.fetchone()[0])


def update_athlete(
    athlete_id: int,
    *,
    name: str,
    nickname: str | None = None,
    position: str | None = None,
    group: str | None = None,
    birth_date: date | None = None,
    connection_factory: ConnectionFactory = database_write_connection,
) -> None:
    """Atualiza os campos editáveis sem tocar em nome_alternativo."""
    query = """
        UPDATE public.atleta
        SET nome = %s,
            apelido = %s,
            posicao = %s,
            grupo = %s,
            data_nascimento = %s
        WHERE id_atleta = %s
        RETURNING id_atleta
    """
    values = (
        _required_name(name),
        _optional_text(nickname),
        _optional_text(position),
        _optional_text(group),
        birth_date,
        int(athlete_id),
    )
    with connection_factory() as database, database.cursor() as cursor:
        cursor.execute(query, values)
        if cursor.fetchone() is None:
            raise ValueError("Atleta não encontrado.")


def delete_athlete(
    athlete_id: int,
    *,
    connection_factory: ConnectionFactory = database_write_connection,
) -> None:
    """Exclui somente atletas sem medições relacionadas."""
    with connection_factory() as database, database.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM public.medida_valor WHERE id_atleta = %s",
            (int(athlete_id),),
        )
        if int(cursor.fetchone()[0]) > 0:
            raise AthleteInUseError(
                "O atleta possui medições e não pode ser excluído."
            )
        cursor.execute(
            "DELETE FROM public.atleta WHERE id_atleta = %s RETURNING id_atleta",
            (int(athlete_id),),
        )
        if cursor.fetchone() is None:
            raise ValueError("Atleta não encontrado.")
