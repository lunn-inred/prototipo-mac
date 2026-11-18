from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
import streamlit as st
from streamlit.testing.v1 import AppTest

from frontend.streamlit.components.thermography import timeline


def regional_rows(app):
    class Rows(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows, self.row, self.cell = [], None, None
        def handle_starttag(self, tag, attrs):
            if tag == 'tr' and dict(attrs).get('data-region'):
                self.row = [dict(attrs)['data-region']]
            elif tag in ('td', 'th') and self.row is not None:
                self.cell = ''
        def handle_data(self, data):
            if self.cell is not None:
                self.cell += data
        def handle_endtag(self, tag):
            if tag in ('td', 'th') and self.cell is not None:
                self.row.append(self.cell); self.cell = None
            if tag == 'tr' and self.row is not None:
                self.rows.append(self.row); self.row = None
    parser = Rows()
    for element in app.get('html'):
        parser.feed(element.proto.body)
    return parser.rows


class TimelineComparisonTests(unittest.TestCase):
    def setUp(self):
        baseline_read = patch.object(timeline, 'get_baseline', return_value=None)
        baseline_read.start()
        self.addCleanup(baseline_read.stop)
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)
        self.entries = [dict(id=str(i), athlete_id=1, collected_at=date(2026, 10, i + 1),
                             sequence=i, thumbnail=Image.new('RGB', (20, 20))) for i in range(3)]
        self.saved = {}
        for i, entry in enumerate(self.entries):
            views = {}
            for view in ('front', 'back'):
                views[view] = dict(temperature=30 + (i if view == 'front' else i * 1.5),
                                   default_threshold=31 + i, image=Image.new('RGB', (20, 20)))
            self.saved[entry['id']] = {**entry, 'views': views}

    @staticmethod
    def comparison_response(baseline, current, limit=None, palette=None, gamma=1.0):
        # Simulate the HTTP adapter's decoded response; numerical processing is
        # tested separately in backend/tests/test_temperature_comparison.py.
        previous, actual = baseline['temperature'], current['temperature']
        regions = lambda mean: {part: dict(mean_temperature=mean, hot_percentage=100 if mean >= 31 else 0)
                                for part in ('total', 'coxa', 'joelho', 'canela', 'pe')}
        return dict(max_difference=abs(actual - previous), limit=limit or max(.1, abs(actual - previous)),
                    unchanged=previous == actual, has_overlap=True,
                    images={side: Image.new('RGB', (20, 20), 'white') for side in ('right', 'left')},
                    legend=Image.new('RGB', (420, 125)),
                    summaries={side: dict(baseline=regions(previous), current=regions(actual))
                               for side in ('right', 'left')})

    def test_comparison_is_cached_without_scanning_other_dates(self):
        with patch.object(timeline, 'load_local_analysis', side_effect=lambda entry: self.saved[entry['id']]), \
             patch.object(timeline, 'compare_temperature_maps', side_effect=self.comparison_response) as compare:
            result = timeline._cached_comparison(self.entries[0], self.entries[1])
            self.assertEqual(result['front']['limit'], 1)
            self.assertEqual(result['back']['limit'], 1.5)
            count = compare.call_count
            self.assertEqual(count, 2)
            timeline._cached_comparison(self.entries[0], self.entries[1])
            self.assertEqual(compare.call_count, count)
            changed = timeline._cached_comparison(self.entries[1], self.entries[2])
            self.assertEqual(compare.call_count, count + 2)
            self.assertEqual(changed['front']['limit'], 1)
            self.assertEqual(changed['back']['limit'], 1.5)
            farther = timeline._cached_comparison(self.entries[0], self.entries[2])
            self.assertEqual(compare.call_count, count + 4)
            self.assertEqual(farther['front']['limit'], 2)
            self.assertEqual(farther['back']['limit'], 3)
            linear = timeline._cached_comparison(self.entries[0], self.entries[1], gamma=1.0)
            self.assertEqual(compare.call_count, count + 6)
            self.assertEqual(compare.call_args.kwargs['gamma'], 1.0)
            self.assertEqual(linear['front']['limit'], result['front']['limit'])
            self.assertEqual(linear['back']['limit'], result['back']['limit'])

    def test_timeline_renders_total_and_regional_percentages(self):
        root = Path(__file__).resolve().parents[2]
        with patch('frontend.streamlit.presentation.thermography_data.load_thermography_athletes',
                   return_value=[dict(id_atleta=1, nome='Teste')]), \
             patch.object(timeline, 'list_local_analyses', return_value=self.entries), \
             patch.object(timeline, 'load_local_analysis', side_effect=lambda entry: self.saved[entry['id']]), \
             patch.object(timeline, 'compare_temperature_maps', side_effect=self.comparison_response), \
             patch.object(timeline.st, 'image', wraps=timeline.st.image) as show_image:
            app = AppTest.from_file(str(root / 'frontend/streamlit/pages/Timeline_Termo.py'),
                                   default_timeout=30).run()
            app.selectbox(key='thermography_timeline_player').set_value(1).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual(len(app.error), 0)
            self.assertEqual([title.value for title in app.title], ['Timeline térmica'])
            self.assertNotIn('Timeline térmica', [header.value for header in app.subheader])
            self.assertEqual([tab.label for tab in app.tabs], ['Frente', 'Costas'])
            titles = [text.value for text in app.markdown]
            self.assertIn('##### Basal (01/10/2026)', titles)
            self.assertIn('##### Atual (03/10/2026)', titles)
            self.assertFalse(any(caption.value.startswith('Basal:') and 'Atual:' in caption.value
                                 for caption in app.caption))
            leg_captions = [call.kwargs.get('caption') for call in show_image.call_args_list
                            if call.kwargs.get('caption') in ('Perna esquerda', 'Perna direita')]
            self.assertEqual(leg_captions, ['Perna direita', 'Perna esquerda',
                                           'Perna esquerda', 'Perna direita'])
            self.assertEqual(len(app.dataframe), 0)
            rows = regional_rows(app)
            self.assertEqual(len(rows), 20)
            for label in ('Coxa', 'Joelho', 'Canela', 'Pé'):
                metrics = [row for row in rows if row[1] == label]
                self.assertEqual(len(metrics), 4)
                self.assertTrue(all(row[2:] == ['100.0%', '0.0%', '+100.0'] for row in metrics))
            removed_texts = ('Limiares originais', 'Atual − basal por pixel',
                             'Escala deste comparativo', 'Contraste não linear',
                             'Mesmo limiar nas duas coletas', 'Análises armazenadas localmente')
            self.assertFalse(any(text in caption.value for caption in app.caption for text in removed_texts))
            self.assertEqual(app.slider(key='timeline_comparison_gamma_front').value, .5)
            self.assertEqual(app.slider(key='timeline_comparison_gamma_back').value, .5)
            self.assertEqual([slider.label for slider in app.slider],
                             ['Ajuste de contraste (gama)'] * 2)
            before = regional_rows(app)
            app.slider(key='timeline_comparison_gamma_front').set_value(1.).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual(regional_rows(app), before)
            self.assertEqual(app.slider(key='timeline_comparison_gamma_front').value, 1.)
            self.assertEqual(app.slider(key='timeline_comparison_gamma_back').value, 1.)
            app.slider(key='timeline_comparison_gamma_back').set_value(.65).run()
            self.assertEqual(app.slider(key='timeline_comparison_gamma_front').value, .65)
            self.assertEqual(app.session_state['timeline_gamma_value'], .65)
            app.select_slider(key='thermography_timeline_date_1').set_value(date(2026, 10, 2)).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertIn('##### Atual (02/10/2026)', [text.value for text in app.markdown])
            self.assertEqual(len(app.dataframe), 0)
            app.select_slider(key='thermography_timeline_date_1').set_value(date(2026, 10, 1)).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertFalse(any('Sem variação de temperatura' in message.value for message in app.info))
            self.assertFalse(any('A coleta atual é alinhada' in message.value for message in app.caption))

    def test_empty_region_does_not_hide_other_regional_metrics(self):
        root = Path(__file__).resolve().parents[2]
        def comparison_with_empty_knee(*args, **kwargs):
            response = self.comparison_response(*args, **kwargs)
            response.update(thermal_zone='neutral', zone_label='Zona neutra')
            for side in ('right', 'left'):
                response['summaries'][side]['current']['joelho']['hot_percentage'] = None
            return response
        with patch('frontend.streamlit.presentation.thermography_data.load_thermography_athletes',
                   return_value=[dict(id_atleta=1, nome='Teste')]), \
             patch.object(timeline, 'list_local_analyses', return_value=self.entries), \
             patch.object(timeline, 'load_local_analysis', side_effect=lambda entry: self.saved[entry['id']]), \
             patch.object(timeline, 'compare_temperature_maps', side_effect=comparison_with_empty_knee):
            app = AppTest.from_file(str(root/'frontend/streamlit/pages/Timeline_Termo.py'), default_timeout=30).run()
            app.selectbox(key='thermography_timeline_player').set_value(1).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            rows = regional_rows(app)
            totals = [row for row in rows if row[1] == 'Total']
            self.assertEqual(len(totals), 4)
            knees = [row for row in rows if row[1] == 'Joelho']
            self.assertEqual(len(knees), 4)
            self.assertTrue(all(row[2] == '—' for row in knees))
            for label in ('Coxa', 'Canela', 'Pé'):
                metrics = [row for row in rows if row[1] == label]
                self.assertTrue(all(row[2] == '100.0%' for row in metrics))

    def test_regional_cards_preserve_each_region_and_show_data_without_total(self):
        script = '''
import streamlit as st
from frontend.streamlit.components.thermography.timeline import _render_regional_comparison
baseline = {part: {'hot_percentage': value} for part, value in
            [('total', None), ('coxa', 10.), ('joelho', 20.), ('canela', 30.), ('pe', 40.)]}
current = {part: {'hot_percentage': value} for part, value in
           [('total', None), ('coxa', 15.), ('joelho', 12.), ('canela', 30.), ('pe', 50.)]}
comparison = {'thermal_zone': 'cold', 'zone_label': 'Zona fria', 'summaries':
              {side: {'baseline': baseline, 'current': current} for side in ('right', 'left')}}
_render_regional_comparison(comparison, 'front')
'''
        app = AppTest.from_string(script).run()
        self.assertEqual(len(app.exception), 0, list(app.exception))
        for label, value, delta in (('Coxa', '15.0%', '+5.0'), ('Joelho', '12.0%', '-8.0'),
                                     ('Canela', '30.0%', '+0.0'), ('Pé', '50.0%', '+10.0')):
            metrics = [row for row in regional_rows(app) if row[1] == label]
            self.assertEqual(len(metrics), 2)
            self.assertTrue(all(row[2] == value and row[4] == delta for row in metrics))
