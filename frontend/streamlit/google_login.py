"""Browser login handoff; the Google credentials stay in the API process."""

from __future__ import annotations

import httpx
import os
import streamlit as st
import webbrowser
from pathlib import Path

from frontend.streamlit.api_client.config import api_base_url, api_key, setting


def enabled() -> bool:
    return bool(setting("MAC_GOOGLE_CLIENT_ID"))


def session_token() -> str | None:
    return st.session_state.get("mac_google_session") if enabled() else None


def _desktop_session_path() -> Path:
    configured = setting("MAC_GOOGLE_DESKTOP_SESSION_FILE")
    return (Path(configured).expanduser().resolve() if configured else
            Path(__file__).resolve().parents[2] / "data" / "credentials" / "desktop-session.txt")


def _save_desktop_session(token: str) -> None:
    path = _desktop_session_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            target.write(token)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _clear_desktop_session() -> None:
    if setting("MAC_DESKTOP_MODE") == "1":
        _desktop_session_path().unlink(missing_ok=True)


def authenticated() -> bool:
    """Confirma a sessão antes de expor a navegação interna."""
    token = session_token()
    if not token:
        return False
    try:
        response = httpx.get(
            f"{api_base_url()}/auth/google/session",
            headers={"X-API-Key": api_key() or "", "Authorization": f"Bearer {token}"},
            timeout=5,
        )
    except httpx.HTTPError:
        st.session_state["mac_google_login_error"] = "Não foi possível verificar a sessão. Tente novamente."
        return False
    if response.status_code == 200:
        return True
    if response.status_code == 401:
        st.session_state.pop("mac_google_session", None)
        try:
            _clear_desktop_session()
        except OSError:
            pass
        st.session_state["mac_google_login_error"] = "Sua sessão expirou. Entre novamente."
    else:
        st.session_state["mac_google_login_error"] = "Não foi possível verificar a sessão. Tente novamente."
    return False


def restore_session() -> None:
    if not enabled():
        return
    if setting("MAC_DESKTOP_MODE") == "1" and not session_token():
        try:
            stored = _desktop_session_path().read_text(encoding="utf-8").strip()
            if stored:
                st.session_state["mac_google_session"] = stored
        except (OSError, UnicodeError):
            pass
    ticket = st.query_params.get("mac_login_ticket")
    if ticket:
        st.query_params.clear()
        try:
            response = httpx.post(
                f"{api_base_url()}/auth/google/redeem",
                params={"ticket": ticket},
                headers={"X-API-Key": api_key() or ""}, timeout=15,
            )
            response.raise_for_status()
            st.session_state["mac_google_session"] = response.json()["session_token"]
        except (httpx.HTTPError, KeyError, ValueError):
            st.session_state["mac_google_login_error"] = "O login expirou. Tente entrar novamente."


def render_login() -> None:
    """Página exclusiva exibida enquanto não há sessão Google."""
    st.title("MAC Performance")
    st.subheader("Entrar")
    st.write("Entre com a conta Google do MAC para continuar.")
    if message := st.session_state.pop("mac_google_login_error", None):
        st.error(message)
    if setting("MAC_DESKTOP_MODE") == "1":
        _render_desktop_login()
    else:
        public_api = (setting("MAC_GOOGLE_PUBLIC_API_URL") or "http://localhost:8000").rstrip("/")
        st.link_button("Entrar com Google", f"{public_api}/auth/google/start")


def _render_desktop_login() -> None:
    if not st.session_state.get("mac_desktop_poll_token") and st.button("Entrar com Google"):
        try:
            response = httpx.post(
                f"{api_base_url()}/auth/google/desktop/start",
                headers={"X-API-Key": api_key() or ""}, timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            st.session_state["mac_desktop_poll_token"] = data["poll_token"]
            st.session_state["mac_desktop_authorization_url"] = data["authorization_url"]
            webbrowser.open(data["authorization_url"], new=2)
        except (httpx.HTTPError, KeyError, ValueError):
            st.error("Não foi possível iniciar o login no navegador. Confira a configuração OAuth do desktop.")
    if st.session_state.get("mac_desktop_poll_token"):
        st.info("Conclua o login no navegador. O MAC abrirá suas páginas nesta janela.")
        st.link_button("Abrir a página do Google novamente", st.session_state["mac_desktop_authorization_url"])
        _wait_for_desktop_login()


@st.fragment(run_every="2s")
def _wait_for_desktop_login() -> None:
    poll_token = st.session_state.get("mac_desktop_poll_token")
    if not poll_token:
        return
    try:
        response = httpx.post(
            f"{api_base_url()}/auth/google/desktop/poll",
            json={"poll_token": poll_token},
            headers={"X-API-Key": api_key() or ""}, timeout=5,
        )
    except httpx.HTTPError:
        st.warning("Aguardando a API local para concluir o login.")
        return
    if response.status_code == 202:
        return
    st.session_state.pop("mac_desktop_poll_token", None)
    st.session_state.pop("mac_desktop_authorization_url", None)
    if response.status_code == 200:
        try:
            token = response.json()["session_token"]
            st.session_state["mac_google_session"] = token
            try:
                _save_desktop_session(token)
            except OSError:
                st.session_state["mac_google_login_error"] = "Não foi possível lembrar o login neste computador."
        except (KeyError, ValueError):
            st.session_state["mac_google_login_error"] = "A resposta do login é inválida. Tente novamente."
        st.rerun()
    elif response.status_code == 410:
        st.session_state["mac_google_login_error"] = "O login expirou. Clique em Entrar com Google para tentar novamente."
        st.rerun()
    else:
        st.session_state["mac_google_login_error"] = "O login não foi concluído. Clique em Entrar com Google para tentar novamente."
        st.rerun()


def render_logout() -> None:
    """Ação de saída disponível apenas na navegação autenticada."""
    if not enabled() or not session_token():
        return

    with st.sidebar:
        if st.button("Sair da conta Google"):
            try:
                httpx.post(
                    f"{api_base_url()}/auth/google/logout",
                    headers={"Authorization": f"Bearer {session_token()}"}, timeout=5,
                )
            except httpx.HTTPError:
                pass
            st.session_state.pop("mac_google_session", None)
            try:
                _clear_desktop_session()
            except OSError:
                st.session_state["mac_google_login_error"] = "Não foi possível remover a sessão salva neste computador."
            st.rerun()
