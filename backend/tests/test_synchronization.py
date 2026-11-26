"""Mesclagem e transporte de sincronização, sem Google nem PostgreSQL reais."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4
from backend.mac_api.modules.backups import sync_data as data, synchronization as sync


class SyncStagingTests(unittest.TestCase):
    def test_stage_uses_writable_backup_directory(self):
        with TemporaryDirectory() as temporary:
            backups = Path(temporary) / 'backups'
            backups.mkdir()
            with patch.object(sync.service, 'backups_directory', return_value=backups):
                stage = sync._create_stage()
            self.assertEqual(stage.parent, backups)
            self.assertTrue(stage.is_dir())
            self.assertTrue(stage.name.startswith('.mac-sync-'))

    def test_acl_denial_fails_once_before_drive_or_database_and_updates_job(self):
        from backend.mac_api.modules.backups import jobs
        with TemporaryDirectory() as temporary, \
             patch.object(sync.service, '_assert_ready'), \
             patch.object(sync.service, 'backups_directory', return_value=Path(temporary)), \
             patch.object(sync, 'analyses_directory', return_value=Path(temporary)/'analyses'), \
             patch.object(sync, 'Drive') as drive, \
             patch.object(sync.service, '_connection') as connection, \
             patch.object(Path, 'mkdir', side_effect=PermissionError(13, 'private-token')) as mkdir, \
             patch.dict(jobs._jobs, {'stage-test': dict(kind='sync', status='queued', message='Aguardando')}), \
             self.assertLogs(jobs.__name__, level='ERROR') as logs:
            jobs._run('stage-test', lambda progress: sync.synchronize(progress=progress))
            result = jobs.status('stage-test')
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['error_type'], 'PermissionError')
            self.assertIn('Preparando arquivos locais', result['message'])
            self.assertNotIn('private-token', result['message']+'\n'.join(logs.output))
            mkdir.assert_called_once()
            drive.assert_not_called()
            connection.assert_not_called()


class SyncMergeTests(unittest.TestCase):
    def test_staging_uses_writable_backups_and_permission_failure_is_not_retried(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch.object(sync.service, 'backups_directory', return_value=directory):
                stage = sync._create_stage()
                self.assertEqual(stage.parent, directory)
                self.assertTrue(stage.is_dir())
                self.assertTrue(stage.name.startswith('.mac-sync-'))
                with patch.object(Path, 'mkdir', side_effect=PermissionError(13, 'private-path')) as mkdir:
                    with self.assertRaises(PermissionError):
                        sync._create_stage()
                    mkdir.assert_called_once()

    def test_staging_failure_is_reported_as_failed_job_before_drive_or_database(self):
        from backend.mac_api.modules.backups import jobs
        with TemporaryDirectory() as temporary, \
             patch.object(sync.service, '_assert_ready'), \
             patch.object(sync.service, 'backups_directory', return_value=Path(temporary)), \
             patch.object(sync, '_create_stage', side_effect=PermissionError(13, 'private-path')), \
             patch.object(sync, 'Drive') as drive, \
             patch.dict(jobs._jobs, {'stage-test': dict(kind='sync', status='queued', message='Aguardando')}):
            with self.assertLogs(jobs.__name__, level='ERROR') as logs:
                jobs._run('stage-test', lambda progress: sync.synchronize(progress=progress))
            result = jobs.status('stage-test')
            self.assertEqual(result['status'], 'failed')
            self.assertIn('Preparando arquivos locais', result['message'])
            self.assertNotIn('private-path', result['message'] + '\n'.join(logs.output))
            drive.assert_not_called()

    def test_regional_catalog_alignment_updates_links_and_refuses_other_measure_collisions(self):
        def snapshot(reverse=False):
            regions = [f'{part}_{side}_{view}' for part in ('COXA', 'JOELHO', 'CANELA', 'PE')
                       for side in ('DIREITA', 'ESQUERDA') for view in ('FRENTE', 'VERSO')]
            names = [f'EVA_{r}' for r in regions] + [f'{r}_ZONA_{z}' for r in regions
                                                        for z in ('FRIA', 'NEUTRA', 'QUENTE')]
            if reverse:
                names.reverse()
            measures = {data.canonical([str(i)]): dict(id_medida=str(i), nome=name,
                        id_grupo_medida='1') for i, name in enumerate(names, 1)}
            return dict(keys={'medida': ['id_medida']}, schema={'foreign_keys': [
                dict(child='medida_valor', parent='medida', columns=['id_medida'], references=['id_medida'])]},
                tables={'grupo_medida': {'1': dict(id_grupo_medida='1', nome='termografia')},
                        'medida': measures, 'medida_valor': {'v': dict(id_medida='1', valor='99')}})
        local, remote = snapshot(), snapshot(True)
        original = deepcopy(remote)
        _, _, result = sync._align_regional_measure_ids(None, local, remote)
        self.assertEqual(result['tables']['medida'], local['tables']['medida'])
        self.assertEqual(result['tables']['medida_valor']['v'], dict(id_medida='64', valor='99'))
        self.assertEqual(remote, original)
        collision = deepcopy(remote)
        collision['tables']['medida'].pop('["64"]')
        collision['tables']['medida']['["100"]'] = dict(id_medida='100', nome='EVA_COXA_DIREITA_FRENTE', id_grupo_medida='1')
        collision['tables']['medida']['["64"]'] = dict(id_medida='64', nome='GPS_OTHER', id_grupo_medida='2')
        with self.assertRaisesRegex(ValueError, 'colide'):
            sync._align_regional_measure_ids(None, local, collision)
        unsupported = deepcopy(remote)
        unsupported['schema']['foreign_keys'].append(dict(child='other', parent='medida',
                                                          columns=['m'], references=['id_medida']))
        with self.assertRaisesRegex(ValueError, 'referências'):
            sync._align_regional_measure_ids(None, local, unsupported)

    def test_thermal_id_collision_preserves_other_rows_and_converges(self):
        def row(identity, athlete, measure='1', value='70'):
            return dict(id_medida_valor=str(identity), id_atleta=str(athlete),
                        id_medida=measure, data='2026-11-01 00:00:00', valor=value)

        tables = {
            'grupo_medida': {'["1"]': dict(id_grupo_medida='1', nome='termografia')},
            'medida': {'["1"]': dict(id_medida='1', id_grupo_medida='1')},
            'medida_valor': {'["1"]': row(1, 7)},
        }
        state = dict(tables=tables, keys={'grupo_medida': ['id_grupo_medida'],
                                         'medida': ['id_medida'], 'medida_valor': ['id_medida_valor']},
                     schema=dict(tables={name: [dict(name=k, generated='') for k in next(iter(rows.values()))]
                                         for name, rows in tables.items()}, foreign_keys=[]),
                     sequence_values={})
        state['schema_version'] = data.fingerprint(state['schema'])
        base = deepcopy(state)
        local, remote = deepcopy(state), deepcopy(state)
        # Local reused ID 2 for GPS; Drive reused it for the winning thermal row.
        local['tables']['medida_valor']['["2"]'] = row(2, 8, '2', '999')
        remote['tables']['medida_valor'] = {'["2"]': row(2, 7, value='80')}
        before = deepcopy((base, local, remote))
        for baseline in (base, None):
            normalized = data.prepare_thermal_merge(baseline, local, remote, set(), {(7, '2026-11-01')})
            merged = data.merge_database(*normalized)
            self.assertEqual(merged['tables']['medida_valor'], {
                '["2"]': row(2, 8, '2', '999'), '["3"]': row(3, 7, value='80')})
            again = data.prepare_thermal_merge(merged, merged, merged, set(), {(7, '2026-11-01')})
            self.assertEqual(data.merge_database(*again), merged)
        self.assertEqual((base, local, remote), before)
        # The same protection applies when the latest analysis is local.
        normalized = data.prepare_thermal_merge(base, remote, local, {(7, '2026-11-01')}, set())
        self.assertEqual(data.merge_database(*normalized)['tables'], merged['tables'])

    def test_drive_analysis_wins_when_saved_last_without_losing_other_local_files(self):
        first, second, other = [str(uuid4()) for _ in range(3)]
        earlier = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
        def local(identity, day):
            return dict(pair=(7, day), relative=Path(f'atleta_7/{day}/analise_{identity}'),
                        hashes={'metadados.json': identity}, revision=earlier)
        files = {first: local(first, '2026-11-01'), other: local(other, '2026-11-02')}
        drive = {second: dict(relative=f'atleta_7/2026-11-01/analise_{second}', content='drive',
                              revision=(earlier + timedelta(minutes=1)).isoformat())}
        here, there, local_pairs, drive_pairs = sync._resolve_analysis_pairs(files, drive)
        winners = data.merge({}, here, there, scope='análises')
        self.assertEqual(set(winners), {second, other})
        self.assertEqual(winners[second], drive[second])
        self.assertEqual((local_pairs, drive_pairs), (set(), {(7, '2026-11-01')}))

    def test_local_analysis_wins_when_saved_last(self):
        local_id, drive_id = [str(uuid4()) for _ in range(2)]
        earlier = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
        drive = {drive_id: dict(relative=f'atleta_7/2026-11-01/analise_{drive_id}', content='drive',
                                revision=earlier.isoformat())}
        files = {local_id: dict(pair=(7, '2026-11-01'),
                                relative=Path(f'atleta_7/2026-11-01/analise_{local_id}'),
                                hashes={'metadados.json': 'local'}, revision=earlier + timedelta(minutes=1))}
        here, there, local_pairs, drive_pairs = sync._resolve_analysis_pairs(files, drive)
        self.assertEqual(set(data.merge({}, here, there, scope='análises')), {local_id})
        self.assertEqual((local_pairs, drive_pairs), ({(7, '2026-11-01')}, set()))

    def test_last_save_wins_edits_to_same_analysis(self):
        identity = str(uuid4())
        earlier = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
        drive = {identity: dict(relative=f'atleta_7/2026-11-01/analise_{identity}', content='drive',
                                revision=(earlier + timedelta(minutes=1)).isoformat())}
        files = {identity: dict(pair=(7, '2026-11-01'), relative=Path(drive[identity]['relative']),
                                hashes={'metadados.json': 'local'}, revision=earlier)}
        here, there, local_pairs, drive_pairs = sync._resolve_analysis_pairs(files, drive)
        self.assertEqual(here, drive)
        self.assertEqual((local_pairs, drive_pairs), (set(), {(7, '2026-11-01')}))

    def test_last_local_save_wins_edits_to_same_analysis(self):
        identity = str(uuid4())
        earlier = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
        drive = {identity: dict(relative=f'atleta_7/2026-11-01/analise_{identity}', content='drive',
                                revision=earlier.isoformat())}
        files = {identity: dict(pair=(7, '2026-11-01'), relative=Path(drive[identity]['relative']),
                                hashes={'metadados.json': 'local'}, revision=earlier + timedelta(minutes=1))}
        here, there, local_pairs, drive_pairs = sync._resolve_analysis_pairs(files, drive)
        self.assertEqual(there[identity], here[identity])
        self.assertEqual((local_pairs, drive_pairs), ({(7, '2026-11-01')}, set()))

    def test_equal_save_time_prefers_drive_for_same_analysis(self):
        identity = str(uuid4())
        saved = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
        drive = {identity: dict(relative=f'atleta_7/2026-11-01/analise_{identity}', content='old',
                                revision=saved.isoformat())}
        files = {identity: dict(pair=(7, '2026-11-01'), relative=Path(drive[identity]['relative']),
                                hashes={'metadados.json': 'new'}, revision=saved)}
        here, there, local_pairs, drive_pairs = sync._resolve_analysis_pairs(files, drive)
        self.assertEqual(here, drive)
        self.assertEqual(there, drive)
        self.assertEqual((local_pairs, drive_pairs), (set(), {(7, '2026-11-01')}))

    def test_equal_save_time_prefers_drive_for_distinct_analyses(self):
        local_id, drive_id = [str(uuid4()) for _ in range(2)]
        saved = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
        drive = {drive_id: dict(relative=f'atleta_7/2026-11-01/analise_{drive_id}', content='drive',
                                revision=saved.isoformat())}
        files = {local_id: dict(pair=(7, '2026-11-01'),
                                relative=Path(f'atleta_7/2026-11-01/analise_{local_id}'),
                                hashes={'metadados.json': 'local'}, revision=saved)}
        here, there, local_pairs, drive_pairs = sync._resolve_analysis_pairs(files, drive)
        self.assertEqual(set(data.merge({}, here, there, scope='análises')), {drive_id})
        self.assertEqual((local_pairs, drive_pairs), (set(), {(7, '2026-11-01')}))

    def test_drive_thermal_rows_win_same_collection_and_other_measurements_stay_local(self):
        def snapshot(thermal, gps):
            return {'tables': {
                'grupo_medida': {'1': dict(id_grupo_medida='1', nome='termografia'),
                                 '2': dict(id_grupo_medida='2', nome='GPS')},
                'medida': {'1': dict(id_medida='1', id_grupo_medida='1'),
                           '2': dict(id_medida='2', id_grupo_medida='2')},
                'medida_valor': {
                    'thermal': dict(id_atleta='7', id_medida='1', data='2026-11-01 00:00:00', valor=thermal),
                    'gps': dict(id_atleta='7', id_medida='2', data='2026-11-01 00:00:00', valor=gps),
                },
            }}
        local, remote = snapshot('local', 'local-gps'), snapshot('drive', 'drive-gps')
        comparison = data.prefer_thermal_pairs(local, remote, {(7, '2026-11-01')})
        self.assertEqual(comparison['tables']['medida_valor']['thermal']['valor'], 'drive')
        self.assertEqual(comparison['tables']['medida_valor']['gps']['valor'], 'local-gps')
        self.assertEqual(local['tables']['medida_valor']['thermal']['valor'], 'local')
        opposite = data.prefer_thermal_pairs(remote, local, {(7, '2026-11-01')})
        self.assertEqual(opposite['tables']['medida_valor']['thermal']['valor'], 'local')
        self.assertEqual(opposite['tables']['medida_valor']['gps']['valor'], 'drive-gps')

    def test_duplicate_pair_already_in_drive_uses_latest_revision(self):
        identities = [str(uuid4()) for _ in range(2)]
        saved = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
        drive = {identity: dict(relative=f'atleta_7/2026-11-01/analise_{identity}',
                                revision=(saved + timedelta(minutes=index)).isoformat())
                 for index, identity in enumerate(identities)}
        here, there, _, _ = sync._resolve_analysis_pairs({}, drive)
        self.assertEqual(set(data.merge({}, here, there, scope='análises')), {identities[1]})

    def test_duplicate_local_pair_with_one_matching_drive_identity_keeps_one_winner(self):
        shared, newer = [str(uuid4()) for _ in range(2)]
        saved = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
        drive = {shared: dict(relative=f'atleta_7/2026-11-01/analise_{shared}',
                              revision=saved.isoformat(), content='old')}
        files = {
            shared: dict(pair=(7, '2026-11-01'), relative=Path(drive[shared]['relative']),
                         hashes={'metadados.json': 'old'}, revision=saved),
            newer: dict(pair=(7, '2026-11-01'),
                        relative=Path(f'atleta_7/2026-11-01/analise_{newer}'),
                        hashes={'metadados.json': 'new'}, revision=saved + timedelta(minutes=1)),
        }
        here, there, local_pairs, drive_pairs = sync._resolve_analysis_pairs(files, drive)
        self.assertEqual(set(data.merge({}, here, there, scope='análises')), {newer})
        self.assertEqual((local_pairs, drive_pairs), ({(7, '2026-11-01')}, set()))

    def test_three_way_merge_keeps_independent_edits_additions_and_deletions(self):
        base = {'a': {'v': '1'}, 'b': {'v': '2'}, 'deleted': {'v': '3'}}
        local = {'a': {'v': '10'}, 'b': base['b'], 'local': {'v': '4'}}
        remote = {**base, 'b': {'v': '20'}, 'remote': {'v': '5'}}
        self.assertEqual(data.merge(base, local, remote, scope='teste'),
                         {'a': {'v': '10'}, 'b': {'v': '20'}, 'local': {'v': '4'}, 'remote': {'v': '5'}})
        self.assertEqual(data.merge({}, {'x': {'v': '1'}}, {}, scope='teste'), {'x': {'v': '1'}})

    def test_conflicts_include_initial_id_collision_edit_edit_and_edit_delete(self):
        for base, local, remote in [({}, {'id': 'A'}, {'id': 'B'}),
                                   ({'id': 'old'}, {'id': 'A'}, {'id': 'B'}),
                                   ({'id': 'old'}, {}, {'id': 'B'})]:
            with self.subTest(base=base), self.assertRaisesRegex(ValueError, 'Conflito'):
                data.merge(base, local, remote, scope='teste')

    def test_schema_and_view_changes_are_refused_even_when_tables_match(self):
        local = dict(schema={'tables': {}, 'views': ['v1']}, schema_version='one', keys={}, tables={})
        remote = deepcopy(local)
        remote['schema']['views'] = ['v2']
        with self.assertRaisesRegex(ValueError, 'Estrutura incompatível'):
            data.validate(remote, local)

    def test_explicit_thermal_schema_transition_requires_unchanged_drive_head(self):
        old = dict(schema={'views': [['vw_medida_termografia', 'old']], 'tables': {}},
                   schema_version='old', keys={}, tables={})
        local = dict(schema={'views': [['vw_medida_termografia', 'new'],
                                        ['vw_termografia_zonas', 'zones'],
                                        ['vw_termografia_eva_regional', 'eva']], 'tables': {}},
                     schema_version='new', keys={}, tables={})
        baseline = dict(revision='head', database=old, analyses={})
        remote = dict(database=deepcopy(old), analyses={})
        head = dict(properties={'commit': 'head'})
        sync._validate_schema_transition(baseline, remote, head, local)
        with self.assertRaisesRegex(ValueError, 'Drive mudou'):
            sync._validate_schema_transition(baseline, remote, {'properties': {'commit': 'new-head'}}, local)
        changed = deepcopy(local)
        changed['schema']['tables']['unexpected'] = []
        with self.assertRaisesRegex(ValueError, 'views não correspondem'):
            sync._validate_schema_transition(baseline, remote, head, changed)

    def test_migrated_peers_keep_old_records_as_three_way_base(self):
        old = dict(schema={'views': [['vw_medida_termografia', 'old'], ['other', 'same']],
                           'tables': {}}, schema_version='old', keys={}, tables={})
        local = deepcopy(old)
        local['schema']['views'] = [['vw_medida_termografia', 'new'], ['other', 'same'],
                                    ['vw_termografia_zonas', 'zones'],
                                    ['vw_termografia_eva_regional', 'eva']]
        local['schema_version'] = 'new'
        remote = deepcopy(local)
        before = deepcopy(old)
        result = sync._compatible_database_base(old, local, remote)
        self.assertEqual(result['schema'], local['schema'])
        self.assertIs(result['tables'], old['tables'])
        self.assertEqual(old, before)
        self.assertIs(sync._compatible_database_base(None, local, remote), None)
        self.assertIs(sync._compatible_database_base(local, local, remote), local)
        changed = deepcopy(remote)
        changed['schema']['views'][0][1] = 'different'
        with self.assertRaisesRegex(ValueError, 'Estrutura incompatível'):
            sync._compatible_database_base(old, local, changed)
        changed = deepcopy(old)
        changed['schema']['views'][1][1] = 'unexpected'
        with self.assertRaisesRegex(ValueError, 'base de sincronização incompatível'):
            sync._compatible_database_base(changed, local, remote)

    def test_immutable_commit_chain_refuses_competing_heads_missing_parents_and_cycles(self):
        first, second, competing = [str(uuid4()) for _ in range(3)]
        def entry(identity, parent):
            return dict(id=identity, properties=dict(role='commit', commit=identity, parent=parent))
        class Drive:
            entries = []
            def list(self, **kwargs):
                return self.entries
        drive = Drive()
        drive.entries = [entry(first, 'root'), entry(second, first)]
        self.assertEqual(sync._identity(sync._head(drive)), second)
        for entries in ([entry(first, 'root'), entry(competing, 'root')],
                        [entry(second, first)], [entry(first, second), entry(second, first)]):
            drive.entries = entries
            with self.assertRaises(ValueError):
                sync._head(drive)
