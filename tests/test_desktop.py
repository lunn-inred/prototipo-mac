import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import desktop


class DesktopLauncherTests(unittest.TestCase):
    def test_resource_root_points_to_project_during_development(self):
        self.assertEqual(desktop.resource_root(), Path(desktop.__file__).resolve().parent)

    def test_load_environment_reads_values_without_overwriting_process(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment_file = Path(temporary_directory) / "desktop.env"
            environment_file.write_text(
                "# comentário\n"
                "MAC_API_BASE_URL='http://127.0.0.1:8000'\n"
                "MAC_API_KEY=arquivo\n"
                "LINHA_INVALIDA\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"MAC_API_KEY": "processo"}, clear=False):
                os.environ.pop("MAC_API_BASE_URL", None)
                desktop.load_environment(environment_file)
                self.assertEqual(os.environ["MAC_API_BASE_URL"], "http://127.0.0.1:8000")
                self.assertEqual(os.environ["MAC_API_KEY"], "processo")

    @patch("desktop.start_desktop_app")
    def test_main_starts_packaged_streamlit_in_desktop_window(self, start_desktop_app):
        original_directory = Path.cwd()
        try:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("MAC_DESKTOP_ENV_FILE", None)
                desktop.main()
        finally:
            os.chdir(original_directory)

        args, kwargs = start_desktop_app.call_args
        self.assertEqual(Path(args[0]).name, "app.py")
        self.assertEqual(kwargs["title"], "MAC Performance")
        self.assertEqual(kwargs["width"], 1440)
        self.assertEqual(kwargs["height"], 900)
        self.assertEqual(kwargs["options"]["server.fileWatcherType"], "none")
        if sys.platform.startswith("linux"):
            self.assertEqual(os.environ["QT_API"], "pyside6")

    def test_executable_root_uses_executable_location_when_frozen(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(
            sys, "executable", "/opt/mac/MAC Performance"
        ):
            self.assertEqual(desktop.executable_root(), Path("/opt/mac"))


if __name__ == "__main__":
    unittest.main()
