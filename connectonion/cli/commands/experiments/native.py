"""Read-only adapters for official CLIs, using their own saved authentication."""

import shutil
import subprocess
from typing import Optional

import typer

from .api import ExperimentError, group

github_app = group(
    "github",
    "GitHub: read issues and pull requests through gh.",
    "install GitHub CLI, then gh auth login; gh selects its own account",
    "issues <owner/repo>",
)
dingtalk_app = group(
    "dingtalk",
    "DingTalk: read your identity and search colleagues through dws.",
    "install and sign in to the official dws CLI; dws selects its own profile",
    "whoami",
)


def run(program: str, args: list[str]):
    executable = shutil.which(program)
    if not executable:
        raise ExperimentError(f"Install the official {program} CLI before using this experiment.")
    result = subprocess.run([executable, *args], timeout=30)
    if result.returncode:
        raise typer.Exit(result.returncode)


@github_app.command("issues", epilog="Example: co github issues openonion/connectonion --limit 20")
def issues(
    repo: str = typer.Argument(..., help="Repository owner/name"),
    limit: int = typer.Option(20, min=1, max=100, help="Maximum issues returned"),
):
    """Read open issues using gh's account; return gh JSON unchanged. Read-only."""
    run("gh", ["issue", "list", "--repo", repo, "--limit", str(limit), "--json", "number,title,url,state,updatedAt"])


@github_app.command("pulls", epilog="Example: co github pulls openonion/connectonion")
def pulls(
    repo: str = typer.Argument(..., help="Repository owner/name"),
    limit: int = typer.Option(20, min=1, max=100, help="Maximum PRs returned"),
):
    """Read open pull requests using gh's account. Read-only."""
    run("gh", ["pr", "list", "--repo", repo, "--limit", str(limit), "--json", "number,title,url,state,updatedAt"])


@github_app.command("issue", epilog="Example: co github issue openonion/connectonion 2153")
def issue(
    repo: str = typer.Argument(..., help="Repository owner/name"),
    number: int = typer.Argument(..., min=1, help="Issue number"),
):
    """Read one issue, its body and comments using gh's account. Read-only."""
    run("gh", ["issue", "view", str(number), "--repo", repo, "--json", "number,title,body,url,state,comments"])


@dingtalk_app.command("whoami", epilog="Example: co dingtalk whoami")
def whoami(profile: Optional[str] = typer.Option(None, help="Saved dws profile; omitted uses dws's default")):
    """Read the authenticated DingTalk user's identity through dws. Read-only."""
    args = ["contact", "user", "get-self", "--format", "json"]
    if profile:
        args += ["--profile", profile]
    run("dws", args)


@dingtalk_app.command("people", epilog='Example: co dingtalk people "Alice"')
def people(
    query: str = typer.Argument(..., help="Colleague name/keyword"),
    profile: Optional[str] = typer.Option(None, help="Saved dws profile; omitted uses dws's default"),
):
    """Read colleague matches through dws; does not choose a recipient or send. Read-only."""
    args = ["contact", "user", "search", "--query", query, "--format", "json"]
    if profile:
        args += ["--profile", profile]
    run("dws", args)
