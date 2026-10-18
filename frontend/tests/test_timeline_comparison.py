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
    def comparison_response(baseline, current, limit=None, palette=None):
        # Simulate the HTTP adapter's decoded response; numerical processing is
        # tested separately in backend/tests/test_temperature_comparison.py.
        previous, actual = baseline['temperature'], current['temperature']
        regions = lambda mean: {part: dict(mean_temperature=mean, hot_percentage=100 if mean >= 31 else 0)
                                for part in ('total', 'coxa', 'joelho', 'canela', 'pe')}
        return dict(max_difference=abs(actual - previous), limit=limit or abs(actual - previous) or .1,
                    unchanged=previous == actual, has_overlap=True,
                    images={side: Image.new('RGB', (20, 20), 'white') for side in ('right', 'left')},
                    legend=Image.new('RGB', (420, 125)),
                    summaries={side: dict(baseline=regions(previous), current=regions(actual))
                               for side in ('right', 'left')})

    def test_scale_is_shared_cached_and_invalidated_for_baseline_or_records(self):
        with patch.object(timeline, 'load_local_analysis', side_effect=lambda entry: self.saved[entry['id']]), \
             patch.object(timeline, 'compare_temperature_maps', side_effect=self.comparison_response) as compare:
            self.assertEqual(timeline._timeline_color_limit(self.entries[0], self.entries), 3)
            count = compare.call_count
            self.assertEqual(count, 6)
            self.assertEqual(timeline._timeline_color_limit(self.entries[0], self.entries), 3)
            self.assertEqual(compare.call_count, count)
            # Changing the selected date reuses the scanned pair calculations.
            timeline._cached_comparison(self.entries[0], self.entries[1])
            self.assertEqual(compare.call_count, count)
            self.assertEqual(timeline._timeline_color_limit(self.entries[1], self.entries), 1.5)
            self.assertEqual(timeline._timeline_color_limit(self.entries[0], self.entries[:2]), 1.5)

    def test_timeline_renders_percentages_without_regional_table(self):
        root = Path(__file__).resolve().parents[2]
        with patch('frontend.streamlit.presentation.thermography_data.load_thermography_athletes',
                   return_value=[dict(id_atleta=1, nome='Teste')]), \
             patch.object(timeline, 'list_local_analyses', return_value=self.entries), \
             patch.object(timeline, 'load_local_analysis', side_effect=lambda entry: self.saved[entry['id']]), \
             patch.object(timeline, 'compare_temperature_maps', side_effect=self.comparison_response):
            app = AppTest.from_file(str(root / 'frontend/streamlit/pages/Timeline_Termo.py'),
                                   default_timeout=30).run()
            app.selectbox(key='thermography_timeline_player').set_value(1).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual(len(app.error), 0)
            self.assertEqual(len(app.dataframe), 0)
            self.assertTrue(all(metric.value.endswith('%') for metric in app.metric))
            self.assertTrue(any('atual: 33.00 °C' in caption.value for caption in app.caption))
            app.select_slider(key='thermography_timeline_date_1').set_value(date(2026, 10, 2)).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual(len(app.dataframe), 0)
