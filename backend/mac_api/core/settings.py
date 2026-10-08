"""Configuração compartilhada por API e Streamlit, sem acoplamento de framework."""

from __future__ import annotations

import os
from dotenv import load_dotenv
from pathlib import Path
from typing import Any

load_dotenv(Path(__file__).resolve().parents[3] / '.env')

def setting(name: str, default: str | None = None) -> str | None:
    """Lê somente o ambiente, inicializado a partir do .env da raiz."""
    value = os.getenv(name)
    if value is None:
        value = default
    if value is None:
        return None
    return str(value)


def api_base_url() -> str | None:
    value = setting("MAC_API_BASE_URL")
    return value.rstrip("/") if value else None


def api_key() -> str | None:
    return setting("MAC_API_KEY")


def cors_origins() -> list[str]:
    raw = setting("MAC_API_CORS_ORIGINS", "") or ""
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
