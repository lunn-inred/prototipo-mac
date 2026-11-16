"""Dois computadores simulados, somente mac_test e Drive em memória."""
from datetime import date, datetime, timedelta
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.mac_api.modules.backups import service, sync_data, synchronization as sync, bundle
from backend.mac_api.modules.thermography.analysis_registration import register_analysis
from backend.tests.test_analysis_archive import example_views


class MemoryDrive:
    folder = 'test-folder'

    def __init__(self, **kwargs):
        self.files = {}
        self.fail_commit = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def rename_sync_folder(self):
        self.name = 'Analises MAC'

    def list(self, *, sync=False):
        return [deepcopy(record['entry']) for record in self.files.values()]

    def upload(self, source, name, installation, *, sync_properties, mime_type='application/zip'):
        if self.fail_commit and sync_properties['role'] == 'commit':
            raise ValueError('Falha simulada na publicação')
        identity = str(uuid4())
        entry = dict(id=identity, name=name, properties=dict(macSyncFormat='1', sha256=bundle.digest(source), **sync_properties))
        self.files[identity] = dict(entry=entry, content=source.read_bytes())
        return entry

    def download(self, identity, destination, **kwargs):
        record = self.files[identity]
        destination.write_bytes(record['content'])
        return deepcopy(record['entry'])


@unittest.skipUnless(os.getenv('MAC_TEST_DB_ENABLED') == '1', 'PostgreSQL descartável não habilitado')
class SyncPostgresTests(unittest.TestCase):
    def setUp(self):
        config = service.local_config()
        self.assertEqual(config['dbname'], 'mac_test')
        self.assertIn(config['host'], ('127.0.0.1', 'localhost', 'postgres-test'))
        self.assertEqual(str(config['port']), '55432')
        temporary = TemporaryDirectory(prefix='mac-sync-pg-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, MAC_GOOGLE_CLIENT_ID='', MAC_DB_TARGET='local')
        env.start(); self.addCleanup(env.stop)
        self.drive = MemoryDrive()
        fake = patch.object(sync, 'Drive', return_value=self.drive)
        fake.start(); self.addCleanup(fake.stop)
        self.execute('TRUNCATE public.medida_valor,public.atleta,public.partida RESTART IDENTITY')
        initial = self.capture()
        self.states = dict(A=deepcopy(initial), B=deepcopy(initial))
        self.current = None
        self.activate('A')

    def capture(self):
        connection = service._connection()
        try:
            with connection, connection.cursor() as cursor:
                return sync_data.capture(cursor)
        finally:
            connection.close()

    def activate(self, name):
        current = self.capture()
        if self.current:
            self.states[self.current] = current
        connection = service._connection()
        try:
            with connection, connection.cursor() as cursor:
                sync_data.apply(cursor, current, self.states[name])
        finally:
            connection.close()
        self.current = name
        os.environ['MAC_BACKUPS_DIR'] = str(self.root/name/'backups')
        os.environ['MAC_ANALYSES_DIR'] = str(self.root/name/'analyses')

    def execute(self, statement, values=()):
        connection = service._connection()
        try:
            with connection, connection.cursor() as cursor:
                cursor.execute(statement, values)
                return cursor.fetchall() if cursor.description else None
        finally:
            connection.close()

    def athlete(self, name='Teste'):
        return self.execute('INSERT INTO public.atleta(nome) VALUES(%s) RETURNING id_atleta', (name,))[0][0]

    def test_two_computers_share_database_and_zip_then_merge_independent_changes(self):
        athlete = self.athlete()
        registered = register_analysis(athlete_id=athlete, athlete_name='Teste', collected_at=date(2026,11,1),
            mass=75., regional_eva={}, views=example_views())
        first = sync.synchronize()
        self.assertEqual(first['uploaded'], 1)
        self.assertEqual(self.drive.name, 'Analises MAC')
        zip_count = sum(e['entry']['properties']['role'] == 'analysis' for e in self.drive.files.values())
        self.activate('B')
        second = sync.synchronize()
        self.assertEqual(second['downloaded'], 1)
        self.assertEqual(self.execute('SELECT nome FROM public.atleta'), [('Teste',)])
        self.assertEqual(len(bundle.index_analyses(Path(os.environ['MAC_ANALYSES_DIR']))), 1)
        self.execute("UPDATE public.atleta SET posicao='Meia' WHERE id_atleta=%s", (athlete,))
        sync.synchronize()
        self.activate('A')
        new = self.athlete('Novo local')
        self.assertNotEqual(new, athlete)
        sync.synchronize()
        self.assertEqual(self.execute('SELECT nome,posicao FROM public.atleta ORDER BY id_atleta'),
                         [('Teste', 'Meia'), ('Novo local', None)])
        self.activate('B')
        result = sync.synchronize()
        self.assertEqual(result['downloaded'], 0)
        self.assertEqual(result['uploaded'], 0)
        self.assertEqual(sum(e['entry']['properties']['role'] == 'analysis' for e in self.drive.files.values()), zip_count)
        self.assertEqual(self.execute('SELECT count(*) FROM public.atleta'), [(2,)])
        self.assertEqual(self.execute('SELECT massa,eva_dor FROM public.vw_medida_termografia'), [(75., 0.)])

    def test_last_local_save_wins_when_both_computers_replace_same_collection(self):
        athlete = self.athlete()
        day = date(2026, 11, 1)
        register_analysis(athlete_id=athlete, athlete_name='Teste', collected_at=day,
                          mass=75., regional_eva={}, views=example_views())
        sync.synchronize()
        self.activate('B')
        sync.synchronize()
        shutil.rmtree(next(iter(bundle.index_analyses(Path(os.environ['MAC_ANALYSES_DIR'])).values()))['path'])
        remote = register_analysis(athlete_id=athlete, athlete_name='Teste', collected_at=day,
                                   mass=78., regional_eva={}, views=example_views(), overwrite=True)
        sync.synchronize()
        head = sync._head(self.drive)
        index = json.loads(self.drive.files[head['id']]['content'])
        self.assertEqual(set(index['analyses']), {str(remote['analysis']['id'])})
        self.activate('A')
        shutil.rmtree(next(iter(bundle.index_analyses(Path(os.environ['MAC_ANALYSES_DIR'])).values()))['path'])
        local = register_analysis(athlete_id=athlete, athlete_name='Teste', collected_at=day,
                                  mass=71., regional_eva={}, views=example_views(), overwrite=True)
        self.assertNotEqual(local['analysis']['id'], remote['analysis']['id'])
        sync.synchronize()
        entries = bundle.index_analyses(Path(os.environ['MAC_ANALYSES_DIR']))
        self.assertEqual(set(entries), {str(local['analysis']['id'])})
        self.assertEqual(self.execute('SELECT massa FROM public.vw_medida_termografia'), [(71.,)])

    def test_last_drive_save_wins_when_both_computers_replace_same_collection(self):
        athlete = self.athlete()
        day = date(2026, 11, 1)
        register_analysis(athlete_id=athlete, athlete_name='Teste', collected_at=day,
                          mass=75., regional_eva={}, views=example_views())
        sync.synchronize()
        self.activate('B')
        sync.synchronize()
        self.activate('A')
        shutil.rmtree(next(iter(bundle.index_analyses(Path(os.environ['MAC_ANALYSES_DIR'])).values()))['path'])
        local = register_analysis(athlete_id=athlete, athlete_name='Teste', collected_at=day,
                                  mass=71., regional_eva={}, views=example_views(), overwrite=True)
        self.activate('B')
        shutil.rmtree(next(iter(bundle.index_analyses(Path(os.environ['MAC_ANALYSES_DIR'])).values()))['path'])
        remote = register_analysis(athlete_id=athlete, athlete_name='Teste', collected_at=day,
                                   mass=78., regional_eva={}, views=example_views(), overwrite=True)
        sync.synchronize()
        self.activate('A')
        self.assertNotEqual(local['analysis']['id'], remote['analysis']['id'])
        sync.synchronize()
        entries = bundle.index_analyses(Path(os.environ['MAC_ANALYSES_DIR']))
        self.assertEqual(set(entries), {str(remote['analysis']['id'])})
        self.assertEqual(self.execute('SELECT massa FROM public.vw_medida_termografia'), [(78.,)])

    def test_existing_duplicate_local_analysis_is_reduced_to_latest_before_staging(self):
        athlete = self.athlete()
        register_analysis(athlete_id=athlete, athlete_name='Teste', collected_at=date(2026, 11, 1),
                          mass=75., regional_eva={}, views=example_views())
        sync.synchronize()
        root = Path(os.environ['MAC_ANALYSES_DIR'])
        original = next(iter(bundle.index_analyses(root).values()))
        newer_id = str(uuid4())
        newer_path = original['path'].parent / f'analise_{newer_id}'
        shutil.copytree(original['path'], newer_path)
        metadata_file = newer_path / 'metadados.json'
        metadata = json.loads(metadata_file.read_text(encoding='utf-8'))
        metadata['analysis_id'] = newer_id
        metadata['created_at'] = (datetime.fromisoformat(metadata['created_at']) + timedelta(seconds=1)).isoformat()
        metadata_file.write_text(json.dumps(metadata), encoding='utf-8')
        result = sync.synchronize()
        self.assertEqual(set(bundle.index_analyses(root)), {newer_id})
        self.assertEqual(result['analyses'], 1)

    def test_conflicting_edits_and_numeric_id_collisions_do_not_publish_or_replace_local_data(self):
        athlete = self.athlete()
        sync.synchronize()
        self.activate('B'); sync.synchronize()
        self.execute("UPDATE public.atleta SET nome='B' WHERE id_atleta=%s", (athlete,))
        sync.synchronize()
        self.activate('A')
        self.execute("UPDATE public.atleta SET nome='A' WHERE id_atleta=%s", (athlete,))
        count = len(self.drive.files)
        with self.assertRaisesRegex(ValueError, 'Conflito'):
            sync.synchronize()
        self.assertEqual(len(self.drive.files), count)
        self.assertEqual(self.execute('SELECT nome FROM public.atleta'), [('A',)])
        self.assertFalse(service.pending_recovery())

    def test_deletion_propagates_but_never_deletes_a_new_unsynchronized_record(self):
        athlete = self.athlete()
        sync.synchronize()
        self.activate('B'); sync.synchronize()
        self.execute('DELETE FROM public.atleta WHERE id_atleta=%s', (athlete,))
        sync.synchronize()
        self.activate('A')
        self.athlete('Novo')
        sync.synchronize()
        self.assertEqual(self.execute('SELECT nome FROM public.atleta'), [('Novo',)])

    def test_failed_index_publication_rolls_back_sql_and_preserves_previous_baseline(self):
        self.athlete()
        sync.synchronize()
        self.activate('B'); sync.synchronize()
        self.athlete('Remoto')
        sync.synchronize()
        self.activate('A')
        self.execute("UPDATE public.atleta SET posicao='Meia' WHERE id_atleta=1")
        before = self.capture()['tables']
        path = service.backups_directory()/'sync-state.json'
        baseline = path.read_bytes()
        self.drive.fail_commit = True
        with self.assertRaisesRegex(ValueError, 'Falha simulada'):
            sync.synchronize()
        self.assertEqual(self.capture()['tables'], before)
        self.assertEqual(path.read_bytes(), baseline)
        self.assertFalse(service.pending_recovery())
        self.assertTrue(list(service.backups_directory().glob('recovery-sync-*.zip')))

    def test_changed_view_is_refused_without_publishing_or_modifying_rows(self):
        self.athlete()
        sync.synchronize()
        self.activate('B')
        connection = service._connection()
        try:
            # Simular captura de uma estrutura diferente sem deixar DDL no banco.
            with connection.cursor() as cursor:
                cursor.execute('CREATE VIEW public.mac_sync_test_view AS SELECT 1 AS x')
                changed = sync_data.capture(cursor)
            connection.rollback()
        finally:
            connection.close()
        with patch.object(sync_data, 'capture', return_value=changed), self.assertRaisesRegex(ValueError, 'Estrutura incompatível'):
            sync.synchronize()
        self.assertFalse(service.pending_recovery())

    def test_remote_target_is_blocked_before_drive_access(self):
        with patch.dict(os.environ, MAC_DB_TARGET='supabase'), patch.object(sync, 'Drive') as drive:
            with self.assertRaisesRegex(ValueError, 'exclusivamente'):
                sync.synchronize()
            drive.assert_not_called()

    def test_initial_numeric_id_collision_is_not_associated_to_another_player(self):
        self.athlete('Jogador A')
        sync.synchronize()
        self.activate('B')
        self.athlete('Jogador B')
        with self.assertRaisesRegex(ValueError, 'Conflito'):
            sync.synchronize()
        self.assertEqual(self.execute('SELECT nome FROM public.atleta'), [('Jogador B',)])

    def test_partial_analysis_and_available_measures_are_shared(self):
        from backend.tests.test_thermal_drafts import empty_state
        from backend.mac_api.modules.thermography import drafts
        athlete = self.athlete()
        state = empty_state()
        state['draft'].update(player=athlete, mass=72., regional_eva={})
        saved = drafts.save(state)
        sync.synchronize()
        self.activate('B')
        result = sync.synchronize()
        self.assertEqual(result['downloaded'], 1)
        self.assertEqual(drafts.load(saved['id'])['state']['draft']['mass'], 72.)
        self.assertEqual(self.execute('SELECT massa,eva_dor FROM public.vw_medida_termografia'), [(72., 0.)])

    def test_file_publication_failure_restores_local_sql_files_and_baseline(self):
        self.athlete('Remoto')
        register_analysis(athlete_id=1, athlete_name='Remoto', collected_at=date(2026,11,1),
                         mass=75., pain_score=0, views=example_views())
        sync.synchronize()
        self.activate('B')
        root = Path(os.environ['MAC_ANALYSES_DIR'])
        original_replace = os.replace
        def fail(source, destination):
            if Path(source).parent.name.startswith('.mac-incoming-') and Path(destination).parent == root:
                raise OSError('Publicação de arquivos falhou')
            return original_replace(source, destination)
        with patch.object(sync.os, 'replace', side_effect=fail), self.assertRaises(OSError):
            sync.synchronize()
        self.assertEqual(self.execute('SELECT count(*) FROM public.atleta'), [(0,)])
        self.assertFalse((service.backups_directory()/'sync-state.json').exists())
        self.assertFalse(service.pending_recovery())
        result = sync.synchronize()
        self.assertEqual(result['downloaded'], 1)
