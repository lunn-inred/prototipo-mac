"""Presentation adapters for centrally computed metrics."""
from frontend.streamlit.api_client.service_gateway import _request
from frontend.streamlit.api_client.wire import encode, decode
import streamlit as st

@st.cache_data(ttl=60, show_spinner=False)
def call(operation, *args, **kwargs):
    response = _request('POST', f'/api/v1/analytics/{operation}',
                        json={'args': encode(args), 'kwargs': encode(kwargs)})
    return decode(response['result'])

def population_deviation(values):
    return call('population_deviation', list(values))
