"""Unauthenticated users only receive the dedicated login page."""

import os
import unittest
from pathlib import Path
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

        with patch.dict(os.environ, MAC_GOOGLE_CLIENT_ID='test-client', MAC_DESKTOP_MODE='1'), \
             patch('frontend.streamlit.google_login.httpx.post', side_effect=[StartResponse(), PendingResponse()]), \
             patch('frontend.streamlit.google_login.webbrowser.open', return_value=True) as open_browser:
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            self.assertFalse(app.get('link_button'))
            app.button[0].click().run()

        self.assertFalse(app.exception)
        open_browser.assert_called_once()
        self.assertEqual(app.session_state['mac_desktop_poll_token'], 'test-poll')
        self.assertTrue(any('Conclua o login' in item.value for item in app.info))

    def test_desktop_completion_puts_session_in_webview(self):
        class CompletedResponse:
            status_code = 200

            def json(self):
                return {'session_token': 'desktop-session'}

        state = {
            'mac_desktop_poll_token': 'test-poll',
            'mac_desktop_authorization_url': 'https://accounts.google.com',
        }
        with patch.object(google_login.st, 'session_state', state), \
             patch.object(google_login.httpx, 'post', return_value=CompletedResponse()), \
             patch.object(google_login.st, 'rerun') as rerun:
            google_login._wait_for_desktop_login.__wrapped__()

        self.assertEqual(state['mac_google_session'], 'desktop-session')
        self.assertNotIn('mac_desktop_poll_token', state)
        rerun.assert_called_once_with()

    def test_desktop_login_failure_returns_to_retry_button(self):
        class FailedResponse:
            status_code = 400

        state = {
            'mac_desktop_poll_token': 'test-poll',
            'mac_desktop_authorization_url': 'https://accounts.google.com',
        }
        with patch.object(google_login.st, 'session_state', state), \
             patch.object(google_login.httpx, 'post', return_value=FailedResponse()), \
             patch.object(google_login.st, 'rerun') as rerun:
            google_login._wait_for_desktop_login.__wrapped__()

        self.assertNotIn('mac_desktop_poll_token', state)
        self.assertIn('mac_google_login_error', state)
        rerun.assert_called_once_with()
