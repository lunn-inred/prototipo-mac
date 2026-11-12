import base64
from contextlib import contextmanager
from datetime import date
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from backend.mac_api.main import create_app
from backend.mac_api.core.wire import encode, decode
from backend.mac_api.modules.thermography import drafts, analysis_archive as archive
from backend.mac_api.modules.thermography.analysis_registration import AnalysisChangedError
from backend.mac_api.modules.backups import bundle
from backend.tests.test_analysis_archive import example_views


def empty_state():
    return dict(step=0, draft=dict(player=None, mass=None, pain=None, notes='Início', collected_at='2026-11-01'),
                uploads={}, items={}, source=None)


class ThermalDraftTests(unittest.TestCase):
    @contextmanager
    def fake_connection(self, conflict=False):
        database = MagicMock()
        cursor = database.cursor.return_value.__enter__.return_value
        has_data = conflict
        def execute(command, values=()):
            nonlocal has_data
            cursor.fetchone.return_value = (1,)
            cursor.fetchall.return_value = []
            if 'SELECT nome' in command:
                cursor.fetchone.return_value = ('Jogador',)
            elif 'count(*)' in command.lower():
                cursor.fetchone.return_value = (int(has_data),)
            elif command.lstrip().startswith('DELETE'):
                has_data = False
            elif 'SELECT m.id_medida' in command:
                cursor.fetchall.return_value = [(1, 'OBSERVACOES')]
        cursor.execute.side_effect = execute
        yield database

    def setUp(self):
        self.directory = TemporaryDirectory(prefix='mac-draft-test-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        env = patch.dict(os.environ, MAC_ANALYSES_DIR=str(self.root / 'analyses'), MAC_BACKUPS_DIR=str(self.root / 'backups'),
                         MAC_DB_TARGET='local', MAC_API_KEY='draft-test')
        env.start(); self.addCleanup(env.stop)
        self.client = TestClient(create_app())
        self.headers = {'X-API-Key': 'draft-test'}

    def test_empty_draft_roundtrip_survives_new_client_without_database_writes(self):
        with patch('psycopg2.connect', side_effect=AssertionError('Não usar banco sem atleta')):
            response = self.client.post('/api/v1/thermography/drafts', headers=self.headers, json={'state': encode(empty_state())})
            self.assertEqual(response.status_code, 200, response.text)
            entry = decode(response.json())
            self.assertTrue(entry['is_draft'])
            self.assertEqual(entry['athlete_id'], 0)
            client = TestClient(create_app())
            loaded = decode(client.get(f'/api/v1/thermography/drafts/{entry["id"]}', headers=self.headers).json())
            self.assertEqual(loaded['state'], empty_state())
            listing = decode(client.get('/api/v1/thermography/analyses?athlete_id=0&include_drafts=true', headers=self.headers).json())
            self.assertEqual(len(listing), 1)
            self.assertEqual(client.get('/api/v1/thermography/analyses?athlete_id=0', headers=self.headers).json(), [])

    def test_same_id_is_updated_and_stale_revision_is_refused(self):
        original = drafts.save(empty_state())
        state = empty_state(); state['draft']['notes'] = 'Atualizado'
        updated = drafts.save(state, identity=original['id'], expected_revision=original['created_at'])
        self.assertEqual(original['id'], updated['id'])
        with self.assertRaises(AnalysisChangedError):
            drafts.save(empty_state(), identity=original['id'], expected_revision=original['created_at'], overwrite=True)
        self.assertEqual(drafts.load(original['id'])['state']['draft']['notes'], 'Atualizado')

    def test_one_image_and_manual_corrections_roundtrip_without_pickle(self):
        state = empty_state()
        source = example_views()['front']
        buffer = io.BytesIO(); source['image'].save(buffer, format='PNG')
        state['uploads']['front'] = dict(name='primeira.png', rotation=0, content=base64.b64encode(buffer.getvalue()).decode())
        seeds = np.zeros((12, 8), dtype=np.int8); seeds[2, 2] = -1
        state['items']['front:test'] = dict(mask_seeds={'left': seeds}, part_settings_v4=source['part_settings'],
            manual_boxes=source['boxes'], minimum_temperature=20., maximum_temperature=40.,
            saved_analysis=dict(masks=source['segmentation_masks'], temperatures=source['temperatures'], boxes=source['boxes'],
                                minimum_temperature=20., maximum_temperature=40., colorbar_box=None, image_rotation=0))
        entry = drafts.save(state)
        loaded = drafts.load(entry['id'])
        np.testing.assert_array_equal(loaded['state']['items']['front:test']['mask_seeds']['left'], seeds)
        np.testing.assert_array_equal(loaded['state']['items']['front:test']['saved_analysis']['temperatures'], source['temperatures'])
        self.assertEqual(loaded['state']['uploads']['front']['content'], state['uploads']['front']['content'])
        payload = json.loads((drafts.directory(entry['id']) / 'draft.json').read_text())
        self.assertEqual(payload['state']['items']['front:test']['mask_seeds']['left']['type'], 'array')

    def test_partial_edit_does_not_replace_the_complete_archive(self):
        original = archive.save_analysis(athlete_id=1, athlete_name='Original', collected_at=date(2026, 11, 1),
                                         mass=75., pain_score=0, views=example_views())
        state = empty_state()
        state['draft']['player'] = 1
        state['source'] = {key: original[key] for key in ('id', 'athlete_id', 'collected_at', 'created_at')}
        state['source']['collected_at'] = state['source']['collected_at'].isoformat()
        with patch.object(drafts, 'database_write_connection', self.fake_connection):
            entry = drafts.save(state)
        self.assertEqual(entry['id'], original['id'])
        self.assertEqual(len(archive.list_analyses(1)), 1)
        self.assertEqual(archive.load_analysis(1, date(2026,11,1), original['id'])['mass'], 75.)

    def test_conflict_requires_confirmation_before_updating_sql(self):
        archive.save_analysis(athlete_id=1, athlete_name='Original', collected_at=date(2026,11,1), mass=75., pain_score=0, views=example_views())
        @contextmanager
        def connection():
            with self.fake_connection(conflict=True) as database:
                yield database
        state = empty_state(); state['draft']['player'] = 1
        with patch.object(drafts, 'database_write_connection', connection):
            response = self.client.post('/api/v1/thermography/drafts', headers=self.headers, json={'state': encode(state)})
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(response.json()['detail']['code'], 'analysis_date_conflict')
            confirmed = self.client.post('/api/v1/thermography/drafts', headers=self.headers, json={'state': encode(state), 'overwrite': True})
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(len(archive.list_analyses(1)), 1)

    def test_drafts_are_included_in_backup_and_reconciled_without_sql_pairs(self):
        entry = drafts.save(empty_state())
        index = bundle.index_analyses(self.root / 'analyses')
        key = f'draft:{entry["id"]}'
        self.assertIn(key, index)
        self.assertIsNone(index[key]['pair'])
        winners, retained = bundle.reconcile(index, index)
        self.assertEqual(len(winners), 1)
        self.assertTrue(retained[0]['is_draft'])

    def test_failed_publication_preserves_previous_draft(self):
        entry = drafts.save(empty_state())
        original_replace = drafts.os.replace
        def fail(source, destination):
            if Path(source).name.startswith('.pending-'):
                raise OSError('Falha simulada')
            return original_replace(source, destination)
        with patch.object(drafts.os, 'replace', side_effect=fail):
            with self.assertRaises(OSError):
                drafts.save(empty_state(), identity=entry['id'], expected_revision=entry['created_at'])
        self.assertEqual(drafts.load(entry['id'])['created_at'], entry['created_at'])

    def test_invalid_state_or_remote_target_never_opens_database(self):
        with patch('psycopg2.connect') as connect:
            state = empty_state(); state['step'] = 9
            with self.assertRaises(ValueError):
                drafts.save(state)
            with patch.dict(os.environ, MAC_DB_TARGET='supabase'):
                with self.assertRaises(ValueError):
                    drafts.save(empty_state())
            connect.assert_not_called()
