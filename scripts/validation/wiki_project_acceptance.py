"""Build one synthetic project map; opt in to one real model investigation."""

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from connectonion.wiki.config import prepare, set_config
from connectonion.wiki.investigate import investigate
from connectonion.wiki.files import WikiError
from connectonion.wiki.map import build_map
from connectonion.wiki.scan import project_exclusion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--run-model', action='store_true', help='Spend one bounded provider investigation')
    parser.add_argument('--model', default='gpt-5.6-luna')
    args = parser.parse_args()
    parent = (args.directory or Path.cwd()).resolve()
    if project_exclusion(parent / 'atlas'):
        parser.error('The project scanner excludes this directory; choose --directory under a normal workspace, not /tmp')
    base = parent if args.directory else Path(tempfile.mkdtemp(prefix='wiki-project-', dir=parent))
    if (base / 'notebook').exists():
        parser.error('Choose a fresh directory; existing acceptance evidence is preserved')
    fixture = Path(__file__).resolve().parents[2] / 'docs/testing/artifacts/wiki187/atlas-source'
    shutil.copytree(fixture, base / 'atlas')
    for name in ('sessions', 'skills'):
        (base / name).mkdir()
    root = base / 'notebook'
    prepare(root)
    set_config(root, ['runner', 'codex', 'model', args.model, 'limits.timeout_seconds', '300'])
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {'type': 'session_meta', 'payload': {'id': 'atlas-synthetic', 'cwd': str(base / 'atlas'),
                                            'originator': 'codex_cli_rs'}},
        {'timestamp': now, 'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
            'content': [{'type': 'input_text', 'text':
                f'Atlas counts words locally. README.md, count.py, draft.txt and output.txt are in {base / "atlas"}. '
                'Please consider publishing a hosted website later. This is a request, not a completed deployment. '
                'Keep the Wiki page in English.'}]}},
    ]
    (base / 'sessions/rollout-atlas.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
    sources = {'codex': {'id': 'codex', 'kind': 'codex', 'root': str(base / 'sessions'),
                        'enabled': True, 'consented': True, 'since': now[:10]}}
    mapped = build_map(root, sources, {}, days=1, skill_directories=[base / 'skills'])
    if not mapped['projects']:
        parser.error('No fixture project mapped; inspect notebook/.state/map.json before investigating')
    record = mapped['projects'][0]['record']
    result = {'root': str(root), 'record': record, 'map': 'completed', 'investigation': 'not requested'}
    if args.run_model:
        try:
            result['investigation'] = investigate(root, record, 'Atlas', [str(base / 'atlas'), 'Atlas'],
                                                 days=1, clients={}, subscriptions=sources)
        except WikiError as error:
            result['investigation'] = {'status': 'failed', 'error': str(error), 'usage': getattr(error, 'usage', None)}
            (base / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            raise
        result['factual_review'] = 'required: check local workflow, sample result and unimplemented hosting'
    (base / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
