"""Bounded QuickConnect discovery and verified HTTPS probes without credentials."""

import json
import re
import ssl
import time

import httpx

from .synology_profiles import validate_settings
from .synology_transport import SynologyError

QUICKCONNECT_GLOBAL='https://global.quickconnect.to/Serv.php'
MAX_DISCOVERY_BYTES=1024*1024


def _read_discovery(method: str, url: str, *, timeout: float, ca_cert=None, **kwargs) -> dict:
    verification=ssl.create_default_context(cafile=ca_cert) if ca_cert else True
    deadline=time.monotonic()+timeout
    try:
        with httpx.stream(method,url,timeout=timeout,verify=verification,follow_redirects=False,**kwargs) as reply:
            if reply.status_code!=200:
                raise SynologyError('Discovery endpoint did not return a successful HTTPS response.', 'discovery_failed')
            raw=bytearray()
            for chunk in reply.iter_bytes(chunk_size=65536):
                raw.extend(chunk)
                if len(raw)>MAX_DISCOVERY_BYTES or time.monotonic()>deadline:
                    raise SynologyError('NAS discovery exceeded its response or waiting limit.', 'discovery_failed')
        body=json.loads(raw)
        if not isinstance(body,dict):
            raise ValueError
        return body
    except (httpx.TransportError,ValueError):
        raise SynologyError('NAS discovery could not verify a DSM endpoint; supply --url and a trusted --ca-cert.', 'discovery_failed') from None


def resolve_quickconnect(server_id: str, timeout: float = 15) -> list:
    """Resolve a QuickConnect ID to HTTPS candidates without sending NAS credentials."""
    if not re.fullmatch('[A-Za-z0-9-]{1,64}',server_id):
        raise SynologyError('QuickConnect ID must contain 1–64 letters, digits or hyphens.', 'invalid_input')
    info=_read_discovery('POST',QUICKCONNECT_GLOBAL,timeout=timeout,json={
        'version':1,'command':'get_server_info','stop_when_error':False,'stop_when_success':False,
        'id':'dsm_portal_https','serverID':server_id})
    if info.get('errno'):
        raise SynologyError('QuickConnect ID not found; inspect the NAS QuickConnect settings.', 'not_found')
    server=info.get('server',{})
    if not isinstance(server,dict):
        raise SynologyError('QuickConnect returned malformed server information.', 'invalid_response')
    port=server.get('port') or 5001
    if not str(port).isdigit() or not 1<=int(port)<=65535:
        raise SynologyError('QuickConnect returned an invalid HTTPS port.', 'invalid_response')
    interfaces=server.get('interface',[])
    if not isinstance(interfaces,list) or len(interfaces)>32:
        raise SynologyError('QuickConnect returned invalid network candidates.', 'invalid_response')
    hosts=[item.get('ip') for item in interfaces if isinstance(item,dict)]
    hosts += [server.get('ddns'),server.get('external',{}).get('ip')]
    candidates=[]
    for host in hosts:
        if not host or host=='NULL':
            continue
        if not isinstance(host,str) or not re.fullmatch('[A-Za-z0-9.:-]+',host):
            raise SynologyError('QuickConnect returned an invalid candidate host.', 'invalid_response')
        candidates.append(f'https://[{host}]:{port}' if ':' in host else f'https://{host}:{port}')
    relay=info.get('service',{}).get('relay_ip') or info.get('relay_ip')
    if relay:
        candidates.append(f'https://{relay}')
    candidates.append(f'https://{server_id}.quickconnect.to')
    return list(dict.fromkeys(validate_settings({'url':base,'account':'probe'})['url'] for base in candidates))


def pick_reachable(candidates: list, timeout: float = 15, ca_cert: str | None = None) -> str:
    """Probe within one total budget; TLS failures never cause insecure fallback."""
    deadline=time.monotonic()+timeout
    for base in candidates:
        remaining=deadline-time.monotonic()
        if remaining<=0:
            break
        validate_settings({'url':base,'account':'probe','ca_cert':ca_cert})
        try:
            body=_read_discovery('GET',f'{base}/webapi/query.cgi',timeout=min(3,remaining),ca_cert=ca_cert,
                                 params={'api':'SYNO.API.Info','version':1,'method':'query','query':'SYNO.API.Auth'})
        except SynologyError:
            continue
        if body.get('success') is True:
            return base
    raise SynologyError('Could not reach a verified NAS endpoint. Use co syno login --url HTTPS_URL --ca-cert FILE.', 'tls_setup_required')
