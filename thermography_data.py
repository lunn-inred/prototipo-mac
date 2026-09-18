"""Consultas somente leitura para a página de termografia."""

from __future__ import annotations

import streamlit as st

from service_gateway import load_athletes, load_thermography_history as gateway_load_history


@st.cache_data(ttl=300, show_spinner="Carregando jogadores...")
def load_thermography_athletes() -> list[dict[str, object]]:
    """Carrega jogadores de public.atleta pela conexão protegida como read-only."""
    return load_athletes()


def athlete_label(athlete: dict[str, object]) -> str:
    """Define o nome apresentado nos seletores sem perder o ID do cadastro."""
    nickname = str(athlete.get("apelido") or "").strip()
    name = str(athlete.get("nome") or "").strip()
    return nickname or name or f"Jogador {athlete['id_atleta']}"


@st.cache_data(ttl=60, show_spinner="Carregando histórico térmico...")
def load_thermography_history(
    athlete_id: int | None = None,
) -> list[dict[str, object]]:
    """Carrega o histórico exclusivamente pela view pública de termografia."""
    return gateway_load_history(athlete_id)
