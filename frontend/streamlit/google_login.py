"""Browser login handoff; the Google credentials stay in the API process."""

from __future__ import annotations

import httpx
import streamlit as st

from frontend.streamlit.api_client.config import api_base_url, api_key, setting


def enabled() -> bool:
    return bool(setting("MAC_GOOGLE_CLIENT_ID"))


def session_token() -> str | None:
    return st.session_state.get("mac_google_session") if enabled() else None


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
        st.session_state["mac_google_login_error"] = "Sua sessão expirou. Entre novamente."
    else:
        st.session_state["mac_google_login_error"] = "Não foi possível verificar a sessão. Tente novamente."
    return False


def restore_session() -> None:
    if not enabled():
        return
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
    public_api = (setting("MAC_GOOGLE_PUBLIC_API_URL") or "http://localhost:8000").rstrip("/")
    st.link_button("Entrar com Google", f"{public_api}/auth/google/start")


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
            st.rerun()
