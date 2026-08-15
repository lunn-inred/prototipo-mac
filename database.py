"""Configuração compartilhada para acesso ao PostgreSQL do Supabase."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg2
from dotenv import load_dotenv
from psycopg2.extensions import connection


load_dotenv()

DB_SCHEMA = os.getenv("SUPABASE_DB_SCHEMA", "public")


def database_config() -> dict[str, object]:
    """Carrega e valida as credenciais locais sem expor seus valores."""
    variables = {
        "host": "SUPABASE_DB_HOST",
        "port": "SUPABASE_DB_PORT",
        "dbname": "SUPABASE_DB_NAME",
        "user": "SUPABASE_DB_USER",
        "password": "SUPABASE_DB_PASSWORD",
    }
    missing = [env_name for env_name in variables.values() if not os.getenv(env_name)]
    if missing:
        raise RuntimeError(
            "Configuração do banco incompleta no arquivo .env: "
            + ", ".join(missing)
        )

    config = {key: os.environ[env_name] for key, env_name in variables.items()}
    config["sslmode"] = os.getenv("SUPABASE_DB_SSLMODE", "require")
    config["connect_timeout"] = 15
    config["application_name"] = "mac_streamlit_prototype"
    config["options"] = "-c default_transaction_read_only=on"
    return config


@contextmanager
def database_connection() -> Iterator[connection]:
    """Abre exclusivamente uma conexão read-only e a fecha ao final."""
    db_connection = psycopg2.connect(**database_config())
    db_connection.set_session(readonly=True, autocommit=False)
    try:
        with db_connection.cursor() as cursor:
            cursor.execute("SHOW transaction_read_only")
            transaction_mode = cursor.fetchone()[0]
        if transaction_mode != "on":
            raise RuntimeError("O banco não confirmou o modo somente leitura.")
        yield db_connection
    finally:
        db_connection.close()
