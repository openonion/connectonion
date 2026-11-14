"""
Purpose: `co auth asana` — make and save an Asana personal access token with the co browser, from the sign-in you already have, instead of asking you to find the developer console
LLM-Note:
  Dependencies: imports from [getpass, json, os, re, sys, tempfile, time, webbrowser, datetime, pathlib, useful_tools/asana.py (Asana, AsanaError, KEY, TOKEN_PAGE), environment.py, secret_store.py, cli/commands/command_tips.py | lazy: cli/commands/browser_import.handle_browser_import, cli/browser_agent/client._request] | imported by [cli/main.py via the auth command] | tested by [tests/unit/test_asana_auth.py]
  Data flow: a token that already answers /users/me → say who it acts as, done | otherwise, on the system-Chrome engine of co browser: (asked once) co browser import --domain asana.com → open_browser → go_to TOKEN_PAGE → while the URL is a sign-in page, wait for the person to sign in → a page script presses "Create new token" and names it → the person ticks Asana's API terms and presses Create in that window → a page script finds the token-shaped text → GET /users/me with it → encrypted to the store `co env set --secret` uses → once it is the token in use, that tab is replaced by "Asana authorization complete. You may close this tab." (as `co auth google`'s callback page) | any browser step that fails or times out → the developer console in the default browser and one hidden paste
  State/Effects: creates one personal access token in the person's Asana account (Asana does it, when the person presses Create) | writes ASANA_ACCESS_TOKEN encrypted under ~/.co/keys/secrets only after Asana accepted it | the import carries asana.com cookies only | page scripts are written to a 0700 temp dir and removed
  Integration: exposes handle_asana_auth(); the token it saves is the one `co asana` and `co rem` already read, so `co asana check` passes straight after
  Errors: exit 1 when the token in use afterwards is not a working new one (refused, no agent key, a write that failed, a shell export that still wins); an encrypted record that will not open is replaced, not a stop, 130 on Ctrl-C; every exit says whether a token may already exist in Asana | the token is never printed, never put on a command line, and never shown to a model: the page scripts return it to this process only, and only while the page is https://app.asana.com's developer console

Why the browser, and why the person still presses Create: Asana's OAuth needs a
client secret held by a server, so a CLI alone cannot use it. A personal access
token can only be made in the developer console, where Asana asks the person to
accept its API terms; that click stays theirs. Everything around it -- finding
the page, carrying the sign-in over, opening the dialog, naming the token,
reading it back and saving it -- is done here.
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
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from .command_tips import print_tip

ENGINE = "system"            # free, local Chrome; never the billed engine
WAIT_SIGN_IN = 300           # seconds the person has to sign in
WAIT_CREATE = 300            # seconds the person has to tick the terms and press Create
POLL = 2.0
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
  let named = false;
  const dialog = document.querySelector('[role="dialog"]') || document;
  const field = [...dialog.querySelectorAll('input[type="text"], input:not([type])')].filter(visible)
    .find((el) => !el.value);
  if (field && opened) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    setter.call(field, args.name);
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));
    named = true;
  }
  return { tab: !!tab, opened: !!opened, named };
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
# The whole page becomes one line, as `co auth google`'s callback page does. The
# console behind it (with the new token on screen) is gone from the tab as well.
DONE_JS = r"""(args) => {
  try { window.stop(); } catch (e) {}
  document.documentElement.innerHTML =
    '<head><meta charset="utf-8"><title></title></head><body><pre style="margin:8px"></pre></body>';
  document.title = args.text;
  document.querySelector("pre").textContent = args.text;
  return { shown: document.body.innerText.trim() === args.text };
}"""


# -- the browser -------------------------------------------------------------

def _browser(line: str) -> tuple:
    """(exit code, payload) from the co browser daemon; nothing is printed. Replaced in tests."""
    from ..browser_agent.client import _request
    return _request(line, engine_mode=ENGINE)


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
    answer = input("Use your Chrome sign-in for Asana (copies asana.com cookies only)? [Y/n] ").strip().lower()
    if answer not in ("", "y", "yes"):
        return
    from .browser_import import handle_browser_import
    try:
        copied = handle_browser_import(["--domain", "asana.com", "--engine", ENGINE, "--yes"]) == 0
    except PermissionError:
        # macOS keeps other apps' data from a terminal that lacks Full Disk Access.
        print("macOS did not let this terminal read Chrome's cookies (System Settings → Privacy & Security "
              "→ Full Disk Access allows it).")
        copied = False
    except Exception as error:  # noqa: BLE001 - the sign-in can still be done in the window
        print(f"Chrome cookies could not be read ({type(error).__name__}).")
        copied = False
    if not copied:
        print("Chrome sign-in was not carried over; you can sign in in the window instead.")


# How far the browser got: whether a stop must say Asana may hold a new token
# ("form"), and whether the token came from the co browser tab ("browser").
PROGRESS = {"form": False, "browser": False}


def token_from_browser() -> str:
    """A new token read from the developer console, or _BrowserFailed."""
    _carry_sign_in()
    code, payload = _browser("open_browser")
    if code == 6:
        raise _BrowserFailed("co browser is running on another engine; `co browser close` frees it")
    if code != 0:
        raise _BrowserFailed(str(payload)[:200])
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
            print("Sign in to Asana in the browser window that opened. Waiting up to 5 minutes…")
            if not _wait(lambda: _signed_in(url()), WAIT_SIGN_IN):
                raise _BrowserFailed("not signed in to Asana in time")
            _browser(f"go_to {_quote(_token_page())}")
        if not _on_console(url()):
            raise _BrowserFailed("the page is not Asana's developer console")
        name = f"ConnectOnion co asana {date.today().isoformat()}"
        PROGRESS["form"] = True
        state = _run(open_dialog, {"name": name})
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
        PROGRESS["browser"] = True
        return token
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _say_done_in_browser() -> None:
    """After the token is saved and in use: the co browser tab says so, like `co auth google`.

    Only the tab the token was read from, and only while it is still Asana's console;
    the terminal has already said the same, so a tab that cannot be changed is left alone.
    """
    if not PROGRESS["browser"]:
        return
    folder = Path(tempfile.mkdtemp(prefix="co-asana-auth-"))
    try:
        code, payload = _browser("get_current_url")
        if code != 0 or not _on_console(str(payload).strip()):
            return
        _run(_script(folder, "done.js", DONE_JS), {"text": DONE_TEXT})
    except Exception:  # noqa: BLE001 - a courtesy page; the token is already saved
        pass
    finally:
        shutil.rmtree(folder, ignore_errors=True)


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
    except Exception:  # noqa: BLE001 - no browser is fine; the link is printed
        pass
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return getpass.getpass("Paste the token (hidden): ").strip()


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
    except Exception as error:  # noqa: BLE001 - a broken env file is reported, not skipped
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
    from ...useful_tools.asana import _token
    try:
        return _token()
    except Exception:  # noqa: BLE001 - unset or unreadable: not the new token
        return ""


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


def _created_note() -> str:
    return (f" A token may already exist in Asana; revoke it at {_token_page()} if you will not use it."
            if PROGRESS["form"] else "")


def _connect() -> None:
    from ...environment import display_path
    from ...secret_store import SecretStoreError
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
    try:
        token = token_from_browser()
    except _BrowserFailed as why:
        print(f"The browser could not finish ({why}). Paste the token instead.{_created_note()}")
        token = token_from_paste()
    if not TOKEN_SHAPE.fullmatch(token or ""):
        raise _Stop("That is not an Asana personal access token; nothing was saved." + _created_note())
    user, error = _who(token)
    if not user:
        why = "Asana did not accept that token" if _refused(error) else f"Could not reach Asana ({error})"
        raise _Stop(f"{why}; nothing was saved.{_created_note()}")
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
    _say_done_in_browser()
    print(f"✓ Asana connected as {user.get('name') or '?'}; token encrypted to {display_path(path)}")
    print("  Revoke tokens you no longer use at " + _token_page())
    print_tip("Next: co asana check")


def handle_asana_auth() -> None:
    PROGRESS.update(form=False, browser=False)
    try:
        _connect()
    except _Stop as stop:
        _fail(str(stop), stop.next_step, stop.code)
    except (KeyboardInterrupt, EOFError) as event:
        stopped = "Stopped" if isinstance(event, KeyboardInterrupt) else "No input"
        print(file=sys.stderr)
        _fail(f"{stopped}; nothing was saved.{_created_note()}", "co auth asana",
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
