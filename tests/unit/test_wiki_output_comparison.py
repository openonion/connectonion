import importlib.util
import json
from pathlib import Path


def test_comparison_requires_quality_review_and_discloses_changed_input(tmp_path):
    script = Path(__file__).resolve().parents[2] / 'scripts/validation/wiki_compare_outputs.py'
    spec = importlib.util.spec_from_file_location('wiki_compare_outputs', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    baseline, candidate = tmp_path / 'before', tmp_path / 'after'
    for directory, text in ((baseline, 'old source'), (candidate, 'different source')):
        directory.mkdir()
        (directory / 'material.json').write_text(json.dumps([{'text': text}]))
        (directory / 'instructions.md').write_text('Instructions')
        (directory / 'result.json').write_text(json.dumps({'status': 'execution_finished', 'usage': {'input_tokens': 5}}))
    report = module.compare(baseline, candidate)
    assert 'Identical supplied material: False' in report
    assert 'Quality review — pending' in report
    assert 'not recorded' in report
    assert 'Decision — pending' in report
    (candidate / 'material.json').write_text((baseline / 'material.json').read_text())
    assert 'Identical supplied material: True' in module.compare(baseline, candidate)
