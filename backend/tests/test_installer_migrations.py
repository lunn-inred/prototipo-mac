"""Bootstrap de distribuição; escrita somente no mac_test descartável."""
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from backend.mac_api.core import migrations


class MigrationPackageTests(unittest.TestCase):
    def test_baseline_contains_schema_and_catalog_only(self):
        manifest, scripts, baseline = migrations.package_plan()
        text = baseline.decode('utf-8')
        self.assertEqual(len(manifest['includes']), 3)
        self.assertTrue(set(manifest['includes']).issubset(scripts))
        self.assertIn('20261118_thermography_baseline.sql', scripts)
        for table in ('atleta','usuario','partida','medida_valor'):
            self.assertNotIn(f'INSERT INTO public.{table}',text)
            self.assertNotIn(f'COPY public.{table}',text)
        self.assertIn('CREATE TABLE public.atleta',text)

    def test_transaction_wrappers_do_not_escape_migration_transaction(self):
        result = migrations.transactional_sql(b'BEGIN;\nDO $$ BEGIN\n NULL;\nEND $$;\nCOMMIT;\n')
        self.assertNotIn('COMMIT;',result)
        self.assertIn('DO $$ BEGIN',result)

    def test_remote_or_unidentified_targets_are_refused(self):
        for host,name in (('cloud.example','mac_dev'),('127.0.0.1','postgres')):
            with self.assertRaises(RuntimeError):
                migrations.run_migrations(dict(host=host,dbname=name),str(uuid4()))


@unittest.skipUnless(os.getenv('MAC_TEST_DB_ENABLED')=='1','PostgreSQL descartável não habilitado')
class InstallerPostgresTests(unittest.TestCase):
    def setUp(self):
        from backend.mac_api.core.database import database_write_config
        self.config=database_write_config()
        self.assertEqual(self.config['dbname'],'mac_test')
        self.assertEqual(self.config['host'],'127.0.0.1')
        self.identity=str(uuid4())
        self.reset()

    def reset(self, fixture=False):
        import psycopg2
        with psycopg2.connect(**self.config) as c,c.cursor() as q:
            q.execute('DROP SCHEMA IF EXISTS mac_internal CASCADE; DROP SCHEMA public CASCADE; CREATE SCHEMA public')
            if fixture:
                q.execute((Path(__file__).parent/'fixtures/schema.sql').read_text(encoding='utf-8'))

    def tearDown(self):
        self.reset(fixture=True)

    def execute(self,statement,parameters=()):
        import psycopg2
        with psycopg2.connect(**self.config) as c,c.cursor() as q:
            q.execute(statement,parameters or None)
            return q.fetchall() if q.description else []

    def test_clean_bootstrap_is_empty_of_personal_data_and_repeatable(self):
        migrations.run_migrations(self.config,self.identity,initialize=True)
        for table in ('atleta','usuario','partida','medida_valor'):
            self.assertEqual(self.execute(f'SELECT count(*) FROM public.{table}'),[(0,)])
        self.assertEqual(self.execute("SELECT count(*) FROM public.medida WHERE nome LIKE 'EVA_%'"),[(16,)])
        self.assertEqual(self.execute("SELECT count(*) FROM public.medida WHERE nome LIKE '%ZONA_%'"),[(48,)])
        self.assertEqual(migrations.run_migrations(self.config,self.identity),[])
        self.assertEqual(self.execute('SELECT count(*) FROM mac_internal.schema_migrations'),[(len(migrations.package_plan()[1]) + 1,)])

    def test_existing_database_is_not_adopted_or_destroyed(self):
        self.execute('CREATE TABLE public.sentinel(value integer); INSERT INTO public.sentinel VALUES(42)')
        with self.assertRaisesRegex(RuntimeError,'existente sem histórico'):
            migrations.run_migrations(self.config,self.identity,initialize=True)
        self.assertEqual(self.execute('SELECT value FROM public.sentinel'),[(42,)])

    def test_baseline_runs_as_database_owner_without_superuser(self):
        from psycopg2 import sql
        role='mac_install_test_'+uuid4().hex[:8]
        password=uuid4().hex
        try:
            self.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE').format(sql.Identifier(role),sql.Literal(password)))
            self.execute(sql.SQL('GRANT CONNECT,CREATE ON DATABASE mac_test TO {}').format(sql.Identifier(role)))
            self.execute(sql.SQL('ALTER SCHEMA public OWNER TO {}').format(sql.Identifier(role)))
            config={**self.config,'user':role,'password':password}
            migrations.run_migrations(config,self.identity,initialize=True)
            self.assertEqual(migrations.run_migrations(config,self.identity),[])
            self.assertEqual(self.execute('SELECT rolsuper FROM pg_roles WHERE rolname=%s',(role,)),[(False,)])
        finally:
            self.reset()
            self.execute(sql.SQL('REVOKE ALL ON DATABASE mac_test FROM {}').format(sql.Identifier(role)))
            self.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))

    def test_identity_and_schema_changes_block_startup(self):
        migrations.run_migrations(self.config,self.identity,initialize=True)
        with self.assertRaisesRegex(RuntimeError,'outra instalação'):
            migrations.run_migrations(self.config,str(uuid4()))
        self.execute('ALTER TABLE public.atleta ADD COLUMN unexpected text')
        with self.assertRaisesRegex(RuntimeError,'mudou fora'):
            migrations.run_migrations(self.config,self.identity)

    def test_updates_require_backup_and_rollback_sql_and_history_on_failure(self):
        migrations.run_migrations(self.config,self.identity,initialize=True)
        with TemporaryDirectory() as directory:
            root=Path(directory)
            shutil.copytree(migrations.ROOT/'bootstrap',root/'bootstrap')
            shutil.copytree(migrations.ROOT/'migrations',root/'migrations')
            script=root/'migrations/20990101_test.sql'
            script.write_text('BEGIN;\nALTER TABLE public.atleta ADD COLUMN test_column text;\nSELECT * FROM absent_table;\nCOMMIT;\n')
            called=[]
            with self.assertRaisesRegex(RuntimeError,'backup verificado'):
                migrations.run_migrations(self.config,self.identity,root=root)
            import psycopg2
            with self.assertRaises(psycopg2.Error):
                migrations.run_migrations(self.config,self.identity,root=root,backup=lambda config:called.append(True))
            self.assertEqual(called,[True])
            self.assertEqual(self.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND column_name='test_column'"),[(0,)])
            self.assertEqual(self.execute('SELECT count(*) FROM mac_internal.schema_migrations'),[(len(migrations.package_plan()[1]) + 1,)])
            script.write_text('BEGIN;\nALTER TABLE public.atleta ADD COLUMN test_column text;\nCOMMIT;\n')
            self.assertEqual(migrations.run_migrations(self.config,self.identity,root=root,backup=lambda config:called.append(True)),['20990101_test.sql'])
            self.assertEqual(migrations.run_migrations(self.config,self.identity,root=root),[])
            script.write_text('-- historical mutation')
            with self.assertRaisesRegex(RuntimeError,'migration alterada'):
                migrations.run_migrations(self.config,self.identity,root=root)
