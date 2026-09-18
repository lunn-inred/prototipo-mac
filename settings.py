"""Configuração compartilhada por API e Streamlit, sem acoplamento de framework."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 usa o fallback.
    import tomli as tomllib


@lru_cache(maxsize=1)
def _local_secrets() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    if not path.exists():
        return {}
    with path.open("rb") as source:
        return dict(tomllib.load(source))


def setting(name: str, default: str | None = None) -> str | None:
    """Lê primeiro o ambiente e usa secrets.toml apenas no desenvolvimento local."""
    value = os.getenv(name)
    if value is None:
        value = _local_secrets().get(name, default)
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
