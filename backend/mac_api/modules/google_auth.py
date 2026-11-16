"""Google OAuth for the MAC account and its Drive backup folder."""

from __future__ import annotations

import json
import base64
import hashlib
import os
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from backend.mac_api.core.settings import api_key, setting


router = APIRouter(prefix="/auth/google", tags=["Autenticação"])
_lock = threading.Lock()
_pending: dict[str, float] = {}
_tickets: dict[str, tuple[float, str]] = {}
_sessions: dict[str, tuple[float, str]] = {}
_desktop_pending: dict[str, tuple[float, str, str, str, str, str, bool]] = {}
_desktop_results: dict[str, tuple[float, str | None, str | None]] = {}
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


def _credentials_path(*, desktop: bool = False) -> Path:
    if desktop:
        raw = setting("MAC_GOOGLE_DESKTOP_TOKEN_FILE")
        return Path(raw).expanduser().resolve() if raw else Path(__file__).resolve().parents[3] / "data" / "credentials" / "google-drive-desktop.json"
    raw = setting("MAC_GOOGLE_TOKEN_FILE")
    return Path(raw).expanduser().resolve() if raw else Path(__file__).resolve().parents[3] / "data" / "credentials" / "google-drive.json"


def _saved_credentials(*, desktop: bool = False) -> dict[str, str]:
    path = _credentials_path(desktop=desktop)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_credentials(values: dict[str, str], *, desktop: bool = False) -> None:
    path = _credentials_path(desktop=desktop)
    _write_private_json(path, values)


def _write_private_json(path: Path, values: dict) -> None:
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


def _remember_path() -> Path:
    raw = setting("MAC_GOOGLE_DESKTOP_REMEMBER_FILE")
    return Path(raw).expanduser().resolve() if raw else Path(__file__).resolve().parents[3] / "data" / "credentials" / "desktop-remember.json"


def _remembered_session() -> dict:
    try:
        value = json.loads(_remember_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _remember_session(token: str, email: str, expiry: float) -> None:
    _write_private_json(_remember_path(), {
        "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "email": email, "expires_at": expiry,
    })


def _forget_session(token: str) -> None:
    remembered = _remembered_session()
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if remembered.get("token_hash") and secrets.compare_digest(remembered["token_hash"], digest):
        _remember_path().unlink(missing_ok=True)


def _prune(now: float) -> None:
    for collection in (_pending, _tickets, _sessions, _desktop_pending, _desktop_results):
        for key, value in list(collection.items()):
            expiry = value if isinstance(value, float) else value[0]
            if expiry <= now:
                collection.pop(key, None)


def valid_session(token: str | None) -> bool:
    if not token:
        return False
    with _lock:
        session = _sessions.get(token)
        if session and session[0] > time.time():
            return True
        remembered = _remembered_session()
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expiry = remembered.get("expires_at", 0)
        email = remembered.get("email", "")
        expected_email = (setting("MAC_GOOGLE_ALLOWED_EMAIL") or "").strip().lower()
        if (
            isinstance(expiry, (int, float)) and expiry > time.time()
            and email == expected_email and bool(expected_email)
            and isinstance(remembered.get("token_hash"), str)
            and secrets.compare_digest(remembered["token_hash"], digest)
        ):
            _sessions[token] = (expiry, email)
            return True
        return False


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


class DesktopPollInput(BaseModel):
    poll_token: str


def _require_internal_key(value: str | None) -> None:
    expected = api_key()
    if not expected or not value or not secrets.compare_digest(expected, value):
        raise HTTPException(401, "Chave da API inválida.")


def _desktop_client(request: Request) -> tuple[str, str, str, bool]:
    client_id = (setting("MAC_GOOGLE_DESKTOP_CLIENT_ID") or "").strip()
    client_secret = (setting("MAC_GOOGLE_DESKTOP_CLIENT_SECRET") or "").strip()
    if bool(client_id) != bool(client_secret):
        raise HTTPException(503, "Configure ID e secret do cliente OAuth Desktop app.")
    if client_id and client_secret:
        redirect = str(request.url_for("callback"))
        parsed = urlparse(redirect)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise HTTPException(503, "O login desktop exige retorno na API local.")
        return client_id, client_secret, redirect, True
    web_id, web_secret, _, redirect, _ = _config()
    requested_port = request.url.port or (443 if request.url.scheme == "https" else 80)
    if urlparse(redirect).port != requested_port:
        raise HTTPException(503, "Configure um cliente OAuth Desktop app para a porta variável do executável.")
    return web_id, web_secret, redirect, False


@router.post("/desktop/start")
def desktop_start(request: Request, x_api_key: str | None = Header(default=None)) -> dict[str, str]:
    _require_internal_key(x_api_key)
    _, _, allowed_email, _, _ = _config()
    client_id, client_secret, redirect, native = _desktop_client(request)
    state = secrets.token_urlsafe(32)
    poll_token = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    with _lock:
        _prune(time.time())
        expiry = time.time() + _SHORT_SECONDS
        _desktop_pending[state] = (expiry, poll_token, verifier, redirect, client_id, client_secret, native)
        _desktop_results[poll_token] = (expiry, None, None)
    saved = _saved_credentials(desktop=native)
    prompt = "select_account" if saved.get("email") == allowed_email and saved.get("refresh_token") else "consent"
    query = urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": _SCOPE, "state": state, "access_type": "offline", "prompt": prompt,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    return {"authorization_url": f"https://accounts.google.com/o/oauth2/v2/auth?{query}", "poll_token": poll_token}


@router.post("/desktop/poll")
def desktop_poll(payload: DesktopPollInput, x_api_key: str | None = Header(default=None)) -> Response:
    _require_internal_key(x_api_key)
    with _lock:
        result = _desktop_results.get(payload.poll_token)
        if result and result[1] is not None:
            _desktop_results.pop(payload.poll_token, None)
    if not result or result[0] <= time.time():
        raise HTTPException(410, "A tentativa de login expirou. Tente novamente.")
    if result[2]:
        with _lock:
            _desktop_results.pop(payload.poll_token, None)
        raise HTTPException(400, result[2])
    if result[1] is None:
        return Response(status_code=202)
    return JSONResponse({"session_token": result[1]})


def _google_identity(id_token: str, client_id: str) -> dict:
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token as google_id_token

    return google_id_token.verify_oauth2_token(id_token, GoogleRequest(), client_id)


def _folder(access_token: str) -> str:
    """Valida o único destino configurado; nunca cria pastas nem usa IDs em cache."""
    folder_id = (setting('MAC_GOOGLE_BACKUP_FOLDER_ID') or '').strip()
    if not folder_id:
        raise HTTPException(503, 'Configure MAC_GOOGLE_BACKUP_FOLDER_ID no .env com o ID da pasta de backup da equipe. Nenhuma pasta foi criada.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,255}', folder_id):
        raise HTTPException(503, 'MAC_GOOGLE_BACKUP_FOLDER_ID inválido. Informe somente o ID da pasta, não a URL completa.')
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = httpx.get(
            f"https://www.googleapis.com/drive/v3/files/{folder_id}",
            headers=headers, params={
                "fields": "id,mimeType,trashed,capabilities(canAddChildren)",
                "supportsAllDrives": "true",
            }, timeout=15,
        )
    except httpx.HTTPError as error:
        raise HTTPException(503, 'Não foi possível verificar a pasta de backup no Drive. Tente novamente; nenhuma pasta foi criada.') from error
    if response.status_code == 401:
        raise HTTPException(401, 'A autorização do Drive é inválida ou expirou. Entre novamente com a conta autorizada.')
    if response.status_code in (403, 404):
        raise HTTPException(403, 'A pasta de backup não foi encontrada ou não está autorizada para este aplicativo. Confira o ID e a conta Google. Com drive.file, conhecer o ID não concede acesso: pode ser necessário autorizar a pasta pelo Google Picker. Nenhuma pasta foi criada.')
    if response.status_code == 429 or response.status_code >= 500:
        raise HTTPException(503, 'O Drive está temporariamente indisponível. Tente novamente; nenhuma pasta foi criada.')
    if response.status_code != 200:
        raise HTTPException(502, 'O Drive não confirmou o acesso à pasta de backup. Nenhuma pasta foi criada.')
    try:
        metadata = response.json()
        if not isinstance(metadata, dict) or metadata.get('id') != folder_id:
            raise ValueError('Metadados inválidos')
        capabilities = metadata.get('capabilities') or {}
        if not isinstance(capabilities, dict):
            raise ValueError('Permissões inválidas')
    except (ValueError, TypeError) as error:
        raise HTTPException(502, 'O Drive retornou dados inválidos da pasta de backup. Nenhuma pasta foi criada.') from error
    if metadata.get('trashed') is not False:
        raise HTTPException(409, 'A pasta de backup está na lixeira ou seu estado não foi confirmado. Confira a pasta configurada; nenhuma outra foi criada.')
    if metadata.get('mimeType') != 'application/vnd.google-apps.folder':
        raise HTTPException(422, 'MAC_GOOGLE_BACKUP_FOLDER_ID precisa identificar uma pasta do Drive, não um arquivo ou atalho.')
    if capabilities.get('canAddChildren') is not True:
        raise HTTPException(403, 'A autorização atual não permite adicionar arquivos à pasta de backup. Confira as permissões; nenhuma pasta foi criada.')
    return folder_id


def _desktop_callback(code: str, pending: tuple[float, str, str, str, str, str, bool]) -> HTMLResponse:
    _, poll_token, verifier, redirect, client_id, client_secret, native = pending
    _, _, allowed_email, _, _ = _config()
    try:
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id, "client_secret": client_secret, "code": code,
                "grant_type": "authorization_code", "redirect_uri": redirect,
                "code_verifier": verifier,
            }, timeout=20,
        )
        response.raise_for_status()
        tokens = response.json()
        identity = _google_identity(tokens["id_token"], client_id)
        email = str(identity.get("email", "")).lower()
        if identity.get("email_verified") is not True or email != allowed_email:
            raise HTTPException(403, "Esta conta Google não está autorizada no MAC.")
        saved = _saved_credentials(desktop=native)
        refresh = tokens.get("refresh_token") or (
            saved.get("refresh_token") if saved.get("email") == email else None
        )
        if not refresh:
            raise HTTPException(503, "O Google não concedeu acesso offline ao Drive.")
        folder_id = _folder(tokens["access_token"])
        credentials = {"email": email, "refresh_token": refresh, "folder_id": folder_id}
        _save_credentials(credentials, desktop=native)
    except (HTTPException, httpx.HTTPError, KeyError, ValueError) as error:
        message = error.detail if isinstance(error, HTTPException) else "Não foi possível concluir o login Google."
        with _lock:
            _desktop_results[poll_token] = (time.time() + _SHORT_SECONDS, None, message)
        return HTMLResponse(
            "<h1>Login não concluído</h1><p>Volte ao MAC e tente novamente.</p>",
            status_code=400, headers={"Cache-Control": "no-store"},
        )
    session = secrets.token_urlsafe(32)
    expiry = time.time() + _SESSION_SECONDS
    try:
        _remember_session(session, email, expiry)
    except OSError:
        # A sessão atual continua utilizável; o próximo início exigirá login.
        pass
    with _lock:
        _sessions[session] = (expiry, email)
        _desktop_results[poll_token] = (time.time() + _SHORT_SECONDS, session, None)
    return HTMLResponse(
        "<h1>Login concluído</h1><p>Volte à janela do MAC. Esta aba pode ser fechada.</p>",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str = Query(),
    error: str | None = Query(default=None),
) -> Response:
    with _lock:
        desktop_pending = _desktop_pending.pop(state, None)
    if desktop_pending is not None:
        if desktop_pending[0] <= time.time():
            raise HTTPException(400, "Tentativa de login expirada.")
        if error or not code:
            with _lock:
                _desktop_results[desktop_pending[1]] = (
                    time.time() + _SHORT_SECONDS, None, "O login foi cancelado ou recusado no Google.",
                )
            return HTMLResponse(
                "<h1>Login não concluído</h1><p>Volte ao MAC e tente novamente.</p>",
                status_code=400, headers={"Cache-Control": "no-store"},
            )
        return _desktop_callback(code, desktop_pending)
    if not code:
        raise HTTPException(400, "O Google não enviou o código de autorização.")
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
        folder_id = _folder(tokens["access_token"])
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
        if token:
            _forget_session(token)
    return {"status": "ok"}
