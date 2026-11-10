"""Unauthenticated users only receive the dedicated login page."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest


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
