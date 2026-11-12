"""Cliente de backups: todo acesso a disco, Drive e banco pertence à API."""
import streamlit as st
from .service_gateway import _request
from .config import api_base_url, api_key, setting


def _desktop():
    return setting('MAC_DESKTOP_MODE') == '1'


@st.cache_data(ttl=30, show_spinner=False)
def _listing(base_url, key, session, desktop):
    return _request('GET', '/api/v1/backups', params={'desktop': desktop})


def list_backups():
    from frontend.streamlit.google_login import session_token
    return _listing(api_base_url(), api_key(), session_token(), _desktop())


def refresh_backups():
    _listing.clear()


def create_backup():
    return _request('POST', '/api/v1/backups', json={'desktop': _desktop()})


def restore_backup(entry):
    return _request('POST', '/api/v1/backups/restore', json=dict(
        desktop=_desktop(), file_id=entry['id'], expected_sha256=entry['properties']['sha256'], confirm=True))


def job_status(identity):
    return _request('GET', f'/api/v1/backups/jobs/{identity}')
