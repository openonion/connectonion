"""Organisation table facts and the shared directory behaviour (#3037)."""
import base64

import pytest

from test_rem_org_ui_integration import run_js


def test_org_website_uses_fact_then_business_contact_not_free_mail():
    result = run_js(['orgWebsite'], r'''
      const orgFact = (r, key) => r[key] || (key === 'Email' ? r.email || '' : '');
      const facts = r => r, unlabelled = x => x;
      const people = [{email:'fern@gmail.com; elm@cedar.example'}];
      console.log(JSON.stringify([
        orgWebsite({Website:'https://explicit.example/about'}, people),
        orgWebsite({}, people), orgWebsite({}, [{email:'fern@outlook.com; elm@yandex.ru; ash@bigpond.net.au'}]),
        orgWebsite({Website:'javascript:alert(1)'}, people)]));
    ''')
    assert result == [{'url': 'https://explicit.example/about', 'derived': False},
                      {'url': 'https://cedar.example', 'derived': True}, None, None]


def test_org_activity_sums_unique_people_and_keeps_unknown_blank():
    result = run_js(['orgActivity'], r'''
      const relation = r => r.rel;
      const a = {path:'a', rel:{messages_90d:3, last_mail:'2026-11-01', weekly_messages:Array(52).fill(1)}};
      const b = {path:'b', rel:{messages_90d:5, last_mail:'2026-11-02', weekly_messages:Array(52).fill(2)}};
      console.log(JSON.stringify([orgActivity([a,b,a, {path:'c'}]), orgActivity([{path:'c'}])]));
    ''')
    assert result[0]['messages_90d'] == 8
    assert result[0]['weekly_messages'] == [3] * 52
    assert result[1] is None


def test_org_units_expand_recursively_without_duplicates():
    result = run_js(['orgVisibleRows'], r'''
      const child = {r:{path:'child'}, children:[{r:{path:'leaf'},children:[]}]};
      const root = {r:{path:'root'},children:[child]};
      console.log(JSON.stringify([orgVisibleRows([root],new Set()),
        orgVisibleRows([root],new Set(['root','child']))].map(rows=>rows.map(d=>[d.r.path,d.depth]))));
    ''')
    assert result == [[['root', 0]], [['root', 0], ['child', 1], ['leaf', 2]]]


@pytest.mark.parametrize('value', ['logos/fern.png', 'https://example.com/logo.png', '../escape.png', 'logos/link.png'])
def test_org_logo_is_embedded_only_from_inside_notebook(tmp_path, value):
    from connectonion.rem.reader_model import organisation_logo
    logos = tmp_path / 'logos'
    logos.mkdir()
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG1cAAAAASUVORK5CYII=')
    (logos / 'fern.png').write_bytes(png)
    outside = tmp_path.parent / 'escape.png'
    outside.write_bytes(png)
    (logos / 'link.png').symlink_to(outside)
    record = {'category':'orgs', 'text':f'# Fern\n\n## Facts\n- Logo: {value}\n'}
    data = organisation_logo(tmp_path, record)
    assert data == ('data:image/png;base64,' + base64.b64encode(png).decode() if value == 'logos/fern.png' else '')


def test_org_website_keeps_markdown_urls_and_hides_labelled_domains():
    result = run_js(['orgFact', 'orgWebsite'], r'''
      const plainValue = x => x.replace(/\[([^\]]+)\]\([^)]+\)/g,'$1');
      const unlabelled = x => x.replace(/\[personal\][^;]*/g,'');
      const parseFacts = r => new Map(r.email ? [['Email', [{value:r.email}]]] : []);
      const r = {facts:{Website:[{value:'[Official](https://cedar.example/about)'}]}};
      console.log(JSON.stringify([orgWebsite(r, []),
        orgWebsite({}, [{email:'[personal] fern@hidden.example; elm@public.example'}])]));
    ''')
    assert result == [{'url':'https://cedar.example/about', 'derived':False},
                      {'url':'https://public.example', 'derived':True}]


def test_kind_filter_retains_matching_units_with_their_ancestor_context():
    result = run_js(['orgFilterRows'], r'''
      const leaf = {r:{path:'team'},kind:'team',text:'field squad',children:[]};
      const root = {r:{path:'root'},kind:'company',text:'cedar',children:[leaf]};
      const other = {r:{path:'service'},kind:'service',text:'desk',children:[]};
      console.log(JSON.stringify([orgFilterRows([root,other],'team',''),
        orgFilterRows([root,other],'all','squad')].map(rows=>rows.map(d=>[d.r.path,d.children.map(c=>c.r.path)]))));
    ''')
    assert result == [[['root', ['team']]], [['root', ['team']]]]


def test_logo_survives_live_data_and_self_contained_snapshot(tmp_path, monkeypatch):
    import json
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem.reader import _render
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    prepare(tmp_path)
    Notebook(tmp_path).write('orgs/cedar.md', '# Cedar Works\n\n## Facts\n- Logo: logos/cedar.png\n')
    (tmp_path / 'logos').mkdir()
    (tmp_path / 'logos/cedar.png').write_bytes(base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG1cAAAAASUVORK5CYII='))
    files, _, _ = _render(tmp_path, 'full')
    row = next(r for r in json.loads(files['data.json'])['records'] if r['path'] == 'orgs/cedar.md')
    assert row['logo'].startswith('data:image/png;base64,')
    assert row['logo'] in files['file.html']
