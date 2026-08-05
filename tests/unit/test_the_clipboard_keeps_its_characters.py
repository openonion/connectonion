"""What reaches the clipboard when the text is not ASCII.

The humanize typing path pastes CJK runs through the OS clipboard, because a
real user pastes Chinese far more often than they hand-type it. On Windows it
wrote UTF-8 bytes into `clip.exe`:

    subprocess.run(["clip"], input=text.encode())

`clip.exe` decodes its stdin with the console OEM code page — cp936 on Chinese
Windows, cp932 on Japanese — not UTF-8. So `中文` arrived on the clipboard as
mojibake and was pasted into the page wrong. Not a crash: the automation
reported success and typed the wrong characters. #277

The fix routes Windows through PowerShell with the text carried as base64, so
no code page is consulted in either direction. The round-trip test below runs
on the Windows CI runners, which is the real validation this needed.
"""

import platform
import subprocess

import pytest

from connectonion.useful_tools.browser_tools import humanize

CJK = "中文测试"
MIXED = "hello 中文 world 日本語 🎉"


class TestTheCommandsCarryNoCodePage:
    """Runs everywhere: what we would execute, without executing it."""

    def test_windows_does_not_pipe_utf8_into_clip_exe(self, monkeypatch):
        monkeypatch.setattr(platform, 'system', lambda: 'Windows')

        argv = humanize._clipboard_set_argv(CJK)

        flat = ' '.join(argv).lower()
        assert 'clip' not in flat.split('powershell')[0], (
            "clip.exe decodes stdin with the OEM code page; CJK cannot survive it"
        )

    def test_the_text_travels_as_base64_not_as_encoded_bytes(self, monkeypatch):
        """Whatever encoding the console is in, base64 is ASCII."""
        monkeypatch.setattr(platform, 'system', lambda: 'Windows')

        argv = humanize._clipboard_set_argv(CJK)

        assert all(c.isascii() for arg in argv for c in arg), (
            "a non-ASCII character in the argv is a character the console "
            "code page gets to reinterpret"
        )

    def test_mac_and_linux_are_unchanged(self, monkeypatch):
        monkeypatch.setattr(platform, 'system', lambda: 'Darwin')
        assert humanize._clipboard_set_argv(CJK)[0] == 'pbcopy'


@pytest.mark.skipif(platform.system() != 'Windows',
                    reason="the bug and its fix are Windows-only")
class TestTheRoundTripOnWindows:
    """The validation this issue was waiting for. Runs on the Windows runners."""

    @pytest.mark.parametrize("text", [CJK, MIXED, "ascii only"])
    def test_what_goes_on_the_clipboard_comes_back(self, text):
        humanize._clipboard_set(text)
        assert humanize._clipboard_get() == text

    def test_the_previous_clipboard_is_restored(self):
        humanize._clipboard_set("原来的内容")
        saved = humanize._clipboard_get()

        humanize._clipboard_set(CJK)
        humanize._clipboard_set(saved)

        assert humanize._clipboard_get() == "原来的内容"


class TestTextTooLongForACommandLine:
    """Carrying the text inside the command buys a length limit.

    Windows caps a command line at about 8191 characters, and base64 inflates
    UTF-8 by a third — so a long enough paste would be truncated by the shell
    and land on the clipboard as a fragment. Silently, on Windows, only for
    long text: the same shape as the bug this replaced.

    `_paste` already has a fallback for "the clipboard route did not work" — it
    types through the IME path instead — so the honest answer is to decline the
    route rather than to half-use it.
    """

    def test_a_long_run_declines_the_clipboard(self, monkeypatch):
        monkeypatch.setattr(platform, 'system', lambda: 'Windows')

        assert humanize._clipboard_set_argv("中" * 4000) is None

    def test_an_ordinary_field_still_uses_it(self, monkeypatch):
        monkeypatch.setattr(platform, 'system', lambda: 'Windows')

        assert humanize._clipboard_set_argv("中文测试" * 20) is not None

    def test_the_limit_is_on_the_command_not_the_text(self, monkeypatch):
        """The thing that overflows is the encoded command, so measure that."""
        monkeypatch.setattr(platform, 'system', lambda: 'Windows')

        argv = humanize._clipboard_set_argv("a" * 5000)
        if argv is not None:
            assert len(' '.join(argv)) < 8000

    def test_other_platforms_have_no_such_limit(self, monkeypatch):
        """The text goes on stdin there; nothing is measuring a command line."""
        monkeypatch.setattr(platform, 'system', lambda: 'Darwin')

        assert humanize._clipboard_set_argv("中" * 100000) is not None
