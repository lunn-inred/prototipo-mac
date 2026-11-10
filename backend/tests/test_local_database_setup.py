"""Proteções da cópia local; nenhum teste acessa produção."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from backend.mac_api.core import database
from backend.tools import local_database as tool


class LocalDatabaseSafetyTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_local_is_default_even_with_cloud_credentials(self):
        with patch.dict(os.environ, SUPABASE_DB_HOST='remote.example', SUPABASE_DB_PASSWORD='secret'):
            read = database.database_config()
            write = database.database_write_config()
        self.assertEqual((read['host'], read['dbname'], read['port']), ('127.0.0.1', 'mac_dev', '55433'))
        self.assertIn('default_transaction_read_only=on', read['options'])
        self.assertNotIn('options', write)

    def test_remote_is_blocked_for_development_and_tests(self):
        for environment in ('development', 'test'):
            with self.subTest(environment=environment), patch.dict(os.environ, MAC_DB_TARGET='supabase', MAC_ENVIRONMENT=environment):
                with self.assertRaisesRegex(RuntimeError, 'remoto bloqueado'):
                    database.database_write_config()
                with self.assertRaises(RuntimeError):
                    database.database_config()

    def test_api_refuses_startup_with_remote_development_target(self):
        from backend.mac_api.main import create_app
        with patch.dict(os.environ, MAC_DB_TARGET='supabase'), self.assertRaises(RuntimeError):
            create_app()

    def test_local_mode_refuses_remote_hosts_and_ambiguous_database_name(self):
        for host in ('db.supabase.co', '192.168.1.10', 'db-dev.example.com'):
            with self.subTest(host=host), patch.dict(os.environ, MAC_LOCAL_DB_HOST=host):
                with self.assertRaises(RuntimeError):
                    database.database_write_config()
        with patch.dict(os.environ, MAC_LOCAL_DB_NAME='postgres'):
            with self.assertRaises(RuntimeError):
                database.validate_database_target()

    def test_local_hosts_and_disposable_database_are_accepted(self):
        for host in ('localhost', '127.0.0.1', '::1', 'db-dev', 'postgres-test'):
            with self.subTest(host=host), patch.dict(os.environ, MAC_LOCAL_DB_HOST=host, MAC_LOCAL_DB_NAME='mac_test'):
                database.validate_database_target()

    def test_production_remote_requires_explicit_configuration(self):
        values = dict(MAC_DB_TARGET='supabase', MAC_ENVIRONMENT='production',
                      SUPABASE_DB_HOST='remote.example', SUPABASE_DB_PORT='5432',
                      SUPABASE_DB_NAME='postgres', SUPABASE_DB_USER='example', SUPABASE_DB_PASSWORD='test')
        with patch.dict(os.environ, values):
            self.assertEqual(database.database_config()['host'], 'remote.example')
            self.assertIn('default_transaction_read_only=on', database.database_config()['options'])
            self.assertNotIn('options', database.database_write_config())
            self.assertIn('default_transaction_read_only=on', database.cloud_database_config()['options'])

    def test_unknown_environment_or_target_is_rejected(self):
        for values in (dict(MAC_DB_TARGET='fallback'), dict(MAC_ENVIRONMENT='prod')):
            with patch.dict(os.environ, values), self.assertRaises(RuntimeError):
                database.validate_database_target()

    def test_restore_requires_confirmation_and_cannot_target_test_database(self):
        with patch.object(tool, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, '--confirm'):
                tool.restore(Path('/does-not-exist'), confirmed=False)
            run.assert_not_called()
        with patch.dict(os.environ, MAC_LOCAL_DB_NAME='mac_test'), self.assertRaisesRegex(RuntimeError, 'somente mac_dev'):
            tool.local_config()

    def test_dump_checksum_is_verified_before_restore(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'banco.dump').write_bytes(b'dump')
            (path / 'manifesto.json').write_text(json.dumps(dict(format=1, scope='public', sha256='incorrect')))
            with patch.object(tool, 'run') as run, self.assertRaisesRegex(RuntimeError, 'Hash'):
                tool.restore(path, confirmed=True)
            run.assert_not_called()

    def test_existing_objects_are_not_overwritten(self):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [(1,), (0,)]
        with patch.object(tool, 'read_manifest'), patch.object(tool.psycopg2, 'connect', return_value=connection), \
             patch.object(tool, 'run') as run, self.assertRaisesRegex(RuntimeError, 'Nenhuma tabela'):
            tool.restore(Path('/snapshot'), confirmed=True)
        run.assert_not_called()

    def test_restore_uses_fixed_container_target_and_atomic_transaction(self):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [(0,), (0,)]
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'banco.dump').write_bytes(b'dump')
            with patch.object(tool, 'read_manifest'), patch.object(tool.psycopg2, 'connect', return_value=connection), \
                 patch.object(tool, 'run') as run, patch.object(tool, 'verify') as verify:
                tool.restore(path, confirmed=True)
            command = run.call_args.args[0]
            self.assertIn('db-dev', command)
            for argument in ('--host=127.0.0.1', '--dbname=mac_dev', '--schema=public',
                             '--single-transaction', '--exit-on-error'):
                self.assertIn(argument, command)
            self.assertNotIn('--clean', command)
            self.assertNotIn('mac_dev_local', command)
            verify.assert_called_once_with(path)
