"""Google OAuth for the MAC account and its Drive backup folder."""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from backend.mac_api.core.settings import api_key, setting


router = APIRouter(prefix="/auth/google", tags=["Autenticação"])
_lock = threading.Lock()
_pending: dict[str, float] = {}
_tickets: dict[str, tuple[float, str]] = {}
_sessions: dict[str, tuple[float, str]] = {}
_SESSION_SECONDS = 12 * 60 * 60
_SHORT_SECONDS = 5 * 60
_SCOPE = "openid email profile https://www.googleapis.com/auth/drive.file"


def enabled() -> bool:
    return bool(setting("MAC_GOOGLE_CLIENT_ID"))


def _config() -> tuple[str, str, str, str, str]:
    names = (
        "MAC_GOOGLE_CLIENT_ID", "MAC_GOOGLE_CLIENT_SECRET",
        "MAC_GOOGLE_ALLOWED_EMAIL", "MAC_GOOGLE_REDIRECT_URI",
        "MAC_GOOGLE_FRONTEND_URL",
    )
    values = tuple((setting(name) or "").strip() for name in names)
    if not all(values):
        raise HTTPException(503, "Configuração do login Google incompleta.")
    if not api_key():
        raise HTTPException(503, "MAC_API_KEY é obrigatória com login Google.")
    client_id, secret, email, redirect, frontend = values
    if not redirect.endswith("/auth/google/callback"):
        raise HTTPException(503, "Endereço de retorno do Google inválido.")
    return client_id, secret, email.lower(), redirect, frontend.rstrip("/")


def _credentials_path() -> Path:
    raw = setting("MAC_GOOGLE_TOKEN_FILE")
    return Path(raw).expanduser().resolve() if raw else Path(__file__).resolve().parents[3] / "data" / "credentials" / "google-drive.json"


def _saved_credentials() -> dict[str, str]:
    path = _credentials_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_credentials(values: dict[str, str]) -> None:
    path = _credentials_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(values, target)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _prune(now: float) -> None:
    for collection in (_pending, _tickets, _sessions):
        for key, value in list(collection.items()):
            expiry = value if isinstance(value, float) else value[0]
            if expiry <= now:
                collection.pop(key, None)


def valid_session(token: str | None) -> bool:
    if not token:
        return False
    with _lock:
        session = _sessions.get(token)
        return bool(session and session[0] > time.time())


@router.get("/start")
def start() -> RedirectResponse:
    client_id, _, allowed_email, redirect, _ = _config()
    state = secrets.token_urlsafe(32)
    with _lock:
        _prune(time.time())
        _pending[state] = time.time() + _SHORT_SECONDS
    saved = _saved_credentials()
    prompt = "select_account" if saved.get("email") == allowed_email and saved.get("refresh_token") else "consent"
    query = urlencode({
        "client_id": client_id, "redirect_uri": redirect,
        "response_type": "code", "scope": _SCOPE, "state": state,
        "access_type": "offline", "prompt": prompt,
    })
    response = RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}")
    response.set_cookie(
        "mac_oauth_state", state, max_age=_SHORT_SECONDS, httponly=True,
        samesite="lax", secure=redirect.startswith("https://"),
    )
    return response


def _google_identity(id_token: str, client_id: str) -> dict:
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token as google_id_token

    return google_id_token.verify_oauth2_token(id_token, GoogleRequest(), client_id)


def _folder(access_token: str, existing_id: str | None) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}
    if existing_id:
        response = httpx.get(
            f"https://www.googleapis.com/drive/v3/files/{existing_id}",
            headers=headers, params={"fields": "id,trashed"}, timeout=15,
        )
        if response.status_code == 200 and not response.json().get("trashed"):
            return existing_id
    response = httpx.post(
        "https://www.googleapis.com/drive/v3/files",
        headers=headers,
        json={"name": "MAC Backups", "mimeType": "application/vnd.google-apps.folder"},
        params={"fields": "id"}, timeout=15,
    )
    response.raise_for_status()
    return response.json()["id"]


@router.get("/callback")
def callback(
    request: Request,
    code: str = Query(),
    state: str = Query(),
) -> RedirectResponse:
    client_id, secret, allowed_email, redirect, frontend = _config()
    cookie = request.cookies.get("mac_oauth_state", "")
    with _lock:
        expiry = _pending.pop(state, 0)
    if not cookie or not secrets.compare_digest(cookie, state) or expiry <= time.time():
        raise HTTPException(400, "Tentativa de login inválida ou expirada.")
    try:
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id, "client_secret": secret, "code": code,
                "grant_type": "authorization_code", "redirect_uri": redirect,
            }, timeout=20,
        )
        response.raise_for_status()
        tokens = response.json()
        identity = _google_identity(tokens["id_token"], client_id)
        email = str(identity.get("email", "")).lower()
        if identity.get("email_verified") is not True or email != allowed_email:
            raise HTTPException(403, "Esta conta Google não está autorizada no MAC.")
        saved = _saved_credentials()
        refresh = tokens.get("refresh_token") or (
            saved.get("refresh_token") if saved.get("email") == email else None
        )
        if not refresh:
            raise HTTPException(503, "O Google não concedeu acesso offline ao Drive.")
        folder_id = _folder(tokens["access_token"], saved.get("folder_id") if saved.get("email") == email else None)
        _save_credentials({"email": email, "refresh_token": refresh, "folder_id": folder_id})
    except httpx.HTTPError as error:
        raise HTTPException(502, "Não foi possível concluir a autorização no Google.") from error
    session = secrets.token_urlsafe(32)
    ticket = secrets.token_urlsafe(32)
    with _lock:
        _prune(time.time())
        _sessions[session] = (time.time() + _SESSION_SECONDS, email)
        _tickets[ticket] = (time.time() + _SHORT_SECONDS, session)
    result = RedirectResponse(f"{frontend}/?{urlencode({'mac_login_ticket': ticket})}")
    result.delete_cookie("mac_oauth_state")
    return result


@router.post("/redeem")
def redeem(ticket: str = Query(), x_api_key: str | None = Header(default=None)) -> dict[str, str]:
    expected = api_key()
    if not expected or not x_api_key or not secrets.compare_digest(expected, x_api_key):
        raise HTTPException(401, "Chave da API inválida.")
    with _lock:
        entry = _tickets.pop(ticket, None)
    if not entry or entry[0] <= time.time():
        raise HTTPException(400, "Login expirado ou já utilizado.")
    return {"session_token": entry[1]}


@router.get("/session")
def session_status(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    expected = api_key()
    if not expected or not x_api_key or not secrets.compare_digest(expected, x_api_key):
        raise HTTPException(401, "Chave da API inválida.")
    token = authorization.removeprefix("Bearer ") if authorization else None
    if not valid_session(token):
        raise HTTPException(401, "Sessão Google inválida ou expirada.")
    return {"status": "ok"}


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, str]:
    token = authorization.removeprefix("Bearer ") if authorization else ""
    with _lock:
        _sessions.pop(token, None)
    return {"status": "ok"}
