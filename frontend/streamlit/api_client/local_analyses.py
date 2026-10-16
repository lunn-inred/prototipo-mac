"""Persistência local acessada exclusivamente pela API."""
from frontend.streamlit.api_client.service_gateway import _request
from frontend.streamlit.api_client.wire import encode, decode


def save_local_analysis(athlete_id, athlete_name, collected_at, views, *, mass=None, pain_score=None, observations=''):
    return decode(_request('POST', '/api/v1/thermography/analyses', json={
        'athlete_id': int(athlete_id), 'athlete_name': athlete_name,
        'collected_at': collected_at.isoformat(), 'views': encode(views),
        'mass': None if mass is None else float(mass),
        'pain_score': None if pain_score is None else int(pain_score),
        'observations': observations,
    }))


def list_local_analyses(athlete_id):
    return decode(_request('GET', '/api/v1/thermography/analyses', params={'athlete_id': int(athlete_id)}))


def load_local_analysis(entry):
    return decode(_request('GET', f'/api/v1/thermography/analyses/{entry["athlete_id"]}/{entry["collected_at"].isoformat()}/{entry["id"]}'))
