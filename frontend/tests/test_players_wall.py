"""Mural por status, exercitando a interface e a API sem banco real."""
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import streamlit as st
from streamlit.testing.v1 import AppTest

from backend.mac_api.main import create_app


class PlayersWallTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)
        self.athletes = [
            dict(id_atleta=1, nome='ATIVO A', posicao='Meia', status='ativo'),
            dict(id_atleta=2, nome='INATIVO B', posicao='Goleiro', status='inativo'),
            dict(id_atleta=3, nome='LEGADO C', posicao='Meia'),
        ]
        self.client = TestClient(create_app())
        for mock in (
            patch('backend.mac_api.main.data_repository.player_dashboard_data',
                  return_value=dict(athletes=self.athletes, measurements=[])),
            patch('frontend.streamlit.api_client.service_gateway._http_request', side_effect=self.http),
            patch('psycopg2.connect', side_effect=AssertionError('Teste não acessa banco')),
        ):
            mock.start()
            self.addCleanup(mock.stop)
        path = Path(__file__).resolve().parents[1] / 'streamlit/pages/Jogadores.py'
        self.app = AppTest.from_file(str(path), default_timeout=30).run()

    def http(self, method, url, **kwargs):
        kwargs.pop('timeout', None)
        return self.client.request(method, urlsplit(url).path, **kwargs)

    def names(self):
        return [match.group(1) for text in self.app.markdown
                for match in re.finditer(r'class="player-name">([^<]+)', text.value)]

    def test_active_cards_precede_inactive_cards(self):
        self.assertEqual(len(self.app.exception), 0, list(self.app.exception))
        self.assertEqual([header.value for header in self.app.subheader], ['Ativos', 'Inativos'])
        self.assertEqual(self.names(), ['ATIVO A', 'LEGADO C', 'INATIVO B'])

    def test_default_order_uses_display_name_in_each_status_group(self):
        self.athletes[:] = [
            dict(id_atleta=1, nome='A nome completo', apelido='Caio', status='ativo'),
            dict(id_atleta=2, nome='B nome completo', apelido='Zeca', status='inativo'),
            dict(id_atleta=3, nome='Z nome completo', apelido='Álvaro', status='ativo'),
            dict(id_atleta=4, nome='bruno', status='ativo'),
            dict(id_atleta=5, nome='C nome completo', apelido='Álvaro inativo', status='inativo'),
        ]
        st.cache_data.clear()
        self.app.run()
        self.assertEqual(len(self.app.exception), 0, list(self.app.exception))
        order = next(widget for widget in self.app.selectbox if widget.label == 'Ordenar por')
        self.assertEqual(order.value, 'Nome')
        self.assertEqual(self.names(), ['Álvaro', 'bruno', 'Caio', 'Álvaro inativo', 'Zeca'])

    def test_card_html_does_not_start_indented_markdown_code_blocks(self):
        cards = [item.value for item in self.app.markdown if 'class="player-card"' in item.value]
        self.assertEqual(len(cards), 3)
        for card in cards:
            # Uma linha em branco seguida por HTML recuado vira código Markdown,
            # mesmo quando unsafe_allow_html está habilitado.
            self.assertNotRegex(card, r'\n[ \t]*\n[ \t]{4,}\S')
            self.assertIn('class="player-card-header"', card)
            self.assertIn('class="player-metrics"', card)

    def test_filters_apply_to_both_sections_and_empty_group_stays_visible(self):
        next(widget for widget in self.app.selectbox if widget.label == 'Posição').set_value('Goleiro').run()
        self.assertEqual(len(self.app.exception), 0, list(self.app.exception))
        self.assertEqual(self.names(), ['INATIVO B'])
        self.assertEqual([header.value for header in self.app.subheader], ['Ativos', 'Inativos'])
        self.assertTrue(any('Nenhum jogador ativo' in info.value for info in self.app.info))

    def test_deactivation_and_reactivation_move_card_between_sections(self):
        def status(value):
            def change(athlete_id):
                next(athlete for athlete in self.athletes if athlete['id_atleta'] == athlete_id)['status'] = value
            return change
        with patch('backend.mac_api.main.deactivate_athlete', side_effect=status('inativo')), \
             patch('backend.mac_api.main.reactivate_athlete', side_effect=status('ativo')):
            self.app.selectbox(key='deactivate_athlete_id').set_value(1).run()
            self.app.button(key='athlete_status_action').click().run()
            self.assertEqual(len(self.app.exception), 0, list(self.app.exception))
            self.assertEqual(self.names(), ['LEGADO C', 'ATIVO A', 'INATIVO B'])
            self.app.button(key='athlete_status_action').click().run()
            self.assertEqual(len(self.app.exception), 0, list(self.app.exception))
            self.assertEqual(self.names(), ['ATIVO A', 'LEGADO C', 'INATIVO B'])
