"""Consultas somente leitura para a página de termografia."""

from __future__ import annotations

import streamlit as st

from database import database_connection


@st.cache_data(ttl=300, show_spinner="Carregando jogadores...")
def load_thermography_athletes() -> list[dict[str, object]]:
    """Carrega jogadores de public.atleta pela conexão protegida como read-only."""
    query = """
        SELECT
            id_atleta,
            nome,
            apelido,
            posicao,
            grupo
        FROM public.atleta
        ORDER BY
            COALESCE(NULLIF(TRIM(apelido), ''), NULLIF(TRIM(nome), '')),
            id_atleta
    """
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [description.name for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def athlete_label(athlete: dict[str, object]) -> str:
    """Define o nome apresentado nos seletores sem perder o ID do cadastro."""
    nickname = str(athlete.get("apelido") or "").strip()
    name = str(athlete.get("nome") or "").strip()
    return nickname or name or f"Jogador {athlete['id_atleta']}"
