import ast
import subprocess
import sys
import unittest
from pathlib import Path


class FrontendBoundaryTests(unittest.TestCase):
    def test_frontend_never_imports_backend_database_or_processing_dependencies(self):
        root = Path(__file__).resolve().parents[1] / 'streamlit'
        forbidden = ('backend', 'psycopg2', 'cv2', 'scipy', 'pytesseract', 'img2table')
        for path in root.rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                modules = ([node.module or ''] if isinstance(node, ast.ImportFrom)
                           else [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
                for module in modules:
                    self.assertNotIn(module.split('.')[0], forbidden, f'{path}: {module}')

    def test_import_client_does_not_load_backend_even_without_api_configuration(self):
        script = "import sys; import frontend.streamlit.api_client.service_gateway; assert not any(n == 'backend' or n.startswith('backend.') for n in sys.modules)"
        subprocess.run([sys.executable, '-c', script], check=True,
                       cwd=Path(__file__).resolve().parents[2])
