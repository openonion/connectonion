"""Outbound authenticated static upload, independent of Agent reachability."""
import hashlib
import re
from urllib.parse import quote, urlsplit

import httpx

from ....credentials import require_ambient_api_key
from ....backend import backend_url
from .bundle import Bundle, validate_path
from .runtime import RuntimeErrorState


class ArtifactUploader:
    def __init__(self, app_id: str, serving_domain: str, *, api_url=None,
                 token=require_ambient_api_key, transport=None):
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,31}', app_id):
            raise ValueError('Invalid Control Center app_id')
        if (not isinstance(serving_domain, str) or len(serving_domain) > 190
                or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+', serving_domain)
                or any(serving_domain == domain or serving_domain.endswith('.' + domain)
                       for domain in ('openonion.ai', 'connectonion.com'))):
            raise ValueError('Serving domain must be an isolated DNS domain')
        self.app_id, self.domain = app_id, serving_domain
        self.api_url = (api_url or backend_url()).rstrip('/')
        parsed = urlsplit(self.api_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Artifact API requires an HTTPS URL without credentials')
        self.token, self.transport = token, transport

    def __call__(self, bundle: Bundle) -> dict:
        with httpx.Client(timeout=60, follow_redirects=False, transport=self.transport) as client:
            try:
                with client.stream('POST', f'{self.api_url}/api/v1/control-centers/{self.app_id}/revisions',
                        headers={'Authorization': f'Bearer {self.token()}'}, json=bundle.to_wire()) as response:
                    data = bytearray()
                    if response.status_code != 200:
                        raise RuntimeErrorState(f'Artifact upload failed with HTTP {response.status_code}')
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 16 * 1024:
                            raise RuntimeErrorState('Artifact response exceeds limit')
                import json
                result = json.loads(data)
                self._validate(result, bundle)
                return result
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                raise RuntimeErrorState('Artifact upload did not return a verified revision') from exc

    def _validate(self, result, bundle):
        if not isinstance(result, dict) or result.get('revision') != bundle.revision:
            raise RuntimeErrorState('Artifact revision mismatch')
        parsed = urlsplit(result.get('url', ''))
        label = (parsed.hostname or '').removesuffix('.' + self.domain)
        if (parsed.scheme != 'https' or parsed.netloc != f'{label}.{self.domain}'
                or not re.fullmatch(r'r-[a-z2-7]{52}', label)
                or parsed.path != '/' + quote(bundle.entry, safe='/') or parsed.query or parsed.fragment):
            raise RuntimeErrorState('Artifact URL is outside its immutable serving origin')

    def _artifact_origin(self, app):
        parsed = urlsplit(app['url'])
        label = (parsed.hostname or '').removesuffix('.' + self.domain)
        if (parsed.scheme != 'https' or parsed.netloc != f'{label}.{self.domain}'
                or not re.fullmatch(r'r-[a-z2-7]{52}', label) or parsed.query or parsed.fragment):
            raise RuntimeErrorState('Artifact is outside the configured immutable origin')
        return f'https://{parsed.netloc}'

    def source(self, app, record):
        """Read one retained text file, bounded and hashed against its reviewed manifest."""
        validate_path(record['path'])
        if not 0 <= record['bytes'] <= 128 * 1024:
            raise ValueError('File is too large for Code view; open it in the project')
        url = self._artifact_origin(app) + '/' + quote(record['path'], safe='/')
        data = bytearray()
        try:
            with httpx.Client(timeout=15, follow_redirects=False, transport=self.transport) as client:
                with client.stream('GET', url) as response:
                    if response.status_code != 200:
                        raise RuntimeErrorState('Retained source is unavailable')
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > record['bytes']:
                            raise RuntimeErrorState('Retained source exceeds its reviewed size')
        except httpx.HTTPError as exc:
            raise RuntimeErrorState('Retained source could not be read') from exc
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise RuntimeErrorState('Retained source does not match reviewed bytes')
        return bytes(data)

    def available(self, app):
        """Rollback rechecks the retained artifact without sending credentials."""
        try:
            self._artifact_origin(app)
            with httpx.Client(timeout=15, follow_redirects=False, transport=self.transport) as client:
                response = client.head(app['url'])
                return (response.status_code == 200
                        and response.headers.get('x-control-center-revision') == app['revision'])
        except (httpx.HTTPError, RuntimeErrorState):
            return False
