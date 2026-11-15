import unittest
import numpy as np
from backend.tests.test_analysis_archive import example_views
from backend.mac_api.modules.thermography.analysis_archive import _validate_view
from backend.mac_api.modules.thermography.regional_zones import (
    regional_zone_measurements, REGIONAL_ZONE_MEASURES,
)


class RegionalZonesTests(unittest.TestCase):
    def test_http_preview_matches_registration_calculation_without_database(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from backend.mac_api.main import create_app
        from backend.mac_api.core.wire import encode, decode
        views = example_views()
        expected = regional_zone_measurements({v: _validate_view(s) for v, s in views.items()})
        import os
        with patch.dict(os.environ, MAC_API_KEY='preview-test'), \
             patch('psycopg2.connect', side_effect=AssertionError('Prévia não acessa banco')):
            response = TestClient(create_app()).post(
                '/api/v1/thermography/operations/preview_regional_zones',
                json={'args': encode([views]), 'kwargs': {}},
                headers={'X-API-Key': 'preview-test'},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(decode(response.json()['result']), expected)

    def test_boundaries_masks_regions_and_all_views_independent_of_selected_zone(self):
        views = example_views()
        for view in views:
            source = dict(views[view])
            # Each anatomical region contains every boundary and out-of-scale value.
            source['temperatures'] = np.tile(
                np.array([20, 30, 31, 33, 32, 33, 36, 40], dtype=np.float32), (12, 1))
            source['thermal_zone'] = 'cold' if view == 'front' else 'hot'
            source['metrics'] = {'right': {'hot_pixels': 99999}}
            source['segmentation_masks'] = {s: m.copy() for s, m in source['segmentation_masks'].items()}
            source['segmentation_masks']['right'][0, 0] = False
            views[view] = source
        measurements = regional_zone_measurements({v: _validate_view(s) for v, s in views.items()})
        self.assertEqual(set(measurements), REGIONAL_ZONE_MEASURES)
        self.assertEqual(len(measurements), 48)
        for view in ('FRENTE', 'VERSO'):
            for region, cold in (('COXA', 5), ('JOELHO', 6), ('CANELA', 6), ('PE', 6)):
                prefix = f'{region}_DIREITA_{view}_ZONA_'
                self.assertEqual([measurements[prefix+z] for z in ('FRIA','NEUTRA','QUENTE')], [cold, 3, 3])
                prefix = f'{region}_ESQUERDA_{view}_ZONA_'
                self.assertEqual([measurements[prefix+z] for z in ('FRIA','NEUTRA','QUENTE')], [0, 3, 9])
            for side, area in (('DIREITA', 47), ('ESQUERDA', 48)):
                self.assertEqual(sum(measurements[f'{r}_{side}_{view}_ZONA_{z}']
                                     for r in ('COXA', 'JOELHO', 'CANELA', 'PE')
                                     for z in ('FRIA', 'NEUTRA', 'QUENTE')), area)

    def test_moving_anatomical_boundary_changes_region_counts(self):
        views = example_views()
        before = regional_zone_measurements({v: _validate_view(s) for v, s in views.items()})
        views['front'] = {**views['front'], 'part_settings': {
            side: dict(cuts=[50, 60, 90], axis='vertical', foot_at_end=True)
            for side in ('right', 'left')}}
        after = regional_zone_measurements({v: _validate_view(s) for v, s in views.items()})
        self.assertEqual(sum(after[f'COXA_DIREITA_FRENTE_ZONA_{z}'] for z in ('FRIA','NEUTRA','QUENTE')), 24)
        self.assertEqual(sum(before[f'COXA_DIREITA_FRENTE_ZONA_{z}'] for z in ('FRIA','NEUTRA','QUENTE')), 12)

    def test_preview_totals_sum_both_legs_for_each_zone_and_view(self):
        from backend.mac_api.modules.thermography.regional_zones import preview_regional_zones
        result = preview_regional_zones(example_views(), include_totals=True)
        self.assertEqual(len(result['measurements']), 48)
        for view in ('FRENTE', 'VERSO'):
            for zone in ('FRIA', 'NEUTRA', 'QUENTE'):
                expected = sum(count for name, count in result['measurements'].items()
                               if name.endswith(f'_{view}_ZONA_{zone}'))
                self.assertEqual(result['totals'][view][zone], expected)
            self.assertEqual(sum(result['totals'][view].values()), 96)
