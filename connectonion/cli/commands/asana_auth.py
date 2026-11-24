"""
Purpose: `co auth asana` — save an Asana personal access token, made by default in the co browser from your Chrome sign-in (removed again afterwards); pasted with --paste, or when the co browser cannot finish
LLM-Note:
  Dependencies: imports from [dataclasses, getpass, json, os, re, shutil, sys, tempfile, time, webbrowser, datetime, pathlib, useful_tools/asana.py (Asana, AsanaError, KEY, TOKEN_PAGE), environment.py, env_file.py, secret_store.py, cli/commands/command_tips.py | lazy: cli/commands/browser_import.handle_browser_import, cli/browser_agent/client._request] | imported by [cli/main.py via the auth command] | tested by [tests/unit/test_asana_auth.py]
  Data flow: a token that already answers /users/me → say who it acts as, done | --paste: open the developer console in the default browser, one hidden paste | default, on the system-Chrome engine of co browser, in its own tab (co-auth-asana; the shared main tab is never driven): count asana.com cookies already there (cannot tell, or an answer that is not a list → paste instead, nothing copied or cleared; some but no sign-in → paste instead, since a sign-in typed now could not be cleared on its own) → (none, asked once) co browser import --domain asana.com → go_to TOKEN_PAGE → wait out a sign-in page → a page script opens "Create new token", waits for the dialog, names the token `co on <host> <date>` and marks the terms and the Create button → the person accepts Asana's API terms and presses Create → a page script reads the token-shaped text → back in this process for every check below; any browser step that fails → the browser part is cleaned up at once, then the same hidden paste (with no terminal, a pipe is read for at most PIPE_WAIT seconds) | then GET /users/me with it → encrypted to the store `co env set --secret` uses → only when it is the token `co asana` reads, success | on every way out once the co browser opened, once and before any paste: the console tab is replaced by one line (done, continuing in the terminal, or stopped) so the token is not left on screen, and when the co browser had no Asana cookies before, every asana.com cookie is cleared again, site by site, on pages that are verified to be asana.com first, after which the line is shown again on about:blank so it is the last page
  State/Effects: creates one personal access token in the person's Asana account (Asana does, when the person presses Create) | writes ASANA_ACCESS_TOKEN encrypted under ~/.co/keys/secrets only after Asana accepted it, and removes a stale one from the env file that would be read first | the default copies asana.com cookies only, and leaves the co browser's Asana cookies as it found them | page scripts are written to a 0700 temp dir and removed
  Integration: exposes handle_asana_auth(paste=False); the token it saves is the one `co asana` and `co rem` already read, so `co asana check` passes straight after
  Errors: exit 1 when the token in use afterwards is not a working new one (refused, no agent key, a write that failed, a shell export that still wins); an encrypted record that will not open is replaced, not a stop; 130 on Ctrl-C; every exit after the form opened says a token may already exist in Asana | the token is never printed, never put on a command line, and never shown to a model: the page scripts return it to this process only, and only while the page is https://app.asana.com's developer console

Why the browser first (#3063 review, 2026-11-21): every `co auth` lets the
machine do the work and leaves the person only what only a person can do.
Pasting is five steps (open the console, find the button, create, copy,
paste); in the co browser the person only accepts Asana's API terms and
presses Create. What made that acceptable as the default is the clean-up: the
co browser is left with exactly the Asana cookies it had, and the token is
never left on screen. Pasting stays for when the co browser is not there or
cannot tell what it holds, and for anyone who passes --paste. Asana's OAuth
needs a client secret held by a server, so a CLI alone cannot use it.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import sys
import tempfile
import time
import webbrowser
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from .command_tips import print_tip

ENGINE = "system"            # free, local Chrome; never the billed engine
TAB = "co-auth-asana"        # this command's own co browser tab, never the shared main one
WAIT_SIGN_IN = 300           # seconds the person has to sign in
WAIT_CREATE = 300            # seconds the person has to tick the terms and press Create
POLL = 2.0
PIPE_WAIT = 30               # seconds a pipe with no terminal may take to send a pasted token
# 2/<user gid>/<token gid>:<32 hex>, the shape Asana prints a new token in.
TOKEN_SHAPE = re.compile(r"\b\d+/\d{6,}/\d{6,}:[0-9a-f]{32}\b")
ASANA_HOST = "app.asana.com"
SIGN_IN_PATHS = ("/-/login", "/-/signup", "/-/sso", "/login", "/signin")
CONSOLE_PATHS = ("/0/my-apps", "/0/developer-console")

# Page scripts: plain DOM, matched by visible words, so a restyled console still works.
OPEN_DIALOG_JS = r"""(args) => {
  const words = (el) => (el.innerText || el.textContent || el.value || "").trim().toLowerCase();
  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const press = (patterns) => {
    const items = [...document.querySelectorAll('button, [role="button"], a, [role="tab"]')].filter(visible);
    const hit = items.find((el) => patterns.some((p) => words(el).includes(p)));
    if (hit) { hit.click(); return words(hit); }
    return "";
  };
  const tab = press(["personal access token"]);
  const opened = press(["create new token", "new access token", "create token", "+ new"]);
  // The dialog renders after the click (Asana, 2026-11-21: about a second later), so its
  // name field is waited for rather than looked up at once, which found nothing.
  const field = () => {
    const dialog = document.querySelector('[role="dialog"]');
    return dialog && [...dialog.querySelectorAll('input[type="text"], input:not([type])')].filter(visible)
      .find((el) => !el.value);
  };
  return new Promise((resolve) => {
    const started = Date.now();
    const attempt = () => {
      const found = opened && field();
      if (found) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
        setter.call(found, args.name);
        found.dispatchEvent(new Event("input", { bubbles: true }));
        found.dispatchEvent(new Event("change", { bubbles: true }));
        // Point at the two clicks that stay the person's, in the page as well as the terminal.
        const dialog = document.querySelector('[role="dialog"]');
        const mark = (el) => { if (el) { el.style.outline = "3px solid #f06a6a"; el.style.outlineOffset = "3px"; } };
        const terms = dialog.querySelector('input[type="checkbox"]');
        mark(terms && (terms.closest("label") || terms.parentElement || terms));
        const create = [...dialog.querySelectorAll('button, [role="button"]')].filter(visible)
          .find((el) => words(el) === "create token" || words(el).startsWith("create token"));
        mark(create);
        let pointed = false;
        if (args.hint) {
          const note = document.createElement("div");
          note.textContent = args.hint;
          note.setAttribute("data-co-hint", "");
          note.style.cssText = "margin:8px 0;padding:6px 8px;background:#fff3cd;color:#000;font-size:13px;";
          dialog.insertBefore(note, dialog.firstChild);
          pointed = true;
        }
        return resolve({ tab: !!tab, opened: !!opened, named: true, pointed: pointed && !!terms && !!create });
      }
      if (!opened || Date.now() - started > (args.wait || 5000)) return resolve({ tab: !!tab, opened: !!opened, named: false });
      setTimeout(attempt, 200);
    };
    attempt();
  });
}"""

FIND_TOKEN_JS = r"""(args) => {
  const shape = new RegExp(args.shape);
  const found = (text) => { const m = (text || "").match(shape); return m ? m[0] : ""; };
  for (const el of document.querySelectorAll("input, textarea, code, pre, [data-token], [readonly]")) {
    const hit = found(el.value) || found(el.textContent);
    if (hit) return { token: hit };
  }
  return { token: found(document.body ? document.body.innerText : "") };
}"""

DONE_TEXT = "Asana authorization complete. You may close this tab."
STOPPED_TEXT = "co auth asana stopped. You may close this tab."
FALLBACK_TEXT = "co auth asana continues in the terminal. You may close this tab."
# Said in the page too, next to what is marked: the terms and Create stay the person's clicks.
PAGE_HINT = "co auth asana: tick the API terms and press Create token. Nothing else is needed."
# The whole page becomes one line, as `co auth google`'s callback page does. The
# console behind it (with the new token on screen) is gone from the tab as well.
# The same page script ends a run that stopped, with STOPPED_TEXT: the new token is
# never left on screen in a shared browser.
DONE_JS = r"""(args) => {
  try { window.stop(); } catch (e) {}
  document.documentElement.innerHTML =
    '<head><meta charset="utf-8"><title></title></head><body><pre style="margin:8px"></pre></body>';
  document.title = args.text;
  document.querySelector("pre").textContent = args.text;
  return { shown: document.body.innerText.trim() === args.text };
}"""


# -- the browser -------------------------------------------------------------

def _browser(line: str, tab: str | None = TAB) -> tuple:
    """(exit code, payload) from the co browser daemon, in this command's own tab; nothing is printed.

    Replaced in tests. The shared main tab is never driven: other agents use it,
    and a page left there could be navigated away under them.
    """
    from ..browser_agent.client import _request
    return _request(line, tab=tab, engine_mode=ENGINE)


def _script(folder: Path, name: str, body: str) -> Path:
    path = folder / name
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)
    return path


def _run(path: Path, args: dict) -> dict:
    import shlex
    code, payload = _browser(f"run_page_script {shlex.quote(str(path))} {shlex.quote(json.dumps(args))}")
    if code != 0:
        raise _BrowserFailed(str(payload)[:200])
    try:
        result = json.loads(payload)
    except (TypeError, ValueError):
        raise _BrowserFailed("the page script did not answer") from None
    return result if isinstance(result, dict) else {}


class _BrowserFailed(Exception):
    """A browser step did not work; fall back to the paste."""


def _asana(url: str):
    """The parsed URL when it is https://app.asana.com exactly, else None."""
    try:
        parsed = urlparse(str(url).strip())
    except ValueError:
        return None
    return parsed if parsed.scheme == "https" and parsed.hostname == ASANA_HOST else None


def _signed_in(url: str) -> bool:
    parsed = _asana(url)
    return bool(parsed) and not parsed.path.startswith(SIGN_IN_PATHS)


def _on_console(url: str) -> bool:
    parsed = _asana(url)
    return bool(parsed) and parsed.path.startswith(CONSOLE_PATHS)


def _wait(check, seconds: float):
    """check() until it returns something truthy or the time is up; None then."""
    deadline = time.monotonic() + seconds
    while True:
        value = check()
        if value:
            return value
        if time.monotonic() >= deadline:
            return None
        time.sleep(POLL)


def _carry_sign_in() -> None:
    """asana.com cookies only, from Chrome, into the co browser profile; asked once."""
    if not sys.stdin.isatty():
        return
    answer = input("Copy your Chrome sign-in for Asana into the co browser (asana.com cookies only; "
                   "removed again when this finishes)? [Y/n] ").strip().lower()
    if answer not in ("", "y", "yes"):
        return
    from .browser_import import handle_browser_import
    try:
        copied = handle_browser_import(["--domain", "asana.com", "--engine", ENGINE, "--yes"]) == 0
    except PermissionError:
        # macOS keeps other apps' data from a terminal that lacks Full Disk Access;
        # every other failure is reported by the import itself as a non-zero exit.
        print("macOS did not let this terminal read Chrome's cookies (System Settings → Privacy & Security "
              "→ Full Disk Access allows it).")
        copied = False
    if not copied:
        print("Chrome sign-in was not carried over; you can sign in in the window instead.")


@dataclass
class Run:
    """What one `co auth asana` has done that its end must say or undo; one per run, never shared.

    form: the new-token form was opened, so Asana may already hold a token.
    browser: the co browser was opened by this run, so its tab is cleared at the end.
    clear_cookies: the co browser had no asana.com cookies before, so none are left after.
    saved: the new token is saved and is the one `co asana` reads.
    falling_back: the browser part failed and the paste takes over.
    ended: the browser part has been cleaned up; it is done once.
    """
    form: bool = False
    browser: bool = False
    clear_cookies: bool = False
    saved: bool = False
    falling_back: bool = False
    ended: bool = False


def _asana_cookie_domains() -> list[str] | None:
    """The cookie domains the co browser holds for asana.com, or None when it cannot say."""
    code, payload = _browser("cookies ls --all --domain asana.com --json")
    if code != 0:
        return None
    try:
        cookies = json.loads(payload)
    except (TypeError, ValueError):
        return None
    # An empty reply or one of another shape says nothing; only a list answers.
    if not isinstance(cookies, list) or not all(isinstance(c, dict) for c in cookies):
        return None
    return sorted({str(c.get("domain", "")).lstrip(".") for c in cookies if isinstance(c, dict)} - {""})


def _is_asana(url: str) -> bool:
    try:
        host = urlparse(str(url).strip()).hostname or ""
    except ValueError:
        return False
    return host == "asana.com" or host.endswith(".asana.com")


def _clear_asana_cookies() -> tuple:
    """Remove every asana.com cookie, one site at a time: (sites left or None when unknown, whether this tab moved).

    `cookies clear` clears the cookies of the tab's current page, so each site
    is opened first and its address checked: a page that ended up anywhere
    else is never cleared, and nothing is ever cleared without a site.
    """
    moved = False
    for domain in _asana_cookie_domains() or []:
        moved = True
        if _browser(f"go_to {_quote('https://' + domain + '/')}")[0] != 0:
            continue
        code, payload = _browser("get_current_url")
        if code == 0 and _is_asana(str(payload)):
            _browser("cookies clear")
    left = _asana_cookie_domains()
    return (None if left is None else len(left)), moved


def _end_browser(run: Run) -> None:
    """Every way out of a browser run: no token left on screen, no Asana sign-in left behind.

    Runs once, as soon as the browser part is over (before a paste fallback
    waits on the person, not after it). Courtesy and clean-up, never the
    result: each step that fails is said, and the run still ends with what
    happened to the token. The last thing this tab shows is the one line.
    """
    if not run.browser or run.ended:
        return
    run.ended = True
    text = DONE_TEXT if run.saved else FALLBACK_TEXT if run.falling_back else STOPPED_TEXT
    _show_line(text, console_only=True)
    if run.clear_cookies:
        left, moved = _clear_asana_cookies()
        if left:
            print(f"{left} asana.com cookie site(s) are still in the co browser; "
                  "co browser cookies ls --all --domain asana.com shows them.")
        elif left is None:
            print("Could not check the co browser for Asana cookies; "
                  "co browser cookies ls --all --domain asana.com shows them.")
        # Clearing opened each Asana site in this tab; the line goes back on top.
        if moved and _browser("go_to about:blank")[0] == 0:
            _show_line(text, console_only=False)


def _show_line(text: str, console_only: bool) -> None:
    """Replace this tab's page with one line; say so when that could not be done or checked."""
    folder = Path(tempfile.mkdtemp(prefix="co-asana-auth-"))
    try:
        code, payload = _browser("get_current_url")
        if code != 0:
            print(f"Could not see the co browser tab {TAB!r}; close it yourself.")
            return
        if console_only and not _on_console(str(payload).strip()):
            return          # a page that left Asana's console is not ours to rewrite
        _run(_script(folder, "done.js", DONE_JS), {"text": text})
    except _BrowserFailed:
        print(f"The co browser tab {TAB!r} could not be cleared; close it yourself.")
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def token_from_browser(run: Run) -> str:
    """A new token read from the developer console, or _BrowserFailed. _end_browser undoes what this did."""
    code, payload = _browser("open_browser", tab=None)
    if code == 6:
        raise _BrowserFailed("co browser is running on another engine; `co browser close` frees it")
    if code != 0:
        raise _BrowserFailed(str(payload)[:200])
    code, payload = _browser(f'tab open {TAB} --who {TAB} --for "co auth asana: make a token"', tab=None)
    if code != 0:
        raise _BrowserFailed(str(payload)[:200])
    run.browser = True
    before = _asana_cookie_domains()
    if before is None:
        # Unknown is not "none": the co browser may hold the person's own Asana
        # sign-in, which clearing at the end would remove. Nothing is copied or
        # cleared; the token is pasted instead.
        raise _BrowserFailed("could not tell which Asana cookies the co browser already has")
    # No Asana sign-in here before this run: whatever it leaves (copied or typed) goes again.
    run.clear_cookies = not before
    if not before:
        _carry_sign_in()
    folder = Path(tempfile.mkdtemp(prefix="co-asana-auth-"))
    try:
        open_dialog = _script(folder, "open_dialog.js", OPEN_DIALOG_JS)
        find_token = _script(folder, "find_token.js", FIND_TOKEN_JS)
        if _browser(f"go_to {_quote(_token_page())}")[0] != 0:
            raise _BrowserFailed("could not open the Asana developer console")

        def url() -> str:
            code, payload = _browser("get_current_url")
            return str(payload).strip() if code == 0 else ""

        if not _signed_in(url()):
            if not run.clear_cookies:
                # Asana cookies were here already but are no sign-in. A sign-in typed now
                # would be mixed with them and could not be cleared on its own.
                raise _BrowserFailed("the co browser has Asana cookies but is not signed in")
            print("Sign in to Asana in the browser window that opened. Waiting up to 5 minutes…")
            if not _wait(lambda: _signed_in(url()), WAIT_SIGN_IN):
                raise _BrowserFailed("not signed in to Asana in time")
            _browser(f"go_to {_quote(_token_page())}")
        if not _on_console(url()):
            raise _BrowserFailed("the page is not Asana's developer console")
        # "co on <host> <date>", as the #3063 review asked; joined from words because any
        # string that starts "co " is read as a command by the tip sweep, and this is a label.
        name = " ".join(("co", "on", _host(), date.today().isoformat()))
        run.form = True
        state = _run(open_dialog, {"name": name, "hint": PAGE_HINT})
        if state.get("opened"):
            print(f"Opened Asana's new-token form{' and named it ' + repr(name) if state.get('named') else ''}.")
        else:
            print("Press \"Create new token\" in the Asana window.")
        print("In that window, accept Asana's API terms and press Create token. Waiting up to 5 minutes…")
        def read() -> str:
            # Read only from Asana's own console: a page that moved elsewhere is not asked.
            if not _on_console(url()):
                return ""
            return _run(find_token, {"shape": TOKEN_SHAPE.pattern}).get("token") or ""

        token = _wait(read, WAIT_CREATE)
        if not token:
            raise _BrowserFailed("no new token appeared")
        return token
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _host() -> str:
    """This computer's short name, so the person can tell its token apart in Asana's list."""
    import socket
    return socket.gethostname().split(".")[0] or "this computer"


def _quote(text: str) -> str:
    import shlex
    return shlex.quote(text)


def _token_page() -> str:
    from ...useful_tools.asana import TOKEN_PAGE
    return TOKEN_PAGE


# -- the paste fallback --------------------------------------------------------

def token_from_paste() -> str:
    page = _token_page()
    print(f"Open {page} → Personal access tokens → Create new token, accept the terms, and copy it.")
    try:
        webbrowser.open(page)
    except webbrowser.Error:
        pass    # no browser is fine; the link is printed
    if not sys.stdin.isatty():
        return _piped()
    return getpass.getpass("Paste the token (hidden): ").strip()


def _piped() -> str:
    """One line from a pipe, waited for at most PIPE_WAIT seconds: an open pipe that never
    sends (a chat runner's stdin) is a stop, not a hang."""
    if os.name != "nt":            # select() cannot watch a pipe on Windows
        import select
        ready, _, _ = select.select([sys.stdin], [], [], PIPE_WAIT)
        if not ready:
            print(f"No token arrived on standard input within {PIPE_WAIT} s. Run co auth asana in a "
                  "terminal, or pipe the token in: co auth asana --paste < token.txt", file=sys.stderr)
            raise EOFError
    return sys.stdin.readline().strip()


# -- check and save --------------------------------------------------------------

class _Stop(Exception):
    """End as `co asana` does: `✗ <cause>`, then one `Next:` line, on stderr; this exit code."""

    def __init__(self, message: str, next_step: str = "co auth asana", code: int = 1):
        super().__init__(message)
        self.next_step, self.code = next_step, code


def _who(token: str) -> tuple:
    """(/users/me for this token, None) or (None, the AsanaError); 401 means the token is refused."""
    from ...useful_tools.asana import Asana, AsanaError
    try:
        return Asana(token).get_user("me"), None
    except AsanaError as error:
        return None, error


def _refused(error) -> bool:
    return getattr(error, "status", None) in (401, 403)


def _key() -> str:
    from ...useful_tools.asana import KEY
    return KEY


def _sources() -> dict:
    """Where ASANA_ACCESS_TOKEN can come from, in the order `co asana` reads them.

    shell: exported in the process, which this command cannot change; file: the
    selected env file; store: `co env set --secret`'s encrypted store. The store
    is opened only when nothing above it is set, as `co asana` does: a damaged
    record below a working token never stops anything. One that is needed and
    will not open is reported in store_unreadable; saving a new token replaces it.
    """
    from ...environment import global_config_dir, process_environment, read_env_file, selected_env_file
    from ...secret_store import SecretStoreError, get, stored_names
    key = _key()
    found = {"shell": (process_environment().get(key) or "").strip(), "file": "", "store": "",
             "store_unreadable": ""}
    try:
        found["file"] = (read_env_file(selected_env_file()).get(key) or "").strip()
    except (OSError, UnicodeError, ValueError) as error:
        raise _Stop(f"The env file cannot be read ({error})", "co env path") from None
    if found["shell"] or found["file"]:
        return found
    try:
        if key.lower() in stored_names(global_config_dir()):
            found["store"] = get(global_config_dir(), key).strip()
    except SecretStoreError as error:
        found["store_unreadable"] = str(error).split(" Next:")[0].rstrip(". ")
    return found


def _sync_process(token: str) -> None:
    """This process's view: a value loaded from the env file earlier is replaced, so code that
    keeps running here (an SDK, a host) reads the new token too. A shell export is never touched."""
    from ... import environment
    key = _key()
    if os.environ.get(key) and key not in environment.process_environment():
        environment.publish_values({key: token})


def _resolved() -> str:
    """The token `co asana` itself would use in this process, through its own lookup."""
    from ...secret_store import SecretStoreError
    from ...useful_tools.asana import AsanaError, _token
    try:
        return _token()
    except (AsanaError, SecretStoreError, OSError):
        return ""   # unset or unreadable: not the new token


def _in_use(found: dict) -> tuple:
    """(token, where) that `co asana` reads first, or ("", "")."""
    for where in ("shell", "file", "store"):
        if found[where]:
            return found[where], where
    return "", ""


def _ready_to_save() -> None:
    """Fail before anything is created in Asana when the token could not be stored."""
    from ...environment import global_config_dir
    from ...secret_store import MissingAgentKey, read_agent_key
    co_dir = global_config_dir()
    try:
        read_agent_key(co_dir)
    except MissingAgentKey as error:
        # The store's own text ends in "Next: co init"; `co auth` makes the same key (and
        # signs in), and it is the command group this person is already in.
        cause = str(error).split(" Next:")[0].rstrip(". ")
        raise _Stop(f"{cause}. Nothing was created in Asana", "co auth  then co auth asana") from None
    secrets = co_dir / "keys" / "secrets"
    folder = secrets if secrets.exists() else secrets.parent
    if not os.access(folder, os.W_OK):
        raise _Stop(f"{folder} is not writable, so a token could not be saved. Nothing was created in Asana",
                    f"chmod u+w {folder}  then co auth asana")


def _save(token: str) -> Path:
    from ...environment import global_config_dir
    from ...secret_store import put
    return put(global_config_dir(), _key(), token)


def _drop_from_file() -> Path:
    from ...env_file import upsert_env
    from ...environment import selected_env_file
    path = selected_env_file()
    upsert_env(path, {}, remove={_key()})
    return path


def _created_note(run: Run) -> str:
    return (f" A token may already exist in Asana; revoke it at {_token_page()} if you will not use it."
            if run.form else "")


def _connect(run: Run, paste: bool) -> None:
    key = _key()
    found = _sources()
    existing, where = _in_use(found)
    if existing:
        user, error = _who(existing)
        if user:
            print(f"✓ Asana already connected as {user.get('name') or '?'}; nothing was created.")
            print_tip("Next: co asana projects")
            return
        if not _refused(error):
            # Asana or the network failed: the token may be fine, so no new one is made.
            raise _Stop(f"Could not reach Asana to check the saved token ({error})")
        if where == "shell":
            raise _Stop(f"Your shell exports {key}, Asana refuses it, and it is read before anything saved. "
                        f"Nothing was created in Asana", f"unset {key}  then co auth asana")
        print("Asana refuses the saved token; making a new one.")
    elif found.get("store_unreadable"):
        print(f"The saved encrypted {key} cannot be opened ({found['store_unreadable']}); "
              "a new token will replace it.")
    _ready_to_save()
    if paste:
        _finish(token_from_paste(), found, run)
        return
    print("Making a token in the co browser (co auth asana --paste skips the browser).")
    try:
        try:
            token = token_from_browser(run)
        except _BrowserFailed as why:
            # The browser part is over: clear its tab and the sign-in now, not after the paste.
            run.falling_back = True
            _end_browser(run)
            print(f"The browser could not finish ({why}). Paste the token instead.{_created_note(run)}")
            token = token_from_paste()
        _finish(token, found, run)
    finally:
        _end_browser(run)


def _finish(token: str, found: dict, run: Run) -> None:
    """Check the new token with Asana, save it, and claim success only when it is the one read."""
    from ...environment import display_path
    from ...secret_store import SecretStoreError
    key = _key()
    if not TOKEN_SHAPE.fullmatch(token or ""):
        raise _Stop("That is not an Asana personal access token; nothing was saved." + _created_note(run))
    user, error = _who(token)
    if not user:
        why = "Asana did not accept that token" if _refused(error) else f"Could not reach Asana ({error})"
        raise _Stop(f"{why}; nothing was saved.{_created_note(run)}")
    revoke = f" The new token exists in Asana; revoke it at {_token_page()} or save it by hand."
    try:
        path = _save(token)
        if found["file"] and found["file"] != token:
            removed = _drop_from_file()
            print(f"Removed the old {key} from {display_path(removed)}; it was read before the saved one.")
    except (SecretStoreError, OSError) as error:
        raise _Stop(f"Could not save the token ({error}).{revoke}") from None
    _sync_process(token)
    # What a new `co asana` will read (same places, same order), and what this process reads.
    in_use, where = _in_use(_sources())
    if in_use == token and _resolved() != token:
        in_use, where = "", "this process"
    if in_use != token:
        place = {"shell": "your shell", "file": "the env file", "store": "the encrypted store",
                 "this process": "this process's environment"}.get(where, "nowhere")
        fix = (f"unset {key}" if where == "shell" else f"co env unset {key}" if where == "file"
               else "open a new terminal")
        raise _Stop(f"Saved, but {key} from {place} is still read first, so co asana would not use the "
                    "new token", f"{fix}  then co asana check")
    run.saved = True
    print(f"✓ Asana connected as {user.get('name') or '?'}; token encrypted to {display_path(path)}")
    print("  Revoke tokens you no longer use at " + _token_page())
    print_tip("Next: co asana check")


def handle_asana_auth(paste: bool = False) -> None:
    run = Run()
    try:
        _connect(run, paste)
    except _Stop as stop:
        _fail(str(stop), stop.next_step, stop.code)
    except (KeyboardInterrupt, EOFError) as event:
        stopped = "Stopped" if isinstance(event, KeyboardInterrupt) else "No input"
        print(file=sys.stderr)
        _fail(f"{stopped}; nothing was saved.{_created_note(run)}", "co auth asana",
              130 if isinstance(event, KeyboardInterrupt) else 1)


def _fail(cause: str, next_step: str, code: int) -> None:
    """The same two lines every `co asana` failure prints: `✗ <cause>` and `Next: <command>`."""
    from rich.markup import escape

    from .. import style
    from .command_tips import mark_next_step_named, selected_tip
    out = style.console(stderr=True)
    out.print(f"{style.error('✗')} {escape(cause.rstrip('. ') + '.')}")
    out.print(style.next_line(selected_tip(next_step)))
    mark_next_step_named()
    sys.exit(code)
