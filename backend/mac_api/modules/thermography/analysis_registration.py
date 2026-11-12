"""Uma operação para medidas SQL locais e arquivos usados pela timeline."""
import logging

from backend.mac_api.core.database import database_write_connection
from backend.mac_api.core.settings import setting
from . import analysis_archive as archive
from . import collection_state
from .thermography_service import IMAGE_MEASURES, _insert_collection, image_measurements


class AnalysisConflictError(ValueError):
    pass


class AnalysisChangedError(ValueError):
    pass


def register_analysis(*, athlete_id, athlete_name, collected_at, mass, pain_score,
                      observations='', views, connection_factory=None, overwrite=False, analysis_id=None, partial_pair=None, partial_revision=None):
    if overwrite or partial_pair:
        return replace_analysis(source=None, athlete_id=athlete_id, athlete_name=athlete_name,
                                collected_at=collected_at, mass=mass, pain_score=pain_score,
                                observations=observations, views=views, overwrite=overwrite,
                                connection_factory=connection_factory, analysis_id=analysis_id,
                                partial_pair=partial_pair, partial_revision=partial_revision)
    if setting('MAC_DB_TARGET', 'local') != 'local':
        raise ValueError('Registrar Análise exige o banco local configurado.')
    # Mesma precisão e mesma máscara usadas no arquivo: não confiar nas contagens
    # enviadas pelo frontend ou calcular sobre pixels RGB diretamente.
    if set(views) != {'front', 'back'}:
        raise ValueError('Informe as imagens de frente e costas.')
    metrics = {view: archive._validate_view(source)[3]['metrics'] for view, source in views.items()}
    measurements = image_measurements(
        mass=mass, pain_score=pain_score, observations=observations,
        front_right=metrics['front']['right']['hot_pixels'], front_left=metrics['front']['left']['hot_pixels'],
        back_right=metrics['back']['right']['hot_pixels'], back_left=metrics['back']['left']['hot_pixels'],
    )
    entry = None
    try:
        with (connection_factory or database_write_connection)() as database, database.cursor() as cursor:
            cursor.execute('SELECT id_atleta FROM public.atleta WHERE id_atleta=%s FOR UPDATE', (athlete_id,))
            if cursor.fetchone() is None:
                raise ValueError('Jogador não encontrado no banco.')
            if any(item['collected_at'] == collected_at for item in archive.list_analyses(athlete_id)):
                raise AnalysisConflictError('Uma análise do atleta já foi realizada nessa data. Deseja sobrescrevê-la?')
            inserted = _insert_collection(cursor, athlete_id=athlete_id, collected_at=collected_at,
                                          measurements=measurements, required_measures=IMAGE_MEASURES)
            # A linha do atleta já foi bloqueada/validada por _insert_collection.
            cursor.execute('SELECT nome FROM public.atleta WHERE id_atleta = %s', (athlete_id,))
            name = cursor.fetchone()[0]
            entry = archive.save_analysis(
                athlete_id=athlete_id, athlete_name=name or f'Atleta {athlete_id}',
                collected_at=collected_at, mass=float(mass), pain_score=int(pain_score),
                observations=observations, views=views, **({'analysis_id': analysis_id} if analysis_id else {}),
            )
        # O context manager acima só retorna depois do commit.
        return {'analysis': entry, 'inserted_measurements': inserted}
    except Exception:
        if entry is not None:
            try:
                archive.discard_created_analysis(entry)
            except OSError:
                logging.getLogger(__name__).exception('Falha ao compensar arquivos de uma análise não confirmada.')
                raise RuntimeError('Registro não confirmado. Não repita o envio antes de revisar os arquivos locais.')
        raise


def replace_analysis(*, source, athlete_id, athlete_name, collected_at, mass, pain_score,
                     observations='', views, overwrite=False, expected_revision=None, connection_factory=None, analysis_id=None,
                     partial_pair=None, partial_revision=None):
    if setting('MAC_DB_TARGET', 'local') != 'local':
        raise ValueError('Salvar análise exige o banco local configurado.')
    if set(views) != {'front', 'back'}:
        raise ValueError('Informe as imagens de frente e costas.')
    metrics = {view: archive._validate_view(value)[3]['metrics'] for view, value in views.items()}
    measurements = image_measurements(
        mass=mass, pain_score=pain_score, observations=observations,
        front_right=metrics['front']['right']['hot_pixels'], front_left=metrics['front']['left']['hot_pixels'],
        back_right=metrics['back']['right']['hot_pixels'], back_left=metrics['back']['left']['hot_pixels'])
    entry, staged = None, []
    target_pair = (int(athlete_id), collected_at)
    source_pair = (int(source['athlete_id']), source['collected_at']) if source else None
    if partial_pair:
        from datetime import date
        partial_pair = (int(partial_pair[0]), date.fromisoformat(str(partial_pair[1])))
    try:
        with (connection_factory or database_write_connection)() as database, database.cursor() as cursor:
            for player_id in sorted({athlete_id, source['athlete_id'] if source else athlete_id} | ({partial_pair[0]} if partial_pair else set())):
                cursor.execute('SELECT id_atleta FROM public.atleta WHERE id_atleta=%s FOR UPDATE', (player_id,))
                if cursor.fetchone() is None:
                    raise ValueError('Jogador não encontrado no banco.')
            original = archive.load_analysis(**source) if source else None
            if original and expected_revision != original['created_at']:
                raise AnalysisChangedError('Esta análise foi alterada por outra sessão. Abra-a novamente antes de salvar.')
            if partial_pair and collection_state.revision(cursor, partial_pair)[0] != partial_revision:
                raise AnalysisChangedError('As medidas da análise parcial foram alteradas. Reabra o registro antes de salvar.')
            others = [item for item in archive.list_analyses(athlete_id)
                      if item['collected_at'] == collected_at and
                      not (original and str(item['id']) == str(original['id']) and source_pair == target_pair)]
            cursor.execute('''SELECT count(*) FROM public.medida_valor v
                JOIN public.medida m USING (id_medida) JOIN public.grupo_medida g USING (id_grupo_medida)
                WHERE v.id_atleta=%s AND v.data::date=%s AND lower(trim(g.nome))='termografia' ''', target_pair)
            has_target = cursor.fetchone()[0] > 0 and target_pair not in (source_pair if not partial_pair else None, partial_pair)
            if (has_target or others) and not overwrite:
                raise AnalysisConflictError('Uma análise do atleta já foi realizada nessa data. Deseja sobrescrevê-la?')
            # Excluir apenas termografia dos pares explicitamente substituídos.
            # O SQL já foi movido quando uma edição parcial mudou atleta/data.
            source_sql_pair = source_pair if not partial_pair else None
            for pair in sorted({target_pair} | ({source_sql_pair} if source_sql_pair else set()) | ({partial_pair} if partial_pair else set())):
                cursor.execute('''DELETE FROM public.medida_valor v USING public.medida m, public.grupo_medida g
                    WHERE v.id_medida=m.id_medida AND m.id_grupo_medida=g.id_grupo_medida
                    AND lower(trim(g.nome))='termografia' AND v.id_atleta=%s AND v.data::date=%s''', pair)
            replaced = ([original] if original else []) + others
            staged = archive.stage_replacements(replaced)
            inserted = _insert_collection(cursor, athlete_id=athlete_id, collected_at=collected_at,
                                          measurements=measurements, required_measures=IMAGE_MEASURES)
            cursor.execute('SELECT nome FROM public.atleta WHERE id_atleta=%s', (athlete_id,))
            name = cursor.fetchone()[0]
            analysis_id = original['id'] if original else analysis_id or (others[-1]['id'] if others else None)
            entry = archive.save_analysis(athlete_id=athlete_id, athlete_name=name or f'Atleta {athlete_id}',
                collected_at=collected_at, mass=float(mass), pain_score=int(pain_score), observations=observations,
                views=views, analysis_id=analysis_id)
    except Exception:
        try:
            if entry is not None:
                archive.discard_created_analysis(entry)
            archive.restore_replacements(staged)
        except OSError as recovery_error:
            raise RuntimeError('Falha na recuperação dos arquivos. Preserve as pastas .replacing e revise antes de reenviar.') from recovery_error
        raise
    archive.finish_replacements(staged)
    return {'analysis': entry, 'inserted_measurements': inserted}
