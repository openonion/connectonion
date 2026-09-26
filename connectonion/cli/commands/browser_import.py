"""
Purpose: `co browser import` — carry the logins (cookies) of a Chrome profile on this Mac into the co browser profile, through that browser's own cookie API.
LLM-Note:
  Dependencies: imports from [sys, json, shlex, tempfile, shutil, collections, useful_tools/browser_tools/chrome_cookies, useful_tools/browser_tools/engine | lazy: browser_agent.client._request, browser_commands._ensure_paid_client] | imported by [cli/main.py browser()] | tested by [tests/unit/test_browser_import.py]
  Data flow: parse_args → resolve the Chrome profile → read a private copy of its cookie DB → filter by --domain → print sites and counts (never values) → --dry-run stops | confirm once (TTY, or --yes) → Keychain key → decrypt → `open_browser` on the daemon → `cookies ls --all --json` (names only) to find sites the target is already signed in to → `cookies load FILE --all` per site from a 0600 file in a 0700 temp dir that is removed afterwards → per-site report
  State/Effects: reads the source profile only through a copy; writes cookies into the target browser via Playwright add_cookies in the daemon, never by editing its files | CO_BROWSER_SOCK / CO_BROWSER_PROFILE_DIR apply because every write goes through the same daemon client as other browser verbs | a real import starts a browser session (billed on the WTF Browser)
  Integration: exposes handle_browser_import(args, engine=None, headless=False) -> int and IMPORT_HELP | the daemon is reached through _daemon(), which tests replace
  Errors: exit 2 on usage or a missing confirmation, 1 when the source cannot be read or nothing could be written; a site whose batch the browser rejects is retried cookie by cookie so the report can say which ones and why
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from ...useful_tools.browser_tools import chrome_cookies as chrome

IMPORT_HELP = """\
co browser import — carry your Chrome logins into the co browser profile

  co browser import [--from chrome] [--profile NAME] [--domain SITE ...]
                    [--engine wtf|system] [--dry-run] [--yes] [--replace]

  --profile NAME   Chrome profile folder ("Default", "Profile 1") or the name
                   Chrome shows for it ("openonion"). Default: Default
  --domain SITE    only this site and its subdomains; repeat for more. Default: all
  --engine         the browser to import into. Default: the one `co browser config`
                   names, else wtf (the paid WTF Browser)
  --dry-run        list the sites and cookie counts, write nothing, touch no Keychain
  --yes            skip the confirmation (needed when there is no terminal)
  --replace        also import into sites the target is already signed in to

Writes cookies into the target browser's profile through its own cookie API
(Playwright add_cookies), so the target encrypts them its own way. Reads a copy
of Chrome's cookie database; the Chrome profile is never modified. Values are
never printed. macOS may ask to let `security` read "Chrome Safe Storage" from
the Keychain: that is the key Chrome encrypts cookies with. Choose Allow.

Limits: macOS and Google Chrome only. Cookies only: local storage, saved
passwords, history and extensions are not imported. A site that binds its
session to the device (Google, some banks) may still ask you to sign in.
A real import starts a browser session, and a WTF Browser session is billed.

Example:  co browser import --profile "Profile 1" --domain linkedin.com --dry-run
Example:  co browser import --profile "Profile 1" --domain linkedin.com
Back: co browser --help"""

_SWITCHES = {"--dry-run": "dry_run", "--yes": "yes", "-y": "yes", "--replace": "replace"}
_VALUES = {"--from": "source", "--profile": "profile", "--domain": "domains", "--engine": "engine"}


def wants_help(args: List[str]) -> bool:
    return any(token in ("-h", "--help", "help") for token in args)


def parse_args(args: List[str]) -> Optional[dict]:
    """The options as a dict, or None for a usage error."""
    options = {"source": "chrome", "profile": "Default", "domains": [], "engine": None,
               "dry_run": False, "yes": False, "replace": False}
    index = 0
    while index < len(args):
        token = args[index]
        index += 1
        flag, eq, inline = token.partition("=")
        if token in _SWITCHES:
            options[_SWITCHES[token]] = True
        elif flag in _VALUES:
            if eq:
                value = inline
            elif index < len(args):
                value, index = args[index], index + 1
            else:
                return None
            if flag == "--domain":
                options["domains"].append(_clean_domain(value))
            else:
                options[_VALUES[flag]] = value
        else:
            return None
    return options


def _clean_domain(value: str) -> str:
    """linkedin.com from `linkedin.com`, `.linkedin.com` or `https://www.linkedin.com/feed`."""
    value = value.strip().lower()
    if "://" in value:
        value = value.split("://", 1)[1]
    return value.split("/", 1)[0].lstrip(".")


def _engine_for(requested: Optional[str]) -> str:
    """wtf or system. The flag wins; then `co browser config`; else wtf, because
    carrying logins into the paid profile is what this command exists for."""
    from ...useful_tools.browser_tools.engine import SYSTEM, WTF, configured_mode, normalize_mode

    chosen = normalize_mode(requested) if requested else (configured_mode() or WTF)
    return SYSTEM if chosen == SYSTEM else WTF if chosen == WTF else chosen


def _daemon(line: str, *, engine_mode: str, headless: bool) -> tuple:
    """One request to the co browser daemon: (exit code, payload). Replaced in tests."""
    from ..browser_agent.client import _request

    kwargs = {"headless": headless}
    if engine_mode != "auto":
        kwargs["engine_mode"] = engine_mode
    return _request(line, **kwargs)


def _usage() -> int:
    print("usage: co browser import [--from chrome] [--profile NAME] [--domain SITE ...] "
          "[--engine wtf|system] [--dry-run] [--yes] [--replace]", file=sys.stderr)
    print("Next: co browser import --help", file=sys.stderr)
    return 2


def handle_browser_import(args: List[str], engine: Optional[str] = None, headless: bool = False) -> int:
    if wants_help(args):
        print(IMPORT_HELP)
        return 0
    options = parse_args(args)
    if options is None:
        return _usage()
    if engine and not options["engine"]:
        options["engine"] = engine
    if options["source"] != "chrome":
        print(f"--from {options['source']}: only chrome is supported in this version.", file=sys.stderr)
        return 2
    try:
        target = _engine_for(options["engine"])
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    if not chrome.is_macos():
        print("co browser import reads Google Chrome on macOS only in this version.", file=sys.stderr)
        return 1
    try:
        profile_dir = chrome.resolve_profile(chrome.chrome_root(), options["profile"])
        meta_version, cookies = chrome.read_cookies(profile_dir)
    except chrome.ChromeImportError as error:
        print(str(error), file=sys.stderr)
        return 1
    return _run(options, target, headless, profile_dir, meta_version, cookies)


def _run(options, target, headless, profile_dir, meta_version, cookies) -> int:
    domains = options["domains"]
    selected = [c for c in cookies if not domains or any(chrome.matches(c.host, d) for d in domains)]
    if not selected:
        wanted = ", ".join(domains) if domains else "any site"
        print(f"Chrome profile {profile_dir.name} has no cookies for {wanted}.", file=sys.stderr)
        print(f'Next: co browser import --profile "{profile_dir.name}" --dry-run', file=sys.stderr)
        return 1
    by_site: Dict[str, list] = defaultdict(list)
    skipped: Dict[str, Counter] = defaultdict(Counter)
    for cookie in selected:
        site = chrome.site_of(cookie.host, domains)
        reason = chrome.skip_reason(cookie)
        if reason:
            skipped[site][reason] += 1
        else:
            by_site[site].append(cookie)

    print(f"From Chrome profile {profile_dir.name} into the {target} browser:")
    for site in sorted(set(by_site) | set(skipped)):
        print(f"  {site:<32} {len(by_site[site])} cookie(s){_skips(skipped[site])}")
    print("Cookies only: local storage and saved passwords are not imported. Values are not shown.")
    if options["dry_run"]:
        print("Dry run: nothing was written and the Keychain was not read.")
        print(f"Next: {_again(options, profile_dir.name, dry_run=False)}")
        return 0
    if not by_site:
        print("Nothing left to import.", file=sys.stderr)
        return 1
    if not _confirmed(options, target, profile_dir.name):
        return 2
    return _write(options, target, headless, meta_version, by_site, skipped)


def _skips(reasons: Counter) -> str:
    if not reasons:
        return ""
    return "  (skipped " + ", ".join(f"{n} {why}" for why, n in sorted(reasons.items())) + ")"


def _again(options, profile: str, *, dry_run: bool, yes: bool = False) -> str:
    parts = ["--profile", profile]
    for domain in options["domains"]:
        parts += ["--domain", domain]
    if options["engine"]:
        parts += ["--engine", options["engine"]]
    if dry_run:
        parts.append("--dry-run")
    if yes:
        parts.append("--yes")
    return "co browser import " + shlex.join(parts)


def _confirmed(options, target: str, profile: str) -> bool:
    if options["yes"]:
        return True
    if not sys.stdin.isatty():
        print("Refusing to import without a confirmation, and there is no terminal to ask in.",
              file=sys.stderr)
        print(f"Next: {_again(options, profile, dry_run=False, yes=True)}", file=sys.stderr)
        return False
    note = " (starts a billed WTF Browser session)" if target == "wtf" else ""
    answer = input(f"Import these into the {target} browser{note}? "
                   "Sites it is already signed in to are left alone unless --replace. [y/N] ")
    if answer.strip().lower() in ("y", "yes"):
        return True
    print("Nothing imported.", file=sys.stderr)
    return False


def _write(options, target, headless, meta_version, by_site, skipped) -> int:
    print('macOS may now ask to let "security" read "Chrome Safe Storage" from your Keychain. '
          "Choose Allow: it is the key Chrome encrypts cookies with.", file=sys.stderr)
    try:
        key = chrome.derive_key(chrome.keychain_password())
    except chrome.ChromeImportError as error:
        print(str(error), file=sys.stderr)
        return 1
    ready: Dict[str, List[dict]] = {}
    for site, cookies in by_site.items():
        for cookie in cookies:
            value, reason = chrome.decrypt(cookie, key, meta_version)
            if value is None:
                skipped[site][reason] += 1
            else:
                ready.setdefault(site, []).append(chrome.to_playwright(cookie, value))

    engine_mode = "onion" if target == "wtf" else target
    if engine_mode == "onion":
        from .browser_commands import _ensure_paid_client

        failure = _ensure_paid_client()
        if failure is not None:
            print(failure, file=sys.stderr)
            return 1
        print("⏱  The WTF Browser bills for the session this starts.", file=sys.stderr)
    code, payload = _daemon("open_browser", engine_mode=engine_mode, headless=headless)
    if code:
        print(f"could not open the {target} browser: {payload}", file=sys.stderr)
        return code
    existing = _target_sites(engine_mode, headless, list(ready))
    if existing is None:
        return 1
    return _load_and_report(options, target, engine_mode, headless, ready, skipped, existing)


def _target_sites(engine_mode: str, headless: bool, sites: List[str]) -> Optional[Counter]:
    """How many cookies the target already holds per site. Names and domains are
    all that is read; the listing's values are shaped by the daemon anyway."""
    code, payload = _daemon("cookies ls --all --json", engine_mode=engine_mode, headless=headless)
    if code:
        print(f"could not read the target browser's cookies: {payload}", file=sys.stderr)
        return None
    held = Counter()
    for cookie in json.loads(payload or "[]"):
        host = str(cookie.get("domain", "")).lstrip(".")
        for site in sites:
            if chrome.matches(host, site):
                held[site] += 1
    return held


def _load_and_report(options, target, engine_mode, headless, ready, skipped, existing) -> int:
    scratch = Path(tempfile.mkdtemp(prefix="co-browser-import-"))  # 0700: the files are live logins
    written: Dict[str, int] = {}
    left_alone, replaced = [], []
    try:
        for site in sorted(ready):
            if existing[site] and not options["replace"]:
                left_alone.append(site)
                continue
            if existing[site]:
                replaced.append(site)
            written[site] = _load_site(scratch, site, ready[site], skipped[site],
                                       engine_mode=engine_mode, headless=headless)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print(f"Imported into the {target} browser:")
    for site in sorted(set(ready) | set(skipped)):
        if site in left_alone:
            print(f"  {site:<32} skipped: already signed in in the target "
                  f"({existing[site]} cookie(s) there). --replace imports over them")
            continue
        verb = "replaced with" if site in replaced else "wrote"
        print(f"  {site:<32} {verb} {written.get(site, 0)} cookie(s){_skips(skipped[site])}")
    if replaced:
        print("Replaced sites: cookies with the same name, domain and path were overwritten; "
              "other cookies the target held for them are still there.")
    print("A site that binds its session to the device may still ask you to sign in.")
    first = sorted(written)[0] if written else (sorted(left_alone) or sorted(ready))[0]
    print(f"Next: co browser --engine {target} go_to https://{first}")
    return 0 if any(written.values()) or left_alone else 1


def _load_site(scratch: Path, site: str, cookies: List[dict], reasons: Counter,
               *, engine_mode: str, headless: bool) -> int:
    """Load one site's cookies; if the browser rejects the batch, retry one by one
    so the report names which cookies it refused rather than failing the site."""
    code, _ = _load(scratch, site, cookies, engine_mode=engine_mode, headless=headless)
    if code == 0:
        return len(cookies)
    written = 0
    for index, cookie in enumerate(cookies):
        code, message = _load(scratch, f"{site}-{index}", [cookie], engine_mode=engine_mode, headless=headless)
        if code == 0:
            written += 1
        else:
            reasons[f"rejected by the browser ({cookie['name']}: {_scrub(message, cookie['value'])})"] += 1
    return written


def _load(scratch: Path, label: str, cookies: List[dict], *, engine_mode: str, headless: bool) -> tuple:
    path = scratch / f"{label}.json"
    # 0600 from the first byte: the file holds live logins until it is removed below.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"cookies": cookies, "origins": []}))
    try:
        return _daemon(shlex.join(["cookies", "load", str(path), "--all"]),
                       engine_mode=engine_mode, headless=headless)
    finally:
        path.unlink(missing_ok=True)


def _scrub(message: str, value: str) -> str:
    """The browser's reason, first line only, with the cookie's value taken out
    in case an error message ever echoes it."""
    line = (message or "no reason given").strip().splitlines()[0][:160]
    return line.replace(value, "…") if value else line
