import unittest
from unittest.mock import Mock, patch
from frontend.streamlit.components.thermography.dialog_layout import dialog_canvas_limits


class DialogLayoutTests(unittest.TestCase):
    def setUp(self):
        session = patch('frontend.streamlit.components.thermography.dialog_layout.st.session_state', {})
        session.start()
        self.addCleanup(session.stop)

    @patch('frontend.streamlit.components.thermography.dialog_layout._measure_component')
    def test_uses_browser_measurement_and_reserves_toolbar_space(self, component):
        render = Mock(return_value={'size': {'width': 520, 'height': 310}})
        component.return_value = render
        self.assertEqual(dialog_canvas_limits('mask', columns=2), (520, 310))
        self.assertEqual(render.call_args.kwargs['data'], {'columns': 2, 'reserve': 252, 'reported': None})

    @patch('frontend.streamlit.components.thermography.dialog_layout._measure_component')
    def test_reopening_uses_last_measurement_without_small_fallback(self, component):
        render = Mock(side_effect=[{'size': {'width': 1100, 'height': 480}}, {'size': None}])
        component.return_value = render
        self.assertEqual(dialog_canvas_limits('reopen'), (1100, 480))
        self.assertEqual(dialog_canvas_limits('reopen'), (1100, 480))
        self.assertEqual(render.call_args.kwargs['data']['reported'], {'width': 1100, 'height': 480})

    @patch('frontend.streamlit.components.thermography.dialog_layout._measure_component')
    def test_short_viewport_is_not_forced_to_large_canvas(self, component):
        component.return_value = Mock(return_value={'size': {'width': 290, 'height': 85}})
        self.assertEqual(dialog_canvas_limits('parts', toolbar=False), (290, 85))

    @patch('frontend.streamlit.components.thermography.dialog_layout._measure_component')
    def test_fallback_and_maximum_dimensions(self, component):
        render = Mock(side_effect=[{'size': None}, {'size': {'width': 3000, 'height': 1800}}])
        component.return_value = render
        self.assertEqual(dialog_canvas_limits('initial'), (640, 280))
        self.assertEqual(dialog_canvas_limits('large'), (1400, 650))
