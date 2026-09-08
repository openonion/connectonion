"""Synology command execution, prompts and result envelopes."""

import getpass
import json
from pathlib import Path
import shlex
import sys
import time

import typer
try:
    import typer._click as click
    from typer._click.globals import get_current_context
except ImportError:
    import click
    from click import get_current_context


def current_options() -> dict:
    ctx=get_current_context()
    while ctx is not None:
        if isinstance(ctx.obj,dict) and '_synology' in ctx.obj:
            return ctx.obj['_synology']
        ctx=ctx.parent
    return {'nas':None,'json':False,'non_interactive':False,'timeout':60}


def interactive(options: dict) -> bool:
    return not (options['json'] or options['non_interactive']) and sys.stdin.isatty() and sys.stderr.isatty()


def prompt_secret(label: str) -> str:
    return getpass.getpass(label+': ')


def _error(code: str, message: str):
    from ...useful_tools.synology_transport import SynologyError
    raise SynologyError(message,code)


def _require_interaction(options: dict) -> None:
    if not interactive(options):
        _error('interaction_required','This option requires an interactive terminal; use the documented stdin option where supported.')


def _password(options: dict, label: str, *, stdin: bool = False, prompt: bool = False) -> str | None:
    if stdin and prompt:
        _error('invalid_input','Choose the password prompt or password-stdin, not both.')
    if stdin:
        value=sys.stdin.readline(65537)
        if len(value)>65536 or not value.rstrip('\r\n'):
            _error('invalid_input','Password stdin must supply one nonempty line of at most 65536 characters.')
        return value.rstrip('\r\n')
    if prompt:
        _require_interaction(options)
        return prompt_secret(label)
    return None


def _confirm(options: dict, description: str, yes: bool, dry_run: bool) -> None:
    if yes or dry_run:
        return
    if not interactive(options):
        _error('confirmation_required','This change requires --yes when no interactive confirmation is available.')
    if not typer.confirm(description,default=False,err=True):
        _error('declined','The change was declined.')


def _syno(options: dict | None = None, *, dry_run: bool = False):
    from ...environment import load_environment
    load_environment()
    options=options or current_options()
    from ...useful_tools.synology import Synology
    client=Synology(nas=options['nas'],timeout=options['timeout'],dry_run=dry_run,
                    otp_callback=(lambda:prompt_secret('DSM one-time password')) if interactive(options) and not dry_run else None)
    client._fixed_budget=True
    return client


def next_command(operation: str, result: dict, options: dict) -> str:
    prefix=['co','syno']
    if options.get('nas'):
        prefix+=['--nas',options['nas']]
    if result.get('status')=='continuation_required' and result.get('resume'):
        request=result['resume']; words=['move' if request['move'] else 'copy',request['source'],request['destination']]
        if request['recursive'] and not request['move']:
            words+=['--recursive']
        if request['overwrite']:
            words+=['--overwrite']
    elif result.get('operation_id') and result.get('status')=='operation_pending':
        words=['status','--operation',result['operation_id'],'--wait']
    elif result.get('next_cursor'):
        # Repeated query parameters must match. The caller supplies the original
        # argument list rather than inferring a path/query from returned rows.
        words=result.pop('_page_command')+['--cursor',result['next_cursor']]
    elif operation in {'ls','search'} and result.get('items'):
        item=result['items'][0]
        words=['ls' if item['type']=='dir' else 'info',item['path']]
    elif operation in {'share create','share revoke'}:
        words=['share','list']
    elif operation in {'copy','move'} and result.get('status')=='complete':
        words=['info',result['destination']]
    elif operation=='mkdir' and result.get('path') and not result.get('dry_run'):
        words=['ls',result['path']]
    elif operation=='info' and result.get('path'):
        words=['ls' if result.get('type')=='dir' else 'download',result['path']]
    elif operation=='upload' and result.get('completed'):
        words=['info',result['completed'][-1]['path']]
    elif operation=='login':
        words=['status']
    elif operation=='nas use':
        prefix=['co','syno','--nas',result['default']]
        words=['status']
    elif operation=='nas list' and result.get('default'):
        prefix=['co','syno','--nas',result['default']]
        words=['status']
    elif operation in {'logout','nas list'}:
        words=['login']
    else:
        words=['ls']
    return shlex.join(prefix+words)


def emit(operation: str, result=None, error=None, *, options: dict | None = None, exit_code: int = 0) -> None:
    options=options or current_options()
    result=result if isinstance(result,dict) else {'items':result} if result is not None else None
    if error is None:
        next_step=next_command(operation,result or {},options)
    elif error['code'] in {'auth_required','auth_failed','otp_required','otp_rejected','not_configured'}:
        next_step=shlex.join(['co','syno','login']+(['--name',options['nas']] if options.get('nas') else []))
    elif error['code'] in {'stale_cursor','listing_required','invalid_reference'}:
        next_step=shlex.join(['co','syno']+(['--nas',options['nas']] if options.get('nas') else [])+['ls'])
    else:
        next_step=shlex.join(['co','syno',*operation.split(),'--help'])
    if result:
        result.pop('_page_command',None)
    envelope={'schema_version':1,'provider':'synology','nas':options.get('nas'),'command':'co syno '+operation,
              'ok':error is None and exit_code==0,'status':'success' if exit_code==0 else 'partial' if result else 'error',
              'complete':exit_code==0,'data':result,'error':error,'next_command':next_step}
    if options['json']:
        print(json.dumps(envelope,separators=(',',':'),ensure_ascii=False))
    else:
        if result is not None:
            print(json.dumps(result,indent=2,ensure_ascii=False))
        if error:
            print(error['message'],file=sys.stderr)
        print('Next: '+next_step,file=sys.stderr)
    if exit_code:
        raise typer.Exit(exit_code)


def execute(operation: str, action) -> None:
    from ...useful_tools.synology_profiles import ProfileError
    options=current_options()
    try:
        result=action(options)
    except ProfileError as error:
        usage=error.code in {'invalid_input','interaction_required','invalid_path','invalid_profile'}
        emit(operation,error={'code':error.code,'message':str(error)},exit_code=2 if usage else 1)
        return
    except KeyboardInterrupt:
        emit(operation,error={'code':'interrupted','message':'Interrupted; inspect remote state before repeating a write.'},exit_code=130)
        return
    except OSError:
        emit(operation,error={'code':'local_io_error','message':'A local file or credential-store operation failed.'},exit_code=1)
        return
    partial=result.get('status') in {'partial','operation_pending','submission_unknown','task_unavailable',
                                     'operation_failed','continuation_required'} or result.get('completeness')=='partial'
    emit(operation,result,exit_code=1 if partial else 0)


def handle_login(options: dict, *, name, url, quickconnect, username, password_stdin,
                 ca_cert, credential_store, monitoring, snmp_secrets_file) -> dict:
    from ...useful_tools.synology import Synology, pick_reachable, resolve_quickconnect
    from ...useful_tools.synology_profiles import ProfileStore, read_private_json, validate_settings
    if url and quickconnect:
        _error('invalid_input','Choose URL or QuickConnect ID.')
    if options.get('nas') and name and name!=options['nas']:
        _error('invalid_input','--name and --nas select different profiles.')
    name=name or options.get('nas') or 'home'
    if not url and not quickconnect:
        _require_interaction(options)
        url=typer.prompt('HTTPS NAS URL',err=True)
    if not username:
        _require_interaction(options)
        username=typer.prompt('DSM username',err=True)
    deadline=time.monotonic()+options["timeout"]
    if quickconnect:
        candidates=resolve_quickconnect(quickconnect,timeout=min(15,options["timeout"]))
        url=pick_reachable(candidates,timeout=max(.001,deadline-time.monotonic()),ca_cert=ca_cert)
    password=_password(options,'DSM password',stdin=password_stdin,prompt=not password_stdin)
    settings={'url':url,'account':username,'ca_cert':ca_cert}
    secret={'password':password}
    if monitoring:
        try:
            content=Path(monitoring).expanduser().read_bytes()
            if len(content)>65536:
                raise ValueError
            config=json.loads(content)
            if not isinstance(config,dict) or set(config)-{'snmp','ssh'}:
                raise ValueError
            settings.update(config)
        except (ValueError,OSError):
            _error('invalid_input','Monitoring config must be a bounded JSON object with only snmp/ssh settings and no secrets.')
    settings=validate_settings(settings)
    if snmp_secrets_file:
        if not settings.get('snmp'):
            _error('invalid_input','SNMP secret input requires explicit SNMP settings in --monitoring.')
        provided=read_private_json(Path(snmp_secrets_file).expanduser(),limit=65536)
        if set(provided)!={'snmp_auth','snmp_priv'} or not all(isinstance(v,str) and v for v in provided.values()):
            _error('invalid_input','SNMP secret file requires only nonempty snmp_auth and snmp_priv values.')
        secret.update(provided)
    elif settings.get('snmp'):
        _require_interaction(options)
        secret.update(snmp_auth=prompt_secret('SNMPv3 authentication key'),snmp_priv=prompt_secret('SNMPv3 privacy key'))
    client=Synology(url,username,password,ca_cert=ca_cert,timeout=max(.001,deadline-time.monotonic()),
                    otp_callback=(lambda:prompt_secret('DSM one-time password')) if interactive(options) else None)
    # No state publication occurs before authenticated File Station access.
    connection=client.connectivity()
    secret['sid']=client.sid
    profile=ProfileStore().save(name,settings,secret,storage=credential_store)
    return {'profile':name,'url':profile['url'],'account':username,'credential_store':credential_store,
            'verified':connection,'monitoring':list(key for key in ('snmp','ssh') if settings.get(key)),
            'cleanup_warning':profile.get('cleanup_warning')}


def handle_share_create(options, path, *, expires, no_expiry, password, password_stdin, yes, dry_run, listing=None):
    if expires and no_expiry:
        _error('invalid_input','Choose an expiry date or no-expiry.')
    if not expires and not no_expiry:
        if dry_run or not interactive(options):
            _error('invalid_input','Choose --expires YYYY-MM-DD or --no-expiry.')
        choice=typer.prompt('NAS-local expiry date (YYYY-MM-DD), or type none',err=True)
        no_expiry=choice=='none'; expires=None if no_expiry else choice
    if password and password_stdin:
        _error('invalid_input','Choose password prompt or password-stdin.')
    secret=None if dry_run else _password(options,'Sharing password',stdin=password_stdin,prompt=password)
    _confirm(options,'Create this sharing link?',yes,dry_run)
    client=_syno(options,dry_run=dry_run)
    path=client.state.resolve(path,listing)
    result=client.share_create(path,expires=expires,no_expiry=no_expiry,password=secret,dry_run=dry_run)
    if dry_run and (password or password_stdin):
        result['protected']=True
        result['password_validation']='deferred; dry-run does not read secrets'
    return result
