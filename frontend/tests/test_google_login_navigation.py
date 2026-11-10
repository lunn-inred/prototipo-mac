"""Unauthenticated users only receive the dedicated login page."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest
from frontend.streamlit import google_login


APP = Path(__file__).resolve().parents[1] / "streamlit" / "app.py"


class GoogleLoginNavigationTests(unittest.TestCase):
    def test_logged_out_navigation_contains_only_login_page(self):
        original = st.navigation
        declarations = []

        def capture(pages, **kwargs):
            declarations.append((pages, kwargs))
            return original(pages, **kwargs)

        with patch.dict(os.environ, MAC_GOOGLE_CLIENT_ID="test-client"), \
             patch("frontend.streamlit.google_login.authenticated", return_value=False), \
             patch.object(st, "navigation", side_effect=capture):
            app = AppTest.from_file(str(APP), default_timeout=20).run()

        self.assertFalse(app.exception)
        self.assertEqual([button.label for button in app.get("link_button")], ["Entrar com Google"])
        self.assertEqual(len(app.get("image")), 1)
        self.assertTrue(any("google_login_card" in block.proto.id for block in app.get("flex_container")))
        self.assertEqual(len(declarations), 1)
        pages, options = declarations[0]
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].title, "Entrar")
        self.assertEqual(options["position"], "hidden")

    def test_authenticated_navigation_contains_application_pages(self):
        original = st.navigation
        declarations = []

        def capture(pages, **kwargs):
            declarations.append((pages, kwargs))
            return original(pages, **kwargs)

        with patch.dict(os.environ, MAC_GOOGLE_CLIENT_ID="test-client"), \
             patch("frontend.streamlit.google_login.authenticated", return_value=True), \
             patch("frontend.streamlit.google_login.render_logout"), \
             patch.object(st, "navigation", side_effect=capture):
            app = AppTest.from_file(str(APP), default_timeout=20).run()

        self.assertFalse(app.exception)
        self.assertEqual(len(declarations), 1)
        pages, _ = declarations[0]
        self.assertEqual(
            [page.title for page in pages],
            ["Jogadores", "Monitoramento GPS", "Monitoramento Salto", "Termografia", "Timeline térmica"],
        )

    def test_logout_button_is_in_authenticated_sidebar(self):
        with patch.dict(os.environ, MAC_GOOGLE_CLIENT_ID="test-client"), \
             patch("frontend.streamlit.google_login.authenticated", return_value=True):
            app = AppTest.from_file(str(APP), default_timeout=20)
            app.session_state["mac_google_session"] = "test-session"
            app.run()

        self.assertFalse(app.exception)
        self.assertEqual([button.label for button in app.sidebar.button], ["Sair da Conta"])
        self.assertEqual(app.sidebar.button[0].key, "google_logout")

    def test_expired_session_returns_to_login_page(self):
        class ExpiredResponse:
            status_code = 401

        with patch.dict(os.environ, MAC_GOOGLE_CLIENT_ID="test-client"), \
             patch("frontend.streamlit.google_login.httpx.get", return_value=ExpiredResponse()):
            app = AppTest.from_file(str(APP), default_timeout=20)
            app.session_state["mac_google_session"] = "expired-session"
            app.run()

        self.assertFalse(app.exception)
        self.assertEqual([button.label for button in app.get("link_button")], ["Entrar com Google"])
        self.assertEqual([title.value for title in app.title], ["MAC Performance"])

    def test_desktop_login_opens_system_browser_and_waits_in_webview(self):
        class StartResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    'authorization_url': 'https://accounts.google.com/o/oauth2/v2/auth?state=test',
                    'poll_token': 'test-poll',
                }

        class PendingResponse:
            status_code = 202

        def post_for_login(url, **_kwargs):
            return StartResponse() if url.endswith('/desktop/start') else PendingResponse()

        with patch.dict(os.environ, MAC_GOOGLE_CLIENT_ID='test-client', MAC_DESKTOP_MODE='1'), \
             patch('frontend.streamlit.google_login.httpx.post', side_effect=post_for_login) as post, \
             patch('frontend.streamlit.google_login.webbrowser.open', return_value=True) as open_browser:
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            self.assertFalse(app.get('link_button'))
            app.button[0].click().run()
            self.assertEqual([button.label for button in app.button], ['Entrar com Google'])
            app.button[0].click().run()

        self.assertFalse(app.exception)
        self.assertEqual(open_browser.call_count, 2)
        self.assertEqual(sum(call.args[0].endswith('/desktop/start') for call in post.call_args_list), 1)
        self.assertEqual(app.session_state['mac_desktop_poll_token'], 'test-poll')
        self.assertTrue(any('Conclua o login' in item.value for item in app.info))
        self.assertFalse(app.get('link_button'))

    def test_desktop_completion_puts_session_in_webview(self):
        class CompletedResponse:
            status_code = 200

            def json(self):
                return {'session_token': 'desktop-session'}

        state = {
            'mac_desktop_poll_token': 'test-poll',
        }
        with TemporaryDirectory() as directory:
            session_file = Path(directory) / 'session.txt'
            with patch.dict(os.environ, MAC_GOOGLE_DESKTOP_SESSION_FILE=str(session_file)), \
                 patch.object(google_login.st, 'session_state', state), \
                 patch.object(google_login.httpx, 'post', return_value=CompletedResponse()), \
                 patch.object(google_login.st, 'rerun') as rerun:
                google_login._wait_for_desktop_login.__wrapped__()
            self.assertEqual(session_file.read_text(encoding='utf-8'), 'desktop-session')

        self.assertEqual(state['mac_google_session'], 'desktop-session')
        self.assertNotIn('mac_desktop_poll_token', state)
        rerun.assert_called_once_with()

    def test_desktop_restores_saved_session_and_removes_expired_one(self):
        class ExpiredResponse:
            status_code = 401

        with TemporaryDirectory() as directory:
            session_file = Path(directory) / 'session.txt'
            session_file.write_text('saved-session', encoding='utf-8')
            state = {}
            with patch.dict(os.environ, MAC_GOOGLE_CLIENT_ID='test-client', MAC_DESKTOP_MODE='1',
                            MAC_GOOGLE_DESKTOP_SESSION_FILE=str(session_file)), \
                 patch.object(google_login.st, 'session_state', state), \
                 patch.object(google_login.st, 'query_params', {}), \
                 patch.object(google_login.httpx, 'get', return_value=ExpiredResponse()):
                google_login.restore_session()
                self.assertEqual(state['mac_google_session'], 'saved-session')
                self.assertFalse(google_login.authenticated())
            self.assertFalse(session_file.exists())

    def test_desktop_login_failure_returns_to_retry_button(self):
        class FailedResponse:
            status_code = 400

        state = {
            'mac_desktop_poll_token': 'test-poll',
        }
        with patch.object(google_login.st, 'session_state', state), \
             patch.object(google_login.httpx, 'post', return_value=FailedResponse()), \
             patch.object(google_login.st, 'rerun') as rerun:
            google_login._wait_for_desktop_login.__wrapped__()

        self.assertNotIn('mac_desktop_poll_token', state)
        self.assertIn('mac_google_login_error', state)
        rerun.assert_called_once_with()
