"""One line per key in the file that carries the secrets.

`co init` into a directory that already has a .env without an invite code wrote
CO_INVITE_CODE twice:

    8:CO_INVITE_CODE=LYA8Q-HM596-SWE8A
   14:CO_INVITE_CODE=LYA8Q-HM596-SWE8A

Same value both times, so nothing was granted twice — but a duplicated line in
the file that holds the agent's way in is the kind of thing that makes people
stop trusting the file, and the next reader has to work out which one wins
before they can change it.

The cause is one key on two paths. It is appended to keys_to_add when minted,
and also put into global_keys so the branch that writes a *fresh* .env includes
it — and the branch that appends to an existing .env then walks global_keys and
adds it a second time.
"""

import re
from pathlib import Path

import pytest


def _duplicate_keys(text: str) -> list:
    seen, dupes = set(), []
    for line in text.splitlines():
        stripped = line.strip()
        if '=' not in stripped or stripped.startswith('#'):
            continue
        key = stripped.split('=', 1)[0].strip()
        if key in seen:
            dupes.append(key)
        seen.add(key)
    return dupes


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    (tmp_path / 'home' / '.co').mkdir(parents=True)
    (tmp_path / 'home' / '.co' / 'keys.env').write_text(
        "OPENONION_API_KEY=key\nAGENT_ADDRESS=0xabc\n")
    return tmp_path


class TestNoKeyIsWrittenTwice:

    def test_an_existing_env_without_a_code_gets_exactly_one(self, project):
        from connectonion.cli.commands.init import handle_init

        (project / '.env').write_text("OPENAI_API_KEY=sk-mine\n")
        handle_init(ai=None, key=None, template='co-ai', description=None,
                    yes=True, force=True)

        text = (project / '.env').read_text()
        assert _duplicate_keys(text) == [], (
            f"written twice: {_duplicate_keys(text)}\n{text}"
        )

    def test_a_fresh_env_gets_exactly_one(self, project):
        from connectonion.cli.commands.init import handle_init

        handle_init(ai=None, key=None, template='co-ai', description=None,
                    yes=True, force=True)

        text = (project / '.env').read_text()
        assert text.count("CO_INVITE_CODE=") == 1, text

    def test_a_second_init_does_not_mint_a_new_code(self, project):
        """The comment in the code is explicit: regenerating it would silently
        lock out everyone already holding the old one."""
        from connectonion.cli.commands.init import handle_init

        handle_init(ai=None, key=None, template='co-ai', description=None,
                    yes=True, force=True)
        first = re.search(r"CO_INVITE_CODE=(\S+)", (project / '.env').read_text()).group(1)

        handle_init(ai=None, key=None, template='co-ai', description=None,
                    yes=True, force=True)
        text = (project / '.env').read_text()

        assert text.count("CO_INVITE_CODE=") == 1, text
        assert re.search(r"CO_INVITE_CODE=(\S+)", text).group(1) == first
