"""Verified, bounded DSM requests with explicit session and retry ownership."""

import json
import re
import ssl
import time
from functools import wraps
from typing import Callable

import httpx

from .synology_profiles import ProfileError, validate_settings

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
STALE_SESSION = {106, 107, 119}


def command_budget(function):
    """Give reusable SDK instances one budget per outer operation, not per request."""
    @wraps(function)
    def run(self, *args, **kwargs):
        depth = getattr(self, '_budget_depth', 0)
        if depth == 0 and not getattr(self, '_fixed_budget', False):
            self._deadline = time.monotonic() + getattr(self, 'timeout', 60)
        self._budget_depth = depth + 1
        try:
            return function(self, *args, **kwargs)
        finally:
            self._budget_depth = depth
    return run


class SynologyError(ProfileError):
    def __init__(self, message: str, code: str = 'synology_error'):
        super().__init__(code, message)


class SynologyTransport:
    """One NAS/account connection; credentials never fall back field by field."""

    def __init__(self, url: str, account: str, password: str = '', *, sid: str = '',
                 ca_cert: str | None = None, timeout: float = 60, persist: bool = True,
                 otp_callback: Callable[[], str] | None = None,
                 on_session: Callable[[str], None] | None = None):
        settings = validate_settings({'url':url, 'account':account, 'ca_cert':ca_cert})
        if not 0 < timeout <= 3600:
            raise SynologyError('Timeout must be greater than zero and at most 3600 seconds.', 'invalid_input')
        self.url, self.account = settings['url'], settings['account']
        self.password, self.sid = password, sid
        self.ca_cert = settings.get('ca_cert')
        self.timeout = timeout
        self._deadline = time.monotonic() + timeout
        self._persist = persist
        self._otp_callback, self._on_session = otp_callback, on_session
        self._paths = {}
        self._transport = None
        self.tls_verified = True

    def _remaining(self) -> float:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise SynologyError('The command waiting budget expired.', 'timeout')
        return remaining

    def _client(self) -> httpx.Client:
        try:
            verification = ssl.create_default_context(cafile=self.ca_cert) if self.ca_cert else True
        except (OSError, ssl.SSLError):
            raise SynologyError('The selected CA certificate could not be loaded.', 'tls_setup_required') from None
        return httpx.Client(base_url=self.url, timeout=self._remaining(), verify=verification,
                            follow_redirects=False, transport=self._transport)

    def _json_request(self, method: str, path: str, *, mutation: bool = False, **kwargs) -> dict:
        try:
            with self._client() as client:
                with client.stream(method, path, **kwargs) as reply:
                    if not 200 <= reply.status_code < 300:
                        code = 'permission_denied' if reply.status_code in {401,403} else 'http_error'
                        if mutation and (reply.status_code >= 500 or reply.status_code == 408):
                            code = 'submission_unknown'
                        raise SynologyError(f'DSM returned HTTP {reply.status_code}; inspect remote state before retrying a write.', code)
                    raw = bytearray()
                    for chunk in reply.iter_bytes(chunk_size=65536):
                        self._remaining()
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise SynologyError('DSM response exceeded the 8 MiB limit.', 'response_too_large')
            result = json.loads(raw)
            if not isinstance(result, dict) or not isinstance(result.get('success'), bool):
                raise ValueError
            return result
        except SynologyError as error:
            if mutation and error.code in {'timeout','response_too_large'}:
                raise SynologyError('The mutation response was incomplete; inspect remote state before retrying.', 'submission_unknown') from None
            raise
        except httpx.TransportError as error:
            tls = 'CERTIFICATE_VERIFY_FAILED' in str(error) or isinstance(error.__cause__, ssl.SSLError)
            code = 'tls_error' if tls else ('submission_unknown' if mutation else 'network_error')
            message = ('TLS certificate verification failed; configure a trusted CA with co syno login --ca-cert.' if tls
                       else 'The connection failed; inspect remote state before retrying a write.')
            raise SynologyError(message, code) from None
        except (ValueError, UnicodeError):
            raise SynologyError('DSM returned malformed JSON; inspect state before retrying a write.',
                                'submission_unknown' if mutation else 'invalid_response') from None

    def _api(self, api: str, version: int | None = None) -> tuple[str, int]:
        if not self._paths:
            response = self._json_request('GET', '/webapi/query.cgi', params={
                'api':'SYNO.API.Info', 'version':1, 'method':'query', 'query':'all'})
            if not response['success'] or not isinstance(response.get('data'), dict):
                raise SynologyError('DSM API discovery failed.', 'unsupported_api')
            self._paths = response['data']
        item = self._paths.get(api, {})
        path = item.get('path', '')
        minimum, maximum = item.get('minVersion'), item.get('maxVersion')
        if (not isinstance(path, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+\.cgi', path)
                or any(part in {'', '.', '..'} for part in path.split('/'))
                or not isinstance(minimum, int) or not isinstance(maximum, int)
                or minimum < 1 or maximum < minimum):
            raise SynologyError('The NAS does not advertise a usable API for this operation.', 'unsupported_api')
        selected = version if version is not None else maximum
        if not minimum <= selected <= maximum:
            raise SynologyError('The NAS does not support the required File Station API version.', 'unsupported_version')
        return path, selected

    def _path_for(self, api: str) -> str:
        return self._api(api)[0]

    def _login(self) -> None:
        if not self.account or not self.password:
            raise SynologyError('Saved NAS authentication is missing; run co syno login.', 'auth_required')
        path, version = self._api('SYNO.API.Auth', 3)
        params = {'api':'SYNO.API.Auth', 'version':version, 'method':'login',
                  'account':self.account, 'passwd':self.password, 'session':'FileStation', 'format':'sid'}
        response = self._json_request('POST', f'/webapi/{path}', data=params)
        if not response['success'] and response.get('error', {}).get('code') == 403:
            if self._otp_callback is None:
                raise SynologyError('This account requires an interactive OTP login; run co syno login in a terminal.', 'otp_required')
            otp = self._otp_callback()
            if not isinstance(otp, str) or not otp.strip():
                raise SynologyError('OTP login was cancelled.', 'otp_required')
            response = self._json_request('POST', f'/webapi/{path}', data={**params, 'otp_code':otp.strip()})
        if not response['success']:
            code = response.get('error', {}).get('code')
            raise SynologyError('DSM rejected authentication; check username, password and required OTP.',
                                'otp_rejected' if code in {403,404} else 'auth_failed')
        sid = response.get('data', {}).get('sid')
        if not isinstance(sid, str) or not sid:
            raise SynologyError('DSM did not return a usable session.', 'invalid_response')
        self.sid = sid
        if self._persist and self._on_session:
            self._on_session(sid)

    @staticmethod
    def _is_mutation(api: str, method: str) -> bool:
        return method in {'start','create','delete','rename','upload','set','stop'} and api != 'SYNO.FileStation.Search'

    def _call(self, api: str, method: str, version: int, params: dict) -> dict:
        path, version = self._api(api, version)
        values = {'api':api, 'version':version, 'method':method, '_sid':self.sid}
        for key, value in params.items():
            if value is not None:
                encoded = isinstance(value, (dict,list,bool)) or (isinstance(value,str) and key in {'folder_path','dest_folder_path','taskid'})
                values[key] = json.dumps(value, separators=(',', ':')) if encoded else value
        return self._json_request('POST', f'/webapi/{path}', data=values,
                                  mutation=self._is_mutation(api, method))

    def _request(self, api: str, method: str, version: int = 2, **params) -> dict:
        # Negotiate before authenticating, so unsupported operations send no
        # credentials and can never silently degrade to a weaker API version.
        self._api(api, version)
        if not self.sid:
            self._login()
        response = self._call(api, method, version, params)
        if not response['success'] and response.get('error', {}).get('code') in STALE_SESSION:
            self._login()
            response = self._call(api, method, version, params)
        if not response['success']:
            code = response.get('error', {}).get('code')
            category = {105:'permission_denied',402:'permission_denied',407:'permission_denied',
                        408:'not_found',1805:'conflict',102:'unsupported_api',104:'unsupported_version',
                        106:'auth_required',107:'auth_required',119:'auth_required'}.get(code, 'provider_error')
            raise SynologyError(f'DSM rejected the operation (code {code if isinstance(code, int) else "unknown"}).', category)
        data = response.get('data', {})
        if not isinstance(data, dict):
            raise SynologyError('DSM returned an invalid result object.', 'invalid_response')
        return data

    def _logout_remote(self) -> None:
        if self.sid:
            path, version = self._api('SYNO.API.Auth', 3)
            result = self._json_request('POST', f'/webapi/{path}', data={
                'api':'SYNO.API.Auth', 'version':version, 'method':'logout',
                'session':'FileStation', '_sid':self.sid})
            if not result['success']:
                raise SynologyError('Remote session invalidation was not confirmed.', 'logout_unconfirmed')
            self.sid = ''
