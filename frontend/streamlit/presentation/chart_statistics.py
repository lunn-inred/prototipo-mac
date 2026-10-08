from __future__ import annotations
from collections import defaultdict
from collections.abc import Callable
from frontend.streamlit.api_client.analytics_client import call

def daily_statistics(records, value_getter):
    projected = [{"data_coleta": record["data_coleta"], "value": value_getter(record)} for record in records]
    return call('chart_statistics.daily', projected)
