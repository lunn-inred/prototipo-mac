"""Finalização e backup de rascunhos no mac_test descartável."""
from datetime import date
from contextlib import contextmanager
import base64
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from fastapi.testclient import TestClient
from backend.mac_api.main import create_app
from backend.mac_api.core.database import database_write_connection
from backend.mac_api.core.wire import encode, decode
from backend.mac_api.modules.thermography import drafts, analysis_archive as archive
from backend.tests import test_backup_postgres as fixture
from backend.tests.test_analysis_archive import example_views
from backend.tests.test_thermal_drafts import empty_state


@unittest.skipUnless(os.getenv('MAC_TEST_DB_ENABLED') == '1', 'PostgreSQL descartável não habilitado')
class ThermalDraftPostgresTests(unittest.TestCase):
    athlete = fixture.BackupPostgresTests.athlete
    register = fixture.BackupPostgresTests.register
    backup = fixture.BackupPostgresTests.backup
    restore = fixture.BackupPostgresTests.restore

    def setUp(self):
        fixture.BackupPostgresTests.setUp(self)
        environment = patch.dict(os.environ, MAC_API_KEY='draft-pg', MAC_GOOGLE_CLIENT_ID='')
        environment.start(); self.addCleanup(environment.stop)
        self.client = TestClient(create_app())
        self.headers = {'X-API-Key': 'draft-pg'}

    def save_draft(self, state, **extra):
        response = self.client.post('/api/v1/thermography/drafts', headers=self.headers, json=dict(state=encode(state), **extra))
        self.assertEqual(response.status_code, 200, response.text)
        return decode(response.json())

    def payload(self, athlete, draft, **extra):
        return dict(athlete_id=athlete, athlete_name='Teste', collected_at='2026-11-20', mass=80., pain_score=0,
                    observations='', views=encode(example_views()), draft_id=draft['id'], draft_revision=draft['created_at'], **extra)

    def test_empty_draft_promotes_to_complete_using_summary_date_and_same_uuid(self):
        draft = self.save_draft(empty_state())
        athlete = self.athlete('Jogador final')
        response = self.client.post('/api/v1/thermography/analyses/register', headers=self.headers, json=self.payload(athlete, draft))
        self.assertEqual(response.status_code, 201, response.text)
        entry = decode(response.json())['analysis']
        self.assertEqual(entry['id'], draft['id'])
        self.assertEqual(entry['collected_at'], date(2026,11,20))
        self.assertFalse(drafts.directory(draft['id']).exists())
        self.assertEqual(len(archive.list_analyses(athlete)), 1)
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT data_coleta::date,massa,eva_dor FROM public.vw_medida_termografia WHERE id_atleta=%s', (athlete,))
            self.assertEqual(cursor.fetchall(), [(date(2026,11,20), 80, 0)])

    def test_incomplete_edit_updates_database_before_successful_finalization(self):
        athlete = self.athlete()
        original, _ = self.register(athlete)
        state = empty_state()
        state['draft'].update(player=athlete, mass=None, pain=0)
        state['source'] = {key: original[key] for key in ('id','athlete_id','collected_at','created_at')}
        state['source']['collected_at'] = state['source']['collected_at'].isoformat()
        draft = self.save_draft(state)
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT massa FROM public.vw_medida_termografia WHERE id_atleta=%s', (athlete,))
            self.assertIsNone(cursor.fetchone()[0])
            cursor.execute('SELECT eva_dor FROM public.vw_medida_termografia WHERE id_atleta=%s', (athlete,))
            self.assertEqual(cursor.fetchone()[0], 0)
        response = self.client.put(f'/api/v1/thermography/analyses/{athlete}/2026-11-01/{original["id"]}', headers=self.headers,
            json=self.payload(athlete, draft, expected_revision=original['created_at']))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(drafts.directory(draft['id']).exists())
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT data_coleta::date,massa FROM public.vw_medida_termografia WHERE id_atleta=%s', (athlete,))
            self.assertEqual(cursor.fetchall(), [(date(2026,11,20), 80)])

    def test_complete_file_failure_rolls_back_sql_and_preserves_draft_for_retry(self):
        athlete = self.athlete()
        draft = self.save_draft(empty_state())
        with patch('numpy.save', side_effect=OSError('Falha simulada')):
            response = self.client.post('/api/v1/thermography/analyses/register', headers=self.headers, json=self.payload(athlete, draft))
        self.assertEqual(response.status_code, 503)
        self.assertTrue(drafts.directory(draft['id']).is_dir())
        self.assertEqual(archive.list_analyses(athlete), [])
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT count(*) FROM public.medida_valor WHERE id_atleta=%s', (athlete,))
            self.assertEqual(cursor.fetchone()[0], 0)
        response = self.client.post('/api/v1/thermography/analyses/register', headers=self.headers, json=self.payload(athlete, draft))
        self.assertEqual(response.status_code, 201, response.text)

    def test_final_overwrite_is_still_explicit_and_stale_draft_cannot_finalize(self):
        athlete = self.athlete()
        original, _ = self.register(athlete, day=date(2026,11,20))
        draft = self.save_draft(empty_state())
        body = self.payload(athlete, draft)
        conflict = self.client.post('/api/v1/thermography/analyses/register', headers=self.headers, json=body)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()['detail']['code'], 'analysis_date_conflict')
        self.assertEqual(archive.list_analyses(athlete)[0]['id'], original['id'])
        stale = self.client.post('/api/v1/thermography/analyses/register', headers=self.headers,
            json={**body, 'overwrite': True, 'draft_revision': 'antiga'})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()['detail']['code'], 'analysis_changed')
        saved = self.client.post('/api/v1/thermography/analyses/register', headers=self.headers, json={**body, 'overwrite': True})
        self.assertEqual(saved.status_code, 201, saved.text)
        self.assertEqual(archive.list_analyses(athlete)[0]['id'], draft['id'])

    def test_backup_restore_preserves_local_draft_athlete_and_partial_measures(self):
        backup = self.backup()
        athlete = self.athlete('Atleta do rascunho')
        state = empty_state(); state['draft'].update(player=athlete, mass=72.5, pain=0)
        draft = self.save_draft(state)
        result = self.restore(backup['local_copy'])
        self.assertEqual(result['preserved_local'], 1)
        self.assertTrue(drafts.directory(draft['id']).is_dir())
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT nome FROM public.atleta WHERE id_atleta=%s', (athlete,))
            self.assertEqual(cursor.fetchone()[0], 'Atleta do rascunho')
            cursor.execute('SELECT count(*) FROM public.medida_valor')
            self.assertEqual(cursor.fetchone()[0], 3)
            cursor.execute('SELECT massa,eva_dor,observacoes FROM public.vw_medida_termografia WHERE id_atleta=%s', (athlete,))
            self.assertEqual(cursor.fetchone(), (72.5, 0, 'Início'))
        # A revisão lógica continua válida após remapeamento dos IDs SQL no restore.
        self.save_draft(state, draft_id=draft['id'], expected_revision=draft['created_at'])

    def partial_rows(self, athlete):
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('''SELECT m.nome,v.valor,v.valor_texto,v.data::date FROM public.medida_valor v
                JOIN public.medida m USING(id_medida) JOIN public.grupo_medida g USING(id_grupo_medida)
                WHERE v.id_atleta=%s AND lower(trim(g.nome))='termografia' ORDER BY m.nome''', (athlete,))
            return cursor.fetchall()

    def test_metadata_is_inserted_and_updated_without_duplicate_or_fake_values(self):
        athlete = self.athlete()
        state = empty_state(); state['draft'].update(player=athlete, mass=73.5, pain=0)
        entry = self.save_draft(state)
        self.assertEqual(self.partial_rows(athlete), [
            ('EVA_DOR', 0, None, date(2026,11,1)), ('MASSA', 73.5, None, date(2026,11,1)),
            ('OBSERVACOES', None, 'Início', date(2026,11,1))])
        state['draft'].update(mass=74., pain=None, notes='', collected_at='2026-11-02')
        changed = self.save_draft(state, draft_id=entry['id'], expected_revision=entry['created_at'])
        self.assertEqual(entry['id'], changed['id'])
        self.assertEqual(self.partial_rows(athlete), [('MASSA', 74., None, date(2026,11,2))])
        second = self.athlete('Outro atleta')
        state['draft']['player'] = second
        self.save_draft(state, draft_id=changed['id'], expected_revision=changed['created_at'])
        self.assertEqual(self.partial_rows(athlete), [])
        self.assertEqual(self.partial_rows(second), [('MASSA', 74., None, date(2026,11,2))])

    def test_calculated_view_saves_real_counts_without_inventing_the_other_view(self):
        athlete = self.athlete()
        state = empty_state(); state['draft'].update(player=athlete, pain=0)
        state['step'] = 5
        view = example_views()['front']
        buffer = io.BytesIO(); view['image'].save(buffer, format='PNG')
        state['uploads']['front'] = dict(name='frente.png', content=base64.b64encode(buffer.getvalue()).decode(), rotation=0)
        state['items']['front:test'] = dict(minimum_temperature=20., maximum_temperature=40., threshold_temperature=34.,
            saved_analysis=dict(temperatures=view['temperatures'], masks=view['segmentation_masks'], boxes=view['boxes']))
        saved = self.save_draft(state)
        rows = {row[0]: row[1] for row in self.partial_rows(athlete)}
        metrics = archive._validate_view(view)[3]['metrics']
        self.assertEqual(rows['PERNA_DIREITA_FRENTE'], metrics['right']['hot_pixels'])
        self.assertEqual(rows['PERNA_ESQUERDA_FRENTE'], metrics['left']['hot_pixels'])
        self.assertEqual(rows['SOMA_FRENTE'], metrics['right']['hot_pixels']+metrics['left']['hot_pixels'])
        self.assertNotIn('MASSA', rows)
        self.assertNotIn('SOMA_VERSO', rows)
        # Voltar a uma etapa anterior não descarta matrizes ainda válidas.
        state['step'] = 0
        self.save_draft(state, draft_id=saved['id'], expected_revision=saved['created_at'])
        self.assertEqual({row[0]: row[1] for row in self.partial_rows(athlete)}, rows)

    def test_finalizing_own_partial_collection_does_not_require_overwrite(self):
        athlete = self.athlete()
        state = empty_state(); state['draft'].update(player=athlete, mass=73., collected_at='2026-11-20')
        entry = self.save_draft(state)
        with patch('numpy.save', side_effect=OSError('Falha de arquivo simulada')):
            failed = self.client.post('/api/v1/thermography/analyses/register', headers=self.headers, json=self.payload(athlete, entry))
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(next(row[1] for row in self.partial_rows(athlete) if row[0]=='MASSA'), 73.)
        self.assertTrue(drafts.directory(entry['id']).is_dir())
        response = self.client.post('/api/v1/thermography/analyses/register', headers=self.headers, json=self.payload(athlete, entry))
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(decode(response.json())['analysis']['id'], entry['id'])
        self.assertEqual(len(self.partial_rows(athlete)), 8)

    def test_publication_and_transaction_failure_preserve_sql_and_previous_draft(self):
        athlete = self.athlete()
        state = empty_state(); state['draft'].update(player=athlete, mass=73.)
        entry = self.save_draft(state)
        state['draft']['mass'] = 81.
        original_replace = drafts.os.replace
        def fail_publish(source, destination):
            if Path(source).name.startswith('.pending-'):
                raise OSError('Falha de publicação simulada')
            return original_replace(source, destination)
        @contextmanager
        def fail_commit():
            with database_write_connection() as connection:
                yield connection
                raise OSError('Falha de transação simulada')
        for failure in (patch.object(drafts.os, 'replace', side_effect=fail_publish),
                        patch.object(drafts, 'database_write_connection', fail_commit)):
            with failure:
                response = self.client.post('/api/v1/thermography/drafts', headers=self.headers,
                    json=dict(state=encode(state), draft_id=entry['id'], expected_revision=entry['created_at']))
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(drafts.load(entry['id'])['created_at'], entry['created_at'])
            self.assertEqual(next(row[1] for row in self.partial_rows(athlete) if row[0]=='MASSA'), 73.)

    def test_external_sql_change_is_not_silently_overwritten(self):
        athlete = self.athlete()
        state = empty_state(); state['draft'].update(player=athlete, mass=73.)
        entry = self.save_draft(state)
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('UPDATE public.medida_valor SET valor=90 WHERE id_atleta=%s AND valor IS NOT NULL', (athlete,))
        response = self.client.post('/api/v1/thermography/drafts', headers=self.headers,
            json=dict(state=encode(state), draft_id=entry['id'], expected_revision=entry['created_at'], overwrite=True))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['detail']['code'], 'analysis_changed')
        completed = self.client.post('/api/v1/thermography/analyses/register', headers=self.headers,
            json=self.payload(athlete, entry, overwrite=True))
        self.assertEqual(completed.status_code, 409, completed.text)
        self.assertEqual(completed.json()['detail']['code'], 'analysis_changed')

    def test_first_step_ui_saves_available_data_to_database_and_updates_it(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_data.clear(); self.addCleanup(st.cache_data.clear)
        athlete = self.athlete()
        script = f'''\nfrom frontend.streamlit.components.thermography.wizard import render_wizard
from frontend.streamlit.components.thermography.save_flow import render_pending_save
render_wizard({{{athlete}: dict(nome='Teste', id_atleta={athlete})}})
render_pending_save()
'''
        def http(method, url, **kwargs):
            kwargs.pop('timeout', None)
            return self.client.request(method, urlsplit(url).path, **kwargs)
        with patch('frontend.streamlit.api_client.service_gateway._http_request', side_effect=http):
            app = AppTest.from_string(script).run()
            app.selectbox(key='thermography_player').set_value(athlete)
            app.number_input(key='thermography_mass').set_value(73.5).run()
            self.assertTrue(app.button(key='thermal_next').disabled)
            app.button(key='thermal_save_analysis').click().run()
            app.button(key='thermal_save_confirm').click().run()
            self.assertFalse(app.exception)
            self.assertEqual([row[:3] for row in self.partial_rows(athlete)], [('MASSA', 73.5, None)])
            entry = drafts.list_saved(athlete)[0]
            identity = entry['id']
            self.assertNotIn('thermal_saved_draft', app.session_state)
            self.assertIsNone(app.selectbox(key='thermography_player').value)
            self.assertEqual(app.toast[0].value, 'Análise parcial salva. Você poderá visualizá-la em Ver análises anteriores.')
            # A edição posterior começa reabrindo a análise persistida, não o formulário limpo.
            from frontend.streamlit.components.thermography import history
            state = {}
            with patch.object(history.st, 'session_state', state):
                history.load_into_wizard(drafts.load(identity))
            app = AppTest.from_string(script)
            for key, value in state.items():
                app.session_state[key] = value
            app.run()
            app.number_input(key='thermography_mass').set_value(75.).run()
            app.button(key='thermal_save_analysis').click().run()
            app.button(key='thermal_save_confirm').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(drafts.list_saved(athlete)[0]['id'], identity)
            self.assertNotIn('thermal_saved_draft', app.session_state)
            self.assertEqual(app.session_state['thermal_step'], 0)
            self.assertEqual([row[:3] for row in self.partial_rows(athlete)], [('MASSA', 75., None)])

    def test_moved_partial_edit_backup_does_not_resurrect_original_sql(self):
        athlete = self.athlete()
        original, _ = self.register(athlete)
        backup = self.backup()
        state = empty_state(); state['draft'].update(player=athlete, mass=82., collected_at='2026-11-02')
        state['source'] = {key: original[key] for key in ('id','athlete_id','collected_at','created_at')}
        state['source']['collected_at'] = state['source']['collected_at'].isoformat()
        saved = self.save_draft(state)
        self.restore(backup['local_copy'])
        self.assertEqual({row[3] for row in self.partial_rows(athlete)}, {date(2026,11,2)})
        self.assertEqual(next(row[1] for row in self.partial_rows(athlete) if row[0]=='MASSA'), 82.)
        self.save_draft(state, draft_id=saved['id'], expected_revision=saved['created_at'])

    def test_backup_restores_remote_partial_with_measures_and_allows_update(self):
        import shutil
        athlete = self.athlete()
        state = empty_state(); state['draft'].update(player=athlete, mass=73., pain=0)
        saved = self.save_draft(state)
        backup = self.backup()
        shutil.rmtree(drafts.directory(saved['id']))
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute('DELETE FROM public.medida_valor WHERE id_atleta=%s', (athlete,))
        self.restore(backup['local_copy'])
        self.assertEqual(len(self.partial_rows(athlete)), 3)
        state['draft']['mass'] = 77.
        self.save_draft(state, draft_id=saved['id'], expected_revision=saved['created_at'])
        self.assertEqual(next(row[1] for row in self.partial_rows(athlete) if row[0]=='MASSA'), 77.)
