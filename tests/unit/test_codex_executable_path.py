"""A resolved Codex executable stays one argument even under a spaced prefix."""
from pathlib import Path

from connectonion.useful_tools.codex import _base_command


def test_existing_codex_path_with_spaces_is_one_argument(tmp_path, monkeypatch):
    directory = tmp_path/'tools with spaces'
    directory.mkdir()
    command = directory/'codex'
    command.touch()
    monkeypatch.setenv('CODEX_CMD', str(command))
    assert _base_command() == [str(command), 'app-server']


def test_codex_official_installer_path_is_used_when_not_on_path(tmp_path, monkeypatch):
    monkeypatch.delenv('CODEX_CMD', raising=False)
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    monkeypatch.setattr('shutil.which', lambda name: None)
    binary = tmp_path / '.local' / 'bin' / 'codex'
    binary.parent.mkdir(parents=True)
    binary.write_text('#!/bin/sh\n')
    binary.chmod(0o755)
    assert _base_command() == [str(binary), 'app-server']


def test_codex_missing_binary_names_both_search_locations(tmp_path, monkeypatch):
    import json
    from connectonion.useful_tools.codex import codex
    monkeypatch.delenv('CODEX_CMD', raising=False)
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    monkeypatch.setattr('shutil.which', lambda name: None)
    error = json.loads(codex('inspect'))['error']
    assert 'PATH' in error
    assert str(tmp_path / '.local' / 'bin' / 'codex') in error
    assert 'CODEX_CMD' in error
