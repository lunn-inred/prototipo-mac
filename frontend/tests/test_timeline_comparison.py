from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
import streamlit as st
from streamlit.testing.v1 import AppTest

from frontend.streamlit.components.thermography import timeline


class TimelineComparisonTests(unittest.TestCase):
    def setUp(self):
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

    def test_timeline_renders_percentages_without_regional_table(self):
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
            self.assertTrue(all(metric.value.endswith('%') for metric in app.metric))
            removed_texts = ('Limiares originais', 'Atual − basal por pixel',
                             'Escala deste comparativo', 'Contraste não linear',
                             'Mesmo limiar nas duas coletas', 'Análises armazenadas localmente')
            self.assertFalse(any(text in caption.value for caption in app.caption for text in removed_texts))
            self.assertEqual(app.slider(key='timeline_comparison_gamma').value, .5)
            before = [metric.value for metric in app.metric]
            app.slider(key='timeline_comparison_gamma').set_value(1.).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual([metric.value for metric in app.metric], before)
            self.assertEqual(app.slider(key='timeline_comparison_gamma').value, 1.)
            app.select_slider(key='thermography_timeline_date_1').set_value(date(2026, 10, 2)).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertIn('##### Atual (02/10/2026)', [text.value for text in app.markdown])
            self.assertEqual(len(app.dataframe), 0)
