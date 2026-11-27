"""`co rem` help is the agreed design (#1656), printed verbatim, and true to the code.

The pages were written and reviewed before the code, so the test runs in that
direction: every page in rem_help.md is what its command prints, every
command has a page, and every command and flag a page shows exists. A page
that names a flag the parser does not have is the failure #1643 exists to
stop -- an agent copies the example, and it does not run.
"""

import re
import shlex

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from connectonion.cli.commands.rem_help import pages
from connectonion.cli.main import app

runner = CliRunner()
REM = get_command(app).commands["rem"]
ROOT_COMMANDS = ["init", "map", "collect", "investigate", "deepen", "enrich", "muse", "abstract", "decisions", "translate", "tag", "catchup",
                 "open", "list", "show", "search", "start", "stop", "status", "task", "exec", "next", "submit",
                 "sources", "config", "upgrade", "logs", "morning", "doctor", "history"]
ADVANCED = ["scan", "backfill", "map-skills", "import", "stub", "merge", "person", "reflect", "reflections", "propose", "review", "capture",
            "projects"]
OLD_NAMES = {"unfinished": "investigate", "people": "list people --aliases", "daily": "sync",
             "subscriptions": "sources", "subscribe": "sources add", "unsubscribe": "sources remove",
             "route": "config set", "usage": "logs --usage"}


def resolve(words):
    """The click command a `co rem ...` word list reaches, and the words left over."""
    command, rest = REM, list(words)
    while rest and hasattr(command, "commands") and rest[0] in command.commands:
        command = command.commands[rest.pop(0)]
    return command, rest


def help_of(words):
    return runner.invoke(app, ["rem", *words, "--help"], terminal_width=200).stdout


def test_rem_init_options_document_repeatable_mail_selection():
    options = help_of(["init"]).split("Options:", 1)[1].split("Output:", 1)[0]
    line = next((line for line in options.splitlines() if "--mail " in line), "")
    assert "gmail|outlook" in line
    assert "repeatable" in line
    assert "consent" in options and "subscribe" in options


def test_rem_start_and_init_help_match_terminal_no_prompt_behavior():
    assert 'diff' in help_of(['start'])
    assert 'without prompting' in help_of(['start'])
    assert 'pauses at the estimate' not in help_of(['init'])
    assert 'estimate pause unless' not in help_of([])


@pytest.mark.parametrize("name", sorted(pages()))
def test_every_page_is_what_its_command_prints(name):
    words = name.split()[2:]
    assert help_of(words).rstrip("\n") == pages()[name].rstrip("\n")


def test_every_command_and_subcommand_has_a_page():
    names = set(pages())
    for command in [*ROOT_COMMANDS, *ADVANCED, "advanced"]:
        assert f"co rem {command}" in names, command
    for group in ("sources", "config", "projects", "decisions", "import"):
        for sub in REM.commands[group].commands:
            assert f"co rem {group} {sub}" in names, (group, sub)


def test_config_help_describes_speed_default_and_override():
    # Unattended nights default to the standard tier (#3099).
    assert "speed                          standard (default) | fast: Codex's Fast (priority) tier" in pages()["co rem config"]


def test_every_command_is_on_the_root_page_the_advanced_page_or_is_an_old_name():
    """Nothing is hidden (`co commands` lists all of it, #1643); the root page
    simply lists fourteen, and the rest are one page away or say what replaced them."""
    listed = re.findall(r"^  ([a-z][a-z-]*)\s{2,}\S", pages()["co rem"], re.M)
    assert listed == ROOT_COMMANDS
    assert re.findall(r"^  ([a-z][a-z-]*)\s{2,}\S", pages()["co rem advanced"], re.M) == ADVANCED
    assert set(REM.commands) == {*ROOT_COMMANDS, *ADVANCED, "advanced", *OLD_NAMES, "sync"}
    assert "until 1.9.0" not in help_of([])
    assert REM.commands["sync"].help.startswith("Collect, then investigate what is unfinished;")
    assert "co rem collect for new material only, co rem catchup for a whole day" in help_of(["sync"])
    for old, new in OLD_NAMES.items():
        assert REM.commands[old].help.startswith(f"Old name for `co rem {new.split(' --')[0]}"), old
    for name in [*ROOT_COMMANDS, *ADVANCED]:
        assert REM.commands[name].help and "\n" not in REM.commands[name].help, name


def _commands_in(text):
    """Every `co rem ...` a page asks the reader to type, placeholders dropped."""
    for line in text.splitlines():
        for found in re.findall(r"co rem(?: [^()\[\]|`]*)?", line):
            words = [w.rstrip(",.;") for w in shlex.split(found.replace("...", "").replace("\\", ""))[2:]]
            yield line, [w for w in words if not re.fullmatch(r"[A-Z][A-Z_]*|<[^>]+>", w)]


@pytest.mark.parametrize("name", sorted(pages()))
def test_every_command_and_flag_on_a_page_exists(name):
    for line, words in _commands_in(pages()[name]):
        command, rest = resolve(words)
        options = {"--help"} | {opt for param in command.params for opt in (*param.opts, *param.secondary_opts)}
        for word in rest:
            if word.startswith("--"):
                assert word.split("=")[0] in options, f"{name}: {word} in: {line.strip()}"


@pytest.mark.parametrize("name", sorted(set(pages()) - {"co rem"}))
def test_every_leaf_names_its_way_back(name):
    back = re.search(r"^Back:\s+(co rem[^\n]*?)(?: --help)?$", pages()[name], re.M)
    assert back, name
    parent = back.group(1).strip()
    assert parent in pages(), (name, parent)


def test_help_never_runs_the_command(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.investigate.investigate", lambda *a, **k: pytest.fail("model called"))
    result = runner.invoke(app, ["rem", "--root", str(tmp_path), "investigate", "people", "--help"])
    assert result.exit_code == 0 and result.stdout.startswith("co rem investigate —")
    assert not (tmp_path / ".state").exists()


@pytest.mark.parametrize("old,new", sorted(OLD_NAMES.items()))
def test_an_old_name_still_works_and_says_its_new_name(tmp_path, old, new):
    args = {"subscribe": ["codex"], "unsubscribe": ["codex"]}.get(old, [])
    result = runner.invoke(app, ["rem", "--root", str(tmp_path), old, *args])
    assert "works until" not in result.stderr
    assert "works until" not in help_of([old])
    assert f"is now `co rem --root {tmp_path} {new.split(' --')[0]}" in result.stderr \
        or f"is now `co rem --root {tmp_path} {new}" in result.stderr, result.stderr


def test_a_wrapper_sees_its_own_name_in_help(monkeypatch):
    monkeypatch.setenv("CO_REM_PROGRAM", "remi")
    output = help_of(["investigate"])
    assert output.startswith("remi investigate —") and "co rem" not in output


def test_day_stage_groups_are_in_order_and_machinery_is_apart():
    text = help_of([])
    headings = ["Collect — read new mail and sessions",
                "Investigate — fill pages from originals",
                "Deepen — follow leads, add insights",
                "Abstract — learn from pages",
                "Translate — put pages in your language",
                "Tag — organise pages by tag",
                "Run a whole day now", "Background machinery"]
    assert [text.index(heading) for heading in headings] == sorted(text.index(heading) for heading in headings)
    machinery = text.split("Background machinery\n")[1].split("Settings\n")[0]
    assert re.findall(r"^  ([a-z-]+)\s{2,}", machinery, re.M) == ['exec', 'next', 'submit']
    verbs = [name for name in REM.commands if name in ROOT_COMMANDS and name not in ('decisions', 'task', 'sources', 'config')]
    assert verbs == [name for name in ROOT_COMMANDS if name in verbs]


def test_stage_verbs_are_real_commands_and_decisions_has_no_write():
    text = help_of([])
    for heading, verb in [('Collect —', 'collect'), ('Investigate —', 'investigate'),
                          ('Deepen —', 'deepen'), ('Abstract —', 'abstract'), ('Translate —', 'translate'),
                          ('Tag —', 'tag')]:
        section = text.split(heading, 1)[1].split('\n', 1)[1]
        assert re.match(rf'  {verb}\s{{2,}}', section)
    assert 'think' not in next(line for line in text.splitlines() if line.startswith('Deepen —'))
    assert 'co rem decisions write' not in '\n'.join(pages().values())
    assert not getattr(REM.commands['decisions'], 'commands', {})
    assert 'alias' not in help_of(['abstract'])
    assert 'one batch, not until caught up' in help_of(['collect'])
    assert 'Those reads are outside the extraction batch; --source scopes only that batch.' in help_of(['collect'])
