"""Synology NAS client with isolated profiles and verified, bounded transports.

Explicit SDK credentials are ephemeral. The CLI publishes a profile only after
File Station access succeeds. Legacy env-only connections require verified login.
"""

import hashlib
import json

from ..env_file import env_lock
from .synology_profiles import ProfileStore, ProfileError
from .synology_transport import SynologyTransport, SynologyError
from .synology_inspections import InspectionMixin
from .synology_files import FileMixin
from .synology_transfers import TransferMixin
from .synology_sharing import SharingMixin
from .synology_operations import OperationMixin
from .synology_state import SynologyState
from .synology_discovery import resolve_quickconnect, pick_reachable


class Synology(InspectionMixin, TransferMixin, SharingMixin, OperationMixin, FileMixin, SynologyTransport):
    """Inspect and manage ordinary files on one explicitly selected NAS/account."""

    def __init__(self, url: str | None = None, account: str | None = None,
                 password: str | None = None, *, nas: str | None = None,
                 sid: str = '', ca_cert: str | None = None, timeout: float = 60,
                 store: ProfileStore | None = None, dry_run: bool = False,
                 otp_callback=None):
        self.store=store or ProfileStore()
        self.dry_run=dry_run
        self._saved_profile=url is None
        if url is not None and nas is not None:
            raise SynologyError('Choose explicit connection settings or a saved NAS profile.', 'invalid_input')
        if url is None:
            self.profile=self.store.selected(nas)
            self.secret=self.store.credentials(self.profile)
            url,account=self.profile['url'],self.profile['account']
            password,sid=self.secret.get('password',''),self.secret.get('sid','')
            ca_cert=self.profile.get('ca_cert')
            identity=self.profile['id']
        else:
            if not account:
                raise SynologyError('An explicit URL requires its explicit DSM account.', 'invalid_input')
            identity=hashlib.sha256(json.dumps([url,account]).encode()).hexdigest()
            self.profile={'url':url,'account':account,'name':None,'id':identity}
            self.secret={'password':password or '', 'sid':sid}
        self.state=SynologyState(identity)
        super().__init__(url,account,password or '',sid=sid,ca_cert=ca_cert,timeout=timeout,
                         persist=not dry_run,otp_callback=otp_callback)

    def _login(self) -> None:
        if self.dry_run:
            raise SynologyError('Dry-run requires a usable saved session; run co syno login first.', 'auth_required')
        if not self._saved_profile:
            return super()._login()
        lock=self.store.directory/'sessions'/self.profile['id']
        with env_lock(lock,timeout=min(15,self._remaining())):
            current=self.store.selected(self.profile['name'])
            if (current['id']!=self.profile['id'] or
                    current.get('credential_ref')!=self.profile.get('credential_ref')):
                raise SynologyError('NAS profile changed while authenticating; repeat the command.', 'profile_changed')
            fresh=self.store.credentials(current)
            if fresh.get('sid') and fresh['sid']!=self.sid:
                self.sid=fresh['sid']
                return
            self.password=fresh.get('password','')
            super()._login()
            self.store.update_auth(current,{'sid':self.sid})

    def logout(self) -> dict:
        if not self._saved_profile:
            raise SynologyError('Logout requires a saved NAS profile.', 'invalid_input')
        confirmed=False
        remote_error=None
        try:
            self._logout_remote()
            confirmed=True
        except SynologyError as error:
            remote_error={'code':error.code,'message':'Remote invalidation was not confirmed.'}
        finally:
            self.store.clear_auth(self.profile)
        self.secret={}; self.sid=''; self.password=''
        return {'profile':self.profile['name'],'local_auth_cleared':True,
                'remote_invalidation':'confirmed' if confirmed else 'unconfirmed','remote_error':remote_error}
