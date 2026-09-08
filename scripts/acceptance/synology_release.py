"""Opt-in installed-CLI NAS acceptance using only an owned disposable directory.

Run with the installed candidate's Python. Existing files and login are retained.
SNMP/SSH absence is recorded as unavailable, never promoted to a health pass.
"""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import uuid


class Journey:
    def __init__(self, nas, parent, local):
        self.nas, self.local = nas, local
        self.root = parent.rstrip('/') + '/.co-acceptance-' + uuid.uuid4().hex
        self.created = self.sharing_attempted = False
        self.report = {'passed':False, 'checks':[], 'cleanup':[], 'unverified':[]}

    def cli(self, name, *args, error=None, partial=False, stdin=None):
        command = [sys.executable, '-m', 'connectonion.cli.main', 'syno', '--nas', self.nas,
                   '--timeout', '90', *args, '--json']
        child = subprocess.run(command, cwd=self.local, capture_output=True, text=True,
                               input=stdin, timeout=120,
                               env={k:v for k,v in os.environ.items() if k != 'PYTHONPATH'})
        try:
            result = json.loads(child.stdout)
        except ValueError:
            raise AssertionError(name + ': expected one JSON result') from None
        assert result.get('schema_version') == 1, name
        assert result.get('next_command', '').startswith('co syno'), name
        actual = (result.get('error') or {}).get('code')
        if error:
            passed = child.returncode in {1,2} and actual == error
        elif partial:
            passed = child.returncode in {0,1} and result.get('error') is None
        else:
            passed = child.returncode == 0 and result.get('ok') is True
        self.report['checks'].append({'name':name, 'passed':passed, 'exit':child.returncode,
                                      'error_code':actual})
        print(name + ': ' + ('PASS' if passed else 'FAIL'), file=sys.stderr, flush=True)
        assert passed, name + ': ' + str(actual)
        return result.get('data') or {}

    def inspect(self):
        profiles = self.cli('profile inventory', 'nas', 'list')
        assert any(p['name'] == self.nas for p in profiles['items'])
        status = self.cli('aggregate status', 'status', '--refresh', partial=True)
        assert status['checks']['connectivity']['data']['authenticated'] is True
        for name, args in [('network', ('network','status')), ('storage', ('storage','status')),
                           ('disks', ('storage','disks')), ('services', ('service','list'))]:
            check = status['checks'][name]
            if check.get('error',{}).get('code') == 'source_not_configured':
                self.cli(name + ' unavailable', *args, error='source_not_configured')
                self.report['unverified'].append(name + ': optional source not configured')
            else:
                self.cli(name + ' inspection', *args, partial=True)
        self.cli('share roots', 'ls')
        self.report['unverified'].append('logout: retained owner login; covered by isolated regressions')

    def transfer(self):
        root, local = self.root, self.local
        tree = local/'tree'; (tree/'nested').mkdir(parents=True)
        (tree/'empty.bin').write_bytes(b'')
        (tree/'hello world.txt').write_bytes(b'synthetic NAS fixture\n')
        (tree/'nested'/'unicode-\u4e2d.bin').write_bytes(bytes(range(256))*3)
        self.cli('mkdir', 'mkdir', root); self.created = True
        self.cli('mkdir parents', 'mkdir', root+'/deep/child', '--parents')
        self.cli('mkdir dry run', 'mkdir', root+'/dry-dir', '--dry-run')
        self.cli('dry directory absent', 'info', root+'/dry-dir', error='not_found')
        self.cli('upload recursive required', 'upload', str(tree), root, error='recursive_required')
        self.cli('upload dry run', 'upload', str(tree), root, '--recursive', '--dry-run')
        self.cli('dry upload absent', 'info', root+'/tree', error='not_found')
        self.cli('recursive upload', 'upload', str(tree), root, '--recursive')
        self.cli('upload conflict', 'upload', str(tree/'hello world.txt'), root+'/tree', error='conflict')
        skip = self.cli('upload skip existing', 'upload', str(tree/'hello world.txt'), root+'/tree', '--skip-existing')
        assert skip['skipped'] and not skip['completed']
        (tree/'hello world.txt').write_bytes(b'updated synthetic fixture\n')
        self.cli('upload overwrite', 'upload', str(tree/'hello world.txt'), root+'/tree', '--overwrite')
        target = local/'download'; target.mkdir()
        self.cli('download recursive required', 'download', root+'/tree', '--to', str(target), error='recursive_required')
        self.cli('download dry run', 'download', root+'/tree', '--to', str(target), '--recursive', '--dry-run')
        assert not list(target.iterdir())
        self.cli('recursive download', 'download', root+'/tree', '--to', str(target), '--recursive')
        assert file_bytes(tree) == file_bytes(target/'tree'), 'recursive bytes mismatch'
        self.cli('download conflict', 'download', root+'/tree/hello world.txt', '--to', str(target/'tree'), error='conflict')
        (target/'tree/hello world.txt').write_bytes(b'preserve local fixture')
        self.cli('download skip existing', 'download', root+'/tree/hello world.txt', '--to', str(target/'tree'), '--skip-existing')
        assert (target/'tree/hello world.txt').read_bytes() == b'preserve local fixture'
        self.cli('download overwrite', 'download', root+'/tree/hello world.txt', '--to', str(target/'tree'), '--overwrite')
        assert file_bytes(tree) == file_bytes(target/'tree')
        self.report['checks'].append({'name':'all recursive file bytes incl empty/Unicode', 'passed':True})

    def browse(self):
        path = self.root+'/tree'
        first = self.cli('listing page 1', 'ls', path, '--limit','1')
        assert first['next_cursor']
        items, cursor = list(first['items']), first['next_cursor']
        self.cli('cursor parameter mismatch', 'ls', path, '--limit','2','--cursor',cursor,error='stale_cursor')
        while cursor:
            page = self.cli('listing next page', 'ls',path,'--limit','1','--cursor',cursor)
            items += page['items']; cursor = page['next_cursor']
        assert len({i['path'] for i in items}) == len(items) == 3
        assert {i['name'] for i in items} == {'nested','empty.bin','hello world.txt'}, 'listing omitted or added a fixture'
        whole = self.cli('listing pagination preserves provider order','ls',path,'--limit','1000')
        assert items == whole['items'], 'paged listing differs from the complete fixture listing'
        for kind in ('dir','file'):
            names = [i['name'] for i in items if i['type'] == kind]
            assert names == sorted(names), 'fixture names are not ascending within '+kind
        self.report['listing_order'] = [i['name'] for i in items]
        info = self.cli('empty file info', 'info',path+'/empty.bin'); assert info['size'] == 0
        found = self.cli('plain search','search','hello','--in',path,'--type','file')
        assert [i['path'] for i in found['items']] == [path+'/hello world.txt']
        found = self.cli('glob search','search','*.bin','--glob','--in',path,'--type','file','--limit','1')
        assert found['items'] and found['next_cursor']
        self.cli('search next page','search','*.bin','--glob','--in',path,'--type','file','--limit','1','--cursor',found['next_cursor'])
        self.cli('invalid path','info',self.root+'/../outside',error='invalid_path')
        self.cli('invalid page size','ls',path,'--limit','0',error='usage_error')

    def operation(self, name, *args):
        result = self.cli(name,*args,partial=True)
        for _ in range(8):
            if result.get('status') == 'complete':
                self.cli(name+' durable receipt','status','--operation',result['operation_id'],partial=True)
                return
            if result.get('status') == 'operation_pending':
                result = self.cli(name+' poll','status','--operation',result['operation_id'],'--wait',partial=True)
            elif result.get('status') == 'continuation_required':
                result = self.cli(name+' resume',*args,partial=True)
            else:
                raise AssertionError(name+': '+str(result.get('status')))
        raise AssertionError(name+': task did not complete within bounded polls')

    def operations(self):
        root = self.root; source = root+'/tree/hello world.txt'
        self.cli('copy dry run','copy',source,root+'/copy.txt','--dry-run')
        self.cli('dry copy absent','info',root+'/copy.txt',error='not_found')
        self.operation('copy renamed cross folder','copy',source,root+'/copy.txt')
        self.cli('copy collision','copy',source,root+'/copy.txt',error='conflict')
        self.operation('copy explicit overwrite','copy',source,root+'/copy.txt','--overwrite')
        self.operation('move renamed cross folder','move',root+'/copy.txt',root+'/deep/moved.txt')
        self.cli('move removed source','info',root+'/copy.txt',error='not_found')
        self.cli('move destination','info',root+'/deep/moved.txt')
        self.operation('recursive copy','copy',root+'/tree',root+'/tree-copy','--recursive')
        self.cli('self descendant rejected','copy',root+'/tree',root+'/tree/child','--recursive',error='path_conflict')

    def sharing(self):
        path = self.root+'/tree/hello world.txt'
        tomorrow = (date.today()+timedelta(days=1)).isoformat()
        self.cli('share dry run','share','create',path,'--expires',tomorrow,'--yes','--dry-run')
        self.sharing_attempted = True
        result = self.cli('protected share','share','create',path,'--expires',tomorrow,
                          '--password-stdin','--yes',stdin=uuid.uuid4().hex[:16]+'\n')
        assert result['protected'] is True
        identifier = result['id']
        links = self.links(); assert any(x['id'] == identifier for x in links)
        self.cli('revoke dry run','share','revoke',identifier,'--yes','--dry-run')
        assert any(x['id'] == identifier for x in self.links())
        self.cli('share revoke','share','revoke',identifier,'--yes')
        assert not any(x['id'] == identifier for x in self.links())

    def links(self):
        result, cursor = [], None
        while True:
            args = ('--cursor',cursor) if cursor else ()
            page = self.cli('sharing inventory','share','list','--limit','1000',*args)
            result += page['items']; cursor = page['next_cursor']
            if not cursor:
                return result

    def cleanup(self):
        from connectonion.useful_tools.synology import Synology
        if not self.created:
            return
        if self.sharing_attempted:
            for link in self.links():
                if link['path'].startswith(self.root+'/'):
                    self.cli('cleanup owned share','share','revoke',link['id'],'--yes')
        client = Synology(nas=self.nas,timeout=90)
        client.info(self.root)
        result = client._request('SYNO.FileStation.Delete','delete',version=2,path=[self.root],recursive=True)
        assert not result.get('errors')
        assert client._maybe_info(self.root) is None
        self.report['cleanup'].append({'owned_directory_removed':True})


def file_bytes(root):
    return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nas',required=True)
    parser.add_argument('--parent',required=True,help='An existing writable NAS directory, such as /home.')
    parser.add_argument('--allow-fixture-writes',action='store_true')
    parser.add_argument('--allow-test-share',action='store_true')
    args = parser.parse_args()
    if not args.allow_fixture_writes:
        parser.error('Pass --allow-fixture-writes for disposable writes and exact cleanup.')
    from connectonion.useful_tools.synology_files import nas_path
    parent = nas_path(args.parent,root=False)
    with tempfile.TemporaryDirectory(prefix='co-nas-acceptance-') as temporary:
        journey = Journey(args.nas,parent,Path(temporary).resolve())
        try:
            journey.inspect(); journey.transfer(); journey.browse(); journey.operations()
            if args.allow_test_share:
                journey.sharing()
            else:
                journey.report['unverified'].append('sharing: opt-in flag omitted')
            journey.report['passed'] = True
        except Exception as error:
            journey.report['failure'] = str(error)
        finally:
            try:
                journey.cleanup()
            except Exception as error:
                journey.report['passed'] = False
                journey.report['cleanup'].append({'failed':str(error),'owned_path':journey.root})
        print(json.dumps(journey.report,indent=2))
        return 0 if journey.report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
