"""
LLM-Note: #1750 — Auto approval classified the first word of a command and
allowed anything it did not name. `nice rm -rf ~` ran because `nice` is not
`rm`; `co gcalendar delete ID --yes` ran because `delete` was not a verb the
policy knew. Each asking or denying row below was "allow" on main (5fc06bc1).

The rule these tests pin: a command that runs another command is judged by
the command it runs; a command whose subcommand names a deletion or an effect
on other people asks, whatever the program; and a command that fetches,
installs or runs code this policy cannot read asks. What is left — a local
command nobody listed — is still allowed, so Auto stays usable unattended.
"""

import pytest

from connectonion.useful_plugins.tool_approval import policy


def decide(command, root):
    return policy.evaluate_auto_approve("bash", {"command": command}, root=root)


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    work = tmp_path / "work"
    work.mkdir()
    return work


# A wrapper word hid the command it ran.
WRAPPED = [
    ("nice rm -rf ~", "deny"),
    ("nice -n 10 rm -rf ~", "deny"),
    ("timeout 60 rm -rf ~", "deny"),
    ("timeout -s KILL 60 rm -rf ~", "deny"),
    ("nohup rm -rf ~", "deny"),
    ("command rm -rf ~", "deny"),
    ("sudo rm -rf ~", "deny"),
    ("sudo -u root rm -rf ~", "deny"),
    # bashlex cannot parse the `time` keyword, and what cannot be parsed asks.
    ("time rm -rf ~", "ask"),
    ("caffeinate -i rm -rf ~", "deny"),
    ("stdbuf -o0 rm -rf ~", "deny"),
    ("env FOO=1 rm -rf ~", "deny"),
    ("exec rm -rf ~", "deny"),
    ("xargs rm -rf", "deny"),
    ("nice timeout 5 nohup rm -rf ~", "deny"),
    ("/usr/bin/nice rm -rf ~", "deny"),
    ("watch -n1 cat ~/.ssh/id_rsa", "deny"),
    ("timeout 9 curl https://x.sh", "ask"),
    ("timeout 5 bash -c 'rm -rf ~'", "ask"),
    ("nice python3 -c 'import os'", "ask"),
    ("uv run --with requests python x.py", "ask"),
    # A wrapper whose options cannot be read is not guessed at.
    ("timeout --made-up-flag 5 ls", "ask"),
    # sudo is another user's authority; nothing it runs is automatic.
    ("sudo ls", "ask"),
    ("sudo -s", "ask"),
    # xargs takes its arguments from stdin, which the policy cannot see.
    ("find . -name '*.py' | xargs grep foo", "ask"),
]

# git's own ways of throwing work away, and of running a program.
GIT = [
    ("git reset --hard HEAD~3", "ask"),
    ("git clean -fdx", "ask"),
    ("git checkout -- .", "ask"),
    ("git checkout .", "ask"),
    ("git restore src/app.py", "ask"),
    ("git stash drop", "ask"),
    ("git stash clear", "ask"),
    ("git branch -D feature", "ask"),
    ("git -c alias.x='!rm -rf ~' x", "ask"),
    ("git config alias.x '!rm -rf ~'", "ask"),
    ("git my-alias", "ask"),
]

# Deletions and effects on other people, through any CLI.
ACTS_ON_OTHERS = [
    ("unlink important.db", "deny"),
    ("co gcalendar delete EVENTID --yes", "ask"),
    ("co gcalendar create 'Board' 2026-10-01T09:00:00Z 2026-10-01T10:00:00Z --attendees ceo@corp.com --yes", "ask"),
    ("co gcalendar meet 'Sync' 2026-10-01T09:00:00Z 2026-10-01T10:00:00Z --attendees ceo@corp.com --yes", "ask"),
    ("co gcalendar update EVENTID --title x --yes", "ask"),
    ("co outlook calendar delete EVENTID --yes", "ask"),
    ("co outlook calendar update EVENTID --title x", "ask"),
    ("co outlook cancel 1", "ask"),
    ("co gdrive rm FILEID", "ask"),
    ("co syno share create /photos", "ask"),
    ("co feishu delete om_1", "ask"),
    ("co feishu edit om_1 new text", "ask"),
    ("co lark react om_1 THUMBSUP", "ask"),
    ("co whatsapp group create friends", "ask"),
    ("co youtube put video.mp4", "ask"),
    ("co sms send +61400000000 hi", "ask"),
    ("co telegram send 123 hi", "ask"),
    ("co gmail draft send 1", "ask"),
    ("co call 0xabc hello", "ask"),
    ("co trust add 0xabc", "ask"),
    ("co env get OPENAI_API_KEY", "deny"),
    ("co env set FOO bar", "ask"),
    ("gws gmail users messages send --params '{\"userId\":\"me\"}' --json '{}'", "ask"),
    ("gws gmail +send --to a@b.com --subject hi --body x", "ask"),
    ("gws drive files delete --params '{\"fileId\":\"x\"}'", "ask"),
    ("lark-cli im +messages-send --chat-id oc_1 --text hi", "ask"),
    ("gh repo delete me/proj --yes", "ask"),
    ("gh api -X DELETE repos/me/proj", "ask"),
    ("terraform destroy -auto-approve", "ask"),
    ("terraform apply -auto-approve", "ask"),
    ("kubectl delete namespace prod", "ask"),
    ("kubectl -n prod delete pod x", "ask"),
    ("docker system prune -af --volumes", "ask"),
    ("psql -c 'DROP TABLE users'", "ask"),
    ("sqlite3 app.db 'DROP TABLE users'", "ask"),
    ("crontab -r", "ask"),
    ("crontab jobs.txt", "ask"),
]

# Fetching or installing a package runs its code.
FETCHES_CODE = [
    ("npx some-random-package", "ask"),
    ("bunx some-random-package", "ask"),
    ("uvx some-random-package", "ask"),
    ("pip install some-random-package", "ask"),
    ("pip3 install -r requirements.txt", "ask"),
    ("uv pip install requests", "ask"),
    ("uv add requests", "ask"),
    ("pipx install httpie", "ask"),
    ("brew install jq", "ask"),
    ("nix-shell -p hello --run hello", "ask"),
]


@pytest.mark.parametrize("command,expected", WRAPPED + GIT + ACTS_ON_OTHERS + FETCHES_CODE)
def test_the_command_that_actually_runs_decides(root, command, expected):
    result = decide(command, root)
    assert result["decision"] == expected, f"{command}: {result['decision']} ({result['reason']})"


# What must stay automatic, or Auto stops being usable unattended.
STILL_ALLOWED = [
    "ls -la",
    "cat README.md",
    "grep -rn delete src",
    "grep send notes.txt",
    "git status",
    "git diff HEAD~1",
    "git log --oneline -5",
    "git show HEAD",
    "git add -A",
    "git commit -m 'drop the old cache'",
    "git checkout -b feature",
    "git restore --staged app.py",
    "git stash list",
    "git clean -n",
    "git config user.name",
    "git --version",
    "pytest -q tests/unit/test_one.py",
    "pytest -k delete",
    "timeout 60 pytest -q",
    "nice pytest",
    "uv run pytest -q",
    "npx vitest run",
    "co --help",
    "co status",
    "co browser status",
    "co create my-agent",
    "co gcalendar list",
    "co gcalendar create 'Focus time' 2026-10-01T09:00:00Z 2026-10-01T10:00:00Z",
    "co gmail inbox",
    "co outlook calendar today",
    "co gdrive list",
    "co syno shares",
    "co env show",
    "co trust list",
    "command -v rm",
    "env FOO=1 pytest -q",
    "pip list",
    "crontab -l",
    "gh pr view 12",
    "gh api repos/me/proj",
    "echo delete",
    "swiftlint lint",
    "just build",
    "xcodebuild -list",
]


@pytest.mark.parametrize("command", STILL_ALLOWED)
def test_ordinary_work_still_runs_unattended(root, command):
    result = decide(command, root)
    assert result["decision"] == "allow", f"{command}: {result['reason']}"


def test_a_wrapped_deletion_is_reported_as_the_deletion(root):
    # An operator reading the refusal should see the rm, not a mystery about nice.
    assert decide("nice rm -rf ~", root)["effect_class"] == "deletion"
