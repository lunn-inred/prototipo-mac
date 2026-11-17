import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import desktop.launcher as desktop
class DesktopLauncherTests(unittest.TestCase):
    def test_managed_api_logging_includes_backend_without_http_request_logs(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('uvicorn.run') as run, \
             patch.object(sys, 'platform', 'win32'), \
             patch.dict(os.environ, MAC_DESKTOP_MANAGED='1'), \
             patch('desktop.windows_os.known_directory', return_value=Path(directory)):
            desktop.run_local_api(8123)
            config = run.call_args.kwargs['log_config']
            self.assertEqual(config['loggers']['backend']['handlers'], ['file'])
            self.assertEqual(config['loggers']['backend']['level'], 'INFO')
            self.assertFalse(run.call_args.kwargs['access_log'])
            self.assertNotIn('httpx', config['loggers'])

    def test_resource_root_points_to_project_during_development(self):
        self.assertEqual(desktop.resource_root(), Path(desktop.__file__).resolve().parents[1])

    def test_load_environment_reads_values_without_overwriting_process(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment_file = Path(temporary_directory) / ".env"
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

    def test_unified_environment_overrides_stale_process_value(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment_file = Path(temporary_directory) / ".env"
            environment_file.write_text(
                "MAC_API_KEY=backend\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"MAC_API_KEY": "cliente"}, clear=False):
                desktop.load_environment(environment_file, override=True)
                self.assertEqual(os.environ["MAC_API_KEY"], "backend")

    @patch("desktop.launcher.stop_process")
    @patch("desktop.launcher.start_local_api")
    @patch("desktop.launcher.start_desktop_app")
    def test_development_main_uses_separately_started_api(
        self, start_desktop_app, start_local_api, stop_process
    ):
        original_directory = Path.cwd()
        try:
            with patch.dict(
                os.environ,
                {"MAC_API_BASE_URL": "http://127.0.0.1:8000"},
                clear=False,
            ):
                desktop.main()
        finally:
            os.chdir(original_directory)

        args, kwargs = start_desktop_app.call_args
        self.assertEqual(Path(args[0]).name, "app.py")
        self.assertEqual(kwargs["title"], "MAC Performance")
        self.assertEqual(kwargs["width"], 1920)
        self.assertEqual(kwargs["height"], 1080)
        self.assertEqual(kwargs["options"]["server.fileWatcherType"], "none")
        start_local_api.assert_not_called()
        stop_process.assert_called_once_with(None)
        if sys.platform.startswith("linux"):
            self.assertEqual(os.environ["QT_API"], "pyside6")

    def test_linux_window_uses_mac_logo_as_icon(self):
        if not sys.platform.startswith('linux'):
            self.skipTest('Ícone da janela Qt verificado somente no Linux.')
        original_directory = Path.cwd()
        window_options = {}

        def capture_window(*_args, **_kwargs):
            window_options.update(desktop.webview.start.keywords)

        try:
            with patch('desktop.launcher.start_desktop_app', side_effect=capture_window) as start, \
                 patch('desktop.launcher.stop_process'):
                desktop.main()
                self.assertEqual(window_options['gui'], 'qt')
                self.assertEqual(Path(window_options['icon']).name, 'logo_mac.png')
                start.assert_called_once()
        finally:
            os.chdir(original_directory)

    @patch("desktop.launcher.stop_process")
    @patch("desktop.launcher.start_local_api")
    @patch("desktop.launcher.start_desktop_app")
    def test_frozen_main_starts_integrated_api(
        self, start_desktop_app, start_local_api, stop_process
    ):
        api_process = Mock()
        start_local_api.return_value = (api_process, 9123)
        original_directory = Path.cwd()
        try:
            with patch.object(sys, "frozen", True, create=True), patch.object(
                desktop, "configure_runtime", return_value=desktop.resource_root() / "frontend/streamlit/app.py"
            ), patch.dict(os.environ, {}, clear=False):
                desktop.main()
                self.assertEqual(
                    os.environ["MAC_API_BASE_URL"], "http://127.0.0.1:9123"
                )
        finally:
            os.chdir(original_directory)

        start_local_api.assert_called_once_with()
        stop_process.assert_called_once_with(api_process)
        start_desktop_app.assert_called_once()
        self.assertEqual(start_desktop_app.call_args.kwargs["width"], 1920)
        self.assertEqual(start_desktop_app.call_args.kwargs["height"], 1080)

    @patch("desktop.launcher.wait_for_api")
    @patch("desktop.launcher.find_free_port", return_value=9123)
    @patch("desktop.launcher.multiprocessing.Process")
    def test_start_local_api_waits_until_health_check(
        self, process_class, _find_free_port, wait_for_api
    ):
        process = process_class.return_value
        result_process, port = desktop.start_local_api()

        self.assertIs(result_process, process)
        self.assertEqual(port, 9123)
        process.start.assert_called_once_with()
        wait_for_api.assert_called_once_with(9123, process)

    def test_executable_root_uses_executable_location_when_frozen(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(
            sys, "executable", "/opt/mac/MAC Performance"
        ):
            self.assertEqual(desktop.executable_root(), Path("/opt/mac/MAC Performance").resolve().parent)

    def test_frozen_credentials_are_stored_beside_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            original_directory = Path.cwd()
            (Path(directory) / '.env').write_text('', encoding='utf-8')
            try:
                with patch.object(sys, "frozen", True, create=True), \
                     patch.object(sys, "executable", str(Path(directory) / "MAC Performance")), \
                     patch.object(desktop, "resource_root", return_value=Path(desktop.__file__).resolve().parents[1]), \
                     patch('desktop.windows_runtime.installation_file', return_value=Path(directory)/'installation.json'), \
                     patch.dict(os.environ, {}, clear=True):
                    desktop.configure_runtime()
                    self.assertEqual(
                        os.environ["MAC_GOOGLE_DESKTOP_TOKEN_FILE"],
                        str(Path(directory) / "data/credentials/google-drive-desktop.json"),
                    )
                    self.assertEqual(
                        os.environ["MAC_GOOGLE_DESKTOP_REMEMBER_FILE"],
                        str(Path(directory) / "data/credentials/desktop-remember.json"),
                    )
                    self.assertEqual(
                        os.environ["MAC_GOOGLE_DESKTOP_SESSION_FILE"],
                        str(Path(directory) / "data/credentials/desktop-session.txt"),
                    )
            finally:
                os.chdir(original_directory)


if __name__ == "__main__":
    unittest.main()
