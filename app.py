"""Compatibility entry point: streamlit run app.py."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parent / 'frontend/streamlit/app.py'), run_name='__main__')
