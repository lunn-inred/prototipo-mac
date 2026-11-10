"""Uma operação para medidas SQL locais e arquivos usados pela timeline."""
import logging

from backend.mac_api.core.database import database_write_connection
from backend.mac_api.core.settings import setting
from . import analysis_archive as archive
from .thermography_service import IMAGE_MEASURES, _insert_collection, image_measurements


def register_analysis(*, athlete_id, athlete_name, collected_at, mass, pain_score,
                      observations='', views, connection_factory=None):
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
            inserted = _insert_collection(cursor, athlete_id=athlete_id, collected_at=collected_at,
                                          measurements=measurements, required_measures=IMAGE_MEASURES)
            # A linha do atleta já foi bloqueada/validada por _insert_collection.
            cursor.execute('SELECT nome FROM public.atleta WHERE id_atleta = %s', (athlete_id,))
            name = cursor.fetchone()[0]
            entry = archive.save_analysis(
                athlete_id=athlete_id, athlete_name=name or f'Atleta {athlete_id}',
                collected_at=collected_at, mass=float(mass), pain_score=int(pain_score),
                observations=observations, views=views,
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
