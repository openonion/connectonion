"""Open the selected account's real mailbox with a one-time browser login."""
import base64
import json
import re
import time
import webbrowser
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

def handle_email_open(no_browser: bool = False):
    from .project_cmd_lib import load_api_key
    from ...backend import backend_url
    token = load_api_key()
    if not token:
        console(stderr=True).print('Not connected. Next: co auth login', markup=False)
        raise typer.Exit(1)
    try:
        response = requests.post(backend_url()+'/api/v1/auth/mail-link',
            headers={'Authorization': f'Bearer {token}'}, timeout=20)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError('Invalid login response')
        code, account = data.get('code'), data.get('public_key')
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', code):
            raise ValueError('Invalid login response')
        if not isinstance(account, str) or not re.fullmatch(r'0x[0-9a-fA-F]{64}', account):
            raise ValueError('Invalid login account')
    except (requests.RequestException, ValueError) as exc:
        expired = isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code in (401, 403)
        console(stderr=True).print('Your mail login expired. Next: co auth login' if expired else
            'Could not create a mail login link. Check your connection. Next: co email open --no-browser', markup=False)
        raise typer.Exit(1) from exc
    url = MAIL_URL+'/connect#code='+code+'&account='+account
    print(url)
    console(stderr=True).print('Opens your current mailbox. This private link expires in two minutes and works once.', markup=False)
    if not no_browser:
        try: opened = webbrowser.open(url)
        except (webbrowser.Error, OSError): opened = False
        if not opened: console(stderr=True).print('Open the link above in your browser.', markup=False)
    console(stderr=True).print(next_line('co email inbox'))
