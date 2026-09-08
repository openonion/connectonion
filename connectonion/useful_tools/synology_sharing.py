"""Explicit link expiry and protection; link revocation never deletes files."""

from datetime import date
import json
import re
from urllib.parse import urlsplit

from .synology_files import nas_path, page_limit
from .synology_transport import command_budget, SynologyError


def link_id(value: str) -> str:
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9_-]{1,256}',value):
        raise SynologyError('Use the exact link ID from co syno share list for this NAS.', 'invalid_reference')
    return value


class SharingMixin:
    @staticmethod
    def _share_dict(item: dict, show_url: bool = False) -> dict:
        result={'id':link_id(item.get('id')), 'path':nas_path(item.get('path'),root=False),
                'expires':None if item.get('date_expired') in {None,0,'0'} else item['date_expired'],
                'protected':item.get('has_password'),'status':item.get('status'),'nas_timezone':None}
        if show_url:
            url = item.get('url')
            parsed = urlsplit(url) if isinstance(url,str) else None
            if not parsed or parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:
                raise SynologyError('DSM did not return a usable sharing URL.', 'invalid_response')
            result['url']=url
        return result

    @command_budget
    def share_create(self, path: str, *, expires: str | None = None, no_expiry: bool = False,
                     password: str | None = None, dry_run: bool = False) -> dict:
        path=nas_path(path,root=False)
        if bool(expires)==no_expiry:
            raise SynologyError('Choose --expires YYYY-MM-DD or explicit --no-expiry.', 'invalid_input')
        if expires:
            try:
                if date.fromisoformat(expires).isoformat()!=expires:
                    raise ValueError
            except ValueError:
                raise SynologyError('Expiry must be a valid YYYY-MM-DD NAS-local date.', 'invalid_input') from None
        if password is not None and (not password or len(password)>16):
            raise SynologyError('Sharing API v3 passwords must contain 1–16 characters; they are never truncated.', 'invalid_input')
        self._api('SYNO.FileStation.Sharing',3)
        self.info(path)
        result={'path':path,'expires':expires,'protected':password is not None,'nas_timezone':None,'dry_run':dry_run}
        if dry_run:
            return result
        data=self._request('SYNO.FileStation.Sharing','create',version=3,path=json.dumps(path),
                           date_expired=json.dumps(expires) if expires else '0',password=password)
        links=data.get('links')
        if not isinstance(links,list) or len(links)!=1 or links[0].get('error') not in {0,None}:
            raise SynologyError('DSM did not confirm sharing-link creation; inspect existing links before retrying.', 'submission_unknown')
        item={**links[0],'date_expired':expires or '0','has_password':password is not None}
        if item.get('path')!=path:
            raise SynologyError('DSM returned a different sharing path; inspect links before retrying.', 'submission_unknown')
        return {**self._share_dict(item,True),'dry_run':False}

    @command_budget
    def share_list(self, *, limit: int = 20, cursor: str | None = None, show_url: bool = False) -> dict:
        page_limit(limit)
        params={'operation':'share list','limit':limit,'show_url':show_url}
        offset=self.state.read('cursor',cursor,params)['offset'] if cursor else 0
        data=self._request('SYNO.FileStation.Sharing','list',version=3,offset=offset,limit=limit,
                           sort_by='id',sort_direction='asc',force_clean=False)
        links,total=data.get('links'),data.get('total')
        if not isinstance(links,list) or len(links)>limit or not isinstance(total,int) or total<0:
            raise SynologyError('DSM returned invalid sharing-list metadata.', 'invalid_response')
        if not links and offset<total:
            raise SynologyError('Sharing list changed; list it again.', 'stale_cursor')
        next_cursor=self.state.save('cursor',{'params':params,'offset':offset+len(links)}) if offset+len(links)<total else None
        return {'items':[self._share_dict(item,show_url) for item in links],'next_cursor':next_cursor,
                'snapshot':False,'status_source':'DSM cached sharing status','complete':True}

    @command_budget
    def share_revoke(self, identifier: str, *, dry_run: bool = False) -> dict:
        identifier=link_id(identifier)
        item=self._request('SYNO.FileStation.Sharing','getinfo',version=3,id=json.dumps(identifier))
        if item.get('id')!=identifier:
            raise SynologyError('The selected NAS/account did not return that sharing link.', 'not_found')
        result={'id':identifier,'path':nas_path(item.get('path'),root=False),'dry_run':dry_run}
        if not dry_run:
            response=self._request('SYNO.FileStation.Sharing','delete',version=3,id=[identifier])
            if response.get('errors'):
                raise SynologyError('DSM did not confirm link revocation.', 'revoke_failed')
            result['revoked']=identifier
        return result

    @command_budget
    def list_sharing_links(self, last: int = 20, *, show_url: bool = False) -> list:
        return self.share_list(limit=last,show_url=show_url)['items']

    @command_budget
    def share(self, path: str, *, expires: str | None = None, no_expiry: bool = False) -> str:
        """Create a link with a required explicit expiry choice."""
        return self.share_create(path,expires=expires,no_expiry=no_expiry)['url']
