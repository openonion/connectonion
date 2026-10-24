"""Search, replies, read state and account settings over the existing mail API."""
import json
import shlex
from email.utils import parseaddr
import requests
import typer
from ..style import console
from .email_commands import _require_auth, _err, _read_failure, handle_email_send
from .project_cmd_lib import load_api_key
from ...backend import backend_url

out = console()

def _request(method: str, path: str, **kwargs):
    token = load_api_key()
    if not token:
        out.print('Not connected. Next: co auth login', markup=False)
        raise typer.Exit(1)
    try:
        response=requests.request(method,backend_url()+'/api/v1/email/'+path,
            headers={'Authorization':f'Bearer {token}',**kwargs.pop('headers',{})},timeout=20,**kwargs)
        if not response.ok:
            raise ValueError(_err(response))
        return response.json()
    except (requests.RequestException,ValueError) as exc:
        out.print('Could not reach the email service.' if isinstance(exc,requests.RequestException) else f'Email request failed: {exc}',markup=False)
        out.print('Next: co email inbox',markup=False)
        raise typer.Exit(1) from exc

def _read(email_id: str):
    from ...useful_tools.get_emails import get_email
    _require_auth()
    try:return get_email(email_id)
    except (requests.RequestException,ValueError) as exc:
        _read_failure(exc,'received')
        out.print('Next: co email inbox',markup=False)
        raise typer.Exit(1) from exc

def handle_email_mark(email_ids: list[str], unread: bool = False):
    from ...useful_tools.get_emails import _message_id,mark_read,mark_unread
    completed=[]
    ids=[]
    try:
        ids=list(dict.fromkeys(str(_message_id(value)) for value in email_ids))
        _require_auth()
        for message_id in ids:
            (mark_unread if unread else mark_read)(message_id)
            completed.append(message_id)
    except (requests.RequestException,ValueError) as exc:
        if completed:out.print(f'Updated {len(completed)} of {len(ids)} messages before the failure.',markup=False)
        _read_failure(exc,'received')
        out.print('Next: co email inbox',markup=False)
        raise typer.Exit(1) from exc
    out.print(f"Marked {len(ids)} message(s) {'unread' if unread else 'read'}.",markup=False)

def handle_email_search(query: str,last: int = 100,offset: int = 0,json_output: bool = False):
    from ...useful_tools.get_emails import get_emails
    _require_auth()
    try:messages=get_emails(last=last,offset=offset)
    except (requests.RequestException,ValueError,RuntimeError) as exc:
        out.print('Could not reach the email service.' if isinstance(exc,requests.RequestException) else f'Could not search this page: {exc}',markup=False)
        out.print('Next: co email inbox',markup=False)
        raise typer.Exit(1) from exc
    needle=query.strip().casefold()
    if not needle:
        out.print('Enter a non-empty search query.',markup=False)
        raise typer.Exit(1)
    matches=[m for m in messages if any(needle in str(m.get(k,'')).casefold() for k in ('from','to','subject','message'))]
    if json_output:print(json.dumps({'emails':matches,'scanned':len(messages),'offset':offset},ensure_ascii=False));return
    out.print(f'Search: {len(matches)} matches in {len(messages)} messages (offset {offset}).',markup=False)
    for m in matches:out.print(f"{m['id']}  {m['from']}  {m['subject']}",markup=False)
    if len(messages)==last:out.print(f'Older page: co email search {shlex.quote(query)} --last {last} --offset {offset+last}',markup=False)

def handle_email_reply(email_id: str,message: str,*,to: str | None = None,from_address: str | None = None,idempotency_key: str | None = None):
    original=_read(email_id)
    recipient=to or parseaddr(original['from'])[1]
    if '@' not in recipient:
        out.print('The original sender has no valid email address.',markup=False)
        raise typer.Exit(1)
    subject=original['subject'] or '(No subject)'
    prefix='Fwd:' if to else 'Re:'
    if not subject.lower().startswith(prefix.lower()):subject=prefix+' '+subject
    quoted='\n'.join('> '+line for line in (original.get('message') or '').splitlines())
    body=f"{message}\n\nOn {original.get('timestamp','')}, {original['from']} wrote:\n{quoted}"
    handle_email_send(recipient,subject,body,from_address=from_address,idempotency_key=idempotency_key)

def handle_email_tier(json_output: bool = False):
    data=_request('GET','tier')
    if json_output:print(json.dumps(data,ensure_ascii=False));return
    for label,key in [('Mailbox','sender_email'),('Plan','tier'),('Monthly allowance','emails_per_month'),('Usage','quota_status')]:
        out.print(f'{label}: {data.get(key,"—")}',markup=False)


def handle_email_quota(buy: bool = False,idempotency_key: str | None = None,json_output: bool = False):
    """Inspect quota, or buy exactly one backend-defined increment with an explicit retry key."""
    if buy:
        import re
        if not idempotency_key or not re.fullmatch(r'[\x21-\x7e]{1,256}',idempotency_key):
            out.print('Buying requires --idempotency-key with 1–256 visible ASCII characters. Reuse it when retrying.',markup=False)
            raise typer.Exit(1)
        data=_request('POST','purchase-quota',headers={'Idempotency-Key':idempotency_key})
    else:data=_request('GET','tier')
    if json_output:print(json.dumps(data,ensure_ascii=False));return
    if buy:out.print(data.get('message','Quota purchase completed.'),markup=False);return
    out.print(f"Monthly allowance: {data.get('emails_per_month','—')}",markup=False)
    out.print(f"Usage: {data.get('quota_status','—')}",markup=False)
    increment=data.get('quota_increment')
    if increment:out.print(f"One increment adds {increment['emails_per_month']} emails/month for ${increment['price']:.2f}. Buy with: co email quota --buy --idempotency-key <unique-key>",markup=False)
    else:out.print('No extra-quota increment is available on this plan.',markup=False)


def handle_email_change(address: str,*,name: str | None = None,domain: str | None = None,buy: bool = False):
    if not name and not domain:
        out.print('Specify --name, --domain, or both. Next: co email addresses',markup=False)
        raise typer.Exit(1)
    name=name.strip().lower() if name else None
    domain=domain.strip().lower() if domain else None
    settings=_request('GET','addresses')
    owned=next((a for a in settings.get('addresses',[]) if a['address'].casefold()==address.casefold()),None)
    if not owned:
        out.print('This address is not in your owned-address list. Next: co email addresses',markup=False)
        raise typer.Exit(1)
    old_name,old_domain=owned['address'].rsplit('@',1)
    target=f'{name or old_name}@{domain or old_domain}'.lower()
    if target==owned['address'].lower():out.print(f'Already set to {target}.',markup=False);return
    price=settings['prices']['change_local_part' if name and name!=old_name else 'change_domain']
    if not buy:
        out.print(f'Change {owned["address"]} to {target}: ${price:.2f} from credits. Add --buy to apply.',markup=False)
        return
    payload={k:v for k,v in {'local_part':name,'domain':domain}.items() if v}
    result=_request('PATCH',f'addresses/{owned["id"]}',json=payload)
    out.print(result.get('message',f'Changed address to {target}.'),markup=False)


def handle_email_delete_history(address: str,*,include_sent: bool = False,yes: bool = False):
    from urllib.parse import quote
    import re
    if not re.fullmatch(r'[^\s<>/@]+@[^\s<>/@]+\.[^\s<>/@]+',address):
        out.print('Enter a complete mailbox address. Next: co email addresses',markup=False)
        raise typer.Exit(1)
    if not yes:
        out.print(f"Deletes received history for {address}"+(' and its sent logs.' if include_sent else '.'),markup=False)
        out.print('The address remains yours. Add --yes to delete this history.',markup=False)
        return
    result=_request('DELETE',f'addresses/{quote(address,safe="")}/mail',params={'include_sent':str(include_sent).lower()})
    out.print(json.dumps(result,ensure_ascii=False),markup=False)
