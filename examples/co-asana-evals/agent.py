"""The agent `co eval` drives for the co-asana Usage Skill.

It has one tool, `co`, which runs real `co asana` command lines against a
synthetic workspace (fake_asana.py, data in
.co/benchmarks/fixtures/asana-atlas/workspace.json). No request leaves this
process and no real token is read: updates and comments change only the
in-memory copy, which is loaded fresh for every case, so `co asana task` after
`co asana update --yes` shows the change the way Asana would.

Why not the full `co ai` agent: on the rem-source-asana benchmark that agent
spent most of its steps reading git history and the workspace before acting.
A shell limited to `co asana` keeps the run on what this Skill teaches, and
cannot touch the user's real Asana however the model behaves.
"""

from pathlib import Path

from connectonion import Agent, after_user_input, host
from connectonion.useful_plugins import skill, skills

from fake_asana import Workspace, new_listings, run

HERE = Path(__file__).parent
WORKSPACE = HERE / ".co" / "benchmarks" / "fixtures" / "asana-atlas" / "workspace.json"
TODAY = "Tuesday 2026-11-03"

state = {}


def fresh_workspace(agent=None):
    state["workspace"] = Workspace.load(WORKSPACE)
    state["listings"] = new_listings()


def co(command: str, stdin: str = "") -> str:
    """Run one `co asana ...` command line in the user's terminal and return what it printed and its exit code.

    Only `co asana` commands are available (`co asana --help` lists them). Pass
    text for a `-` argument in stdin.
    """
    if "workspace" not in state:
        fresh_workspace()
    return run(command, state["workspace"], state["listings"], stdin=stdin or None)


SYSTEM = (f"You help the user with their Asana from a terminal. Today is {TODAY}. "
          "Your only tool runs `co asana` command lines. Answer from what the commands print.")


def build():
    return Agent("co-asana-eval", tools=[co, skill], system_prompt=SYSTEM,
                 plugins=[skills, [after_user_input(fresh_workspace)]])


host(build)
