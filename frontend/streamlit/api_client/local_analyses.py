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


def list_local_analyses(athlete_id, *, include_drafts=False):
    return decode(_request('GET', '/api/v1/thermography/analyses', params={'athlete_id': int(athlete_id), **({'include_drafts': True} if include_drafts else {})}))


def save_analysis_changes(athlete_id, athlete_name, collected_at, views, *, mass, pain_score,
                          observations='', source=None, overwrite=False, draft=None):
    payload = dict(athlete_id=int(athlete_id), athlete_name=athlete_name, collected_at=collected_at.isoformat(),
                   views=encode(views), mass=float(mass), pain_score=int(pain_score),
                   observations=observations, overwrite=overwrite)
    if draft:
        payload.update(draft_id=draft['id'], draft_revision=draft['created_at'])
    if source:
        payload['expected_revision'] = source['created_at']
        path = f'/api/v1/thermography/analyses/{source["athlete_id"]}/{source["collected_at"].isoformat()}/{source["id"]}'
        return decode(_request('PUT', path, json=payload))
    return decode(_request('POST', '/api/v1/thermography/analyses/register', json=payload))


def register_analysis(athlete_id, athlete_name, collected_at, views, *, mass, pain_score, observations=''):
    return decode(_request('POST', '/api/v1/thermography/analyses/register', json={
        'athlete_id': int(athlete_id), 'athlete_name': athlete_name,
        'collected_at': collected_at.isoformat(), 'views': encode(views),
        'mass': float(mass), 'pain_score': int(pain_score), 'observations': observations,
    }))


def load_local_analysis(entry):
    if entry.get('is_draft'):
        return decode(_request('GET', f'/api/v1/thermography/drafts/{entry["id"]}'))
    return decode(_request('GET', f'/api/v1/thermography/analyses/{entry["athlete_id"]}/{entry["collected_at"].isoformat()}/{entry["id"]}'))


def save_draft(state, *, draft=None, overwrite=False):
    return decode(_request('POST', '/api/v1/thermography/drafts', json=dict(
        state=encode(state), draft_id=draft['id'] if draft else None,
        expected_revision=draft['created_at'] if draft else None, overwrite=overwrite)))
