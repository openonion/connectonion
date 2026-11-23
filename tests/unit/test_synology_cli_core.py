from click import unstyle
"""The actual parser supports every leaf, common option placement and JSON exits."""
import json
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import synology_commands as commands

runner=CliRunner()
LEAVES=['login','logout','nas list','nas use','status','network status','storage status','storage disks',
        'service list','ls','info','search','download','upload','mkdir','copy','move','share create','share list','share revoke']


@pytest.mark.parametrize('leaf',LEAVES+['get','put','shares'])
def test_every_leaf_has_real_help_examples_and_common_options(leaf):
    result=runner.invoke(app,['syno',*leaf.split(),'--help'])
    assert result.exit_code==0,result.output
    for flag in ('--nas','--json','--non-interactive','--timeout'):
        assert flag in unstyle(result.output)
    assert 'Example' in result.output


@pytest.mark.parametrize('args',[
    ['--nas','home','--json','status'],['status','--nas','home','--json'],
    ['--nas','home','status','--nas','home','--json']])
def test_common_flags_route_to_same_profile(args,monkeypatch):
    fake=Mock(); fake.profile={'name':'home'}; fake.account='one'
    fake.status.return_value={'completeness':'complete','checks':{}}
    make=Mock(return_value=fake); monkeypatch.setattr(commands,'_syno',make)
    result=runner.invoke(app,['syno',*args])
    assert result.exit_code==0,result.output
    assert json.loads(result.stdout)['schema_version']==1
    assert make.call_args.args[0]['nas']=='home'


@pytest.mark.parametrize('args',[
    ['--nas','home','status','--nas','office','--json'],
    ['--timeout','10','status','--timeout','20','--json'],
    ['status','--wait','--json'],['status','--operation','abc','--refresh','--json'],
    ['search','a','--json'],['download','/home/a','--overwrite','--skip-existing','--json'],
    ['share','create','/home/a','--json'],['share','revoke','link','--json']])
def test_invalid_inputs_produce_one_json_usage_or_declined_result(args):
    result=runner.invoke(app,['syno',*args])
    assert result.exit_code in {1,2},result.output
    data=json.loads(result.stdout)
    assert data['ok'] is False and data['error']['code']


def test_bare_syno_is_share_listing_and_empty_tip_has_no_phantom_file(monkeypatch):
    fake=Mock(); fake.profile={'name':'home'}; fake.account='one'
    fake.list_page.return_value={'items':[],'next_cursor':None}
    monkeypatch.setattr(commands,'_syno',lambda *a,**k:fake)
    result=runner.invoke(app,['syno','--json'])
    assert result.exit_code==0,result.output
    assert 'download' not in json.loads(result.stdout)['next_command']
    fake.list_page.assert_called_once()


def test_json_never_prompts_for_share_password_or_confirmation(monkeypatch):
    monkeypatch.setattr(commands,'prompt_secret',lambda *a,**k:pytest.fail('must not prompt'))
    result=runner.invoke(app,['syno','share','create','/home/a','--no-expiry','--password','--yes','--json'])
    assert result.exit_code==2,result.output
    assert json.loads(result.stdout)['error']['code']=='interaction_required'
