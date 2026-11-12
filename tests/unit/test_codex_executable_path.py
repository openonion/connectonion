"""A resolved Codex executable stays one argument even under a spaced prefix."""
from connectonion.useful_tools.codex import _base_command


def test_existing_codex_path_with_spaces_is_one_argument(tmp_path, monkeypatch):
    directory = tmp_path/'tools with spaces'
    directory.mkdir()
    command = directory/'codex'
    command.touch()
    monkeypatch.setenv('CODEX_CMD', str(command))
    assert _base_command() == [str(command), 'app-server']
