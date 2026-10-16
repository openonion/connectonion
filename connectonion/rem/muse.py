"""Follow one page's unread leads, or think through its cited originals."""

import re
import shutil
import uuid
from pathlib import Path

from .config import read_config
from .evidence import write_evidence
from .files import Notebook, RemError, state_path
from .investigate import gather, page_handles
from .page_review import QUOTE, _listed_sources, prose
from .reader_model import _source_ids, cited_context
from .service import now, run_logs, subscriptions

ENRICH_DAYS = 3650
MUSE_TURNS = ("Now do Turn 1 only.",
              *(f"Turn {n}: study chosen question {n - 1} (the next of your five). "
                "Follow the skill's Turns 2–6 rules." for n in range(2, 7)),
              "Last turn — look back, as the skill says.")


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


def _cited_originals(root: Path, page: str, supplied=()) -> list[dict]:
    return [{"role": "cited-original", "source": source, "timestamp": context["time"],
             "speaker": context["sender"], "subject": context.get("subject", ""), "text": context["excerpt"]}
            for source, context in cited_context(root, [{"text": page}], private=True).items()
            if source not in supplied]


def _ledger(laid_out: dict, page: str) -> dict:
    sources = set(laid_out["sources"])
    cited = _source_ids([{"text": page}])
    uncited = sorted(sources - cited)
    index = laid_out["index"]
    return {"role": "evidence-index", "source": "investigation:evidence", "timestamp": now().isoformat(),
            "file": str(index), "sources": laid_out["sources"],
            "text": (f"{len(sources)} reachable sources; the page already cites {len(sources & cited)} of them "
                     f"({len(cited)} cited source ids in total).\nUncited source ids (first 200 of {len(uncited)}):\n"
                     + "\n".join(uncited[:200]) + "\n\n" + index.read_text(encoding="utf-8")[:30_000]
                     + f"\nRead the full index at {index}; evidence files are under {index.parent}. ")}


def _outcome(notebook, record, before, result, *, items=0, coverage=()) -> dict:
    after = notebook.read(record)
    return {"record": record, "changed": [record] if after != before else [],
            "page_chars": [len(before), len(after)], "report": result.get("report", ""),
            "usage": result.get("usage"), "threads": result.get("threads", []),
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
    directory = state_path(root, f"evidence/{uuid.uuid4().hex}")
    try:
        ledger = _ledger(write_evidence(directory, gathered), page)
        coverage_item = {"role": "coverage", "source": "investigation:coverage", "timestamp": now().isoformat(),
                         "text": "\n".join(coverage) + f"\nRaw mail archive: {root}/.state/mail/messages "
                                 f"(search with rg -il). Attachments: {root}/.state/attachments."}
        items = [_page_item(root, record, page), coverage_item, ledger,
                 *_cited_originals(root, page, set(ledger["sources"]))]
        result = runner(notebook, items, read_config(root), stage="enrich", stage_progress=stage_progress)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    return _outcome(notebook, record, page, result, items=len(gathered), coverage=coverage)


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


def _quotes(page: str) -> set[str]:
    return set(QUOTE.findall(re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", prose(page))))


def _restore(notebook: Notebook, record: str, before: str) -> str:
    after = notebook.read(record)
    quotes = len(_quotes(before) - _quotes(after))
    sources = len(_listed_sources(before) - _listed_sources(after))
    if not quotes and not sources:
        return ""
    notebook.write(record, before)
    return (f"Muse lost {quotes} quote{'s' if quotes != 1 else ''} and "
            f"{sources} source id{'s' if sources != 1 else ''}; restored the page from the start of the run")


def muse(root, record, *, runner=None, stage_progress=None) -> dict:
    notebook, page, runner = _page(root, record, "muse", runner)
    originals = _cited_originals(root, page)
    items = [_page_item(root, record, page), *originals, *_prior_runs(root, record)]
    result = runner(notebook, items, read_config(root), stage="muse", turns=MUSE_TURNS, stage_progress=stage_progress)
    restored = _restore(notebook, record, page)
    return {**_outcome(notebook, record, page, result, items=len(originals)),
            "restored": restored, "turns": len(MUSE_TURNS)}
