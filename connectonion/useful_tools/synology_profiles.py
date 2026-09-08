"""Private, atomic NAS profiles with explicit credential-store selection."""

import json
import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4

from ..environment import global_config_dir
from ..env_file import env_lock


class ProfileError(ValueError):
    """Safe setup guidance without credential-store or provider payloads."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def private_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.syno-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def read_private_json(path: Path, *, limit: int = 1024 * 1024) -> dict:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or (os.name != 'nt' and stat.S_IMODE(info.st_mode) & 0o077):
            raise ValueError
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as stream:
            actual = os.fstat(stream.fileno())
            if not stat.S_ISREG(actual.st_mode) or (os.name != 'nt' and stat.S_IMODE(actual.st_mode) & 0o077):
                raise ValueError
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (OSError, ValueError, TypeError):
        raise ProfileError('invalid_profile_store', 'NAS profile storage is unreadable or not a private regular file.') from None


def validate_settings(settings: dict) -> dict:
    url = settings.get('url', '')
    if not isinstance(url, str):
        raise ProfileError('invalid_profile', 'A NAS URL must be a string.')
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        port = -1
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.password is not None
            or parsed.path not in {'', '/'} or parsed.query or parsed.fragment or port == -1):
        raise ProfileError('tls_setup_required', 'Use an HTTPS NAS origin without credentials, path, query or fragment; configure --ca-cert for a private CA.')
    account = settings.get('account')
    if not isinstance(account, str) or not account.strip():
        raise ProfileError('invalid_profile', 'A DSM username is required.')
    result = {'url':url.rstrip('/'), 'account':account}
    for key in ('ca_cert', 'quickconnect', 'snmp', 'ssh'):
        if settings.get(key) is not None:
            result[key] = settings[key]
    allowed = {
        'snmp':{'host','port','username','auth_protocol','priv_protocol','context'},
        'ssh':{'host','port','username','key_file','known_hosts'},
    }
    for adapter, keys in allowed.items():
        config = result.get(adapter)
        if config is not None and (not isinstance(config, dict) or set(config) - keys):
            raise ProfileError('invalid_profile', 'Monitoring settings contain unsupported fields; store authentication separately.')
    if result.get('ca_cert'):
        ca = Path(result['ca_cert']).expanduser().resolve()
        if not ca.is_file():
            raise ProfileError('tls_setup_required', 'The selected CA certificate file does not exist.')
        result['ca_cert'] = str(ca)
    return result


class ProfileStore:
    """Profiles contain settings and opaque secret references, never passwords."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or global_config_dir() / 'synology'
        self.index_path = self.directory / 'profiles.json'

    def _read(self) -> dict:
        if not self.index_path.exists():
            return {'schema_version':1, 'default':None, 'profiles':{}}
        data = read_private_json(self.index_path)
        if data.get('schema_version') != 1 or not isinstance(data.get('profiles'), dict):
            raise ProfileError('invalid_profile_store', 'Unsupported NAS profile format; inspect the saved profiles.')
        if (data.get('default') is not None and data.get('default') not in data['profiles']
                or any(not isinstance(p,dict) or p.get('name')!=name for name,p in data['profiles'].items())):
            raise ProfileError('invalid_profile_store', 'NAS profile index or default is invalid.')
        return data

    def selected(self, name: str | None = None) -> dict:
        data = self._read()
        name = name or data['default']
        if not name or name not in data['profiles']:
            raise ProfileError('not_configured', 'No selected NAS profile. Run co syno login; legacy env credentials require explicit verified login.')
        profile = data['profiles'][name]
        if not isinstance(profile, dict) or profile.get('name') != name:
            raise ProfileError('invalid_profile_store', 'NAS profile identity is invalid.')
        validate_settings(profile)
        return profile

    def list(self) -> dict:
        data = self._read()
        return {'default':data['default'], 'items':[
            {key:value for key,value in profile.items() if key not in {'credential_ref','snmp','ssh'}}
            | {'authenticated':bool(profile.get('credential_ref'))}
            for profile in data['profiles'].values()]}

    def use(self, name: str) -> None:
        with env_lock(self.index_path):
            self.selected(name)
            data = self._read()
            data['default'] = name
            private_json(self.index_path, data)

    def secret_path(self, reference: str) -> Path:
        if not isinstance(reference, str) or not re.fullmatch('[a-f0-9]{32}', reference):
            raise ProfileError('invalid_profile_store', 'NAS credential reference is invalid.')
        return self.directory / 'credentials' / f'{reference}.json'

    @staticmethod
    def _keyring():
        try:
            import keyring
            backend = keyring.get_keyring()
            if backend.priority <= 0 or backend.__class__.__module__ not in {
                    'keyring.backends.macOS', 'keyring.backends.Windows',
                    'keyring.backends.SecretService', 'keyring.backends.kwallet'}:
                raise RuntimeError
            return keyring
        except Exception:
            raise ProfileError('credential_store_unavailable', 'OS credential store unavailable; install connectonion[synology] or explicitly choose --credential-store file on POSIX.') from None

    def _write_secret(self, storage: str, reference: str, secret: dict) -> None:
        if storage == 'file':
            if os.name == 'nt':
                raise ProfileError('credential_store_unavailable', 'Use the OS credential store on Windows; the POSIX private-file fallback is unsupported.')
            private_json(self.secret_path(reference), secret)
        elif storage == 'keyring':
            keyring = self._keyring()
            try:
                keyring.set_password('connectonion.synology', reference, json.dumps(secret))
            except Exception:
                raise ProfileError('credential_store_unavailable', 'Could not save NAS authentication in the OS credential store.') from None
        else:
            raise ProfileError('invalid_profile', 'Credential storage must be keyring or file.')

    def credentials(self, profile: dict) -> dict:
        reference = profile.get('credential_ref')
        if not reference:
            return {}
        self.secret_path(reference)  # Validate even when the backing store is keyring.
        if profile.get('credential_store') == 'file':
            return read_private_json(self.secret_path(reference), limit=65536)
        if profile.get('credential_store') != 'keyring':
            raise ProfileError('invalid_profile_store', 'Unknown NAS credential storage type.')
        keyring = self._keyring()
        try:
            value = keyring.get_password('connectonion.synology', reference)
            data = json.loads(value) if value else {}
            if not isinstance(data, dict):
                raise ValueError
            return data
        except Exception:
            raise ProfileError('credential_store_unavailable', 'Could not read NAS authentication from the OS credential store.') from None

    def _delete_secret(self, profile: dict) -> None:
        reference = profile.get('credential_ref')
        if not reference:
            return
        if profile['credential_store'] == 'file':
            self.secret_path(reference).unlink(missing_ok=True)
        else:
            keyring = self._keyring()
            try:
                keyring.delete_password('connectonion.synology', reference)
            except keyring.errors.PasswordDeleteError:
                # A previously removed record already satisfies logout.
                if keyring.get_password('connectonion.synology', reference) is not None:
                    raise ProfileError('credential_store_unavailable', 'Could not clear NAS authentication from the OS credential store.') from None
            except Exception:
                raise ProfileError('credential_store_unavailable', 'Could not clear NAS authentication from the OS credential store.') from None

    def save(self, name: str, settings: dict, secret: dict, *, storage: str = 'keyring') -> dict:
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', name):
            raise ProfileError('invalid_profile', 'NAS profile names use 1–64 letters, digits, dots, underscores or hyphens.')
        settings = validate_settings(settings)
        secret = {key:value for key,value in secret.items() if key in {'password','sid','snmp_auth','snmp_priv'}}
        with env_lock(self.index_path):
            data = self._read()
            old = data['profiles'].get(name)
            reference = uuid4().hex
            self._write_secret(storage, reference, secret)
            profile = {**settings, 'name':name, 'id':uuid4().hex,
                       'credential_store':storage, 'credential_ref':reference}
            data['profiles'][name] = profile
            data['default'] = data['default'] or name
            private_json(self.index_path, data)
            if old:
                try:
                    self._delete_secret(old)
                except ProfileError:
                    # The new verified profile is already committed. Cleanup
                    # failure must not pretend that the old profile is active.
                    profile = {**profile, 'cleanup_warning':'Previous credential record could not be removed; it is no longer selected.'}
            return profile

    def update_auth(self, profile: dict, secret: dict) -> None:
        with env_lock(self.index_path):
            current = self.selected(profile['name'])
            if current['id'] != profile['id'] or current.get('credential_ref') != profile.get('credential_ref'):
                raise ProfileError('profile_changed', 'NAS profile changed during authentication; repeat the inspection.')
            merged = {**self.credentials(current), **secret}
            merged.pop('otp', None)
            self._write_secret(current['credential_store'], current['credential_ref'], merged)

    def clear_auth(self, profile: dict) -> None:
        with env_lock(self.index_path):
            current = self.selected(profile['name'])
            if current['id'] != profile['id']:
                raise ProfileError('profile_changed', 'NAS profile changed before logout; inspect profiles again.')
            self._delete_secret(current)
            data = self._read()
            data['profiles'][profile['name']].pop('credential_ref', None)
            private_json(self.index_path, data)
