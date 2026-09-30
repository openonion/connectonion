"""`[env] …/keys.env` is printed only on request, and once (#2008).

It used to print whenever stderr was a terminal, and loading runs at import
and again per command, so every `co` command in a real terminal opened with
the same line two or three times.
"""

import io

from connectonion import environment


class _Terminal(io.StringIO):
    def isatty(self):
        return True


def _load_twice(tmp_path, monkeypatch, debug):
    (tmp_path / "keys.env").write_text("SOME_SETTING=1\n")
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path))
    monkeypatch.delenv("SOME_SETTING", raising=False)
    if debug:
        monkeypatch.setenv("CO_DEBUG_ENV", "1")
    else:
        monkeypatch.delenv("CO_DEBUG_ENV", raising=False)
    monkeypatch.setattr(environment, "_announced", set())
    monkeypatch.setattr(environment, "_loaded", {})
    err = _Terminal()
    monkeypatch.setattr("sys.stderr", err)
    environment.load_environment()
    environment.load_environment()
    return err.getvalue()


def test_a_terminal_sees_nothing_unless_it_asks(tmp_path, monkeypatch):
    assert _load_twice(tmp_path, monkeypatch, debug=False) == ""


def test_co_debug_env_names_the_file_once(tmp_path, monkeypatch):
    printed = _load_twice(tmp_path, monkeypatch, debug=True)
    assert printed.splitlines() == [f"[env] {(tmp_path / 'keys.env').resolve()}"]
