"""PostgreSQL local por padrão, com origem remota explícita e protegida."""

from __future__ import annotations

from contextlib import contextmanager
from ipaddress import ip_address
from typing import Iterator

import psycopg2
from psycopg2.extensions import connection

from backend.mac_api.core.settings import setting


def cloud_database_config() -> dict[str, object]:
    """Origem de exportações; nunca é um fallback da conexão local."""
    variables = {
        "host": "SUPABASE_DB_HOST",
        "port": "SUPABASE_DB_PORT",
        "dbname": "SUPABASE_DB_NAME",
        "user": "SUPABASE_DB_USER",
        "password": "SUPABASE_DB_PASSWORD",
    }
    missing = [
        secret_name
        for secret_name in variables.values()
        if not setting(secret_name)
    ]
    if missing:
        raise RuntimeError(
            "Configuração do banco incompleta: "
            + ", ".join(missing)
        )

    config = {key: setting(secret_name) for key, secret_name in variables.items()}
    config["sslmode"] = setting("SUPABASE_DB_SSLMODE", "require")
    config["connect_timeout"] = 15
    config["application_name"] = "mac_cloud_backup_read"
    config["options"] = "-c default_transaction_read_only=on"
    return config


def validate_database_target() -> None:
    """Bloqueia destinos remotos em desenvolvimento, sem abrir conexões."""
    target = setting('MAC_DB_TARGET', 'local')
    environment = setting('MAC_ENVIRONMENT', 'development')
    if environment not in ('development', 'test', 'production'):
        raise RuntimeError('MAC_ENVIRONMENT inválido: use development, test ou production.')
    if target not in ('local', 'supabase'):
        raise RuntimeError('MAC_DB_TARGET inválido: use local ou supabase.')
    if target == 'supabase':
        if environment != 'production':
            raise RuntimeError('Acesso remoto bloqueado em desenvolvimento/testes. Use o banco local.')
        return
    host = setting('MAC_LOCAL_DB_HOST', '127.0.0.1')
    try:
        loopback = ip_address(str(host)).is_loopback
    except ValueError:
        loopback = False
    if not loopback and host not in ('localhost', 'db-dev', 'postgres-test'):
        raise RuntimeError('MAC_LOCAL_DB_HOST deve ser loopback ou o serviço Docker local autorizado.')
    if setting('MAC_LOCAL_DB_NAME', 'mac_dev') not in ('mac_dev', 'mac_test'):
        raise RuntimeError('O banco local deve ser mac_dev ou mac_test; destino recusado.')


def _application_config(*, readonly: bool) -> dict[str, object]:
    validate_database_target()
    if setting('MAC_DB_TARGET', 'local') == 'supabase':
        config = cloud_database_config()
        config.pop('options', None)
    else:
        config = {
            'host': setting('MAC_LOCAL_DB_HOST', '127.0.0.1'),
            'port': setting('MAC_LOCAL_DB_PORT', '55433'),
            'dbname': setting('MAC_LOCAL_DB_NAME', 'mac_dev'),
            'user': setting('MAC_LOCAL_DB_USER', 'mac_dev'),
            'password': setting('MAC_LOCAL_DB_PASSWORD', 'mac_dev_local'),
            'sslmode': 'disable',
            'connect_timeout': 15,
        }
    config['application_name'] = 'mac_performance_read' if readonly else 'mac_performance_write'
    if readonly:
        config['options'] = '-c default_transaction_read_only=on'
    return config


def database_config() -> dict[str, object]:
    return _application_config(readonly=True)


def database_write_config() -> dict[str, object]:
    return _application_config(readonly=False)


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


@contextmanager
def database_write_connection() -> Iterator[connection]:
    """Abre uma transação de escrita e aplica commit ou rollback ao final."""
    db_connection = psycopg2.connect(**database_write_config())
    db_connection.set_session(readonly=False, autocommit=False)
    try:
        with db_connection.cursor() as cursor:
            cursor.execute("SHOW transaction_read_only")
            transaction_mode = cursor.fetchone()[0]
        if transaction_mode != "off":
            raise RuntimeError("O banco não confirmou o modo de escrita.")
        yield db_connection
        db_connection.commit()
    except Exception:
        db_connection.rollback()
        raise
    finally:
        db_connection.close()
