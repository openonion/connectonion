"""`co call --out PATH` on a text result writes no file and says nothing.

Measured against the real deployed nw-map agent:

    $ co call --out /tmp/notimage.png 0xcf1619cb… uptime
     00:46:31 up 37 days, 21:18,  4 users,  load average: 0.11, 0.13, 0.09
    exit=0
    $ ls /tmp/notimage.png
    ls: cannot access '/tmp/notimage.png': No such file or directory

The flag is documented as image-specific, and that part is honest:

    --out PATH        save an image result (screenshot) to PATH; else ./screenshot.png

What it does not say is what happens when the result is text — and the answer is
that the option is dropped without a word. `co call --out result.txt <addr> co
status` reads like "save the output to a file" to anyone who has not read that
line, and they get no file and no explanation.

Same family as the rest of this release: an instruction that quietly does
nothing. The exit code stays 0 because the call DID succeed — only the save did
not apply — and the note goes to stderr, which the module's own contract reserves
for exactly this ("stdout = result, stderr = errors").
"""

import pytest

from connectonion.cli.commands import call_commands


class _Result:
    def __init__(self, text="", images=None, ok=True, error=None):
        self.text = text
        self.images = images or []
        self.ok = ok
        self.error = error


@pytest.fixture
def call(monkeypatch, tmp_path):
    """Run handle_call against a stand-in remote, in a scratch cwd."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(call_commands, "_load_keys", lambda: {"stub": True})

    def _run(args, result):
        class _Remote:
            def call(self, tool, command=None, timeout=60.0, **kw):
                return result

        import connectonion

        monkeypatch.setattr(connectonion, "connect", lambda address, **kw: _Remote())
        return call_commands.handle_call(args)

    return _run


ADDRESS = "0xabc"


class TestATextResultWithOutSaysSo:

    def test_it_still_prints_the_text(self, call, capsys):
        code = call(["--out", "shot.png", ADDRESS, "uptime"], _Result(text="up 37 days"))

        assert code == 0
        assert "up 37 days" in capsys.readouterr().out

    def test_it_mentions_the_option_did_not_apply(self, call, capsys):
        call(["--out", "shot.png", ADDRESS, "uptime"], _Result(text="up 37 days"))

        assert "--out" in capsys.readouterr().err

    def test_the_note_goes_to_stderr_not_stdout(self, call, capsys):
        """stdout is the result, so a script piping it must not receive prose."""
        call(["--out", "shot.png", ADDRESS, "uptime"], _Result(text="up 37 days"))
        captured = capsys.readouterr()

        assert captured.out.strip() == "up 37 days"

    def test_no_file_is_created(self, call, tmp_path):
        """Writing the text into a .png would be worse than not writing."""
        call(["--out", "shot.png", ADDRESS, "uptime"], _Result(text="up 37 days"))

        assert not (tmp_path / "shot.png").exists()

    def test_the_exit_code_is_still_success(self, call):
        """The call worked; only the save did not apply."""
        assert call(["--out", "shot.png", ADDRESS, "uptime"], _Result(text="ok")) == 0


class TestWithoutOutNothingIsSaid:
    """The common case must not acquire a warning."""

    def test_a_text_result_is_quiet(self, call, capsys):
        call([ADDRESS, "uptime"], _Result(text="up 37 days"))

        assert capsys.readouterr().err == ""


class TestAnImageResultIsUnchanged:

    IMAGE = "data:image/png;base64,iVBORw0KGgo="

    def test_it_is_written_to_the_given_path(self, call, tmp_path, capsys):
        code = call(["--out", "shot.png", ADDRESS, "co", "browser", "take_screenshot"],
                    _Result(images=[self.IMAGE]))

        assert code == 0
        assert (tmp_path / "shot.png").exists()
        assert capsys.readouterr().out.strip() == "shot.png"

    def test_it_says_nothing_on_stderr(self, call, capsys):
        call(["--out", "shot.png", ADDRESS, "co", "browser", "take_screenshot"],
             _Result(images=[self.IMAGE]))

        assert capsys.readouterr().err == ""

    def test_the_default_path_still_applies(self, call, tmp_path):
        call([ADDRESS, "co", "browser", "take_screenshot"], _Result(images=[self.IMAGE]))

        assert (tmp_path / "screenshot.png").exists()
