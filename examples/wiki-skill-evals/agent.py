"""The agent `co eval` drives for the Wiki's page skills: the same agent as `co ai`.

The Wiki runs these skills under Codex in production; `co eval` drives a
ConnectOnion Agent, so a run here tests the skill's text on this agent's
model, not the production model. Compare runs of the same benchmark before and
after a skill edit, never against a production run.

Every case starts with an empty out/. With pages left from earlier cases the
agent read them as examples instead of writing, and a second run of a case
found its own page already there, which `write` refuses to replace, and
spent its turns editing it line by line. A real investigation starts in a
fresh task directory too.
"""

import shutil
from pathlib import Path

from connectonion import after_user_input, host
from connectonion.cli.co_ai.agent import create_agent

OUT = Path(__file__).parent / "out"
# Kept for .co/benchmarks/check_pages.py, where `co eval run` keeps them from the agent.
WRITTEN = Path(__file__).parent / ".co" / "benchmarks" / "written"


def fresh_out(agent):
    WRITTEN.mkdir(parents=True, exist_ok=True)
    for page in OUT.glob("*.md"):
        shutil.move(str(page), WRITTEN / page.name)
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()


host(lambda: create_agent(role=None, extra_plugins=[[after_user_input(fresh_out)]]))
