"""Pipe-safe CLI envelopes and canonical recovery commands."""
import json
from unittest.mock import Mock
import pytest
from typer.testing import CliRunner
from connectonion.cli.main import app
from connectonion.cli.commands import synology_commands as commands
from connectonion.useful_tools.synology_transport import SynologyError

runner=CliRunner()


def fake_nas(monkeypatch):
    fake=Mock(); fake.profile={'name':'home'}; fake.account='one'
    monkeypatch.setattr(commands,'_syno',lambda *a,**k:fake)
    return fake


def test_status_json_is_one_stable_document(monkeypatch):
    fake=fake_nas(monkeypatch); fake.status.return_value={'completeness':'complete','checks':{}}
    result=runner.invoke(app,['syno','status','--json'])
    data=json.loads(result.stdout)
    assert result.exit_code==0 and data['ok'] and data['schema_version']==1
    assert not result.stderr and '\x1b' not in result.stdout


def test_status_json_failure_has_stable_code_and_exit(monkeypatch):
    fake=fake_nas(monkeypatch); fake.status.side_effect=SynologyError('Cannot authenticate','auth_required')
    result=runner.invoke(app,['syno','status','--json'])
    data=json.loads(result.stdout)
    assert result.exit_code==1 and data['error']['code']=='auth_required'


def test_piped_listing_has_canonical_quoted_next_command_on_stderr(monkeypatch):
    fake=fake_nas(monkeypatch)
    fake.list_page.return_value={'items':[{'path':'/home/a b.pdf','type':'file','size':0}]}
    result=runner.invoke(app,['syno','ls','/home'])
    assert result.exit_code==0,result.output
    assert "Next: co syno info '/home/a b.pdf'" in result.stderr
    assert 'Next:' not in result.stdout
    assert json.loads(result.stdout)['items'][0]['size']==0


def test_partial_inspection_does_not_exit_success(monkeypatch):
    fake=fake_nas(monkeypatch); fake.status.return_value={'completeness':'partial','checks':{}}
    result=runner.invoke(app,['syno','status','--json'])
    assert result.exit_code==1 and json.loads(result.stdout)['complete'] is False


def test_shares_alias_routes_to_masked_inventory(monkeypatch):
    fake=fake_nas(monkeypatch); fake.share_list.return_value={'items':[]}
    result=runner.invoke(app,['syno','shares','-n','7','--json'])
    assert result.exit_code==0,result.output
    fake.share_list.assert_called_once_with(limit=7,cursor=None,show_url=False)


def test_numeric_legacy_alias_passes_explicit_listing(monkeypatch):
    fake=fake_nas(monkeypatch)
    fake.state.resolve.return_value='/home/a'; fake.download.return_value={'status':'complete'}
    result=runner.invoke(app,['syno','get','1','--listing','frozen','--to','./Downloads','--json'])
    assert result.exit_code==0,result.output
    fake.state.resolve.assert_called_once_with('1','frozen')
    assert fake.download.call_args.args==('/home/a','./Downloads')


def test_interruption_keeps_json_shape_and_exit_130(monkeypatch):
    fake=fake_nas(monkeypatch); fake.list_page.side_effect=KeyboardInterrupt()
    result=runner.invoke(app,['syno','ls','--json'])
    assert result.exit_code==130 and json.loads(result.stdout)['error']['code']=='interrupted'
