"""Open OO Mail and sign a browser-bound challenge using the selected identity."""
import base64
import json
import re
import time
import webbrowser
import typer
from ..style import console

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
    console().print(MAIL_URL,markup=False)
    if not no_browser and not webbrowser.open(MAIL_URL):
        console().print('Open this URL in your browser. Choose Connect mailbox to use your existing account.',markup=False)
