"""Regressões de carregamento e cache, sem acesso ao banco real."""
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
import unittest

import httpx
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from backend.mac_api.main import create_app
from frontend.streamlit.api_client import service_gateway as gateway


class ReferenceCacheTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)

    def test_repeated_reads_reuse_responses_and_return_independent_copies(self):
        with patch.object(gateway, '_request', return_value=[{'id_atleta': 1}]) as request:
            first = gateway.load_athletes()
            first[0]['nome'] = 'Edição local'
            self.assertNotIn('nome', gateway.load_athletes()[0])
            gateway.load_jump_collections()
            gateway.load_jump_collections()
            self.assertEqual(request.call_count, 2)

    def test_api_url_and_credentials_isolate_cached_data(self):
        with patch.object(gateway, '_request', return_value=[]) as request, \
             patch.object(gateway, 'api_key', return_value='a') as credential, \
             patch.object(gateway, 'api_base_url', return_value='http://api-one') as base_url:
            gateway.load_athletes()
            gateway.load_athletes()
            credential.return_value = 'b'
            gateway.load_athletes()
            base_url.return_value = 'http://api-two'
            gateway.load_athletes()
            self.assertEqual(request.call_count, 3)

    def test_confirmed_mutations_invalidate_reference_data(self):
        today = date.today()
        mutations = [
            lambda: gateway.create_athlete(name='Teste'),
            lambda: gateway.update_athlete(1, name='Teste'),
            lambda: gateway.deactivate_athlete(1),
            lambda: gateway.reactivate_athlete(1),
            lambda: gateway.create_jump({}),
            lambda: gateway.update_jump(1, today, {}),
            lambda: gateway.delete_jump(1, today),
            lambda: gateway.import_jump_payload([]),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                st.cache_data.clear()
                def response(method, path, **kwargs):
                    if method == 'GET':
                        return []
                    return {'id_atleta': 1, 'inserted_measurements': 1, 'deleted_measurements': 1}
                with patch.object(gateway, '_request', side_effect=response) as request:
                    gateway.load_athletes()
                    gateway.load_jump_collections()
                    mutation()
                    gateway.load_athletes()
                    gateway.load_jump_collections()
                    self.assertEqual(request.call_count, 5)

    def test_failed_mutation_preserves_read_cache(self):
        with patch.object(gateway, '_request', return_value=[]) as request:
            gateway.load_athletes()
            request.side_effect = gateway.ApiClientError('Falha simulada')
            with self.assertRaises(gateway.ApiClientError):
                gateway.deactivate_athlete(1)
            self.assertEqual(gateway.load_athletes(), [])
            self.assertEqual(request.call_count, 2)

    def test_http_connections_reused_but_authentication_remains_per_request(self):
        gateway._http_client.cache_clear()
        self.addCleanup(gateway._http_client.cache_clear)
        response = httpx.Response(200, json=[], request=httpx.Request('GET', 'http://test/read'))
        with patch.object(gateway.httpx, 'Client') as factory, \
             patch.object(gateway.atexit, 'register') as register, \
             patch.object(gateway, 'api_key', side_effect=['a', 'b']):
            factory.return_value.request.return_value = response
            gateway._request('GET', '/read')
            gateway._request('GET', '/read')
            factory.assert_called_once_with()
            register.assert_called_once_with(factory.return_value.close)
            calls = factory.return_value.request.call_args_list
            self.assertEqual(calls[0].kwargs['headers']['X-API-Key'], 'a')
            self.assertEqual(calls[1].kwargs['headers']['X-API-Key'], 'b')


class DeferredPageLoadingTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)

    def test_analyses_load_only_when_opened_and_crud_history_is_deferred(self):
        root = Path(__file__).resolve().parents[1] / 'streamlit/pages'
        for page, kind, path in [('Metricas_de_Salto.py', 'jump', '/api/v1/jumps'),
                                 ('Monitoramento_GPS.py', 'gps', '/api/v1/gps')]:
            with self.subTest(page=page), ExitStack() as stack:
                st.cache_data.clear()
                requests = []
                client = TestClient(create_app())
                stack.callback(client.close)
                def http(method, url, **kwargs):
                    kwargs.pop('timeout', None)
                    endpoint = urlsplit(url).path
                    requests.append(endpoint)
                    return client.request(method, endpoint, **kwargs)
                athlete = dict(id_atleta=1, nome='TESTE', apelido=None, posicao='Meia', grupo='G1', status='ativo')
                record = dict(atleta='TESTE', posicao='Meia', grupo='G1', data_coleta=date.today(),
                              maior_cmj=35., maior_sj=30., distance_km=5., high_speed_distance=.2)
                stack.enter_context(patch('psycopg2.connect', side_effect=AssertionError('Sem banco real')))
                stack.enter_context(patch.object(gateway, '_http_request', side_effect=http))
                repository = 'backend.mac_api.main.data_repository'
                stack.enter_context(patch(f'{repository}.list_athletes', return_value=[athlete]))
                stack.enter_context(patch(f'{repository}.jump_collections', return_value=[]))
                stack.enter_context(patch(f'{repository}.jump_records', return_value=[record]))
                stack.enter_context(patch(f'{repository}.gps_records', return_value=[record]))
                app = AppTest.from_file(str(root / page), default_timeout=30).run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertEqual(requests, ['/api/v1/athletes'])
                self.assertEqual(len(app.get('plotly_chart')), 0)

                app.session_state[f'{kind}_analysis_open'] = True
                app.run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertEqual(len(app.error), 0, list(app.error))
                self.assertEqual(requests.count('/api/v1/athletes'), 1)
                self.assertEqual(requests.count(path), 1)
                self.assertTrue(any(endpoint.startswith('/api/v1/analytics/') for endpoint in requests))

                # Também exercita as séries individuais e o desenho dos gráficos.
                next(widget for widget in app.multiselect if widget.label == 'Atletas').set_value(['TESTE'])
                # AppTest ainda não serializa o estado dos expanders como widgets.
                app.session_state[f'{kind}_analysis_open'] = True
                app.run()
                if kind == 'gps':
                    next(widget for widget in app.multiselect if widget.label == 'Variáveis').set_value(['Distância total (km)'])
                    app.session_state[f'{kind}_analysis_open'] = True
                    app.run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertGreater(len(app.get('plotly_chart')), 0)
                self.assertEqual(requests.count('/api/v1/athletes'), 1)
                self.assertEqual(requests.count(path), 1)

                # Fechar o painel não refaz estatísticas nem consultas do histórico.
                previous_count = len(requests)
                app.session_state[f'{kind}_analysis_open'] = False
                app.run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertEqual(len(requests), previous_count)
                if kind == 'jump':
                    app.session_state['jump_import_documents'] = [dict(arquivo='saltos.xlsx', linhas=[])]
                    app.session_state['jump_management_tab'] = 'Importar planilha'
                    app.run()
                    uploader_id = app.get('file_uploader')[0].proto.id
                    app.session_state['jump_management_tab'] = 'Editar'
                    app.run()
                    self.assertEqual(len(app.exception), 0, list(app.exception))
                    self.assertEqual(app.get('file_uploader')[0].proto.id, uploader_id)
                    self.assertEqual(app.session_state['jump_import_documents'][0]['arquivo'], 'saltos.xlsx')
                    self.assertEqual(requests.count('/api/v1/jumps/collections'), 1)
                    app.session_state['jump_management_tab'] = 'Excluir'
                    app.run()
                    self.assertEqual(requests.count('/api/v1/jumps/collections'), 1)
