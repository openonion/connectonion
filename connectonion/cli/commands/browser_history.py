"""Recent Chrome visits, read from a temporary copy without starting a browser."""

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ...useful_tools.browser_tools import chrome_cookies as chrome

EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


def history_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="co browser history",
        description="Read Google Chrome visits on macOS. Reads a temporary copy of History; "
                    "never opens pages, starts a browser or makes network requests.",
        epilog='Example: co browser history --days 1 --json\n'
               'Example: co browser history --profile "Profile 1" --domain example.org --query team\n'
               'Back: co browser --help',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=7, metavar="N", help="look back N days (positive integer; default: 7)")
    parser.add_argument("--domain", metavar="SITE", help="only this domain and its subdomains")
    parser.add_argument("--query", metavar="TEXT", help="literal, case-insensitive text in title or URL; combines with --domain")
    parser.add_argument("--profile", default="Default", metavar="NAME",
                        help='Chrome folder ("Default", "Profile 1") or display name; default: Default')
    parser.add_argument("--json", action="store_true", help="print a JSON list of visits: time (UTC), title, URL")
    return parser


def read_history(profile: Path, days: int = 7) -> list[dict]:
    """One row per visit, newest first, including repeated visits to the same URL."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days) - EPOCH) // timedelta(microseconds=1)
    with tempfile.TemporaryDirectory(prefix="co-browser-history-") as temporary:
        copied = Path(temporary) / "History"
        shutil.copyfile(profile / "History", copied)
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = profile / ("History" + suffix)
            if sidecar.is_file():
                shutil.copyfile(sidecar, Path(temporary) / sidecar.name)
        with closing(sqlite3.connect(copied)) as db:
            rows = db.execute("SELECT visits.visit_time, urls.title, urls.url FROM visits "
                              "JOIN urls ON urls.id = visits.url WHERE visits.visit_time >= ? "
                              "ORDER BY visits.visit_time DESC, visits.id DESC", (cutoff,)).fetchall()
    return [{"time": (EPOCH + timedelta(microseconds=when)).isoformat(), "title": title or "", "url": url}
            for when, title, url in rows]


def matches_domain(url: str, domain: str) -> bool:
    wanted = (urlsplit(domain if "://" in domain else "//" + domain).hostname or "").strip(".").lower()
    host = (urlsplit(url).hostname or "").rstrip(".").lower()
    return bool(wanted) and (host == wanted or host.endswith("." + wanted))


def matches_query(visit: dict, query: str) -> bool:
    return query.casefold() in unquote(visit["title"] + " " + visit["url"]).casefold()


def handle_browser_history(args: list[str]) -> int:
    parser = history_parser()
    options = parser.parse_args(args)
    if options.days < 1:
        parser.error("--days must be a positive integer")
    if not chrome.is_macos():
        print("co browser history reads Google Chrome on macOS only.", file=sys.stderr)
        return 1
    profile = chrome.resolve_profile(chrome.chrome_root(), options.profile)
    visits = [visit for visit in read_history(profile, options.days)
              if (not options.domain or matches_domain(visit["url"], options.domain))
              and (not options.query or matches_query(visit, options.query))]
    if options.json:
        print(json.dumps(visits, ensure_ascii=False))
    else:
        for visit in visits:
            print(f"{visit['time']}\t{visit['title']}\t{visit['url']}")
    return 0
