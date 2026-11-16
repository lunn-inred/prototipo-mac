import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import Mock
from uuid import uuid4

from desktop import windows_os, windows_runtime, windows_setup


class WindowsSetupTests(unittest.TestCase):
    def test_service_waits_for_recovery_beyond_sixty_seconds(self):
        service = SimpleNamespace(SC_MANAGER_CONNECT=1, SERVICE_START=16,
            SERVICE_QUERY_STATUS=4, SERVICE_STOPPED=1, SERVICE_RUNNING=4,
            OpenSCManager=Mock(return_value=10), OpenService=Mock(return_value=20),
            QueryServiceStatus=Mock(side_effect=[(0,1),(0,2),(0,4)]),
            StartService=Mock(), CloseServiceHandle=Mock())
        with patch.dict('sys.modules', win32service=service), \
             patch.object(windows_os.time, 'monotonic', side_effect=[0,70,71]), \
             patch.object(windows_os.time, 'sleep'):
            windows_os.start_service()
        service.StartService.assert_called_once_with(20, None)
        self.assertEqual(service.CloseServiceHandle.call_count, 2)

    def test_existing_local_group_is_accepted_but_access_denied_is_not(self):
        for code in (1379, 2223, 5):
            with self.subTest(code=code):
                error = OSError('group operation failed')
                error.winerror = code
                network = SimpleNamespace(NetLocalGroupAdd=Mock(side_effect=error), NetLocalGroupAddMembers=Mock())
                security = SimpleNamespace(LookupAccountName=Mock(return_value=('sid', None, None)),
                                           ConvertSidToStringSid=Mock(return_value='group-sid'))
                with patch.dict('sys.modules', win32net=network, win32security=security):
                    if code == 5:
                        with self.assertRaises(OSError):
                            windows_os.authorized_group('user')
                        network.NetLocalGroupAddMembers.assert_not_called()
                    else:
                        self.assertEqual(windows_os.authorized_group('user'), 'group-sid')

    def test_initdb_uses_native_restriction_without_inheriting_bypass_marker(self):
        with patch.dict(os.environ, PG_RESTRICT_EXEC='1'), patch.object(windows_os, 'run_tool') as run:
            windows_os.restricted_initdb(['initdb.exe', '--auth=scram-sha-256'])
        self.assertEqual(run.call_args.args[0], ['initdb.exe', '--auth=scram-sha-256'])
        self.assertNotIn('PG_RESTRICT_EXEC', run.call_args.kwargs['env'])

    def test_token_handle_is_closed_without_context_manager_support(self):
        token = SimpleNamespace(Close=Mock())
        security = SimpleNamespace(OpenProcessToken=Mock(return_value=token),
            TokenUser=1, GetTokenInformation=Mock(return_value=('sid', 0)),
            ConvertSidToStringSid=Mock(return_value='user-sid'))
        modules = {'win32api': SimpleNamespace(GetCurrentProcess=lambda: 1),
                   'win32con': SimpleNamespace(TOKEN_QUERY=8), 'win32security': security}
        with patch.dict('sys.modules', modules):
            self.assertEqual(windows_os.current_sid(), 'user-sid')
            token.Close.assert_called_once()
            token.Close.reset_mock()
            security.GetTokenInformation.side_effect = RuntimeError('token unavailable')
            with self.assertRaises(RuntimeError):
                windows_os.current_sid()
            token.Close.assert_called_once()

    def state(self,root):
        return dict(format=1,id=str(uuid4()),service=windows_os.SERVICE,
                    postgres_major=17,port=55434,install_dir=str(root/'app'),status='ready')

    def test_configuration_and_user_files_are_outside_install_directory(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            def known(common):return root/('machine' if common else 'user')
            with patch.object(windows_os,'known_directory',side_effect=known),patch.object(windows_os,'protect'),patch.object(windows_os,'current_sid',return_value='user-sid'),patch.dict(os.environ,{},clear=True):
                windows_runtime.configure_user_paths(self.state(root))
                self.assertEqual(os.environ['MAC_ANALYSES_DIR'],str(root/'machine/thermography'))
                self.assertEqual(os.environ['MAC_GOOGLE_DESKTOP_TOKEN_FILE'],str(root/'user/credentials/google-drive-desktop.json'))
                self.assertEqual(os.environ['MAC_LOCAL_DB_HOST'],'127.0.0.1')
                self.assertEqual(os.environ['MAC_LOCAL_DB_PORT'],'55434')

    def test_backup_is_checked_without_password_in_command_line(self):
        with TemporaryDirectory() as directory:
            root=Path(directory); commands=[]
            def run(arguments,**kwargs):
                commands.append((arguments,kwargs))
                for item in arguments:
                    if str(item).startswith('--file='):
                        Path(str(item)[7:]).write_bytes(b'PGDMP-test')
            with patch.object(windows_os,'known_directory',return_value=root),patch.object(windows_os,'run_tool',side_effect=run):
                path=windows_runtime.backup_database(dict(port=55434,user='mac_app',password='never-log-this'),self.state(root))
            self.assertTrue(path.with_suffix('.sha256').is_file())
            self.assertEqual(len(commands),2)
            self.assertNotIn('never-log-this',str([c[0] for c in commands]))
            self.assertEqual(commands[0][1]['env']['PGOPTIONS'],'-c default_transaction_read_only=on')

    def test_unknown_service_is_not_started(self):
        with patch.object(windows_os,'service_configuration',return_value=None),patch.object(windows_os,'start_service') as start:
            with self.assertRaisesRegex(RuntimeError,'ausente'):
                windows_runtime.ensure_database(self.state(Path('/app')))
            start.assert_not_called()

    def test_foreign_service_is_refused(self):
        with patch.object(windows_os,'service_configuration',return_value=(None,None,None,'other.exe')),patch.object(windows_os,'known_directory',return_value=Path('/machine')):
            with self.assertRaisesRegex(RuntimeError,'não pertence'):
                windows_runtime.verify_service(self.state(Path('/app')))

    def test_installer_cannot_execute_on_linux(self):
        with patch.object(windows_setup.sys,'platform','linux'):
            with self.assertRaisesRegex(RuntimeError,'Windows'):
                windows_setup.main(['--setup-action','install'])

    def test_managed_launcher_prepares_database_before_api(self):
        import desktop.launcher as launcher
        calls=[]
        instance=Mock()
        script=Path(launcher.__file__).resolve().parents[1]/'frontend/streamlit/app.py'
        with patch.object(launcher.sys,'platform','win32'),patch.object(launcher.sys,'frozen',True,create=True), \
             patch.object(launcher,'configure_runtime',return_value=script), \
             patch.dict(os.environ,MAC_DESKTOP_MANAGED='1'), \
             patch.object(windows_os,'instance_lock',return_value=instance), \
             patch.object(windows_runtime,'prepare',side_effect=lambda:calls.append('database')), \
             patch.object(launcher,'start_local_api',side_effect=lambda:(calls.append('api') or (Mock(),9123))), \
             patch.object(launcher,'start_desktop_app',side_effect=lambda *a,**kw:calls.append('window')), \
             patch.object(launcher,'stop_process'):
            launcher.main()
        self.assertEqual(calls,['database','api','window'])
        instance.Close.assert_called_once()

    def test_failed_database_preparation_does_not_open_window_or_api(self):
        import desktop.launcher as launcher
        instance=Mock()
        script=Path(launcher.__file__).resolve().parents[1]/'frontend/streamlit/app.py'
        with patch.object(launcher.sys,'platform','win32'),patch.object(launcher.sys,'frozen',True,create=True), \
             patch.object(launcher,'configure_runtime',return_value=script), \
             patch.dict(os.environ,MAC_DESKTOP_MANAGED='1'), \
             patch.object(windows_os,'instance_lock',return_value=instance), \
             patch.object(windows_runtime,'prepare',side_effect=RuntimeError('schema incompatível')), \
             patch.object(windows_runtime,'show_error') as error, \
             patch.object(launcher,'start_local_api') as api, \
             patch.object(launcher,'start_desktop_app') as window, \
             patch.object(launcher,'stop_process'):
            with self.assertRaises(SystemExit):
                launcher.main()
        api.assert_not_called();window.assert_not_called();error.assert_called_once()
        instance.Close.assert_called_once()
