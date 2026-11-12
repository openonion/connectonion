"""Open the selected account's real mailbox with a one-time browser login."""
import base64
import json
import re
import time
import webbrowser
import io
import sys
import requests
import typer
from ..style import console, next_line

MAIL_URL = 'https://mail.openonion.ai'

def connection_code(challenge: str, *, now: float | None = None) -> str:
    """Sign only the exact two-minute OO Mail protocol; never export the key."""
    if not re.fullmatch(r'ConnectOnion-Auth-OO-Mail-[a-f0-9]{48}-\d{10}', challenge):
        raise ValueError('Invalid challenge. Generate a new command in OO Mail.')
    age=(time.time() if now is None else now)-int(challenge.rsplit('-',1)[1])
    if not -5 <= age <= 120:
        raise ValueError('This challenge expired. Generate a new command in OO Mail.')
    from ...environment import load_environment
    from ...project import project_identity
    from ... import address
    load_environment()
    identity=project_identity()
    if not identity:
        raise ValueError('No selected identity. Run co init, then try again.')
    proof={'public_key':identity['address'],'message':challenge,
           'signature':address.sign(identity,challenge.encode()).hex()}
    return base64.urlsafe_b64encode(json.dumps(proof).encode()).decode().rstrip('=')

def handle_email_connect(challenge: str):
    try:
        code=connection_code(challenge)
    except ValueError as exc:
        console(stderr=True).print(str(exc),markup=False)
        raise typer.Exit(1) from exc
    print(code)
    console(stderr=True).print('Paste this short-lived code into the OO Mail tab that generated the command. Your private key stays on this computer.',markup=False)

def _login_ticket(token: str) -> dict:
    from ...backend import backend_url
    response=requests.post(backend_url()+'/api/v1/auth/mail-link',
        headers={'Authorization':f'Bearer {token}'},timeout=20)
    response.raise_for_status()
    data=response.json()
    if not isinstance(data,dict):raise ValueError('Invalid login response')
    if not isinstance(data.get('code'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',data['code']):
        raise ValueError('Invalid login response')
    if not isinstance(data.get('public_key'),str) or not re.fullmatch(r'0x[0-9a-fA-F]{64}',data['public_key']):
        raise ValueError('Invalid login account')
    lifetime=data.get('expires_in')
    if isinstance(lifetime,bool) or not isinstance(lifetime,int) or not 0<lifetime<=600:
        raise ValueError('Invalid login expiry')
    return data


def _login_url(ticket: dict) -> str:
    return MAIL_URL+'/connect#code='+ticket['code']+'&account='+ticket['public_key']


def _phone_qr(url: str) -> str:
    import qrcode
    code=qrcode.QRCode(border=2)
    code.add_data(url)
    out=io.StringIO()
    code.print_ascii(out=out,invert=True)
    return out.getvalue()


def handle_email_open(no_browser: bool = False, qr: bool = False):
    from .project_cmd_lib import load_api_key
    token=load_api_key()
    if not token:
        console(stderr=True).print('Not connected. Next: co auth login',markup=False)
        raise typer.Exit(1)
    phone_only=no_browser or qr
    try:
        desktop=_login_ticket(token)
        # The automatic desktop visit consumes its ticket. The printed phone
        # link must be a different ticket, issued before either is opened.
        phone=desktop if phone_only else _login_ticket(token)
        if phone['public_key'].lower()!=desktop['public_key'].lower() or (not phone_only and phone['code']==desktop['code']):
            raise ValueError('Invalid independent phone ticket')
    except (requests.RequestException,ValueError) as exc:
        expired=isinstance(exc,requests.HTTPError) and exc.response is not None and exc.response.status_code in (401,403)
        console(stderr=True).print('Your mail login expired. Next: co auth login' if expired else
            'Could not create a mail login link. Check your connection. Next: co email open --no-browser',markup=False)
        raise typer.Exit(1) from exc
    url=_login_url(phone)
    print(url)
    lifetime=phone['expires_in']
    duration=f'{lifetime//60}m {lifetime%60}s' if lifetime>=60 else f'{lifetime}s'
    show_qr=qr or (not no_browser and sys.stderr.isatty())
    instruction='Open it on your phone, or scan the QR below.' if show_qr else 'Open this link directly on your phone.'
    console(stderr=True).print(f'Private phone link · expires in {duration} · works once. {instruction}',markup=False)
    if show_qr:
        sys.stderr.write(_phone_qr(url))
    if not phone_only:
        try:opened=webbrowser.open(_login_url(desktop))
        except (webbrowser.Error,OSError):opened=False
        console(stderr=True).print('Opened this mailbox on your computer. The phone link above remains unused.' if opened else
            'Open the link above in your browser or on your phone.',markup=False)
    console(stderr=True).print(next_line('co email inbox'))
