"""Client configuration. Database credentials are never consumed here."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / '.env')

def setting(name, default=None):
    value = os.getenv(name)
    if value is not None:
        return value
    if name in {'MAC_API_BASE_URL', 'MAC_API_KEY', 'MAC_API_TIMEOUT_SECONDS'}:
        import streamlit as st
        try:
            return st.secrets.get(name, default)
        except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
            pass
    return default

def api_base_url():
    return (setting('MAC_API_BASE_URL') or 'http://127.0.0.1:8000').rstrip('/')

def api_key():
    return setting('MAC_API_KEY')
