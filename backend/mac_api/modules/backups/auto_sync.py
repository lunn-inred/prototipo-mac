"""Sincronização automática por sinal local persistente e consulta periódica ao Drive."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from threading import Event, Lock, Thread
import time
from uuid import uuid4

from fastapi import HTTPException

from backend.mac_api.core.settings import setting
from . import jobs, service

POLL_SECONDS = 20
DEBOUNCE_SECONDS = 5
MAX_RETRY_SECONDS = 300
_lock = Lock()
_wake = Event()
_active_job: str | None = None


def enabled() -> bool:
    return (setting('MAC_AUTO_SYNC_ENABLED', '1') == '1'
            and setting('MAC_ENVIRONMENT', 'development') != 'test'
            and setting('MAC_TEST_DB_ENABLED') != '1'
            and setting('MAC_DB_TARGET', 'local') == 'local'
            and bool(setting('MAC_GOOGLE_ALLOWED_EMAIL'))
            and bool(setting('MAC_GOOGLE_CLIENT_ID') or setting('MAC_GOOGLE_DESKTOP_CLIENT_ID')))


def _path() -> Path:
    return service.backups_directory() / 'auto-sync-state.json'


def _read() -> dict:
    path = _path()
    if not path.exists():
        return dict(generation=0, pending=False, last_success=None, last_error=None,
                    retry_at=0, failures=0, pending_at=0)
    return json.loads(path.read_text(encoding='utf-8'))


def _write(state: dict) -> None:
    path = _path()
    pending = path.with_name(f'.{path.name}-{uuid4().hex}.pending')
    try:
        descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            output.write(json.dumps(state, ensure_ascii=False))
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def mark_dirty() -> None:
    if not enabled():
        return
    with _lock:
        state = _read()
        state.update(generation=state['generation'] + 1, pending=True,
                     pending_at=time.time(), last_error=None, retry_at=0, failures=0)
        _write(state)
    _wake.set()


def generation() -> int | None:
    if not enabled():
        return None
    with _lock:
        return _read()['generation']


def record_success(observed_generation: int | None) -> None:
    if observed_generation is None:
        return
    with _lock:
        state = _read()
        if state['generation'] == observed_generation:
            state['pending'] = False
        state.update(last_success=datetime.now(timezone.utc).isoformat(),
                     last_error=None, retry_at=0, failures=0)
        _write(state)
    _wake.set()


def status() -> dict:
    if not enabled():
        return dict(enabled=False, state='disabled')
    with _lock:
        state = _read()
        active = _active_job
    return dict(enabled=True,
                state='syncing' if active else 'error' if state.get('last_error') else
                      'pending' if state.get('pending') else 'idle',
                pending=bool(state.get('pending')), last_success=state.get('last_success'),
                last_error=state.get('last_error'), job_id=active,
                revision=_baseline_revision())


def _baseline_revision() -> str | None:
    path = service.backups_directory() / 'sync-state.json'
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8')).get('revision')


def _record_failure(message: str) -> None:
    with _lock:
        state = _read()
        failures = state.get('failures', 0) + 1
        state.update(failures=failures, last_error=message,
                     retry_at=time.time() + min(MAX_RETRY_SECONDS, 5 * 2 ** min(failures, 6)))
        _write(state)


def _cycle(stop: Event) -> float:
    global _active_job
    if not enabled():
        return POLL_SECONDS
    with _lock:
        state = _read()
    now = time.time()
    if state.get('retry_at', 0) > now:
        return min(POLL_SECONDS, state['retry_at'] - now)
    if state.get('pending') and state.get('pending_at', 0) + DEBOUNCE_SECONDS > now:
        return min(POLL_SECONDS, state['pending_at'] + DEBOUNCE_SECONDS - now)
    generation = state['generation']
    if not state.get('pending'):
        from .synchronization import status as drive_status
        remote = drive_status(desktop=True)
        baseline_revision = _baseline_revision()
        if remote['revision'] == baseline_revision and baseline_revision is not None:
            if state.get('last_error'):
                with _lock:
                    updated = _read()
                    updated.update(last_error=None, retry_at=0, failures=0)
                    _write(updated)
            return POLL_SECONDS
    try:
        job = jobs.start('sync', desktop=True)
    except HTTPException as error:
        if error.status_code == 409:
            return 2
        raise
    with _lock:
        _active_job = job['id']
    try:
        while not stop.wait(1):
            job = jobs.status(job['id'])
            if job['status'] not in ('queued', 'running'):
                break
        else:
            return POLL_SECONDS
        if job['status'] == 'failed':
            _record_failure(job['message'])
        else:
            record_success(generation)
    finally:
        with _lock:
            _active_job = None
    return POLL_SECONDS


def start_worker() -> tuple[Event, Thread] | None:
    if not enabled():
        return None
    stop = Event()

    def run():
        while not stop.is_set():
            try:
                delay = _cycle(stop)
            except Exception as error:
                logging.getLogger(__name__).error('Sincronização automática falhou: %s', type(error).__name__)
                try:
                    _record_failure('Falha ao consultar o Drive. Confira o login e a conexão; a sincronização será tentada novamente.')
                except Exception:
                    logging.getLogger(__name__).exception('Não foi possível registrar a falha da sincronização automática.')
                delay = POLL_SECONDS
            _wake.wait(delay)
            _wake.clear()

    worker = Thread(target=run, name='mac-auto-sync', daemon=True)
    worker.start()
    return stop, worker


def stop_worker(handle: tuple[Event, Thread] | None) -> None:
    if handle:
        stop, worker = handle
        stop.set()
        _wake.set()
        worker.join(timeout=2)
