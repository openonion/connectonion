"""The whole loop, as a user would live it, with nothing faked.

Tell Codex something -> `co wiki start` (real CLI process, real Codex + Spark
maintainer, real launchd job) -> ask a Codex that has the wiki-use Skill and
watch it answer from the notebook through `co wiki` -> correct yourself ->
sync -> the page changes -> sync again -> no model call -> stop -> nothing left.

Opt-in (real_api + provider_cli). Uses an isolated CODEX_HOME holding only a
copy of the operator's auth.json, so the "user's" sessions land in a temp
sessions directory and nothing here reads the operator's own history. The
launchd job it installs carries a root-specific label and is removed in
`finally`; if this test is killed mid-way, `co wiki --root <tmp> stop` cleans up.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from connectonion.skills_catalog import useful_skills_dir

pytestmark = [pytest.mark.real_api, pytest.mark.provider_cli, pytest.mark.timeout(900)]

SPARK = "gpt-5.3-codex-spark"


@pytest.fixture
def world(tmp_path):
    auth = Path.home() / ".codex" / "auth.json"
    if not auth.is_file() or not shutil.which("codex"):
        pytest.skip("needs a logged-in Codex CLI")
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700)
    shutil.copyfile(auth, codex_home / "auth.json")
    os.chmod(codex_home / "auth.json", 0o600)
    # The assistant side gets the wiki-use Skill exactly as it ships.
    shutil.copytree(useful_skills_dir() / "wiki-use", codex_home / "skills" / "wiki-use")
    project = tmp_path / "aurora"
    project.mkdir()
    env = {**os.environ, "CODEX_HOME": str(codex_home),
           "PATH": f"{Path(sys.executable).parent}:{os.environ.get('PATH', '')}",
           "PYTHONPATH": str(Path(__file__).resolve().parents[3])}
    return {"root": tmp_path / "wiki", "codex_home": codex_home, "project": project, "env": env}


def co(world, *args, check=True):
    result = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "wiki",
                             "--root", str(world["root"]), "--json", *args],
                            capture_output=True, text=True, env=world["env"], timeout=600)
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else {"stderr": result.stderr}


def tell_codex(world, prompt):
    """A real user session: non-interactive Codex, its rollout lands in codex_home/sessions."""
    result = subprocess.run(["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write", "-m", SPARK,
                             "-c", "shell_environment_policy.inherit=all", prompt],
                            cwd=world["project"], capture_output=True, text=True, env=world["env"], timeout=300)
    assert result.returncode == 0, result.stderr
    return result.stdout


def rollouts(world):
    return sorted((world["codex_home"] / "sessions").rglob("rollout-*.jsonl"))


def launchd_knows(label):
    return subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"],
                          capture_output=True, text=True).returncode == 0


def test_tell_start_ask_correct_stop(world):
    root = world["root"]
    label = None
    try:
        # 1. Tell.
        tell_codex(world, "Note for the record, no action needed: for Project Aurora we decided to store "
                          "notes as Markdown files rather than SQLite, because portability matters most. "
                          "Reply with one word: noted.")
        assert rollouts(world), "codex exec did not write a rollout under the isolated CODEX_HOME"

        # 2. Start: consent, first batch in the foreground, then the launchd job.
        started = co(world, "start", "--yes")
        assert started["ok"], started
        assert started["data"]["first_batch"]["outcome"] == "completed", started["data"]["first_batch"]
        label = started["data"]["label"]
        assert launchd_knows(label)
        hits = co(world, "search", "Aurora")["data"]
        assert hits, "nothing about Aurora was written"
        # Codex's own <recommended_plugins> block must not have become a page (it did once).
        assert not co(world, "search", "airtable")["data"]
        assert co(world, "list", "opportunities")["data"] == []
        page = co(world, "show", hits[0]["record"])["data"]
        assert "Markdown" in page and "portab" in page.lower(), page

        # 3. Ask: a Codex with the wiki-use Skill must reach the notebook through `co wiki`.
        answer = tell_codex(world, f"Use your wiki-use skill. The notebook root is {root}. "
                                   "Question: what did we decide about Project Aurora's storage, and why? "
                                   "Run the co wiki commands, then answer in two sentences and name the record path.")
        assert "markdown" in answer.lower(), answer
        assert "portab" in answer.lower(), answer
        ask_rollout = rollouts(world)[-1].read_text(encoding="utf-8")
        assert "co wiki" in ask_rollout, "the assistant answered without touching the notebook"

        # 4. Correct, sync: the page changes rather than gaining a contradicting twin.
        tell_codex(world, "Correction, no action needed: for Project Aurora the main reason for Markdown is "
                          "inspectability, not portability. Keep Markdown; SQLite was never adopted. Reply: noted.")
        synced = co(world, "sync")["data"]
        assert synced["outcome"] == "completed", synced
        pages = co(world, "list", "decisions")["data"] + co(world, "list", "projects")["data"]
        text = "\n".join(co(world, "show", record)["data"] for record in pages)
        assert "inspectab" in text.lower(), text
        aurora_pages = [record for record in pages if "aurora" in record.lower()]
        assert len(aurora_pages) <= 2, aurora_pages  # one project page, one decision page at most

        # 5. Nothing new: no model call.
        again = co(world, "sync")["data"]
        assert again["outcome"] == "no_change" and again["runner_attempts"] == 0, again

        # 6. The reader carries the current page.
        opened = co(world, "open", "--no-launch")["data"]
        assert "inspectab" in Path(opened["page"]).read_text(encoding="utf-8").lower()

        # 7. Logs tell the truth about what ran: two batches reached the model (the first
        # start and the correction). The no_change runs are ours from step 5 plus the one
        # the launchd job fired the moment it was loaded -- its presence is the evidence
        # that the background job runs at all.
        outcomes = [run["outcome"] for run in co(world, "logs")["data"]]
        assert outcomes.count("completed") == 2, outcomes
        assert outcomes.count("no_change") >= 2, outcomes
        assert set(outcomes) <= {"completed", "no_change"}, outcomes
        assert all(run["usage"] for run in co(world, "logs")["data"] if run["outcome"] == "completed")
    finally:
        stopped = co(world, "stop", check=False)
        if label:
            assert not launchd_knows(label), stopped
    assert co(world, "status")["data"]["state"].startswith("Stopped")


def test_launchd_tick_serves_a_slot(world):
    """The real clock: a saved time one minute ahead, the launchd tick (every
    TICK_SECONDS) notices it has come due and runs one batch; the tick after that
    runs nothing. No sessions exist, so no model is called. Takes ~TICK_SECONDS×2."""
    import time
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from connectonion.wiki.schedule import TICK_SECONDS

    label = None
    try:
        assert co(world, "config", "set", "schedule.timezone", "Australia/Sydney")["ok"]
        zone = ZoneInfo("Australia/Sydney")
        slot = (datetime.now(zone) + timedelta(minutes=1)).replace(second=0, microsecond=0)
        assert co(world, "config", "set", "schedule.times", slot.strftime("%H:%M"))["ok"]
        started = co(world, "start", "--yes")
        label = started["data"]["label"]
        assert launchd_knows(label)
        assert started["data"]["first_batch"]["outcome"] == "no_change"
        fired = None
        deadline = time.monotonic() + 2 * TICK_SECONDS + 60
        while time.monotonic() < deadline and fired is None:
            time.sleep(15)
            for run in co(world, "logs")["data"]:
                if datetime.fromisoformat(run["started_at"]).astimezone(zone) >= slot:
                    fired = run
        assert fired is not None, f"no scheduled run after the {slot:%H:%M} slot within two ticks"
        assert fired["outcome"] == "no_change" and fired["runner_attempts"] == 0
        # The tick that ran it recorded the slot as served; a manual scheduled tick is now quiet.
        assert co(world, "sync", "--scheduled")["data"] == {"due": False, "ran": False}
        assert co(world, "status")["data"]["worker"]["last_scheduled_slot"] == slot.isoformat()
    finally:
        co(world, "stop", check=False)
        if label:
            assert not launchd_knows(label)
