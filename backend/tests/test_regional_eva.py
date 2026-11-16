"""Contrato regional puro e integração optativa no PostgreSQL descartável."""
from datetime import date
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.mac_api.modules.thermography.regional_eva import (
    REGIONAL_EVA, eva_measurements, normalize_regional_eva, maximum_eva,
)


class RegionalEvaTests(unittest.TestCase):
    def test_sixteen_regions_defaults_and_independent_sides_views(self):
        self.assertEqual(len(REGIONAL_EVA), 16)
        values = {'front-thigh-right': 3, 'back-thigh-right': 8, 'front-thigh-left': 1}
        result = eva_measurements(values)
        self.assertEqual(len(result), 16)
        self.assertEqual(result['EVA_COXA_DIREITA_FRENTE'], 3)
        self.assertEqual(result['EVA_COXA_DIREITA_VERSO'], 8)
        self.assertEqual(result['EVA_PE_ESQUERDA_VERSO'], 0)
        self.assertEqual(maximum_eva(values), 8)
        self.assertEqual(maximum_eva({}), 0)
        self.assertIsNone(maximum_eva(None))
        self.assertEqual(eva_measurements(None), {})

    def test_unknown_regions_and_non_integer_scores_rejected(self):
        for value in (-1, 11, 1.5, True, '3', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_regional_eva({'front-thigh-right': value})
        with self.assertRaises(ValueError):
            normalize_regional_eva({'front-coxa-right': 2})

    def test_legacy_general_does_not_become_a_regional_assessment(self):
        from backend.mac_api.modules.thermography.drafts import validate_state, measurements
        from backend.tests.test_thermal_drafts import empty_state
        state = empty_state()
        state['draft']['pain'] = 9
        validate_state(state)
        self.assertIsNone(state['draft']['pain'])
        self.assertNotIn('EVA_DOR', measurements(state, {}))


@unittest.skipUnless(os.getenv('MAC_TEST_DB_ENABLED') == '1', 'PostgreSQL descartável não habilitado')
class RegionalEvaPostgresTests(unittest.TestCase):
    def test_migration_save_edit_partial_dashboard_and_rollback(self):
        from backend.mac_api.core.database import database_write_connection, database_write_config
        from backend.mac_api.modules.thermography.analysis_registration import register_analysis, replace_analysis
        from backend.mac_api.modules.thermography import analysis_archive as archive, drafts
        from backend.mac_api.repositories.data_repository import player_dashboard_data
        from backend.tests.test_analysis_archive import example_views
        from backend.tests.test_thermal_drafts import empty_state
        config = database_write_config()
        self.assertEqual(config['dbname'], 'mac_test')
        self.assertIn(config['host'], ('127.0.0.1', 'localhost', 'postgres-test'))
        migration = (Path(__file__).resolve().parents[1] / 'migrations/20261116_thermography_regional_eva.sql').read_text()
        with TemporaryDirectory(prefix='mac-eva-pg-') as root, patch.dict(os.environ, MAC_ANALYSES_DIR=root):
            with database_write_connection() as c, c.cursor() as q:
                q.execute("INSERT INTO public.atleta(nome) VALUES('EVA teste') RETURNING id_atleta")
                athlete = q.fetchone()[0]
                q.execute("INSERT INTO public.medida(nome,id_grupo_medida) SELECT 'EVA_DOR',id_grupo_medida FROM public.grupo_medida WHERE nome='termografia' AND NOT EXISTS(SELECT 1 FROM public.medida WHERE nome='EVA_DOR')")
                q.execute("INSERT INTO public.medida_valor(id_atleta,id_medida,valor,data) SELECT %s,id_medida,9,'2026-01-01' FROM public.medida WHERE nome='EVA_DOR'", (athlete,))
                # A fixture antiga omitia posição/grupo da view; reproduzir o contrato real.
                q.execute('DROP VIEW public.vw_medida_termografia')
                q.execute((Path(__file__).resolve().parents[1] / 'migrations/20261115_thermography_regional_zones.sql').read_text())
                q.execute(migration)
                q.execute(migration)
                q.execute("SELECT count(*) FROM public.medida WHERE nome='EVA_DOR'")
                self.assertEqual(q.fetchone()[0], 0)
                q.execute("SELECT count(*) FROM public.medida WHERE nome = ANY(%s)", (list(REGIONAL_EVA.values()),))
                self.assertEqual(q.fetchone()[0], 16)
            values = dict(athlete_id=athlete, athlete_name='Teste', collected_at=date(2026,11,1), mass=70,
                          regional_eva={'front-thigh-right': 8}, views=example_views())
            saved = register_analysis(**values)['analysis']
            loaded = archive.load_analysis(athlete, values['collected_at'], saved['id'])
            self.assertEqual(loaded['regional_eva']['front-thigh-right'], 8)
            with database_write_connection() as c, c.cursor() as q:
                q.execute('SELECT eva_dor FROM public.vw_medida_termografia WHERE id_atleta=%s', (athlete,))
                self.assertEqual(q.fetchone()[0], 8)
                q.execute('SELECT eva_pe_esquerda_verso FROM public.vw_termografia_eva_regional WHERE id_atleta=%s', (athlete,))
                self.assertEqual(q.fetchone()[0], 0)
            source = dict(athlete_id=athlete,collected_at=values['collected_at'],analysis_id=saved['id'])
            updated = replace_analysis(source=source,expected_revision=saved['created_at'],
                                       **{**values,'regional_eva':{'back-foot-left': 3}})['analysis']
            self.assertEqual(updated['pain_score'], 3)
            with patch('numpy.save',side_effect=OSError('Falha simulada')):
                with self.assertRaises(OSError):
                    replace_analysis(source=source,expected_revision=updated['created_at'],
                                     **{**values,'regional_eva':{'back-foot-left':10}})
            self.assertEqual(archive.load_analysis(athlete,values['collected_at'],saved['id'])['pain_score'],3)
            state = empty_state()
            state['draft'].update(player=athlete,regional_eva={'front-knee-left':7},collected_at='2026-11-02')
            partial = drafts.save(state)
            self.assertEqual(drafts.load(partial['id'])['state']['draft']['regional_eva']['front-knee-left'],7)
            dashboard = player_dashboard_data()
            eva = [r for r in dashboard['measurements'] if r['id_atleta']==athlete and r['medida']=='eva_dor']
            self.assertEqual([(r['data'],r['valor']) for r in eva],[(date(2026,11,2),7)])
            with database_write_connection() as c, c.cursor() as q:
                q.execute('SELECT eva_dor FROM public.vw_medida_termografia WHERE id_atleta=%s AND data_coleta::date=%s',(athlete,date(2026,11,1)))
                self.assertEqual(q.fetchone()[0],3)
                q.execute('DELETE FROM public.medida_valor WHERE id_atleta=%s',(athlete,))
                q.execute('DELETE FROM public.atleta WHERE id_atleta=%s',(athlete,))
