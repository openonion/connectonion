"""The live acceptance harness must use a directory the real scanner accepts."""
import importlib.util
from pathlib import Path

import pytest


def test_acceptance_rejects_excluded_directory_before_creating_fixture(tmp_path, monkeypatch, capsys):
    script = Path(__file__).resolve().parents[2] / 'scripts/validation/wiki_project_acceptance.py'
    spec = importlib.util.spec_from_file_location('wiki_project_acceptance', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = tmp_path / 'excluded'
    monkeypatch.setattr('sys.argv', [str(script), '--directory', str(base)])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert 'project scanner excludes' in capsys.readouterr().err
    assert not base.exists()
