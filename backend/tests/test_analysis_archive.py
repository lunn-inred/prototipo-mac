import json
import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from backend.mac_api.main import create_app
from backend.mac_api.core.wire import encode, decode
from backend.mac_api.modules.thermography import analysis_archive as archive
from backend.mac_api.modules.thermography.thermal_analysis import timeline_view_at_threshold, compare_hot_masks


def example_views():
    shape = (12, 8)
    masks = {'right': np.zeros(shape, dtype=bool), 'left': np.zeros(shape, dtype=bool)}
    masks['right'][:, :4] = True; masks['left'][:, 4:] = True
    source = dict(image=Image.new('RGB', (8, 12), 'orange'),
                  temperatures=np.linspace(20, 40, 96, dtype=np.float32).reshape(shape),
                  segmentation_masks=masks, boxes={'right': dict(left=0, top=0, width=4, height=12),
                                                   'left': dict(left=4, top=0, width=4, height=12)},
                  minimum_temperature=20., maximum_temperature=40., default_threshold=34.,
                  image_rotation=90, original_filename='coleta.jpeg',
                  part_settings={side: dict(cuts=[25, 50, 75], axis='vertical', foot_at_end=True)
                                 for side in ('right', 'left')})
    return {'front': source, 'back': source}


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='mac-analysis-tests-')
        self.addCleanup(self.directory.cleanup)
        environment = patch.dict(os.environ, MAC_ANALYSES_DIR=self.directory.name, MAC_API_KEY='test-local-key')
        environment.start(); self.addCleanup(environment.stop)
        self.client = TestClient(create_app())
        self.headers = {'X-API-Key': 'test-local-key'}

    def save(self):
        return archive.save_analysis(athlete_id=123, athlete_name='João / teste', collected_at=date(2026,10,14),
                                     mass=75., pain_score=2, observations='Observação com acento', views=example_views())

    def test_files_metadata_reload_and_comparison_survive_new_client(self):
        saved = self.save()
        folder = Path(self.directory.name)/'atleta_123'/'2026-10-14'/f'analise_{saved["id"]}'
        self.assertTrue((folder/'frente/original.png').is_file())
        self.assertTrue((folder/'verso/mascara_esquerda.png').is_file())
        metadata = json.loads((folder/'metadados.json').read_text())
        self.assertEqual(metadata['athlete_name'], 'João / teste')
        self.assertEqual(metadata['views']['front']['part_settings']['right']['boundaries_pixels'], [3,6,9])
        self.assertNotIn('database_reference', metadata)
        with patch('psycopg2.connect', side_effect=AssertionError('Banco não deve ser acessado')):
            client = TestClient(create_app())
            response = client.get('/api/v1/thermography/analyses?athlete_id=123', headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(decode(response.json())), 1)
            response = client.get(f'/api/v1/thermography/analyses/123/2026-10-14/{saved["id"]}', headers=self.headers)
            self.assertEqual(response.status_code, 200)
            entry = decode(response.json())
        np.testing.assert_array_equal(entry['views']['front']['temperatures'], example_views()['front']['temperatures'])
        np.testing.assert_array_equal(entry['views']['front']['segmentation_masks']['right'], example_views()['front']['segmentation_masks']['right'])
        basal = timeline_view_at_threshold(entry['views']['front'], 34.)
        current = timeline_view_at_threshold(entry['views']['front'], 36.)
        self.assertLess(current['metrics']['right']['hot_pixels'], basal['metrics']['right']['hot_pixels'])
        comparison = compare_hot_masks(basal['hot_masks']['right'], current['hot_masks']['right'],
                                       basal['boxes']['right'], current['boxes']['right'])
        self.assertGreater(comparison['resolved_pixels'], 0)

    def test_same_day_saves_use_distinct_ids_and_isolate_players(self):
        first, second = self.save(), self.save()
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(len(archive.list_analyses(123)), 2)
        self.assertEqual(archive.list_analyses(124), [])

    def test_invalid_input_leaves_no_partial_directory(self):
        views = example_views(); views['front']['segmentation_masks']['right'] = np.zeros((1,1), dtype=bool)
        with self.assertRaises(ValueError):
            archive.save_analysis(athlete_id=123, athlete_name='Teste', collected_at=date.today(), views=views)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_failed_write_cleans_only_pending_analysis(self):
        saved = self.save()
        with patch('numpy.save', side_effect=OSError('Falha simulada')):
            with self.assertRaises(OSError): self.save()
        self.assertEqual([entry['id'] for entry in archive.list_analyses(123)], [saved['id']])
        self.assertFalse(list(Path(self.directory.name).rglob('.pending_*')))

    def test_invalid_id_and_symlink_cannot_escape_root(self):
        with self.assertRaises(ValueError): archive.load_analysis(123,date.today(),'../../fora')
        with TemporaryDirectory() as outside:
            (Path(self.directory.name)/'atleta_123').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError): archive.list_analyses(123)

    def test_api_save_authentication_and_missing_analysis(self):
        payload = dict(athlete_id=123, athlete_name='Atleta', collected_at='2026-10-14', views=encode(example_views()))
        self.assertEqual(self.client.post('/api/v1/thermography/analyses', json=payload).status_code, 401)
        response = self.client.post('/api/v1/thermography/analyses', headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.client.get('/api/v1/thermography/analyses/124/2026-10-14/'+decode(response.json())['id'], headers=self.headers).status_code, 404)

    def test_default_relative_path_is_independent_of_current_directory(self):
        with patch.dict(os.environ, MAC_ANALYSES_DIR='./data/thermography'):
            expected = Path(archive.__file__).resolve().parents[4]/'data/thermography'
            with patch('pathlib.Path.cwd', return_value=Path('/tmp')):
                self.assertEqual(archive.analyses_directory(), expected.resolve())

    def test_frozen_app_saves_beside_binary_not_temporary_extraction(self):
        with patch.dict(os.environ, MAC_ANALYSES_DIR='./data/thermography'), \
             patch.object(archive.sys, 'frozen', True, create=True), \
             patch.object(archive.sys, 'executable', '/tmp/mac-archive-binary/MAC Performance'):
            self.assertEqual(archive.analyses_directory(), Path('/tmp/mac-archive-binary/data/thermography'))
