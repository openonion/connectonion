import json
from pathlib import Path
from unittest.mock import patch
from typer.testing import CliRunner
from connectonion.cli.main import app
from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook
from connectonion.wiki.map import build_map
from connectonion.wiki.scan import canonical_origin
from connectonion.wiki.skill_map import map_skills


def test_selected_mail_failures_report_partial_and_preserve_maps(tmp_path):
    skills = tmp_path/'skills';skills.mkdir()
    class Broken:
        def my_addresses(self): raise RuntimeError('secret error details')
    for error in (None, RuntimeError('secret client details')):
        root=tmp_path/('account' if error is None else 'client')
        with patch('connectonion.wiki.service.mail_client', return_value=Broken(), side_effect=error):
            result=CliRunner().invoke(app,['wiki','--root',str(root),'--json','init','--mail','outlook','--skills-dir',str(skills)])
        assert result.exit_code == 1
        data=json.loads(result.stdout)
        assert data['ok'] is False and data['data']['phase']=='partial'
        assert data['data']['errors'][0]['source']=='outlook'
        assert 'secret' not in result.stdout
        assert (root/'notes/projects-map.md').exists()


def test_setup_commands_keep_custom_root(tmp_path):
    root=tmp_path/"someone's notes"
    with patch('connectonion.wiki.map.build_map',return_value={}), patch('connectonion.wiki.service.mail_available', return_value=False):
        result=CliRunner().invoke(app,['wiki','--root',str(root),'--json','init'])
    import shlex
    text=json.loads(result.stdout)['data']['tips'][0]
    command=text.split('then run ',1)[1].removesuffix('.')
    assert shlex.split(command)==['co','wiki','--root',str(root),'init']


def test_equivalent_remotes_and_metadata_refresh_preserve_prose(tmp_path):
    assert canonical_origin('git@Example.org:team/Demo.git')==canonical_origin('https://example.org/team/Demo.git')
    assert canonical_origin('https://example.org/team/demo.git')!=canonical_origin('https://example.org/team/Demo.git')
    rows=[dict(repo='/repo/demo',origin='git@example.org:team/demo.git',path='/repo/demo',sessions=1,first='2026-09-01',last='2026-09-01')]
    skills=tmp_path/'installed';skills.mkdir();root=tmp_path/'wiki';prepare(root)
    with patch('connectonion.wiki.map.scan_projects',return_value=rows):
        first=build_map(root,{}, {},skill_directories=[skills]);record=first['projects'][0]['record']
        nb=Notebook(root);nb.write(record,nb.read(record)+'\nHuman decision: keep this.\n')
        rows.append({**rows[0],'path':'/clone/demo','repo':'/clone/demo','origin':'https://example.org/team/demo.git','sessions':9,'last':'2026-09-20'})
        second=build_map(root,{}, {},skill_directories=[skills]);assert len(second['projects'])==1
        page=nb.read(record);assert '- Sessions: 10' in page and '- Last seen: 2026-09-20' in page
        assert 'Human decision: keep this.' in page


def test_skill_source_refresh_retains_authored_description(tmp_path):
    source=tmp_path/'installed/demo/SKILL.md';source.parent.mkdir(parents=True)
    source.write_text('---\nname: Demo\ndescription: First\n---\n')
    nb=Notebook(tmp_path/'wiki');res=map_skills(nb,[source.parent.parent]);record=res['created'][0]
    nb.write(record,nb.read(record).replace('First','My own explanation'))
    source.write_text(source.read_text().replace('First','Second'))
    map_skills(nb,[source.parent.parent]);page=nb.read(record)
    assert 'My own explanation' in page and '## Current installed metadata\nSecond' in page
    map_skills(nb,[source.parent.parent]);assert nb.read(record)==page


def test_show_me_shows_the_owners_page(tmp_path):
    # 1.8.8b11: `investigate me` worked and `show me` said "expected a Markdown
    # record inside a Wiki category".
    from connectonion.wiki.files import state_path, write_json
    root=tmp_path/'wiki';prepare(root)
    Notebook(root).write('people/ada.md','# Ada Lovelace\n\n- Email: ada@example.com\n')
    write_json(state_path(root,'map.json'),{'owner':{'record':'people/ada.md','addresses':['ada@example.com']}})
    result=CliRunner().invoke(app,['wiki','--root',str(root),'show','me'])
    assert result.exit_code==0, result.output
    assert '# Ada Lovelace' in result.output


def test_show_me_before_init_says_how_to_get_a_page(tmp_path):
    root=tmp_path/'wiki';prepare(root)
    result=CliRunner().invoke(app,['wiki','--root',str(root),'show','me'])
    assert result.exit_code!=0
    assert 'co wiki init' in result.output and 'expected a Markdown record' not in result.output
