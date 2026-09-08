"""Complete NAS paths, scoped browsing, completed searches and directory plans."""

from pathlib import PurePosixPath
import time

from .synology_transport import command_budget, SynologyError

ADDITIONAL = ['size','time','real_path','type','mount_point_type']
MAX_SEARCH = 10000


def nas_path(value: str, *, root: bool = True) -> str:
    if (not isinstance(value, str) or not value.startswith('/') or '\\' in value
            or any(ord(c)<32 for c in value)
            or (value != '/' and any(part in {'','.','..'} for part in value.rstrip('/').split('/')[1:]))):
        raise SynologyError('Use a complete NAS path without empty, dot or parent segments.', 'invalid_path')
    result = value.rstrip('/') or '/'
    if result == '/' and not root:
        raise SynologyError('Choose a path inside an accessible shared folder.', 'invalid_path')
    return result


def within(path: str, boundary: str) -> bool:
    return path == boundary or path.startswith(boundary.rstrip('/') + '/')


def page_limit(limit: int) -> None:
    if not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise SynologyError('Limit must be between 1 and 1000.', 'invalid_input')


class FileMixin:
    @staticmethod
    def _file_dict(item: dict) -> dict:
        if not isinstance(item, dict) or not isinstance(item.get('isdir'), bool):
            raise SynologyError('DSM returned an invalid file entry.', 'invalid_response')
        path = nas_path(item.get('path'), root=False)
        extra = item.get('additional', {})
        if not isinstance(extra, dict) or not isinstance(extra.get('time', {}), dict):
            raise SynologyError('DSM returned invalid file metadata.', 'invalid_response')
        size = extra.get('size')
        if size is not None and (not isinstance(size, int) or size < 0):
            raise SynologyError('DSM returned an invalid file size.', 'invalid_response')
        return {'path':path, 'name':PurePosixPath(path).name, 'type':'dir' if item['isdir'] else 'file',
                'size':None if item['isdir'] else size, 'modified':extra.get('time', {}).get('mtime'),
                'real_path':extra.get('real_path'), 'mount_point_type':extra.get('mount_point_type')}

    def _list_raw(self, path: str, limit: int, offset: int = 0,
                  sort: str = 'name', order: str = 'asc') -> tuple[list, int]:
        params = {'limit':limit, 'offset':offset, 'sort_by':{'modified':'mtime'}.get(sort, sort),
                  'sort_direction':order, 'additional':ADDITIONAL}
        if path != '/':
            params['folder_path'] = path
        if path == '/':
            params['additional'] = ['time','real_path','mount_point_type']
        data = self._request('SYNO.FileStation.List', 'list_share' if path == '/' else 'list', **params)
        entries = data.get('shares' if path == '/' else 'files')
        total = data.get('total')
        if not isinstance(entries, list) or len(entries)>limit or not isinstance(total, int) or total<0:
            raise SynologyError('DSM returned incomplete listing metadata.', 'invalid_response')
        items = [self._file_dict(item) for item in entries]
        if any(str(PurePosixPath(item['path']).parent) != path for item in items):
            raise SynologyError('DSM listing escaped the requested folder.', 'path_escape')
        return items, total

    @command_budget
    def list_page(self, path: str = '/', *, limit: int = 20, cursor: str | None = None,
                  sort: str = 'name', order: str = 'asc') -> dict:
        path = nas_path(path)
        page_limit(limit)
        if sort not in {'name','modified','size'} or order not in {'asc','desc'}:
            raise SynologyError('Use sort name/modified/size and order asc/desc.', 'invalid_input')
        params = {'operation':'ls','path':path,'limit':limit,'sort':sort,'order':order}
        offset = self.state.read('cursor',cursor,params)['offset'] if cursor else 0
        if not isinstance(offset, int) or offset<0:
            raise SynologyError('Invalid listing offset; repeat the listing.', 'stale_cursor')
        items,total = self._list_raw(path,limit,offset,sort,order)
        if not items and offset < total:
            raise SynologyError('Directory changed while paging; repeat the listing.', 'stale_cursor')
        next_cursor = self.state.save('cursor', {'params':params,'offset':offset+len(items)}) if offset+len(items)<total else None
        return {'items':items,'next_cursor':next_cursor,'listing_id':self.state.listing(items),
                'snapshot':False,'complete':True,'total_reported':total}

    @command_budget
    def list_files(self, path: str | None = None, last: int = 20) -> list:
        """List one live page in name order; use list_page for continuation."""
        page_limit(last)
        return self._list_raw(nas_path(path or '/'), last)[0]

    @command_budget
    def info(self, path: str) -> dict:
        path = nas_path(path, root=False)
        data = self._request('SYNO.FileStation.List','getinfo',path=[path],additional=ADDITIONAL)
        entries = data.get('files')
        if not isinstance(entries, list) or len(entries)!=1:
            raise SynologyError('DSM did not return the requested path.', 'not_found')
        if entries[0].get('code'):
            code = entries[0]['code']
            raise SynologyError('DSM could not inspect the requested path.', 'not_found' if code == 408 else 'provider_error')
        result = self._file_dict(entries[0])
        if result['path'] != path:
            raise SynologyError('DSM returned a different path from the requested one.', 'path_escape')
        return result

    def _maybe_info(self, path: str) -> dict | None:
        try:
            return self.info(path)
        except SynologyError as error:
            if error.code == 'not_found':
                return None
            raise

    def _directory(self, path: str) -> dict:
        item = self.info(path)
        if item['type'] != 'dir':
            raise SynologyError('The required directory is a file.', 'type_conflict')
        return item

    def _search_snapshot(self, query: str, path: str, glob: bool, kind: str,
                         poll_interval: float, poll_attempts: int) -> list:
        pattern = query if glob else f'*{query}*'
        started = self._request('SYNO.FileStation.Search','start',folder_path=[path],pattern=pattern,
                                recursive=True,filetype={'directory':'dir','all':'all','file':'file'}[kind])
        task = started.get('taskid')
        if not isinstance(task, str) or not task:
            raise SynologyError('DSM did not identify its search task.', 'invalid_response')
        original_error = None
        try:
            for _ in range(poll_attempts):
                if self._remaining() <= 2:
                    raise SynologyError('Search exceeded its waiting budget; cleanup was requested.', 'search_timeout')
                found = self._request('SYNO.FileStation.Search','list',taskid=task,limit=1000,
                                      additional=ADDITIONAL,sort_by='name',sort_direction='asc')
                if found.get('finished') is True:
                    break
                time.sleep(min(poll_interval, self._remaining()))
            else:
                raise SynologyError('Search did not finish within its polling limit.', 'search_timeout')
            total, entries = found.get('total'), found.get('files')
            if not isinstance(total, int) or not isinstance(entries,list) or not 0 <= total <= MAX_SEARCH:
                raise SynologyError('Search exceeded the 10000-result snapshot limit; narrow --in.', 'response_too_large')
            while len(entries) < total:
                page = self._request('SYNO.FileStation.Search','list',taskid=task,limit=1000,offset=len(entries),
                                     additional=ADDITIONAL,sort_by='name',sort_direction='asc')
                if page.get('finished') is not True or page.get('total') != total or not page.get('files'):
                    raise SynologyError('The completed search snapshot changed during retrieval.', 'incomplete_search')
                entries.extend(page['files'])
            if len(entries) != total:
                raise SynologyError('DSM search result count did not match its snapshot.', 'incomplete_search')
            items = [self._file_dict(item) for item in entries]
            if any(not within(item['path'],path) for item in items):
                raise SynologyError('Search returned a path outside its selected scope.', 'path_escape')
            return items
        except BaseException as error:
            original_error = error
            raise
        finally:
            try:
                self._request('SYNO.FileStation.Search','clean',taskid=task)
            except Exception as cleanup:
                if original_error is None:
                    raise SynologyError('Search completed but server task cleanup was not confirmed.', 'cleanup_unconfirmed') from None
                original_error.cleanup_error = getattr(cleanup, 'code', 'cleanup_unconfirmed')

    @command_budget
    def search_page(self, query: str, path: str, *, glob: bool = False, kind: str = 'all',
                    limit: int = 20, cursor: str | None = None, poll_interval: float = .3,
                    poll_attempts: int = 1000) -> dict:
        path = nas_path(path,root=False)
        page_limit(limit)
        if not query.strip() or kind not in {'file','directory','all'}:
            raise SynologyError('Provide a nonempty name and type file/directory/all.', 'invalid_input')
        if not glob and any(c in query for c in '*?[],'):
            raise SynologyError('Use --glob to explicitly search with patterns.', 'invalid_input')
        params = {'operation':'search','query':query,'path':path,'glob':glob,'kind':kind,'limit':limit}
        snapshot = self.state.read('cursor',cursor,params) if cursor else {
            'items':self._search_snapshot(query,path,glob,kind,poll_interval,poll_attempts),'offset':0}
        offset, all_items = snapshot['offset'], snapshot['items']
        items = all_items[offset:offset+limit]
        next_cursor = self.state.save('cursor',{'params':params,'offset':offset+limit,'items':all_items}) if offset+limit<len(all_items) else None
        return {'items':items,'next_cursor':next_cursor,'listing_id':self.state.listing(items),
                'snapshot':True,'complete':True,'total':len(all_items)}

    @command_budget
    def search_files(self, query: str, path: str, last: int = 20,
                     poll_attempts: int = 1000, poll_interval: float = .3) -> list:
        return self.search_page(query,path,limit=last,poll_attempts=poll_attempts,poll_interval=poll_interval)['items']

    @command_budget
    def mkdir(self, path: str, *, parents: bool = False, dry_run: bool = False) -> dict:
        path = nas_path(path,root=False)
        parts = PurePosixPath(path).parts
        if len(parts)<3:
            raise SynologyError('mkdir cannot create DSM shared roots.', 'invalid_path')
        create = []
        for index in range(2,len(parts)+1):
            candidate = str(PurePosixPath(*parts[:index]))
            item = self._maybe_info(candidate)
            if item:
                if item['type'] != 'dir':
                    raise SynologyError('Directory creation encountered a file.', 'type_conflict')
                if candidate == path and not parents:
                    raise SynologyError('The destination already exists.', 'conflict')
            elif index == 2 or (candidate != path and not parents):
                raise SynologyError('Destination parent/shared folder does not exist.', 'not_found')
            else:
                create.append(candidate)
        completed = []
        if not dry_run:
            for candidate in create:
                self._request('SYNO.FileStation.CreateFolder','create',folder_path=[str(PurePosixPath(candidate).parent)],
                              name=[PurePosixPath(candidate).name],force_parent=False)
                completed.append(candidate)
        return {'path':path,'dry_run':dry_run,'create':create,'completed':completed}
