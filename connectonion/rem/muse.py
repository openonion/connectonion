"""Follow one page's unread leads, or think through its cited originals."""

import json
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

from .config import read_config
from .evidence import INDEX, write_evidence
from .files import Notebook, RemError, read_json, state_path, write_json
from .investigate import gather, page_handles, project_paths
from .page_review import prose
from .reader_model import _source_ids, cited_context
from .project_material import stored
from .service import now, run_logs, subscriptions

ENRICH_DAYS = 3650
# 2026-10-20: gh paginated 1,346 PRs with comments in 36 s; 400 hid older history.
GITHUB_LIST_LIMIT = 5000
PERIOD_CHARS = 15_000
MAX_PERIODS = 6
INSIGHT = re.compile(r"verdict:\s*\**\s*insight\b", re.I)
MUSE_TURNS = ("Now do Turn 1 only.",
              *(f"Turn {n}: study chosen question {n - 1} (the next of your five). "
                "Follow the skill's Turns 2–6 rules." for n in range(2, 7)),
              "Last turn — look back, as the skill says.")


def ledger_dir(root, record) -> Path:
    # 2026-10-20: pages deepened in parallel in different categories can share a stem.
    return state_path(root, f"enrich/{Path(record).with_suffix('')}")


def _archive_note(root) -> str:
    return (f"Raw mail archive: {root}/.state/mail/messages (search with rg -il). "
            f"Attachments: {root}/.state/attachments.")


def _page(root: Path, record: str, stage: str, runner):
    notebook = Notebook(root)
    if not notebook.path(record).is_file():
        raise RemError(f"{record} does not exist; create a page before running {stage}.")
    if not record.startswith(("people/", "projects/", "orgs/")):
        raise RemError(f"{stage.capitalize()} needs a page under people/, projects/ or orgs/.")
    if runner is None:
        from . import runner as runner_module
        runner_module.check_skill(root, stage)
        runner = runner_module.run_stage
    return notebook, notebook.read(record), runner


def _page_item(root: Path, record: str, page: str) -> dict:
    return {"role": "page", "record": record, "source": "investigation:page", "timestamp": now().isoformat(),
            "text": f"The page as it stands, at {record}. Other pages of this notebook are under {root} "
                    "(people/, projects/, orgs/): read them for context, never edit them.\n\n" + page}


def _earlier_insights(page: str) -> list[dict]:
    """2026-10-21: a second muse round must add to the insights already on the page."""
    section = re.search(r'(?ms)^## Insight[ \t]*\n(.*?)(?=^## |^Investigation:|\Z)', prose(page))
    bullets = re.findall(r'(?m)^[-*] .*(?:\n[ \t]+\S.*)*', section[1] if section else '')
    bullets = [bullet for bullet in bullets if not re.fullmatch(r'[-*] Unknown(?: — not investigated yet)?', bullet)]
    if not bullets:
        return []
    return [{"role": "earlier-insights", "source": "investigation:earlier-insights", "timestamp": now().isoformat(),
             "text": "These Insight bullets are already on the page. Do not reword them. A new insight must "
                     "contradict, resolve or extend one of them with a fact it lacks, or be about something "
                     "none of them covers; say which in your reply.\n\n" + '\n'.join(bullets)}]


def _cited_originals(root: Path, page: str, supplied=()) -> list[dict]:
    # An attachment's or a GitHub item's context has no time or sender; only mail rows do.
    return [{"role": "cited-original", "source": source, "timestamp": context.get("time", ""),
             "speaker": context.get("sender", ""), "subject": context.get("subject", ""), "text": context["excerpt"]}
            for source, context in cited_context(root, [{"text": page}], private=True).items()
            if source not in supplied]


def _ledger_items(root, record) -> list[dict]:
    directory = ledger_dir(root, record)
    # A ledger written before category paths still serves a standalone muse.
    if not directory.exists():
        directory = state_path(root, f"enrich/{Path(record).stem}")
    index, originals = directory / INDEX, directory / "items.json"
    if not index.is_file() or not originals.is_file():
        return []
    page = Notebook(root).read(record)
    # Git history guides reading; it is not a retained citable original.
    source_ids = list(dict.fromkeys(item["source"] for item in read_json(originals, [])
                                    if item.get("source") and item.get("role") != "git-log"))
    sources = set(source_ids)
    cited = _source_ids([{"text": page}])
    uncited = sorted(sources - cited)
    ledger = {"role": "evidence-index", "source": "investigation:evidence", "timestamp": now().isoformat(),
            "file": str(index), "sources": source_ids,
            "text": (f"{len(sources)} reachable sources; the page already cites {len(sources & cited)} of them "
                     f"({len(cited)} cited source ids in total).\nUncited source ids (first 200 of {len(uncited)}):\n"
                     + "\n".join(uncited[:200])
                     + f"\n\nRead the full index at {index}: one line per evidence file; inside a file "
                     "each entry starts with `### <source id> · ...`, cite that id. "
                     f"Evidence files are under {directory}.")}
    return [ledger, {"role": "original_evidence", "source": "investigation:original-evidence",
                     "timestamp": now().isoformat(), "file": str(originals),
                     "text": f"Original gathered evidence for this page is retained at {originals}; "
                             "the evidence files above are its readable layout."}]


def _mapped_sessions(root, record) -> list[dict]:
    return [{"role": "user", "source": row["source"], "timestamp": row["timestamp"], "speaker": "owner",
             "project": row.get("cwd", ""), "text": row["text"]} for row in stored(root, record)]


def _github_checkouts(page) -> list[tuple[str, str]]:
    checkouts = []
    for path in dict.fromkeys(project_paths(page)):
        if not Path(path).is_dir():
            continue
        remote = subprocess.run(["git", "-C", path, "remote", "get-url", "origin"],
                                capture_output=True, text=True, timeout=120)
        match = re.fullmatch(r"(?:https?://|ssh://git@|git://|git@)github\.com[:/]"
                             r"([\w.-]+/[\w.-]+?)(?:\.git)?/?", remote.stdout.strip())
        if remote.returncode == 0 and match:
            checkouts.append((path, match[1]))
    return checkouts


def _github_item(repo, row, kind) -> dict:
    author = (row.get("author") or {}).get("login", "")
    text = (f"{row['url']}\nState: {row['state']}\nAuthor: {author}\nCreated: {row['createdAt']}\n"
            f"Title: {row['title']}\n\n{row.get('body') or ''}")
    for comment in row.get("comments", []):
        login = (comment.get("author") or {}).get("login", "")
        text += f"\n\n--- comment by {login} at {comment['createdAt']}\n{comment.get('body') or ''}"
    return {"role": "github", "source": f"github:{repo}#{row['number']}", "speaker": author,
            "kind": kind, "state": row["state"],
            "timestamp": row["createdAt"], "subject": row["title"], "text": text[:40_000]}


def _github_items(page, title="") -> tuple[list[dict], list[str]]:
    items, coverage = [], []
    repos = list(dict.fromkeys(repo for _, repo in _github_checkouts(page)))
    for repo in repos:
        if shutil.which("gh") is None:
            coverage.append(f"github {repo}: not read (gh is not installed)")
            continue
        rows = []
        for kind in ("issue", "pr"):
            result = subprocess.run(["gh", kind, "list", "-R", repo, "--state", "all", "--limit", str(GITHUB_LIST_LIMIT),
                                     "--json", "number,title,body,author,createdAt,state,url,comments"],
                                    capture_output=True, text=True, timeout=600)
            if result.returncode:
                coverage.append(f"github {repo}: not read ({result.stderr.strip()[:200]})")
                break
            rows.append([_github_item(repo, row, kind) for row in json.loads(result.stdout)])
        else:
            items.extend(item for group in rows for item in group)
            coverage.append(f"github {repo}: {len(rows[0])} issues, {len(rows[1])} pull requests")
    if len(title) >= 4:
        for owner in dict.fromkeys(repo.split("/")[0] for repo in repos):
            for history in (False, True):
                found, note = _github_search(owner, title, history=history)
                items.extend(found)
                coverage.append(note)
    unique = {}
    for item in items:
        unique.setdefault(item["source"], item)
    return list(unique.values()), coverage


def _github_search(owner, title, *, history=False) -> tuple[list[dict], str]:
    label = f'github {"history search" if history else "search"} {owner} "{title}"'
    if shutil.which("gh") is None:
        return [], f"{label}: not read (gh is not installed)"
    rows = []
    for kind in ("issues", "prs"):
        query = f"{title} in:title" if history else title
        order = ["--sort", "created", "--order", "asc"] if history else []
        result = subprocess.run(["gh", "search", kind, query, "--owner", owner, *order,
                                 "--limit", "300" if history else "100", "--json",
                                 "number,title,body,author,createdAt,state,url,repository"],
                                capture_output=True, text=True, timeout=120)
        if result.returncode:
            return [], f"{label}: not read ({result.stderr.strip()[:200]})"
        rows.append([_github_item(row["repository"]["nameWithOwner"], row,
                                  "pr" if kind == "prs" else "issue") for row in json.loads(result.stdout)])
    return ([item for group in rows for item in group],
            f"{label}: {len(rows[0])} issues, {len(rows[1])} pull requests")


def _git_log_items(page) -> list[dict]:
    items = []
    for path, _ in _github_checkouts(page):
        argv = ["git", "-C", path, "log", "origin/HEAD", "--date=short", "--format=%h %ad %an %s", "--", "."]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        if result.returncode:
            argv[4] = "HEAD"
            result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            items.append({"role": "git-log", "source": f"git-log:{path}", "timestamp": now().isoformat(),
                          "text": result.stdout})
    return items


def _about(item, title, repos) -> bool:
    """Its own repository's items, or another's that name it: best-match search hits
    on a word in a body filled the 2026-10-20 handoff timeline with unrelated work."""
    repo = item["source"].removeprefix("github:").partition("#")[0]
    return repo in repos or title.casefold() in item["subject"].casefold()


def _history_rows(page, github, title="") -> list[dict]:
    """A sub-project's commits must touch its mapped directory, not just its repository."""
    repos = {repo for _, repo in _github_checkouts(page)}
    rows = [{"date": item["timestamp"][:10], "kind": item["kind"],
             "line": f"{item['source']} {'PR' if item['kind'] == 'pr' else 'issue'} "
                     f"{item['state'].lower()}: {item['subject']}"}
            for item in github if _about(item, title, repos)]
    for path in dict.fromkeys(project_paths(page)):
        if not Path(path).is_dir():
            continue
        argv = ["git", "-C", path, "log", "origin/HEAD", "--first-parent", "--reverse",
                "--date=short", "--format=%h %ad %s", "--", "."]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        if result.returncode:
            argv[4] = "HEAD"
            result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                sha, date, subject = line.split(" ", 2)
                rows.append({"date": date, "kind": "commit", "line": f"commit {sha}: {subject}"})
    # Two mapped folders of one checkout list the same commits.
    return list({(row["date"], row["line"]): row for row in rows}.values())


def _history_months(rows) -> list[tuple[str, list[dict]]]:
    months = defaultdict(list)
    for row in rows:
        months[row["date"][:7]].append(row)
    return sorted(months.items())


def _periods(rows) -> list[tuple[str, str]]:
    """2026-10-20: four enrich rounds found only October decisions in a history since 2025-08.

    Budget consecutive months, leaving a busy month whole; beyond six periods,
    merge the smallest neighbours, allowing the merged periods to exceed the budget.
    """
    periods = []
    for month, entries in _history_months(rows):
        size = len(_timeline_text(entries))
        if periods and periods[-1][2] + size <= PERIOD_CHARS:
            first, _, previous_size = periods.pop()
            periods.append((first, month, previous_size + size))
        else:
            periods.append((month, month, size))
    while len(periods) > MAX_PERIODS:
        at = min(range(len(periods) - 1), key=lambda i: periods[i][2] + periods[i + 1][2])
        first, last = periods[at:at + 2]
        periods[at:at + 2] = [(first[0], last[1], first[2] + last[2])]
    return [(first, last) for first, last, _ in periods]


def _enrich_turns(periods) -> tuple[str, ...]:
    """2026-10-20: a 15k-character page had 12 quotes; its history never quoted the owner."""
    first, last = periods[0]
    own_words = ("for the period's most important decision, quote the user's own words from that period "
                 "if a session message or mail the user wrote says it (copy it exactly, in its language, "
                 "and cite it); if none exists, say so in your reply.")
    return (f"Read the page, the coverage and ledger items, and the skill; then study period 1 of "
            f"{len(periods)}: {first}–{last}. Read only this period of the timeline: read the originals its lines point to "
            "and add that period's turning points as dated, cited Key decisions lines. "
            f"Do not follow other leads yet. Also, {own_words}",
            *(f"Period {k} of {len(periods)}: {first}–{last}. Same as before; "
              f"do not repeat lines already on the page. Also, {own_words}"
              for k, (first, last) in enumerate(periods[1:], 2)),
            "Now follow the remaining leads as the skill says, check what you must not drop, and give the final reply.")


def _timeline_text(rows) -> str:
    """Keep every period visible even when a busy history needs fewer examples."""
    months = _history_months(rows)
    header = ("Project history, oldest first. Reading guide only: cite the `github:` ids; "
              "cite a commit as `git:<full sha>` (look it up with `git -C <path> show`).")
    # Every line while the whole history fits: a 6.5k timeline cut October's 40 handoff PRs to 12.
    for count in (None, 30, 12, 8, 5, 3, 1):
        lines = [header]
        for month, entries in months:
            commits = sum(row["kind"] == "commit" for row in entries)
            prs = sum(row["kind"] == "pr" for row in entries)
            issues = sum(row["kind"] == "issue" for row in entries)
            lines += [f"## {month} — {commits} commits, {prs} pull requests, {issues} issues"]
            ordered = sorted(entries, key=lambda row: (row["kind"] == "commit", row["date"]))
            lines += [f"- {row['date']} {row['line']}" for row in ordered[:count]]
        text = "\n".join(lines)
        if len(text) <= 60_000:
            return text
    # Even one unusually long subject per month can exceed the reading budget.
    fixed = "\n".join(line for line in lines if not line.startswith("- "))
    width = (60_000 - len(fixed) - len(months)) // len(months)
    if width < 0:
        raise RemError("Project timeline month headings exceed 60,000 characters")
    return "\n".join(line[:width] if line.startswith("- ") else line for line in lines)


def _outcome(notebook, record, before, result, *, items=0, coverage=()) -> dict:
    after = notebook.read(record)
    return {"record": record, "changed": [record] if after != before else [],
            "page_chars": [len(before), len(after)], "report": result.get("report", ""),
            "usage": result.get("usage"), "threads": result.get("threads", []),
            "repairs": result.get("repairs", 0), "repair_usage": result.get("repair_usage", {}),
            "items": items, "coverage": list(coverage)}


def enrich(root, record, *, runner=None, stage_progress=None) -> dict:
    notebook, page, runner = _page(root, record, "enrich", runner)
    if stage_progress:
        stage_progress("gathering sources")
    title, handles = page_handles(notebook, record)
    gathered, coverage = gather(
        title, handles, days=ENRICH_DAYS, clients={}, subscriptions=subscriptions(root), attachments_dir=None,
        mail_skipped="live mail is not searched by enrich; the saved mail archive was read",
        stage_progress=stage_progress, archive_root=root, record=record)
    timeline, periods = [], []
    if record.startswith("projects/"):
        sessions = _mapped_sessions(root, record)
        github, github_coverage = _github_items(page, title)
        logs = _git_log_items(page)
        rows = _history_rows(page, github, title)
        periods = _periods(rows)
        timeline = [{"role": "timeline", "source": "investigation:timeline", "timestamp": now().isoformat(),
                     "text": _timeline_text(rows)}]
        gathered = list({item["source"]: item for item in [*gathered, *sessions, *github, *logs]}.values())
        coverage += [f"mapped sessions: {len(sessions)} owner messages", *github_coverage,
                     f"git log: {len(logs)} checkouts read (reading guide only)"]
    directory = ledger_dir(root, record)
    shutil.rmtree(directory, ignore_errors=True)
    write_evidence(directory, gathered)
    write_json(directory / "items.json", gathered)
    ledger = _ledger_items(root, record)
    coverage_item = {"role": "coverage", "source": "investigation:coverage", "timestamp": now().isoformat(),
                     "text": "\n".join(coverage) + "\n" + _archive_note(root)}
    items = [_page_item(root, record, page), coverage_item, *timeline, *ledger,
             *_cited_originals(root, page, set(ledger[0]["sources"])), *_prior_runs(root, record)]
    if stage_progress:
        stage_progress("following leads")
    turns = {"turns": _enrich_turns(periods)} if len(periods) > 1 else {}
    result = runner(notebook, items, read_config(root), stage="enrich", stage_progress=stage_progress, **turns)
    return {**_outcome(notebook, record, page, result, items=len(gathered), coverage=coverage),
            "periods": len(periods)}


def _prior_runs(root: Path, record: str) -> list[dict]:
    logs = run_logs(root)
    reports = []
    for phase, label in (("enrich", "Open leads from enrich"), ("muse", "Questions the last muse run left")):
        latest = next((run for run in logs if run.get("phase") == phase and run.get("record") == record
                       and run.get("outcome") == "completed"), None)
        if latest and latest.get("report"):
            reports.append(f"## {label}\n{latest['report']}")
    return [{"role": "prior-runs", "source": "investigation:prior-runs", "timestamp": now().isoformat(),
             "text": "\n\n".join(reports)}] if reports else []


def muse(root, record, *, runner=None, stage_progress=None) -> dict:
    notebook, page, runner = _page(root, record, "muse", runner)
    originals = _cited_originals(root, page)
    ledger = _ledger_items(root, record) or [{
        "role": "evidence-index", "source": "investigation:evidence", "timestamp": now().isoformat(),
        "text": "No enrich ledger exists for this page yet."}]
    ledger[0]["text"] += "\n" + _archive_note(root)
    items = [_page_item(root, record, page), *_earlier_insights(page), *ledger, *originals, *_prior_runs(root, record)]
    result = runner(notebook, items, read_config(root), stage="muse", turns=MUSE_TURNS, stage_progress=stage_progress)
    # What the page had is guarded at promotion (page_review.dropped); a second, whole-page restore
    # here reverted accepted rounds on 2026-10-20, comparing a page re-numbered on save.
    return {**_outcome(notebook, record, page, result, items=len(originals)),
            "turns": len(MUSE_TURNS),
            "insights": sum(bool(INSIGHT.search(reply)) for reply in result.get("turn_replies", [])[1:-1])}
