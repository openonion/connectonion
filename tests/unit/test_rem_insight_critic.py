"""The insight critic reads indexed originals independently of the writer."""

from connectonion.rem import insight_critic
from connectonion.rem.evidence import write_evidence
from connectonion.rem.files import Notebook


def test_critic_reads_originals_from_evidence_index(tmp_path):
    notebook = Notebook(tmp_path)
    record = 'projects/atlas.md'
    notebook.stub_project(record, 'Atlas', [])
    originals = [{'role': 'user', 'source': f'codex:session-atlas:{i}',
                  'text': f'Atlas request {i}', 'speaker': 'user', 'timestamp': '2026-10-01'}
                 for i in range(2)]
    laid_out = write_evidence(tmp_path / 'evidence', originals)
    bullets = ['- Pattern: Atlas requests return to the demo. [1][2]']
    candidate = ('# Atlas\n\n## Insight\n' + bullets[0] + '\n\n## Sources\n'
                 '- [1] codex:session-atlas:0\n- [2] codex:session-atlas:1\n')
    items = [{'role': 'evidence-index', 'source': 'investigation:evidence',
              'originals': str(laid_out['originals']), 'text': 'Index text'}]

    packet = insight_critic.critic_packet(notebook, candidate, record, items, bullets)
    assert packet['missing_citations'] == []
    assert [row['context']['excerpt'] for row in packet['sources']] == ['Atlas request 0', 'Atlas request 1']
    assert all(row['context']['sender'] == 'user' for row in packet['sources'])
