"""Two-party mailbox transfer using the backend's fixed signed message protocol."""
import json
import os
from pathlib import Path
import re
import time
import requests
import typer
from ... import address as identity_crypto
from ...backend import backend_url
from ..style import console

out=console()
KEY=re.compile(r'0x[a-f0-9]{64}')
FIELDS={'address','from_public_key','to_public_key','timestamp','from_signature','to_signature'}

def transfer_message(data: dict) -> str:
    return (f"ConnectOnion-Transfer-Address-{data['address']}-and-its-mail"
            f"-from-{data['from_public_key']}-to-{data['to_public_key']}-{data['timestamp']}")

def _identity():
    from ...environment import load_environment
    from ...project import project_identity
    load_environment()
    value=project_identity()
    if not value:raise ValueError('No selected identity. Run co init first.')
    return value

def _validate(data: dict,*,complete: bool = False,verify_signatures: bool = True):
    if not isinstance(data,dict) or set(data)-FIELDS:raise ValueError('Invalid transfer file fields.')
    for key in ('from_public_key','to_public_key'):
        if not KEY.fullmatch(str(data.get(key,''))):raise ValueError('Invalid account public key.')
    if data['from_public_key']==data['to_public_key']:raise ValueError('Sender and recipient must be different accounts.')
    mailbox=data.get('address','')
    if not isinstance(mailbox,str) or mailbox!=mailbox.lower() or not re.fullmatch(r'[^\s<>/@]+@[^\s<>/@]+\.[^\s<>/@]+',mailbox):
        raise ValueError('Transfer address must be a lowercase email address.')
    stamp=data.get('timestamp')
    if isinstance(stamp,bool) or not isinstance(stamp,int) or abs(time.time()-stamp)>300:
        raise ValueError('Transfer expired. Prepare a fresh request; signatures last five minutes.')
    if not verify_signatures:return
    message=transfer_message(data).encode()
    for role in ('from','to') if complete else ('from',):
        signature=data.get(role+'_signature','')
        if not isinstance(signature,str) or not re.fullmatch(r'[a-f0-9]{128}',signature) or not identity_crypto.verify(data[role+'_public_key'],message,bytes.fromhex(signature)):
            raise ValueError(f'Invalid {role} signature. Request a fresh transfer file.')

def _read(path: Path):
    if path.stat().st_size>16384:raise ValueError('Transfer file is too large.')
    return json.loads(path.read_text())

def _write(path: Path,data: dict):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(data,stream,indent=2)

def prepare(mailbox: str,to: str,destination: Path):
    identity=_identity()
    data={'address':mailbox.strip().lower(),'from_public_key':identity['address'],
          'to_public_key':to.strip().lower(),'timestamp':int(time.time())}
    # Validate structure before asking the selected key to sign any content.
    _validate(data,verify_signatures=False)
    data['from_signature']=identity_crypto.sign(identity,transfer_message(data).encode()).hex()
    _validate(data);_write(destination,data)
    out.print(f'Prepared {data["address"]} and its mail for {data["to_public_key"]}. Request expires in five minutes.',markup=False)

def accept(source: Path,destination: Path):
    data=_read(source);_validate(data)
    identity=_identity()
    if identity['address']!=data['to_public_key']:raise ValueError('This identity is not the named recipient. Use the recipient’s selected account.')
    data['to_signature']=identity_crypto.sign(identity,transfer_message(data).encode()).hex()
    _validate(data,complete=True);_write(destination,data)
    out.print(f'Signed acceptance of {data["address"]} and its existing mail.',markup=False)

def complete(source: Path,yes: bool = False):
    data=_read(source);_validate(data,complete=True)
    if not yes:
        out.print(f'Transfers {data["address"]} and all its received/sent history from {data["from_public_key"]} to {data["to_public_key"]}. Add --yes to apply.',markup=False)
        return
    response=requests.post(backend_url()+'/api/v1/email/addresses/transfer',json=data,timeout=20)
    if not response.ok:
        from .email_commands import _err
        raise ValueError(_err(response))
    out.print(json.dumps(response.json(),ensure_ascii=False),markup=False)

def run(operation,*args,**kwargs):
    try:operation(*args,**kwargs)
    except (OSError,ValueError,requests.RequestException) as exc:
        out.print('Could not reach the email service.' if isinstance(exc,requests.RequestException) else str(exc),markup=False)
        raise typer.Exit(1) from exc
