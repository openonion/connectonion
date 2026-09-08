"""The twenty-command NAS parser and inherited common options."""

from typing import Optional
import typer
try:
    from typer._click.exceptions import ClickException, UsageError
except ImportError:
    from click import ClickException, UsageError

from ..typer_groups import _OneSuggestion
from . import synology_commands as commands

COMMON={'nas','json','non_interactive','timeout'}


def common_params():
    return [typer.core.TyperOption(param_decls=['--nas'],type=str,default=None,help='Select a saved NAS for this invocation.'),
            typer.core.TyperOption(param_decls=['--json'],is_flag=True,default=False,help='Emit one JSON result; never prompt.'),
            typer.core.TyperOption(param_decls=['--non-interactive'],is_flag=True,default=False,help='Never prompt.'),
            typer.core.TyperOption(param_decls=['--timeout'],type=float,default=60,help='Command waiting budget in seconds (0 < seconds <= 3600).')]


class SynologyCommand(typer.core.TyperCommand):
    def __init__(self,*args,**kwargs):
        kwargs['params']=list(kwargs.get('params') or [])+common_params()
        super().__init__(*args,**kwargs)

    def invoke(self,ctx):
        for name in COMMON:
            ctx.params.pop(name,None)
        return super().invoke(ctx)


class SynologyGroup(_OneSuggestion):
    def __init__(self,*args,**kwargs):
        kwargs['params']=list(kwargs.get('params') or [])+common_params()
        super().__init__(*args,**kwargs)

    def invoke(self,ctx):
        for name in COMMON:
            ctx.params.pop(name,None)
        return super().invoke(ctx)


class SharingGroup(SynologyGroup):
    def resolve_command(self,ctx,args):
        # Keep `share PATH` as a migration alias with create's full safety flags.
        if args and (args[0].startswith('/') or args[0].isascii() and args[0].isdigit()):
            args=['create',*args]
        return super().resolve_command(ctx,args)


class SynologyRoot(SynologyGroup):
    def parse_args(self,ctx,args):
        options={'nas':None,'json':False,'non_interactive':False,'timeout':60.0}
        seen={}; remaining=[]; index=0
        try:
            while index<len(args):
                token=args[index]
                if token=='--':
                    remaining.extend(args[index:]); break
                flag,sep,value=token.partition('=')
                if flag not in {'--nas','--json','--non-interactive','--timeout'}:
                    remaining.append(token); index+=1; continue
                key=flag[2:].replace('-','_')
                if key in {'json','non_interactive'}:
                    if sep:
                        raise UsageError(f'{flag} does not take a value.')
                    value=True
                else:
                    if not sep:
                        index+=1
                        if index>=len(args) or args[index].startswith('--'):
                            raise UsageError(f'{flag} requires a value.')
                        value=args[index]
                    if key=='timeout':
                        try:
                            value=float(value)
                            if not 0<value<=3600:
                                raise ValueError
                        except ValueError:
                            raise UsageError('--timeout must be greater than zero and at most 3600.') from None
                if key in seen and seen[key]!=value:
                    raise UsageError(f'Conflicting repeated {flag} values.')
                options[key]=seen[key]=value
                index+=1
            ctx.ensure_object(dict)
            ctx.obj['_synology']=options
            return super().parse_args(ctx,remaining)
        except ClickException as error:
            # The JSON flag may occur after the invalid option.
            options['json']='--json' in args
            commands.emit('',error={'code':'usage_error','message':error.format_message()},options=options,exit_code=2)

    def invoke(self,ctx):
        try:
            return super().invoke(ctx)
        except ClickException as error:
            commands.emit('',error={'code':'usage_error','message':error.format_message()},options=ctx.obj['_synology'],exit_code=2)


syno_app=typer.Typer(cls=SynologyRoot,no_args_is_help=False,rich_markup_mode=None,
    help='Connect to a Synology NAS, inspect its state and manage everyday files. Bare co syno lists shared folders.',
    epilog='Examples: co syno login --name home; co syno --nas home status; co syno ls /home/docs')


def group(name,help_text,cls=SynologyGroup):
    return typer.Typer(cls=cls,no_args_is_help=True,rich_markup_mode=None,help=help_text,
                       epilog=f'Example: co syno {name} --help')


nas_app=group('nas','Inspect saved NAS profiles and select the default.')
network_app=group('network','Inspect NAS interfaces separately from client connectivity.')
storage_app=group('storage','Inspect the capacity and disk indicators supplied by the configured SNMPv3 source.')
service_app=group('service','Enumerate services using explicitly configured SSH read commands.')
share_app=group('share','Create, list and revoke sharing links. Legacy share PATH dispatches to create.',SharingGroup)
for name,child in [('nas',nas_app),('network',network_app),('storage',storage_app),('service',service_app),('share',share_app)]:
    syno_app.add_typer(child,name=name)


def command(app,name,example,help_text=None,hidden=False):
    return app.command(name,cls=SynologyCommand,help=help_text,epilog='Example: '+example,hidden=hidden)


@syno_app.callback(invoke_without_command=True)
def default(ctx:typer.Context):
    if ctx.invoked_subcommand is None:
        ls(path="/",limit=20,cursor=None,sort="name",order="asc")


@command(syno_app,'login','co syno login --name home --url https://nas.example:5001 --username alice',
         'Verify File Station access before saving a profile. HTTPS and interactive-only OTP; no secrets on argv.')
def login(name:Optional[str]=typer.Option(None,'--name'),url:Optional[str]=typer.Option(None,'--url'),
          quickconnect:Optional[str]=typer.Option(None,'--quickconnect'),username:Optional[str]=typer.Option(None,'--username'),
          password_stdin:bool=typer.Option(False,'--password-stdin'),ca_cert:Optional[str]=typer.Option(None,'--ca-cert'),
          credential_store:str=typer.Option('keyring','--credential-store',help='OS keyring, or explicit POSIX file fallback.'),
          monitoring:Optional[str]=typer.Option(None,'--monitoring',help='JSON file with explicit non-secret snmp/ssh settings.'),
          snmp_secrets_file:Optional[str]=typer.Option(None,'--snmp-secrets-file',help='Private JSON file with snmp_auth/snmp_priv; otherwise prompt.')):
    commands.execute('login',lambda o:commands.handle_login(o,name=name,url=url,quickconnect=quickconnect,username=username,
        password_stdin=password_stdin,ca_cert=ca_cert,credential_store=credential_store,monitoring=monitoring,snmp_secrets_file=snmp_secrets_file))


@command(syno_app,'logout','co syno --nas home logout','Clear local authentication even when remote session invalidation is unavailable; retain settings.')
def logout():
    commands.execute('logout',lambda o:commands._syno(o).logout())


@command(nas_app,'list','co syno nas list --json','List saved settings and selected default without revealing secrets.')
def nas_list():
    def run(o):
        from ...useful_tools.synology_profiles import ProfileStore
        return ProfileStore().list()
    commands.execute('nas list',run)


@command(nas_app,'use','co syno nas use office','Select a saved default. Adding a second profile never switches automatically.')
def nas_use(name:str=typer.Argument(...)):
    def run(o):
        from ...useful_tools.synology_profiles import ProfileStore
        ProfileStore().use(name)
        return {'default':name}
    commands.execute('nas use',run)


@command(syno_app,'status','co syno status --operation OPERATION_ID --wait',
         'Inspect live connectivity and configured monitoring sources. Partial coverage exits 1. Operation checks never resubmit writes.')
def status(refresh:bool=typer.Option(False,'--refresh'),operation:Optional[str]=typer.Option(None,'--operation'),
           wait:bool=typer.Option(False,'--wait')):
    def run(o):
        if (wait and not operation) or (operation and refresh):
            commands._error('invalid_input','--wait requires --operation; --operation cannot be combined with --refresh.')
        client=commands._syno(o)
        return client.operation_status(operation,wait=wait) if operation else client.status()
    commands.execute('status',run)


@command(network_app,'status','co syno network status --refresh','Read NAS IF-MIB/IPv4 data and verified client endpoint timing. All inspections are fresh.')
def network_status(refresh:bool=typer.Option(False,'--refresh')):
    commands.execute('network status',lambda o:commands._syno(o).network_status())


@command(storage_app,'status','co syno storage status --json','Read RAID capacity counters and status. Provider rows are not inferred topology.')
def storage_status(refresh:bool=typer.Option(False,'--refresh')):
    commands.execute('storage status',lambda o:commands._syno(o).storage_status())


@command(storage_app,'disks','co syno storage disks --refresh','Read disk identity, deployment state and available health/temperature indicators; missing is unavailable.')
def storage_disks(refresh:bool=typer.Option(False,'--refresh')):
    commands.execute('storage disks',lambda o:commands._syno(o).storage_disks())


@command(service_app,'list','co syno service list --running','Enumerate actual synoservice state through the explicit SSH key and known-host source.')
def service_list(running:bool=typer.Option(False,'--running'),refresh:bool=typer.Option(False,'--refresh')):
    commands.execute('service list',lambda o:commands._syno(o).service_list(running=running))


@command(syno_app,'ls','co syno ls /home/docs --limit 20 --sort name --order asc',
         'List accessible shares or a full directory path. Default order is name ascending. Live pages can change.')
def ls(path:str=typer.Argument('/'),limit:int=typer.Option(20,'--limit','--last','-n',min=1,max=1000),
       cursor:Optional[str]=typer.Option(None,'--cursor'),sort:str=typer.Option('name','--sort'),order:str=typer.Option('asc','--order')):
    def run(o):
        value=commands._syno(o).list_page(path,limit=limit,cursor=cursor,sort=sort,order=order)
        value['_page_command']=['ls',path,'--limit',str(limit),'--sort',sort,'--order',order]
        return value
    commands.execute('ls',run)


@command(syno_app,'info','co syno info /home/docs/report.pdf','Inspect a complete NAS file or directory path.')
def info(path:str=typer.Argument(...)):
    commands.execute('info',lambda o:commands._syno(o).info(path))


@command(syno_app,'search','co syno search invoice --in /home/docs --type file',
         'Search names in an explicit shared-directory scope. Wait for completion and clean the task before paging its snapshot.')
def search(query:str=typer.Argument(...),path:str=typer.Option(...,'--in'),glob:bool=typer.Option(False,'--glob'),
           kind:str=typer.Option('all','--type'),limit:int=typer.Option(20,'--limit','--last','-n',min=1,max=1000),
           cursor:Optional[str]=typer.Option(None,'--cursor')):
    def run(o):
        value=commands._syno(o).search_page(query,path,glob=glob,kind=kind,limit=limit,cursor=cursor)
        value['_page_command']=['search',query,'--in',path,'--type',kind,'--limit',str(limit)]+(['--glob'] if glob else [])
        return value
    commands.execute('search',run)


def transfer(direction,path,dest,recursive,overwrite,skip_existing,dry_run,listing=None):
    def run(o):
        if overwrite and skip_existing:
            commands._error('invalid_input','Choose --overwrite or --skip-existing.')
        client=commands._syno(o,dry_run=dry_run)
        if direction=='download':
            return client.download(client.state.resolve(path,listing),dest,recursive=recursive,overwrite=overwrite,
                                   skip_existing=skip_existing,dry_run=dry_run)
        return client.upload(path,dest,recursive=recursive,overwrite=overwrite,skip_existing=skip_existing,dry_run=dry_run)
    commands.execute(direction,run)


@command(syno_app,'download','co syno download /home/docs/report.pdf --to ./Downloads/',
         'Download without overwrite by default. Directories require --recursive; local parents must exist. Numeric migration rows require --listing.')
def download(path:str=typer.Argument(...),dest:str=typer.Option('.','--to'),recursive:bool=typer.Option(False,'--recursive'),
             overwrite:bool=typer.Option(False,'--overwrite'),skip_existing:bool=typer.Option(False,'--skip-existing'),
             dry_run:bool=typer.Option(False,'--dry-run'),listing:Optional[str]=typer.Option(None,'--listing')):
    transfer('download',path,dest,recursive,overwrite,skip_existing,dry_run,listing)


@command(syno_app,'upload','co syno upload ./report.pdf /home/docs/',
         'Upload into an existing NAS directory. Directories require --recursive and preserve their base name and empty directories.')
def upload(local:str=typer.Argument(...),directory:str=typer.Argument(...),recursive:bool=typer.Option(False,'--recursive'),
           overwrite:bool=typer.Option(False,'--overwrite'),skip_existing:bool=typer.Option(False,'--skip-existing'),dry_run:bool=typer.Option(False,'--dry-run')):
    transfer('upload',local,directory,recursive,overwrite,skip_existing,dry_run)


@command(syno_app,'mkdir','co syno mkdir /home/docs/archive --parents --dry-run','Create ordinary directories; never create DSM shared roots.')
def mkdir(path:str=typer.Argument(...),parents:bool=typer.Option(False,'--parents'),dry_run:bool=typer.Option(False,'--dry-run')):
    commands.execute('mkdir',lambda o:commands._syno(o,dry_run=dry_run).mkdir(path,parents=parents,dry_run=dry_run))


@command(syno_app,'copy','co syno copy /home/docs/report.pdf /home/archive/final.pdf',
         'Copy within one NAS without directory-tree merging. Pending task IDs survive restart; repeat this command only when continuation is requested.')
def copy(source:str=typer.Argument(...),destination:str=typer.Argument(...),recursive:bool=typer.Option(False,'--recursive'),
         overwrite:bool=typer.Option(False,'--overwrite'),dry_run:bool=typer.Option(False,'--dry-run')):
    commands.execute('copy',lambda o:commands._syno(o,dry_run=dry_run).copy(source,destination,recursive=recursive,overwrite=overwrite,dry_run=dry_run))


@command(syno_app,'move','co syno move /home/docs/report.pdf /home/archive/final.pdf',
         'Move or rename within one NAS. No self-descendant moves or existing-directory-tree merging.')
def move(source:str=typer.Argument(...),destination:str=typer.Argument(...),overwrite:bool=typer.Option(False,'--overwrite'),
         dry_run:bool=typer.Option(False,'--dry-run')):
    commands.execute('move',lambda o:commands._syno(o,dry_run=dry_run).move(source,destination,overwrite=overwrite,dry_run=dry_run))


@command(share_app,'create','co syno share create /home/docs/report.pdf --expires 2026-09-30 --yes',
         'Create a link with explicit NAS-local expiry or no-expiry. Unattended writes require --yes; passwords are limited to 16 characters.')
def share_create(path:str=typer.Argument(...),expires:Optional[str]=typer.Option(None,'--expires'),
                 no_expiry:bool=typer.Option(False,'--no-expiry'),password:bool=typer.Option(False,'--password'),
                 password_stdin:bool=typer.Option(False,'--password-stdin'),yes:bool=typer.Option(False,'--yes'),
                 dry_run:bool=typer.Option(False,'--dry-run'),listing:Optional[str]=typer.Option(None,'--listing')):
    commands.execute('share create',lambda o:commands.handle_share_create(o,path,expires=expires,no_expiry=no_expiry,
        password=password,password_stdin=password_stdin,yes=yes,dry_run=dry_run,listing=listing))


@command(share_app,'list','co syno share list --limit 20',
         'List IDs, paths, expiry, protection and provider status. Bearer URLs appear only with --show-url.')
def share_list(limit:int=typer.Option(20,'--limit','--last','-n',min=1,max=1000),cursor:Optional[str]=typer.Option(None,'--cursor'),
               show_url:bool=typer.Option(False,'--show-url')):
    def run(o):
        result=commands._syno(o).share_list(limit=limit,cursor=cursor,show_url=show_url)
        result['_page_command']=['share','list','--limit',str(limit)]+(['--show-url'] if show_url else [])
        return result
    commands.execute('share list',run)


@command(share_app,'revoke','co syno share revoke LINK_ID --yes','Revoke this selected NAS/account link; never delete its source file.')
def share_revoke(identifier:str=typer.Argument(...),yes:bool=typer.Option(False,'--yes'),dry_run:bool=typer.Option(False,'--dry-run')):
    def run(o):
        commands._confirm(o,'Revoke this sharing link?',yes,dry_run)
        return commands._syno(o,dry_run=dry_run).share_revoke(identifier,dry_run=dry_run)
    commands.execute('share revoke',run)


# Aliases use the exact canonical callback and parser options, including the
# required frozen listing context. Main help and emitted tips stay canonical.
command(syno_app,'get','co syno get 1 --listing LISTING_ID --to ./Downloads/',
        'Migration alias for download. Numeric rows always require their frozen --listing ID.')(download)
command(syno_app,'put','co syno put ./report.pdf /home/docs/',
        'Migration alias for upload; all transfer safeguards and options apply.')(upload)
command(syno_app,'shares','co syno shares --show-url',
        'Migration alias for share list; URLs are hidden unless explicitly requested.')(share_list)
