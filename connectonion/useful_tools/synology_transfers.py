"""Explicit recursive transfers with guarded paths and atomic local placement."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile

import httpx

from .synology_files import nas_path, within
from .synology_transport import command_budget, SynologyError, STALE_SESSION

MAX_TREE = 10000


def checked_local(value: str | Path, *, exists: bool = True) -> Path:
    path = Path(os.path.abspath(Path(value).expanduser()))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current/part
        if current.is_symlink():
            raise SynologyError('Local symlinks are not followed by NAS transfers.', 'path_escape')
        if current.exists() and not (current.is_file() or current.is_dir()):
            raise SynologyError('Transfers require ordinary local files or directories.', 'invalid_path')
    if exists and not path.exists():
        raise SynologyError('The local path does not exist.', 'not_found')
    return path


def local_target(destination: str, name: str) -> Path:
    target = checked_local(destination, exists=False)
    if str(destination).endswith(('/',os.sep)) and not target.is_dir():
        raise SynologyError('A trailing-slash destination must be an existing directory.', 'not_found')
    if target.is_dir():
        target = target/name
    if not target.parent.is_dir():
        raise SynologyError('The destination parent directory must exist.', 'not_found')
    return checked_local(target,exists=False)


@contextmanager
def local_parent(path: Path):
    """Pin the ancestor chain with no-follow directory descriptors on POSIX."""
    checked_local(path, exists=False)
    if os.name == 'nt':
        yield None
        return
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parent.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def _local_conflict(target: Path, kind: str, overwrite: bool, skip: bool) -> str:
    checked_local(target, exists=False)
    if not target.exists():
        return 'create'
    if target.is_dir() != (kind == 'dir'):
        raise SynologyError('The local destination has a conflicting file/directory type.', 'type_conflict')
    if not overwrite and not skip:
        raise SynologyError('Local destination exists; choose --overwrite or --skip-existing.', 'conflict')
    return 'skip' if skip and kind == 'file' else ('merge' if kind == 'dir' else 'overwrite')


class TransferMixin:
    def _remote_boundary(self, path: str) -> tuple[str, str]:
        share = '/' + PurePosixPath(path).parts[1]
        info = self._directory(share)
        real = info.get('real_path')
        if not isinstance(real, str) or not real.startswith('/'):
            raise SynologyError('The NAS did not provide resolved paths needed for a safe transfer.', 'unsupported_source')
        return share, real.rstrip('/')

    @staticmethod
    def _check_remote(item: dict, boundary: tuple[str,str]) -> None:
        share, real = boundary
        expected = real + item['path'][len(share):]
        if (not within(item['path'],share) or item.get('real_path') != expected
                or item.get('mount_point_type') not in {None,'','local'}):
            raise SynologyError('A remote symlink, mount or resolved path leaves the selected ordinary tree.', 'path_escape')

    def _remote_tree(self, path: str, recursive: bool) -> list:
        root = self.info(path)
        boundary = self._remote_boundary(path)
        self._check_remote(root,boundary)
        if root['type']=='dir' and not recursive:
            raise SynologyError('Directory transfer requires --recursive.', 'recursive_required')
        items, seen = [root], {path}
        for item in items:
            self._remaining()
            if item['type'] != 'dir':
                continue
            offset = 0
            while True:
                page,total = self._list_raw(item['path'],1000,offset)
                for child in page:
                    self._check_remote(child,boundary)
                    if child['path'] in seen or len(items)>=MAX_TREE:
                        raise SynologyError('Remote tree changed or exceeded 10000 entries; narrow the transfer.', 'incomplete_tree')
                    seen.add(child['path']); items.append(child)
                offset += len(page)
                if offset >= total:
                    break
                if not page:
                    raise SynologyError('Remote tree changed while preparing the transfer.', 'incomplete_tree')
        return items

    def _download_file(self, item: dict, target: Path, overwrite: bool) -> dict:
        for attempt in range(2):
            try:
                return self._download_attempt(item,target,overwrite)
            except SynologyError as error:
                if attempt == 0 and error.code == 'stale_session':
                    self._login()
                    continue
                raise

    def _download_attempt(self, item: dict, target: Path, overwrite: bool) -> dict:
        path, version = self._api('SYNO.FileStation.Download',2)
        if not self.sid:
            self._login()
        # A concurrent remote tree edit cannot be made race-free by File
        # Station. Recheck its resolved path immediately before each transfer.
        current = self.info(item['path'])
        if any(current.get(key) != item.get(key) for key in ('real_path','type','size','modified')):
            raise SynologyError('Remote file changed after transfer preflight.', 'source_changed')
        fields = {'api':'SYNO.FileStation.Download','version':version,'method':'download',
                  'path':json.dumps([item['path']]),'mode':'download','_sid':self.sid}
        with local_parent(target) as parent_fd:
            temp_name = '.co-download-' + os.urandom(16).hex()
            temporary = target.parent/temp_name
            fd = os.open(temp_name if parent_fd is not None else temporary,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent_fd)
            digest, count = hashlib.sha256(), 0
            try:
                with os.fdopen(fd,'wb') as stream, self._client() as client:
                    with client.stream('POST',f'/webapi/{path}',data=fields,headers={'Accept-Encoding':'identity'}) as reply:
                        if not 200 <= reply.status_code < 300:
                            raise SynologyError('DSM refused the download or returned a redirect.', 'download_failed')
                        if reply.headers.get('content-encoding','identity') != 'identity':
                            raise SynologyError('Unexpected transfer content encoding.', 'invalid_response')
                        if ('application/json' in reply.headers.get('content-type','')
                                and 'attachment' not in reply.headers.get('content-disposition','').lower()):
                            # Do not write an error document into the destination.
                            raw=bytearray()
                            for chunk in reply.iter_bytes(chunk_size=65536):
                                self._remaining()
                                raw.extend(chunk)
                                if len(raw)>1024*1024:
                                    raise SynologyError('DSM download error exceeded its response limit.', 'response_too_large')
                            try:
                                body=json.loads(raw)
                                code=body.get('error',{}).get('code') if isinstance(body,dict) else None
                            except (ValueError,AttributeError):
                                code=None
                            if code in STALE_SESSION:
                                raise SynologyError('DSM explicitly rejected the expired download session.', 'stale_session')
                            raise SynologyError('DSM returned JSON instead of an attachment; inspect the session and path.', 'download_rejected')
                        expected = reply.headers.get('content-length')
                        for chunk in reply.iter_bytes(chunk_size=65536):
                            self._remaining()
                            count += len(chunk)
                            if isinstance(item.get('size'),int) and count > item['size']:
                                raise SynologyError('Downloaded bytes exceed the inspected file length.', 'length_mismatch')
                            digest.update(chunk); stream.write(chunk)
                        if ((expected is not None and (not expected.isdigit() or int(expected)!=count))
                                or (item.get('size') is not None and item['size'] != count)):
                            raise SynologyError('Downloaded bytes do not match the available length evidence.', 'length_mismatch')
                    stream.flush(); os.fsync(stream.fileno())
                checked_local(target, exists=False)
                if overwrite:
                    os.replace(temp_name if parent_fd is not None else temporary,
                               target.name if parent_fd is not None else target,
                               src_dir_fd=parent_fd,dst_dir_fd=parent_fd)
                else:
                    os.link(temp_name if parent_fd is not None else temporary,
                            target.name if parent_fd is not None else target,
                            src_dir_fd=parent_fd,dst_dir_fd=parent_fd,follow_symlinks=False)
                return {'path':str(target),'bytes':count,'sha256':digest.hexdigest(),'hash_source':'downloaded_bytes'}
            except FileExistsError:
                raise SynologyError('Local destination appeared during transfer; original bytes were preserved.', 'conflict') from None
            except httpx.TransportError:
                raise SynologyError('The download connection was interrupted; original bytes were preserved.', 'network_error') from None
            finally:
                if parent_fd is None:
                    temporary.unlink(missing_ok=True)
                else:
                    try:
                        os.unlink(temp_name,dir_fd=parent_fd)
                    except FileNotFoundError:
                        # replace consumes the temporary name on success.
                        if not overwrite:
                            raise

    @command_budget
    def download(self, path: str, dest: str = '.', *, recursive: bool = False,
                 overwrite: bool = False, skip_existing: bool = False, dry_run: bool = False) -> dict:
        if overwrite and skip_existing:
            raise SynologyError('Choose either overwrite or skip-existing.', 'invalid_input')
        path = nas_path(path,root=False)
        items = self._remote_tree(path,recursive)
        target = local_target(dest,PurePosixPath(path).name)
        plan=[]
        for item in items:
            local = target / item['path'][len(path)+1:] if item['path']!=path else target
            plan.append({'source':item['path'],'target':str(local),'type':item['type'],
                         'action':_local_conflict(local,item['type'],overwrite,skip_existing)})
        return self._run_transfer(plan,items,dry_run,upload=False,overwrite=overwrite)

    def _upload_file(self, local: Path, remote: str, overwrite: bool) -> dict:
        path,version = self._api('SYNO.FileStation.Upload',2)
        if not self.sid:
            self._login()
        fields = {'api':'SYNO.FileStation.Upload','version':str(version),'method':'upload',
                  'path':str(PurePosixPath(remote).parent),'create_parents':'false',
                  'overwrite':'true' if overwrite else 'false'}
        for attempt in range(2):
            checked_local(local)
            with local_parent(local) as parent_fd:
                fd = os.open(local.name if parent_fd is not None else local,
                             os.O_RDONLY | getattr(os,'O_NOFOLLOW',0),dir_fd=parent_fd)
                with os.fdopen(fd,'rb') as stream:
                    before = os.fstat(stream.fileno())
                    if not stat.S_ISREG(before.st_mode):
                        raise SynologyError('Upload requires an ordinary file.', 'invalid_path')
                    response = self._json_request('POST',f'/webapi/{path}',params={'_sid':self.sid},
                                                   data=fields,files={'file':(local.name,stream)},mutation=True)
                    after = os.fstat(stream.fileno())
                    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                        raise SynologyError('Local file changed during upload; inspect the remote result.', 'submission_unknown')
            if response['success']:
                return {'path':remote,'bytes':before.st_size,'evidence':'DSM upload acknowledgement; no server hash supplied'}
            code = response.get('error',{}).get('code')
            if attempt==0 and code in STALE_SESSION:
                self._login()
                continue
            raise SynologyError('DSM rejected the upload.', 'conflict' if code==1805 else 'upload_rejected')

    @command_budget
    def upload(self, local_path: str, path: str, overwrite: bool = False, *, recursive: bool = False,
               skip_existing: bool = False, dry_run: bool = False) -> dict:
        if overwrite and skip_existing:
            raise SynologyError('Choose either overwrite or skip-existing.', 'invalid_input')
        local = checked_local(local_path)
        path = nas_path(path,root=False)
        parent = self._directory(path)
        boundary = self._remote_boundary(path)
        self._check_remote(parent,boundary)
        if local.is_dir() and not recursive:
            raise SynologyError('Directory transfer requires --recursive.', 'recursive_required')
        sources=[local]
        if local.is_dir():
            for base,dirs,files in os.walk(local,followlinks=False):
                self._remaining()
                for name in sorted(dirs+files):
                    sources.append(checked_local(Path(base)/name))
                    if len(sources)>MAX_TREE:
                        raise SynologyError('Local tree exceeded 10000 entries; narrow the transfer.', 'response_too_large')
        plan=[]
        for source in sources:
            remote = str(PurePosixPath(path)/source.relative_to(local.parent).as_posix())
            kind = 'dir' if source.is_dir() else 'file'
            existing = self._maybe_info(remote)
            action = 'create'
            if existing:
                self._check_remote(existing,boundary)
                if existing['type']!=kind:
                    raise SynologyError('Remote destination has a conflicting type.', 'type_conflict')
                if not overwrite and not skip_existing:
                    raise SynologyError('Remote destination exists; choose --overwrite or --skip-existing.', 'conflict')
                action = 'merge' if kind=='dir' else ('skip' if skip_existing else 'overwrite')
            plan.append({'source':str(source),'target':remote,'type':kind,'action':action})
        return self._run_transfer(plan,[],dry_run,upload=True,overwrite=overwrite)

    def _run_transfer(self, plan: list, items: list, dry_run: bool, *, upload: bool, overwrite: bool) -> dict:
        result={'dry_run':dry_run,'plan':plan,'completed':[],'skipped':[],'failed':[],'status':'complete'}
        if dry_run:
            return result
        for index,step in enumerate(plan):
            try:
                self._remaining()
                if step['action'] in {'skip','merge'}:
                    result['skipped'].append({'path':step['target'],'reason':step['action']})
                    continue
                if step['type']=='dir':
                    if upload:
                        self.mkdir(step['target'])
                    else:
                        target=Path(step['target'])
                        with local_parent(target) as parent_fd:
                            os.mkdir(target.name if parent_fd is not None else target,mode=0o700,dir_fd=parent_fd)
                    result['completed'].append({'path':step['target'],'type':'dir'})
                else:
                    value = (self._upload_file(Path(step['source']),step['target'],overwrite) if upload else
                             self._download_file(items[index],Path(step['target']),overwrite))
                    result['completed'].append(value)
            except (SynologyError,OSError) as error:
                result['status']='partial'
                result['failed'].append({'path':step['target'],'code':getattr(error,'code','local_io_error'),
                                         'message':str(error) if isinstance(error,SynologyError) else 'Local file operation failed.'})
                result['not_started'] = [pending['target'] for pending in plan[index+1:]]
                break
        return result
