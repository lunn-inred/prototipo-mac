"""Start the web UI from its own working directory, preserving theme settings."""
import os
import sys
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent / 'streamlit'
    os.chdir(root)
    from streamlit.web import cli
    sys.argv = ['streamlit', 'run', str(root / 'app.py'), *sys.argv[1:]]
    cli.main()

if __name__ == '__main__':
    main()
