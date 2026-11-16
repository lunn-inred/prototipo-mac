"""The source entry point selects the project environment before importing GUI packages."""

import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class DesktopEntryTests(unittest.TestCase):
    def test_system_python_restarts_with_project_venv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "desktop.py"
            script.write_text((Path(__file__).resolve().parents[2] / "desktop.py").read_text(encoding="utf-8"), encoding="utf-8")
            interpreter = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            interpreter.parent.mkdir(parents=True)
            interpreter.touch()
            switch = runpy.run_path(str(script), run_name="desktop_entry_test")["_use_project_venv"]

            with patch.object(sys, "prefix", str(root / "other-venv")), \
                 patch.object(sys, "argv", [str(script), "--example"]), \
                 patch.dict(os.environ, {"PATH": "original-path"}), \
                 patch("os.execv") as execv:
                switch()
                execv.assert_called_once_with(str(interpreter), [str(interpreter), str(script), "--example"])
                self.assertEqual(os.environ["VIRTUAL_ENV"], str(root / ".venv"))
                self.assertTrue(os.environ["PATH"].startswith(str(interpreter.parent)))

            with patch.object(sys, "prefix", str(root / ".venv")), patch("os.execv") as execv:
                switch()
                execv.assert_not_called()


if __name__ == "__main__":
    unittest.main()
