"""Conservative identity/hierarchy suggestions; never merge or rewrite pages."""
import posixpath
import re

from .project_obligations import evidence, sections
from .reader_model import REFERENCE


def identity(record):
    facts = sections(record['text']).get('facts', '')
    repo_line = next((line for line in facts.splitlines() if re.match(r'^\s*-?\s*Repository:', line, re.I)), '')
    repo = re.search(r'(?:github\.com[/:])([\w.-]+/[\w.-]+)', repo_line, re.I)
    slug = repo[1].removesuffix('.git').casefold() if repo else ''
    if not slug:
        plain = re.search(r'Repository:\s*`?([\w.-]+/[\w.-]+)(?:`|\s|$)', repo_line)
        slug = plain[1].casefold() if plain else ''
    domain_line = next((line for line in facts.splitlines() if re.match(r'^\s*-?\s*(?:Website|Domain):', line, re.I)), '')
    url = re.search(r'(?:https?://)?([\w.-]+\.[a-z]{2,})(?:[/\s)]|$)', domain_line, re.I)
    domain = url[1].casefold().removeprefix('www.') if url else ''
    name = re.sub(r'[^\w]', '', record['title'].casefold())
    return {'repo': slug, 'domain': domain, 'name': name, 'repo_line': repo_line, 'domain_line': domain_line}


def suggestion(record, target, basis, text):
    return {**evidence(record, text, 'facts')[0], 'path': target['path'], 'suggestion': True,
            'reason': basis, 'via': record['path']}


def project_tree(records):
    projects = [r for r in records if r['category'] == 'projects']
    identities = {r['path']: identity(r) for r in projects}
    for row in projects:
        row.update(parent=None, same_as=[])
        own = identities[row['path']]
        for other in projects:
            if row is other:
                continue
            target = identities[other['path']]
            shared = next((field for field in ('repo', 'domain', 'name') if own[field] and own[field] == target[field]), None)
            if shared:
                row['same_as'].append(suggestion(row, other, 'same normalized ' + shared, own.get(shared + '_line', '')))
        row['same_as'].sort(key=lambda item: item['path'])
    # Explicit child-to-parent wording is stronger than repository-family hints.
    for row in projects:
        duplicates = {item['path'] for item in row['same_as']}
        candidates = []
        body = '\n'.join(text for name, text in sections(row['text']).items() if name != 'sources')
        for line in body.splitlines():
            if re.search(r'part of|sub-?project of|parent(?: project)?\s*:|属于|子项目', line, re.I):
                for _, raw in REFERENCE.findall(line):
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(row['path']), raw))
                    candidates += [(r, line) for r in projects if r['path'] == target and target != row['path'] and target not in duplicates]
        if len({r['path'] for r, _ in candidates}) == 1:
            target, line = candidates[0]
            row['parent'] = suggestion(row, target, 'explicit parent relationship', line)
        if not row['parent']:
            _repo_parent(row, projects, identities)
    _remove_cycles(projects)


def _repo_parent(row, projects, identities):
    own = identities[row['path']]
    if not own['repo']:
        return
    org, repo = own['repo'].split('/')
    if not repo.startswith(('oo-', 'co-')) and repo not in ('docs-site', 'browser', 'handoff'):
        return
    peers = [r for r in projects if r != row and identities[r['path']]['repo'].startswith(org + '/')]
    named = [(r, line) for r in peers for line in row['text'].splitlines()
             if re.search(r'(?:backend|frontend|component|service|docs) for\s+' + re.escape(r['title']) + r'(?!\w)', line, re.I)]
    if len({r['path'] for r, _ in named}) == 1:
        target, line = named[0]
        row['parent'] = suggestion(row, target, 'same GitHub owner and named product component', line)
        return
    candidates = [r for r in peers
                  if re.search(r'\b(?:main|core|flagship) (?:product|platform)\b|主产品', r['text'], re.I)]
    if len(candidates) == 1 and candidates[0]['path'] not in {s['path'] for s in row['same_as']}:
        row['parent'] = suggestion(row, candidates[0], 'same GitHub owner; component repo and explicit main product', own['repo_line'])


def _remove_cycles(projects):
    parents = {r['path']: r['parent']['path'] for r in projects if r['parent']}
    cyclic = set()
    for origin in parents:
        visited, node = set(), origin
        while node in parents and node not in visited:
            visited.add(node)
            node = parents[node]
        if node in visited:
            cyclic.update(visited)
    for row in projects:
        if row['path'] in cyclic:
            row['parent'] = None
