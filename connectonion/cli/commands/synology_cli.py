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
    help='Connect to a Synology NAS, inspect its state and manage everyday files. Bare co syno lists shared folders (Read-only).',
    epilog='Examples: co syno login --name home; co syno --nas home status; co syno ls /home/docs')


def group(help_text,example,cls=SynologyGroup):
    return typer.Typer(cls=cls,no_args_is_help=True,rich_markup_mode=None,help=help_text,
                       epilog='Example: '+example)


nas_app=group('List saved NAS profiles (Read-only) and choose which one commands use by default (Changes local settings).',
              'co syno nas list')
network_app=group('Show the NAS network interfaces and how quickly this computer reaches the NAS. Read-only. '
                  'Needs SNMP monitoring set up with co syno login --monitoring.','co syno network status')
storage_app=group('Show volume capacity and disk health as reported by the NAS. Read-only. '
                  'Needs SNMP monitoring set up with co syno login --monitoring.','co syno storage status')
service_app=group('List the NAS system services and whether each is running. Read-only. '
                  'Connects over SSH, so it needs SSH settings from co syno login --monitoring.','co syno service list --running')
share_app=group('Create, list and revoke sharing links to NAS files. Creates or Removes links on the NAS; list is Read-only. '
                'co syno share PATH is short for co syno share create PATH.','co syno share list',SharingGroup)
for name,child in [('nas',nas_app),('network',network_app),('storage',storage_app),('service',service_app),('share',share_app)]:
    syno_app.add_typer(child,name=name)


def command(app,name,example,help_text=None,hidden=False):
    return app.command(name,cls=SynologyCommand,help=help_text,epilog='Example: '+example,hidden=hidden)


@syno_app.callback(invoke_without_command=True)
def default(ctx:typer.Context):
    if ctx.invoked_subcommand is None:
        ls(path="/",limit=20,cursor=None,sort="name",order="asc")


@command(syno_app,'login','co syno login --name home --url https://nas.example:5001 --username alice',
         'Sign in to a Synology NAS and save it as a named profile. Checks the account can open File Station first, then Writes '
         'the profile to local settings and the password to your OS keyring (or a private file with --credential-store). '
         'Needs an HTTPS URL or QuickConnect ID. One-time codes are asked for at the prompt; give the password at the prompt '
         'or with --password-stdin, never as an argument.')
def login(name:Optional[str]=typer.Option(None,'--name'),url:Optional[str]=typer.Option(None,'--url'),
          quickconnect:Optional[str]=typer.Option(None,'--quickconnect'),username:Optional[str]=typer.Option(None,'--username'),
          password_stdin:bool=typer.Option(False,'--password-stdin'),ca_cert:Optional[str]=typer.Option(None,'--ca-cert'),
          credential_store:str=typer.Option('keyring','--credential-store',help='OS keyring, or explicit POSIX file fallback.'),
          monitoring:Optional[str]=typer.Option(None,'--monitoring',help='JSON file with explicit non-secret snmp/ssh settings.'),
          snmp_secrets_file:Optional[str]=typer.Option(None,'--snmp-secrets-file',help='Private JSON file with snmp_auth/snmp_priv; otherwise prompt.')):
    commands.execute('login',lambda o:commands.handle_login(o,name=name,url=url,quickconnect=quickconnect,username=username,
        password_stdin=password_stdin,ca_cert=ca_cert,credential_store=credential_store,monitoring=monitoring,snmp_secrets_file=snmp_secrets_file))


@command(syno_app,'logout','co syno --nas home logout','Sign out of a saved NAS. Removes its saved password and session from this computer and keeps the profile settings. '
         'The local sign-in is cleared even when the NAS cannot be reached to end the session.')
def logout():
    commands.execute('logout',lambda o:commands._syno(o).logout())


@command(nas_app,'list','co syno nas list --json','List saved settings and selected default without revealing secrets. Read-only.')
def nas_list():
    def run(o):
        from ...useful_tools.synology_profiles import ProfileStore
        return ProfileStore().list()
    commands.execute('nas list',run)


@command(nas_app,'use','co syno nas use office','Make a saved NAS the default for later co syno commands. Changes local settings only. '
         'Saving another NAS with co syno login never changes the default by itself.')
def nas_use(name:str=typer.Argument(...)):
    def run(o):
        from ...useful_tools.synology_profiles import ProfileStore
        ProfileStore().use(name)
        return {'default':name}
    commands.execute('nas use',run)


@command(syno_app,'status','co syno status --operation OPERATION_ID --wait',
         'Check that the NAS is reachable and summarise its device, network, storage, disks and services. Read-only. '
         'Exits 1 when some of those checks could not run. With --operation, shows the progress of an earlier copy or move '
         'and never starts it again.')
def status(refresh:bool=typer.Option(False,'--refresh'),operation:Optional[str]=typer.Option(None,'--operation'),
           wait:bool=typer.Option(False,'--wait')):
    def run(o):
        if (wait and not operation) or (operation and refresh):
            commands._error('invalid_input','--wait requires --operation; --operation cannot be combined with --refresh.')
        client=commands._syno(o)
        return client.operation_status(operation,wait=wait) if operation else client.status()
    commands.execute('status',run)


@command(network_app,'status','co syno network status --refresh','Show each NAS network interface (up or down, speed, IPv4 addresses) and how long this computer takes to reach the NAS. '
         'Read-only. Reads the NAS over SNMP, so it needs co syno login --monitoring. Always checks live.')
def network_status(refresh:bool=typer.Option(False,'--refresh')):
    commands.execute('network status',lambda o:commands._syno(o).network_status())


@command(storage_app,'status','co syno storage status --json','Show each storage volume with its health, free and total space, exactly as the NAS reports them. Read-only. '
         'Does not show which disks make up a volume; see co syno storage disks. Needs co syno login --monitoring.')
def storage_status(refresh:bool=typer.Option(False,'--refresh')):
    commands.execute('storage status',lambda o:commands._syno(o).storage_status())


@command(storage_app,'disks','co syno storage disks --refresh','Show each disk with its model, status, and the health and temperature readings the NAS reports; a missing reading means the NAS did not provide it. Read-only. Needs co syno login --monitoring.')
def storage_disks(refresh:bool=typer.Option(False,'--refresh')):
    commands.execute('storage disks',lambda o:commands._syno(o).storage_disks())


@command(service_app,'list','co syno service list --running','List NAS system services and whether each is running; --running shows only running ones. Read-only. '
         'Connects over SSH with the key and known-hosts file set in co syno login --monitoring.')
def service_list(running:bool=typer.Option(False,'--running'),refresh:bool=typer.Option(False,'--refresh')):
    commands.execute('service list',lambda o:commands._syno(o).service_list(running=running))


@command(syno_app,'ls','co syno ls /home/docs --limit 20 --sort name --order asc',
         'List your shared folders, or the contents of a full NAS folder path. Read-only. Sorted by name, A to Z, unless --sort/--order. '
         'Results can shift between pages if files are added or deleted meanwhile.')
def ls(path:str=typer.Argument('/'),limit:int=typer.Option(20,'--limit','--last','-n',min=1,max=1000),
       cursor:Optional[str]=typer.Option(None,'--cursor'),sort:str=typer.Option('name','--sort'),order:str=typer.Option('asc','--order')):
    def run(o):
        value=commands._syno(o).list_page(path,limit=limit,cursor=cursor,sort=sort,order=order)
        value['_page_command']=['ls',path,'--limit',str(limit),'--sort',sort,'--order',order]
        return value
    commands.execute('ls',run)


@command(syno_app,'info','co syno info /home/docs/report.pdf','Inspect a complete NAS file or directory path. Read-only.')
def info(path:str=typer.Argument(...)):
    commands.execute('info',lambda o:commands._syno(o).info(path))


@command(syno_app,'search','co syno search invoice --in /home/docs --type file',
         'Find files and folders by name under a NAS folder (--in), including subfolders. Read-only on your files. '
         'Waits for the NAS to finish searching, removes the temporary search there, then shows results a page at a time '
         '(next page with --cursor). Use --glob for patterns such as *.pdf.')
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
         'Download a file or folder from the NAS to this computer. Writes local files under --to, which must already exist. '
         'Existing files are kept unless --overwrite; folders need --recursive. To download by row number from ls or search '
         'output, also pass that output\'s listing_id with --listing.')
def download(path:str=typer.Argument(...),dest:str=typer.Option('.','--to'),recursive:bool=typer.Option(False,'--recursive'),
             overwrite:bool=typer.Option(False,'--overwrite'),skip_existing:bool=typer.Option(False,'--skip-existing'),
             dry_run:bool=typer.Option(False,'--dry-run'),listing:Optional[str]=typer.Option(None,'--listing')):
    transfer('download',path,dest,recursive,overwrite,skip_existing,dry_run,listing)


@command(syno_app,'upload','co syno upload ./report.pdf /home/docs/',
         'Upload into an existing NAS directory. Uploads files to the NAS. Directories require --recursive and preserve their base name and empty directories.')
def upload(local:str=typer.Argument(...),directory:str=typer.Argument(...),recursive:bool=typer.Option(False,'--recursive'),
           overwrite:bool=typer.Option(False,'--overwrite'),skip_existing:bool=typer.Option(False,'--skip-existing'),dry_run:bool=typer.Option(False,'--dry-run')):
    transfer('upload',local,directory,recursive,overwrite,skip_existing,dry_run)


@command(syno_app,'mkdir','co syno mkdir /home/docs/archive --parents --dry-run','Create a folder inside an existing shared folder on the NAS. Creates it on the NAS; --parents also creates missing folders '
         'along the path. Cannot create a new top-level shared folder; do that in the Synology web interface (DSM).')
def mkdir(path:str=typer.Argument(...),parents:bool=typer.Option(False,'--parents'),dry_run:bool=typer.Option(False,'--dry-run')):
    commands.execute('mkdir',lambda o:commands._syno(o,dry_run=dry_run).mkdir(path,parents=parents,dry_run=dry_run))


@command(syno_app,'copy','co syno copy /home/docs/report.pdf /home/archive/final.pdf',
         'Copy a file or folder to another path on the same NAS. Creates the copy on the NAS; folders need --recursive and are never '
         'merged into an existing folder. A copy that does not finish in time keeps its progress: re-run the same command '
         'only when the output tells you to continue.')
def copy(source:str=typer.Argument(...),destination:str=typer.Argument(...),recursive:bool=typer.Option(False,'--recursive'),
         overwrite:bool=typer.Option(False,'--overwrite'),dry_run:bool=typer.Option(False,'--dry-run')):
    commands.execute('copy',lambda o:commands._syno(o,dry_run=dry_run).copy(source,destination,recursive=recursive,overwrite=overwrite,dry_run=dry_run))


@command(syno_app,'move','co syno move /home/docs/report.pdf /home/archive/final.pdf',
         'Move or rename a file or folder on the same NAS. Changes paths on the NAS. Cannot move a folder into itself or merge it '
         'into an existing folder. A move that does not finish in time keeps its progress: re-run the same command only when '
         'the output tells you to continue.')
def move(source:str=typer.Argument(...),destination:str=typer.Argument(...),overwrite:bool=typer.Option(False,'--overwrite'),
         dry_run:bool=typer.Option(False,'--dry-run')):
    commands.execute('move',lambda o:commands._syno(o,dry_run=dry_run).move(source,destination,overwrite=overwrite,dry_run=dry_run))


@command(share_app,'create','co syno share create /home/docs/report.pdf --expires 2026-09-30 --yes',
         'Create a link with explicit NAS-local expiry or no-expiry. Creates a link anyone holding it can open, unless --password. Unattended writes require --yes; passwords are limited to 16 characters.')
def share_create(path:str=typer.Argument(...),expires:Optional[str]=typer.Option(None,'--expires'),
                 no_expiry:bool=typer.Option(False,'--no-expiry'),password:bool=typer.Option(False,'--password'),
                 password_stdin:bool=typer.Option(False,'--password-stdin'),yes:bool=typer.Option(False,'--yes'),
                 dry_run:bool=typer.Option(False,'--dry-run'),listing:Optional[str]=typer.Option(None,'--listing')):
    commands.execute('share create',lambda o:commands.handle_share_create(o,path,expires=expires,no_expiry=no_expiry,
        password=password,password_stdin=password_stdin,yes=yes,dry_run=dry_run,listing=listing))


@command(share_app,'list','co syno share list --limit 20',
         'List your sharing links with their ID, file path, expiry, password protection and status on the NAS. Read-only. '
         'The link URLs are hidden unless --show-url, since anyone holding one can use it.')
def share_list(limit:int=typer.Option(20,'--limit','--last','-n',min=1,max=1000),cursor:Optional[str]=typer.Option(None,'--cursor'),
               show_url:bool=typer.Option(False,'--show-url')):
    def run(o):
        result=commands._syno(o).share_list(limit=limit,cursor=cursor,show_url=show_url)
        result['_page_command']=['share','list','--limit',str(limit)]+(['--show-url'] if show_url else [])
        return result
    commands.execute('share list',run)


@command(share_app,'revoke','co syno share revoke LINK_ID --yes','Turn off a sharing link by its ID (from co syno share list) so it stops working. Removes only the link; the shared file stays.')
def share_revoke(identifier:str=typer.Argument(...),yes:bool=typer.Option(False,'--yes'),dry_run:bool=typer.Option(False,'--dry-run')):
    def run(o):
        commands._confirm(o,'Revoke this sharing link?',yes,dry_run)
        return commands._syno(o,dry_run=dry_run).share_revoke(identifier,dry_run=dry_run)
    commands.execute('share revoke',run)


# Aliases use the exact canonical callback and parser options, including the
# required frozen listing context. Main help and emitted tips stay canonical.
command(syno_app,'get','co syno get 1 --listing LISTING_ID --to ./Downloads/',
        'Download from the NAS to this computer; older name for co syno download. Writes local files. A row number from ls '
        'or search output needs that output\'s listing_id with --listing.')(download)
command(syno_app,'put','co syno put ./report.pdf /home/docs/',
        'Uploads files to the NAS; older name for co syno upload, with the same options and safeguards.')(upload)
command(syno_app,'shares','co syno shares --show-url',
        'List your sharing links; older name for co syno share list. Read-only. Link URLs are hidden unless --show-url.')(share_list)
