"""Restauração destrutiva exclusivamente no mac_test descartável, nunca mac_dev."""
from datetime import date
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
import time
from unittest.mock import patch

from backend.mac_api.core.database import database_write_config, database_write_connection
from backend.mac_api.modules.backups import service, bundle
from backend.mac_api.modules.thermography.analysis_registration import register_analysis, replace_analysis
from backend.tests.test_analysis_archive import example_views


class FakeDrive:
    def __init__(self, **kwargs):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def upload(self, source, name, installation):
        return dict(id='test-file', name=name, size=source.stat().st_size,
                    properties=dict(sha256=bundle.digest(source), macBackupFormat='1', installation=installation))


@unittest.skipUnless(os.getenv('MAC_TEST_DB_ENABLED') == '1', 'PostgreSQL descartável não habilitado')
class BackupPostgresTests(unittest.TestCase):
    def setUp(self):
        config = database_write_config()
        self.assertEqual(config['dbname'], 'mac_test')
        self.assertIn(config['host'], ('127.0.0.1', 'localhost', 'postgres-test'))
        self.directory = TemporaryDirectory(prefix='mac-backup-postgres-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.analyses = self.root / 'analyses'
        environment = patch.dict(os.environ, MAC_BACKUPS_DIR=str(self.root / 'backups'), MAC_ANALYSES_DIR=str(self.analyses))
        environment.start(); self.addCleanup(environment.stop)
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('TRUNCATE public.medida_valor,public.atleta,public.partida RESTART IDENTITY')

    def athlete(self, name='Teste'):
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('INSERT INTO public.atleta (nome) VALUES (%s) RETURNING id_atleta', (name,))
            return cursor.fetchone()[0]

    def register(self, athlete, day=date(2026, 11, 1), mass=75):
        values = dict(athlete_id=athlete, athlete_name='Interface', collected_at=day,
                      mass=mass, pain_score=0, observations='Linha 1\nLinha 2, acento é', views=example_views())
        return register_analysis(**values)['analysis'], values

    def backup(self):
        with patch.object(service, 'Drive', FakeDrive):
            return service.create_backup()

    def restore(self, source):
        work = self.root / f'restore-{len(list(self.root.glob("restore-*")))}'
        work.mkdir()
        return service.restore_downloaded(Path(source), work)

    def rows(self):
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT id_atleta,nome,status FROM public.atleta ORDER BY id_atleta')
            athletes = cursor.fetchall()
            cursor.execute('SELECT id_atleta,id_medida,valor,valor_texto,data FROM public.medida_valor ORDER BY id_atleta,id_medida,data')
            return athletes, cursor.fetchall()

    def test_restore_replaces_database_but_preserves_newer_equal_and_local_only_analysis(self):
        first, second, third = [self.athlete(name) for name in ('Primeiro', 'Segundo', 'Terceiro')]
        old, values = self.register(first)
        equal, _ = self.register(second)
        remote_only, _ = self.register(third)
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT id_medida FROM public.medida WHERE nome='MAIOR_CMJ'")
            jump_measure = cursor.fetchone()[0]
            cursor.execute('INSERT INTO public.medida_valor(id_atleta,id_medida,valor,data) VALUES(%s,%s,30,%s)', (first, jump_measure, date(2026, 11, 1)))
        backup = self.backup()
        newer = replace_analysis(source=dict(athlete_id=first, collected_at=old['collected_at'], analysis_id=old['id']),
            expected_revision=old['created_at'], **{**values, 'mass': 90, 'pain_score': 5})['analysis']
        local_only_id = self.athlete('Somente local')
        local_only, _ = self.register(local_only_id, mass=81)
        # Esta coleta só existe no backup depois de simular remoção local.
        from backend.mac_api.modules.thermography.analysis_archive import discard_created_analysis
        discard_created_analysis(remote_only)
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('DELETE FROM public.medida_valor WHERE id_atleta=%s', (third,))
            cursor.execute('UPDATE public.medida_valor SET valor=40 WHERE id_atleta=%s AND id_medida=%s', (first, jump_measure))
        before = bundle.index_analyses(self.analyses)
        result = self.restore(backup['local_copy'])
        self.assertEqual(result['preserved_local'], 3)
        self.assertEqual(result['analyses'], 4)
        self.assertTrue(Path(result['recovery_copy']).is_file())
        after = bundle.index_analyses(self.analyses)
        for identity in (newer['id'], equal['id'], local_only['id']):
            self.assertEqual(after[identity]['hashes'], before[identity]['hashes'])
        self.assertIn(remote_only['id'], after)
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT id_atleta,massa,eva_dor,observacoes FROM public.vw_medida_termografia ORDER BY id_atleta')
            records = cursor.fetchall()
            self.assertEqual([row[1] for row in records], [90, 75, 75, 81])
            self.assertEqual(records[0][2], 5)
            self.assertEqual(records[0][3], 'Linha 1\nLinha 2, acento é')
            cursor.execute('SELECT valor FROM public.medida_valor WHERE id_atleta=%s AND id_medida=%s', (first, jump_measure))
            self.assertEqual(cursor.fetchone()[0], 30)
        self.assertGreater(self.athlete('Após restauração'), local_only_id)
        self.assertFalse(service.pending_recovery())

    def test_file_publication_failure_rolls_back_database_and_original_images(self):
        athlete = self.athlete()
        entry, values = self.register(athlete)
        backup = self.backup()
        replace_analysis(source=dict(athlete_id=athlete, collected_at=entry['collected_at'], analysis_id=entry['id']),
            expected_revision=entry['created_at'], **{**values, 'mass': 91})
        before_rows, before_images = self.rows(), bundle.index_analyses(self.analyses)
        original_replace = service.os.replace
        def fail_publish(source, destination):
            if Path(source).name.startswith('.mac-restore-'):
                raise OSError('Falha de publicação simulada')
            return original_replace(source, destination)
        with patch.object(service.os, 'replace', side_effect=fail_publish):
            with self.assertRaises(OSError):
                self.restore(backup['local_copy'])
        self.assertEqual(self.rows(), before_rows)
        self.assertEqual(bundle.index_analyses(self.analyses)[entry['id']]['hashes'], before_images[entry['id']]['hashes'])
        self.assertFalse(service.pending_recovery())
        self.assertEqual(len(list((self.root / 'backups').glob('recovery-*.zip'))), 1)

    def test_athlete_id_conflict_is_refused_without_overwriting_anything(self):
        athlete = self.athlete('Nome no backup')
        entry, values = self.register(athlete)
        backup = self.backup()
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('UPDATE public.atleta SET nome=%s WHERE id_atleta=%s', ('Outra pessoa local', athlete))
        before = self.rows()
        with self.assertRaisesRegex(ValueError, 'ID de atleta'):
            self.restore(backup['local_copy'])
        self.assertEqual(self.rows(), before)
        self.assertEqual(len(bundle.index_analyses(self.analyses)), 1)
        self.assertFalse(service.pending_recovery())

    def test_newer_remote_analysis_replaces_older_local_and_its_measures(self):
        athlete = self.athlete()
        entry, values = self.register(athlete)
        old_files = self.root / 'old'
        shutil.copytree(self.analyses, old_files)
        newer = replace_analysis(source=dict(athlete_id=athlete, collected_at=entry['collected_at'], analysis_id=entry['id']),
            expected_revision=entry['created_at'], **{**values, 'mass': 88})['analysis']
        backup = self.backup()
        shutil.rmtree(self.analyses)
        shutil.copytree(old_files, self.analyses)
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE public.medida_valor SET valor=70 WHERE id_atleta=%s AND id_medida=(SELECT id_medida FROM public.medida WHERE nome='MASSA')", (athlete,))
        result = self.restore(backup['local_copy'])
        self.assertEqual(result['preserved_local'], 0)
        self.assertEqual(bundle.index_analyses(self.analyses)[entry['id']]['metadata']['created_at'], newer['created_at'])
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT massa FROM public.vw_medida_termografia WHERE id_atleta=%s', (athlete,))
            self.assertEqual(cursor.fetchone()[0], 88)

    def test_moved_newer_local_analysis_removes_old_backup_collection(self):
        first = self.athlete('Origem')
        entry, values = self.register(first)
        backup = self.backup()
        second = self.athlete('Destino local')
        moved = replace_analysis(source=dict(athlete_id=first, collected_at=entry['collected_at'], analysis_id=entry['id']),
            expected_revision=entry['created_at'], **{**values, 'athlete_id': second, 'collected_at': date(2026, 11, 12), 'mass': 84})['analysis']
        self.restore(backup['local_copy'])
        restored = bundle.index_analyses(self.analyses)[entry['id']]
        self.assertEqual(restored['pair'], (second, '2026-11-12'))
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT id_atleta,data_coleta::date,massa FROM public.vw_medida_termografia')
            self.assertEqual(cursor.fetchall(), [(second, date(2026, 11, 12), 84)])

    def test_schema_mismatch_is_refused_without_changing_rows(self):
        athlete = self.athlete()
        self.register(athlete)
        backup = self.backup()
        before = self.rows()
        try:
            with database_write_connection() as connection, connection.cursor() as cursor:
                cursor.execute('ALTER TABLE public.atleta ADD COLUMN backup_test_extra integer')
            with self.assertRaisesRegex(ValueError, 'incompatível'):
                self.restore(backup['local_copy'])
            self.assertEqual(self.rows(), before)
            self.assertFalse(service.pending_recovery())
        finally:
            with database_write_connection() as connection, connection.cursor() as cursor:
                cursor.execute('ALTER TABLE public.atleta DROP COLUMN IF EXISTS backup_test_extra')

    def test_api_jobs_backup_and_restore_end_to_end_with_mock_drive(self):
        from fastapi.testclient import TestClient
        from backend.mac_api.main import create_app
        from backend.mac_api.modules.backups import jobs
        athlete = self.athlete()
        entry, values = self.register(athlete)
        cloud_file = self.root / 'mock-drive.zip'
        class OfflineDrive(FakeDrive):
            def upload(self, source, name, installation):
                shutil.copyfile(source, cloud_file)
                return super().upload(source, name, installation)
            def metadata(self, identity):
                return dict(id='test-file', properties={'sha256': bundle.digest(cloud_file)})
            def download(self, identity, target):
                shutil.copyfile(cloud_file, target)
                return self.metadata(identity)
        def wait(client, identity, headers):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                response = client.get(f'/api/v1/backups/jobs/{identity}', headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                job = response.json()
                if job['status'] in ('completed', 'failed'):
                    self.assertEqual(job['status'], 'completed', job)
                    return job
                time.sleep(.03)
            self.fail('A tarefa de teste não terminou no prazo.')
        with patch.dict(os.environ, MAC_API_KEY='backup-integration', MAC_GOOGLE_CLIENT_ID='test-google'), \
             patch('backend.mac_api.modules.google_auth.valid_session', return_value=True), \
             patch.object(service, 'Drive', OfflineDrive):
            client = TestClient(create_app())
            headers = {'X-API-Key': 'backup-integration', 'Authorization': 'Bearer test-session'}
            start = client.post('/api/v1/backups', headers=headers, json={})
            self.assertEqual(start.status_code, 202, start.text)
            sent = wait(client, start.json()['id'], headers)
            replace_analysis(source=dict(athlete_id=athlete, collected_at=entry['collected_at'], analysis_id=entry['id']),
                expected_revision=entry['created_at'], **{**values, 'mass': 92})
            start = client.post('/api/v1/backups/restore', headers=headers, json=dict(
                file_id='test-file', expected_sha256=sent['result']['file']['properties']['sha256'], confirm=True))
            self.assertEqual(start.status_code, 202, start.text)
            restored = wait(client, start.json()['id'], headers)
            self.assertEqual(restored['result']['preserved_local'], 1)
            self.assertTrue(Path(restored['result']['recovery_copy']).exists())
            records = client.get('/api/v1/thermography', headers=headers).json()
            self.assertEqual(records[0]['massa'], 92)

    def test_identical_files_without_local_sql_keep_valid_measures_from_backup(self):
        athlete = self.athlete()
        entry, values = self.register(athlete)
        backup = self.backup()
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('DELETE FROM public.medida_valor WHERE id_atleta=%s', (athlete,))
        self.restore(backup['local_copy'])
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT massa FROM public.vw_medida_termografia WHERE id_atleta=%s', (athlete,))
            self.assertEqual(cursor.fetchone()[0], 75)

    def test_local_only_analysis_reinstates_missing_measure_definitions_and_group_id(self):
        # Backup anterior ao cadastro das medidas térmicas, mas com o mesmo esquema.
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT id_medida,nome,id_grupo_medida FROM public.medida WHERE id_grupo_medida=2 ORDER BY id_medida')
            definitions = cursor.fetchall()
            cursor.execute('DELETE FROM public.medida WHERE id_grupo_medida=2')
            cursor.execute('DELETE FROM public.grupo_medida WHERE id_grupo_medida=2')
        backup = self.backup()
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO public.grupo_medida(id_grupo_medida,nome) VALUES(2,'termografia')")
            cursor.executemany('INSERT INTO public.medida(id_medida,nome,id_grupo_medida) VALUES(%s,%s,%s)', definitions)
        athlete = self.athlete('Criado depois do backup')
        self.register(athlete, mass=83)
        self.restore(backup['local_copy'])
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT massa FROM public.vw_medida_termografia WHERE id_atleta=%s', (athlete,))
            self.assertEqual(cursor.fetchone()[0], 83)
