"""Escolha persistente de basal, sem modificar imagens ou segmentações."""
from uuid import UUID
from backend.mac_api.core.database import database_connection, database_write_connection
from backend.mac_api.core.settings import setting
from . import analysis_archive


def get_baseline(athlete_id, *, connection_factory=None):
    with (connection_factory or database_connection)() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT analysis_id::text FROM public.termografia_basal WHERE id_atleta=%s', (athlete_id,))
        row = cursor.fetchone()
    return {'analysis_id': row[0]} if row else None


def set_baseline(athlete_id, analysis_id, *, connection_factory=None):
    if setting('MAC_DB_TARGET', 'local') != 'local':
        raise ValueError('A escolha da basal exige o banco local configurado.')
    analysis_id = str(UUID(str(analysis_id)))
    # Só uma análise completa do próprio atleta pode ser escolhida, não um rascunho.
    if not any(str(entry['id']) == analysis_id for entry in analysis_archive.list_analyses(athlete_id)):
        raise FileNotFoundError('A análise basal não está disponível para este jogador.')
    with (connection_factory or database_write_connection)() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT id_atleta FROM public.atleta WHERE id_atleta=%s FOR KEY SHARE', (athlete_id,))
        if cursor.fetchone() is None:
            raise ValueError('Jogador não encontrado no banco.')
        cursor.execute('''INSERT INTO public.termografia_basal(id_atleta, analysis_id)
                          VALUES (%s,%s)
                          ON CONFLICT (id_atleta) DO UPDATE
                          SET analysis_id=EXCLUDED.analysis_id, updated_at=CURRENT_TIMESTAMP''',
                       (athlete_id, analysis_id))
    return {'analysis_id': analysis_id}
