"""Prévias em boa resolução, sem modificar originais ou depender de SQL."""
import base64
from datetime import date
import hashlib
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from PIL import Image
from fastapi.testclient import TestClient
from backend.mac_api.main import create_app
from backend.mac_api.core.wire import decode
from backend.mac_api.modules.thermography import analysis_archive as archive, drafts
from backend.mac_api.modules.thermography.analysis_previews import build_thumbnails
from backend.tests.test_analysis_archive import example_views
from backend.tests.test_thermal_drafts import empty_state


class AnalysisPreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='mac-preview-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, MAC_ANALYSES_DIR=str(self.root/'analyses'),
            MAC_BACKUPS_DIR=str(self.root/'backups'), MAC_API_KEY='preview-test',
            MAC_GOOGLE_CLIENT_ID='', MAC_DB_TARGET='local', MAC_ENVIRONMENT='test')
        env.start(); self.addCleanup(env.stop)
        blocked = patch('psycopg2.connect', side_effect=AssertionError('Prévias não usam SQL'))
        blocked.start(); self.addCleanup(blocked.stop)

    def test_previews_preserve_aspect_and_do_not_upscale_or_mutate_input(self):
        original = Image.new('RGB', (1200,800), 'red')
        small = Image.new('RGB', (80,120), 'blue')
        previews = build_thumbnails(dict(front=original, back=small))
        self.assertEqual(previews['front'].width, 640)
        self.assertLessEqual(previews['front'].height, 480)
        self.assertAlmostEqual(previews['front'].width/previews['front'].height, 1.5, delta=.01)
        self.assertEqual(previews['back'].size, small.size)
        self.assertEqual(original.size, (1200,800))

    def test_archive_summary_includes_both_views_without_changing_original_files(self):
        root = self.root/'analyses'/'example'
        for folder, size, color in [('frente',(1200,800),'red'), ('verso',(800,1200),'blue')]:
            (root/folder).mkdir(parents=True)
            Image.new('RGB', size, color).save(root/folder/'original.png')
        paths = [root/folder/'original.png' for folder in ('frente','verso')]
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
        metadata = dict(analysis_id='test', athlete_id=1, athlete_name='Teste',
            collected_at='2026-11-14', created_at='2026-11-14T00:00:00+00:00', mass=75., pain_score=0, observations='')
        summary = archive._summary(root, metadata)
        self.assertEqual(set(summary['thumbnails']), {'front','back'})
        self.assertEqual(summary['thumbnails']['front'].width, 640)
        self.assertEqual(summary['thumbnails']['back'].height, 480)
        self.assertEqual(summary['thumbnails']['front'].getpixel((0,0)), (255,0,0))
        self.assertEqual(summary['thumbnails']['back'].getpixel((0,0)), (0,0,255))
        self.assertEqual(before, [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths])
        self.assertLessEqual(summary['thumbnail'].width,170)

    def test_partial_summary_preserves_both_views_and_their_rotation(self):
        state = empty_state()
        state['step'] = 1
        for view, size, color, rotation in [('front',(1200,800),'red',90), ('back',(800,1200),'blue',0)]:
            buffer = io.BytesIO(); Image.new('RGB',size,color).save(buffer,format='PNG')
            state['uploads'][view] = dict(name=view+'.png',rotation=rotation,
                content=base64.b64encode(buffer.getvalue()).decode('ascii'))
        entry = drafts.save(state)
        self.assertEqual(set(entry['thumbnails']), {'front','back'})
        self.assertEqual(entry['thumbnails']['front'].size, (320,480))
        self.assertEqual(entry['thumbnails']['back'].size, (320,480))
        path = drafts.directory(entry['id'])/'draft.json'
        before = path.read_bytes()
        drafts.summary(entry['id'])
        self.assertEqual(before,path.read_bytes())

    def test_partial_summary_with_one_or_no_views_does_not_invent_images(self):
        state = empty_state()
        buffer = io.BytesIO(); Image.new('RGB',(80,120),'red').save(buffer,format='PNG')
        state['uploads']['back'] = dict(name='costas.png',rotation=0,
            content=base64.b64encode(buffer.getvalue()).decode('ascii'))
        entry = drafts.save(state)
        self.assertEqual(set(entry['thumbnails']), {'back'})
        empty = drafts.save(empty_state())
        self.assertEqual(empty['thumbnails'], {})
        self.assertIsInstance(empty['thumbnail'], Image.Image)

    def test_api_list_transports_the_two_views_and_keeps_legacy_thumbnail(self):
        views = example_views()
        views['back'] = {**views['back'], 'image': Image.new('RGB',(8,12),'blue')}
        archive.save_analysis(athlete_id=1,athlete_name='Teste',collected_at=date(2026,11,14),
            mass=75.,pain_score=0,views=views)
        client = TestClient(create_app())
        response = client.get('/api/v1/thermography/analyses?athlete_id=1',headers={'X-API-Key':'preview-test'})
        self.assertEqual(response.status_code,200,response.text)
        entry = decode(response.json())[0]
        self.assertEqual(set(entry['thumbnails']), {'front','back'})
        self.assertIsInstance(entry['thumbnail'],Image.Image)
        self.assertEqual(entry['thumbnails']['back'].getpixel((0,0)), (0,0,255))
