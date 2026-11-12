"""Transporte Drive: pasta configurada, tokens locais e upload em blocos."""
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException
from backend.mac_api.core.settings import setting
from backend.mac_api.modules import google_auth
from .bundle import digest

API = 'https://www.googleapis.com/drive/v3/files'


class Drive:
    def __init__(self, *, desktop=False):
        native = desktop and bool(google_auth._saved_credentials(desktop=True).get('refresh_token'))
        saved = google_auth._saved_credentials(desktop=native)
        allowed = (setting('MAC_GOOGLE_ALLOWED_EMAIL') or '').strip().lower()
        if not allowed or saved.get('email') != allowed or not saved.get('refresh_token'):
            raise ValueError('Entre com a conta Google autorizada nesta instalação antes de usar o backup.')
        prefix = 'MAC_GOOGLE_DESKTOP_' if native else 'MAC_GOOGLE_'
        client_id, secret = setting(prefix + 'CLIENT_ID'), setting(prefix + 'CLIENT_SECRET')
        if not client_id or not secret:
            raise ValueError('Cliente OAuth do Drive incompleto nesta instalação.')
        self.client = httpx.Client(timeout=httpx.Timeout(120, connect=20), follow_redirects=False)
        try:
            response = self.client.post('https://oauth2.googleapis.com/token', data=dict(
                client_id=client_id, client_secret=secret, refresh_token=saved['refresh_token'], grant_type='refresh_token'))
            if response.status_code != 200:
                raise ValueError('Não foi possível renovar a autorização do Drive. Saia e entre novamente com a conta Google.')
            token = response.json()['access_token']
            self.folder = google_auth._folder(token)
            self.headers = {'Authorization': f'Bearer {token}'}
        except Exception:
            self.client.close()
            raise

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _checked(self, response):
        if response.status_code not in (200, 201):
            raise ValueError(f'O Drive recusou a operação (HTTP {response.status_code}). Confira autorização, espaço e conexão.')
        return response

    def list(self):
        entries, token = [], None
        for _ in range(100):
            response = self._checked(self.client.get(API, headers=self.headers, params=dict(
                q=f"'{self.folder}' in parents and trashed=false and properties has {{ key='macBackupFormat' and value='1' }}",
                fields='nextPageToken,files(id,name,size,createdTime,properties)', pageSize=100,
                orderBy='createdTime desc', **({'pageToken': token} if token else {}))))
            result = response.json()
            entries.extend(result.get('files', []))
            token = result.get('nextPageToken')
            if not token:
                return entries
        raise ValueError('Muitos backups para listar. Organize a pasta antes de continuar.')

    def metadata(self, file_id):
        if not isinstance(file_id, str) or not file_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in file_id):
            raise ValueError('Identificador de backup inválido.')
        result = self._checked(self.client.get(f'{API}/{file_id}', headers=self.headers,
            params={'fields': 'id,name,size,mimeType,parents,properties,trashed'})).json()
        if (self.folder not in result.get('parents', []) or result.get('trashed')
                or result.get('mimeType') != 'application/zip'
                or result.get('properties', {}).get('macBackupFormat') != '1'):
            raise ValueError('O arquivo não é um backup MAC na pasta configurada.')
        return result

    def download(self, file_id, destination):
        metadata = self.metadata(file_id)
        limit = int(setting('MAC_BACKUP_MAX_BYTES', str(10 * 1024**3)))
        if int(metadata.get('size', limit + 1)) > limit:
            raise ValueError('Backup excede MAC_BACKUP_MAX_BYTES.')
        size = 0
        with self.client.stream('GET', f'{API}/{file_id}', params={'alt': 'media'}, headers=self.headers) as response:
            self._checked(response)
            with destination.open('xb') as output:
                destination.chmod(0o600)
                for chunk in response.iter_bytes(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise ValueError('Download excede o limite de tamanho.')
                    output.write(chunk)
        if size != int(metadata['size']) or digest(destination) != metadata.get('properties', {}).get('sha256'):
            raise ValueError('Backup incompleto ou corrompido no Drive.')
        return metadata

    def upload(self, source, name, installation):
        size = source.stat().st_size
        if size > int(setting('MAC_BACKUP_MAX_BYTES', str(10 * 1024**3))):
            raise ValueError('Backup excede MAC_BACKUP_MAX_BYTES.')
        properties = dict(macBackupFormat='1', sha256=digest(source), installation=installation)
        response = self._checked(self.client.post('https://www.googleapis.com/upload/drive/v3/files',
            params={'uploadType': 'resumable', 'fields': 'id,name,size,createdTime,properties'},
            headers={**self.headers, 'X-Upload-Content-Type': 'application/zip', 'X-Upload-Content-Length': str(size)},
            json=dict(name=name, mimeType='application/zip', parents=[self.folder], properties=properties)))
        location = response.headers.get('Location', '')
        parsed = urlparse(location)
        if parsed.scheme != 'https' or parsed.hostname != 'www.googleapis.com':
            raise ValueError('Destino de upload inválido recebido do Drive.')
        offset = 0
        with source.open('rb') as stream:
            while chunk := stream.read(8 * 1024 * 1024):
                response = self.client.put(location, headers={**self.headers,
                    'Content-Length': str(len(chunk)), 'Content-Type': 'application/zip',
                    'Content-Range': f'bytes {offset}-{offset + len(chunk)-1}/{size}'}, content=chunk)
                offset += len(chunk)
                if response.status_code == 308 and offset < size:
                    if response.headers.get('Range') != f'bytes=0-{offset-1}':
                        raise ValueError('O Drive não confirmou o bloco enviado. Tente um novo backup.')
                    continue
                self._checked(response)
                if offset != size:
                    raise ValueError('Upload terminou antes de todos os arquivos serem enviados.')
                return response.json()
        raise ValueError('O upload não foi concluído.')
