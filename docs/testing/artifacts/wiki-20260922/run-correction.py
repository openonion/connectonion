import json
import argparse
from pathlib import Path
from connectonion.wiki.files import Notebook, write_json, state_path
from connectonion.wiki import reflections
from connectonion.wiki.service import approve_sources, run_sync
parser=argparse.ArgumentParser(description='Run a live correction test on a completed synthetic Atlas acceptance fixture.')
parser.add_argument('directory',type=Path)
args=parser.parse_args()
base=args.directory.resolve()
if (base/'correction-record.json').exists():
    parser.error('This fixture already contains correction evidence; use a fresh completed Atlas fixture.')
root=base/'notebook'
r=json.loads((base/'result.json').read_text()); record=r['record']; nb=Notebook(root)
(root/'before-correction.md').write_text(nb.read(record))
source=base/'atlas/ownership.txt'
source.write_text('Synthetic project owner clarification, 2026-09-22: Mira owns Atlas maintenance. Leo was incorrectly recorded as owner. The project remains a local prototype; no hosted website was released.\n')
page=nb.read(record)
page=page.replace('## People and ownership\n','## People and ownership\n- Legacy imported note: Leo is the owner (unverified).\n')
nb.write(record,page)
(root/'stale-page-before-sync.md').write_text(page)
# This disposable notebook has no live subscriptions or background scheduler.
write_json(state_path(root,'subscriptions.json'),{kind:{'id':kind,'kind':kind,'enabled':False,'consented':False} for kind in ('codex','claude-code','gmail','outlook')})
approve_sources(root)
correction=reflections.add(root,record,'Mira owns Atlas maintenance; the earlier Leo attribution is incorrect. No hosted release has occurred.',author='synthetic-user',basis=f'Explicit owner clarification in {source}; inspect this file.',previous='Leo owns Atlas',applies='As of 2026-09-22',sources=[str(source)],kind='correction')
write_json(base/'correction-record.json',correction)
first=run_sync(root)
write_json(base/'sync-result.json',first)
(root/'after-correction.md').write_text(nb.read(record))
if first['outcome']=='completed':
 second=run_sync(root)
 write_json(base/'repeat-sync-result.json',second)
print(json.dumps(first,indent=2))
