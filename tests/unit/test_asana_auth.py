"""`co auth asana`: a personal access token, made in the co browser (or pasted), saved encrypted.

The browser daemon, Asana and the secret store are replaced: no Chrome, no
network, no keys. What matters is the order of steps, that the person's own
clicks are waited for, that a refused or missing token saves nothing, that the
token never reaches the terminal or a command line, and that the default leaves
the shared co browser as it found it: no token on screen, no Asana sign-in it
did not already have.
"""

import json
import shlex

import pytest

from connectonion.cli.commands import asana_auth
from connectonion.useful_tools.asana import AsanaError

pytestmark = pytest.mark.unit

TOKEN = "2/1220155493282912/1220189395633572:" + "a" * 32
OLD = "2/1220155493282912/1110000000000001:" + "b" * 32


class FakeBrowser:
    """Answers the daemon verbs asana_auth sends. `pages` is the URL sequence get_current_url returns.

    `cookies` are the cookie domains the co browser holds. A go_to anywhere but
    the developer console moves the tab there (`redirect` sends it elsewhere),
    and `cookies clear` clears the cookies of the page the tab is on, as the
    daemon does.
    """

    def __init__(self, pages=("https://app.asana.com/0/my-apps",), token_after=1, opened=True,
                 open_code=0, script_code=0, done_code=0, cookies=(), redirect=None):
        self.lines, self.pages, self.polls, self.done = [], list(pages), 0, []
        self.done_code = done_code
        self.token_after, self.opened = token_after, opened
        self.open_code, self.script_code = open_code, script_code
        self.cookies, self.redirect, self.at, self.cleared = list(cookies), redirect, None, []
        self.tabs = []           # the tab each line was sent to (None: the browser itself)

    def __call__(self, line, tab=asana_auth.TAB):
        self.lines.append(line)
        self.tabs.append(tab)
        argv = shlex.split(line)
        if argv[:2] == ["tab", "open"]:
            return 0, argv[2]
        if argv[0] == "open_browser":
            return self.open_code, "Browser opened" if self.open_code == 0 else "pinned to engine=wtf"
        if argv[0] == "go_to":
            if argv[1] != "https://app.asana.com/0/my-apps":
                self.at = self.redirect or argv[1]
            return 0, f"Navigated to {argv[1]}"
        if argv[0] == "get_current_url":
            if self.at:
                return 0, self.at
            return 0, self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]
        if argv[0] == "cookies" and argv[1:] == ["ls", "--all", "--domain", "asana.com", "--json"]:
            return 0, json.dumps([{"name": "ticket", "domain": "." + d, "path": "/", "value": "***"}
                                  for d in self.cookies])
        if argv[0] == "cookies" and argv[1:] == ["clear"]:
            from urllib.parse import urlparse
            host = urlparse(self.at or self.pages[0]).hostname
            self.cleared.append(host)
            self.cookies = [d for d in self.cookies if not (host == d or host.endswith("." + d))]
            return 0, "cleared"
        if argv[0] == "run_page_script":
            if self.script_code:
                return self.script_code, "Error: page closed"
            script = open(argv[1]).read()
            args = json.loads(argv[2])
            if "documentElement.innerHTML" in script:
                self.done.append(args["text"])
                return (0, json.dumps({"shown": True})) if self.done_code == 0 else (1, "Error: page closed")
            if "create new token" in script:
                return 0, json.dumps({"tab": True, "opened": self.opened, "named": self.opened})
            self.polls += 1
            assert args["shape"] == asana_auth.TOKEN_SHAPE.pattern
            return 0, json.dumps({"token": TOKEN if self.polls >= self.token_after else ""})
        raise AssertionError(f"unexpected browser line {line!r}")


@pytest.fixture
def world(monkeypatch):
    """No sleeping, no Chrome import, a fake Asana, fake credential sources and store."""
    state = {"shell": "", "file": "", "store": "", "dropped": [],
             "users": {TOKEN: {"gid": "1220155493282912", "name": "Eric z"}},
             "refused": set(), "down": False, "save_error": None, "ready_error": None}
    monkeypatch.setattr(asana_auth, "POLL", 0)
    monkeypatch.setattr(asana_auth, "_carry_sign_in", lambda: None)
    monkeypatch.setattr(asana_auth.webbrowser, "open", lambda url: True)
    monkeypatch.setattr(asana_auth, "_sources",
                        lambda: {k: state[k] for k in ("shell", "file", "store")})
    monkeypatch.setattr(asana_auth, "_sync_process", lambda token: None)
    monkeypatch.setattr(asana_auth, "_resolved",
                        lambda: asana_auth._in_use({k: state[k] for k in ("shell", "file", "store")})[0])

    def ready():
        if state["ready_error"]:
            raise asana_auth._Stop(state["ready_error"])

    def save(token):
        if state["save_error"]:
            raise state["save_error"]
        state["store"] = token
        return "~/.co/keys/secrets/asana_access_token.enc"

    def drop():
        state["dropped"].append(state["file"])
        state["file"] = ""
        return "~/.co/keys.env"

    def who(token):
        if state["down"]:
            return None, AsanaError("Cannot reach Asana", "co asana check")
        if token in state["refused"] or token not in state["users"]:
            return None, AsanaError("Asana rejected ASANA_ACCESS_TOKEN", "co auth asana", status=401)
        return state["users"][token], None

    monkeypatch.setattr(asana_auth, "_ready_to_save", ready)
    monkeypatch.setattr(asana_auth, "_save", save)
    monkeypatch.setattr(asana_auth, "_drop_from_file", drop)
    monkeypatch.setattr(asana_auth, "_who", who)
    return state


def _use(monkeypatch, browser):
    monkeypatch.setattr(asana_auth, "_browser", browser)
    return browser


def test_a_working_token_is_kept_and_no_new_one_is_made(world, monkeypatch, capsys):
    world["store"] = TOKEN
    browser = _use(monkeypatch, FakeBrowser())
    asana_auth.handle_asana_auth()
    assert "already connected as Eric z" in capsys.readouterr().out
    assert browser.lines == [] and world["store"] == TOKEN


def test_signed_in_browser_makes_reads_checks_and_saves_the_token(world, monkeypatch, capsys):
    browser = _use(monkeypatch, FakeBrowser(token_after=3))
    asana_auth.handle_asana_auth()
    out = capsys.readouterr()
    assert world["store"] == TOKEN
    assert "connected as Eric z" in out.out
    assert TOKEN not in out.out + out.err                         # never printed
    assert all(TOKEN not in line for line in browser.lines)       # never on a command line
    verbs = [shlex.split(line)[0] for line in browser.lines]
    assert verbs[:5] == ["open_browser", "tab", "cookies", "go_to", "get_current_url"]   # what it had, before anything
    assert shlex.split(browser.lines[3])[1] == "https://app.asana.com/0/my-apps"
    # Only the browser itself and its own tab are asked for; every page step is in that tab, never main.
    assert browser.tabs[:2] == [None, None] and set(browser.tabs[2:]) == {asana_auth.TAB}
    assert browser.polls == 3                                     # waited for the person to press Create
    assert "accept Asana's API terms" in out.out                  # the terms stay the person's click


def test_a_sign_in_page_is_waited_out_before_the_form(world, monkeypatch, capsys):
    browser = _use(monkeypatch, FakeBrowser(pages=["https://app.asana.com/-/login",
                                                  "https://app.asana.com/-/login",
                                                  "https://app.asana.com/0/my-apps"]))
    asana_auth.handle_asana_auth()
    assert "Sign in to Asana in the browser window" in capsys.readouterr().out
    assert [shlex.split(l)[0] for l in browser.lines].count("go_to") == 2   # back to the console after sign-in
    assert world["store"] == TOKEN


def test_a_form_it_cannot_find_asks_the_person_to_open_it(world, monkeypatch, capsys):
    _use(monkeypatch, FakeBrowser(opened=False))
    asana_auth.handle_asana_auth()
    assert 'Press "Create new token"' in capsys.readouterr().out
    assert world["store"] == TOKEN


@pytest.mark.parametrize("browser", [
    FakeBrowser(open_code=6),                       # daemon pinned to the billed engine
    FakeBrowser(script_code=1),                     # page closed mid-way
    FakeBrowser(token_after=10 ** 9),               # nobody pressed Create in time
])
def test_any_browser_failure_falls_back_to_a_hidden_paste(world, monkeypatch, capsys, browser):
    _use(monkeypatch, browser)
    monkeypatch.setattr(asana_auth, "WAIT_CREATE", 0)
    monkeypatch.setattr(asana_auth, "token_from_paste", lambda: TOKEN)
    asana_auth.handle_asana_auth()
    out = capsys.readouterr().out
    assert "Paste the token instead" in out and world["store"] == TOKEN


def test_the_billed_engine_is_never_asked_for(world, monkeypatch):
    seen = []

    def request(line, **kwargs):
        seen.append(kwargs.get("engine_mode"))
        return 6, "pinned"

    monkeypatch.setattr("connectonion.cli.browser_agent.client._request", request)
    monkeypatch.setattr(asana_auth, "token_from_paste", lambda: TOKEN)
    asana_auth.handle_asana_auth()
    assert seen == ["system"]


@pytest.mark.parametrize("pasted", ["", "not-a-token", "2/1/2:short"])
def test_something_that_is_not_a_token_saves_nothing(world, monkeypatch, pasted):
    _use(monkeypatch, FakeBrowser(open_code=1))
    monkeypatch.setattr(asana_auth, "token_from_paste", lambda: pasted)
    with pytest.raises(SystemExit) as exit_:
        asana_auth.handle_asana_auth()
    assert exit_.value.code == 1 and world["store"] == ""


def test_a_token_asana_refuses_saves_nothing(world, monkeypatch, capsys):
    world["refused"].add(TOKEN)
    _use(monkeypatch, FakeBrowser())
    with pytest.raises(SystemExit):
        asana_auth.handle_asana_auth()
    assert "Asana did not accept that token" in capsys.readouterr().err and world["store"] == ""


def test_an_unreachable_asana_does_not_replace_a_saved_token(world, monkeypatch, capsys):
    world["store"], world["down"] = OLD, True
    browser = _use(monkeypatch, FakeBrowser())
    with pytest.raises(SystemExit):
        asana_auth.handle_asana_auth()
    assert "Could not reach Asana" in capsys.readouterr().err
    assert browser.lines == [] and world["store"] == OLD


def test_a_refused_saved_token_is_replaced(world, monkeypatch, capsys):
    world["store"] = OLD
    world["refused"].add(OLD)
    _use(monkeypatch, FakeBrowser())
    asana_auth.handle_asana_auth()
    assert "refuses the saved token" in capsys.readouterr().out and world["store"] == TOKEN


def test_a_stale_token_in_the_env_file_is_removed_so_the_new_one_is_read(world, monkeypatch, capsys):
    """Review P2: saved encrypted, yet `co asana check` still read the old file value."""
    world["file"] = OLD
    world["refused"].add(OLD)
    _use(monkeypatch, FakeBrowser())
    asana_auth.handle_asana_auth()
    out = capsys.readouterr().out
    assert world["dropped"] == [OLD] and world["file"] == "" and world["store"] == TOKEN
    assert "Removed the old ASANA_ACCESS_TOKEN" in out and "connected as Eric z" in out


def test_a_refused_shell_export_stops_before_anything_is_created(world, monkeypatch, capsys):
    world["shell"] = OLD
    world["refused"].add(OLD)
    browser = _use(monkeypatch, FakeBrowser())
    with pytest.raises(SystemExit) as exit_:
        asana_auth.handle_asana_auth()
    err = capsys.readouterr().err
    assert exit_.value.code == 1 and browser.lines == [] and world["store"] == ""
    assert "unset ASANA_ACCESS_TOKEN" in err and "Nothing was created" in err


def test_success_is_only_claimed_when_the_new_token_is_the_one_read(world, monkeypatch, capsys):
    _use(monkeypatch, FakeBrowser())
    monkeypatch.setattr(asana_auth, "_drop_from_file", lambda: "~/.co/keys.env")   # the file keeps OLD
    world["file"], world["store"] = "", ""

    calls = []

    def sources():
        calls.append(1)
        found = {"shell": "", "file": OLD if len(calls) > 1 else "", "store": world["store"]}
        return found

    monkeypatch.setattr(asana_auth, "_sources", sources)
    with pytest.raises(SystemExit) as exit_:
        asana_auth.handle_asana_auth()
    out = capsys.readouterr()
    assert exit_.value.code == 1 and "connected as" not in out.out
    assert "still read first" in out.err and "co env unset ASANA_ACCESS_TOKEN" in out.err


def test_no_agent_key_stops_before_the_browser(world, monkeypatch, capsys):
    """Review P2: the store was checked only after a token had been made in Asana."""
    world["ready_error"] = "no agent key at ~/.co/keys/agent.key. Nothing was created in Asana"
    browser = _use(monkeypatch, FakeBrowser())
    with pytest.raises(SystemExit):
        asana_auth.handle_asana_auth()
    assert browser.lines == [] and "no agent key" in capsys.readouterr().err


def test_a_save_that_fails_says_the_token_exists_in_asana(world, monkeypatch, capsys):
    """Review P2: PermissionError escaped as a traceback."""
    world["save_error"] = PermissionError(13, "Permission denied")
    _use(monkeypatch, FakeBrowser())
    with pytest.raises(SystemExit) as exit_:
        asana_auth.handle_asana_auth()
    err = capsys.readouterr().err
    assert exit_.value.code == 1 and "Could not save the token" in err
    assert "exists in Asana" in err and "revoke" in err


@pytest.mark.parametrize("event, code, word", [(KeyboardInterrupt, 130, "Stopped"), (EOFError, 1, "No input")])
def test_cancelling_the_paste_says_so_and_what_may_exist(world, monkeypatch, capsys, event, code, word):
    """Review P2: Ctrl-C at the paste exited 130 with no message and no Next."""
    _use(monkeypatch, FakeBrowser(token_after=10 ** 9))
    monkeypatch.setattr(asana_auth, "WAIT_CREATE", 0)

    def paste():
        raise event()

    monkeypatch.setattr(asana_auth, "token_from_paste", paste)
    with pytest.raises(SystemExit) as exit_:
        asana_auth.handle_asana_auth()
    err = capsys.readouterr().err
    assert exit_.value.code == code and word in err and "Next: co auth asana" in err
    assert "may already exist in Asana" in err          # the form had been opened


def test_cancelling_before_the_form_does_not_mention_a_token(world, monkeypatch, capsys):
    _use(monkeypatch, FakeBrowser(open_code=1))
    monkeypatch.setattr(asana_auth, "token_from_paste", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(SystemExit):
        asana_auth.handle_asana_auth()
    assert "may already exist" not in capsys.readouterr().err


@pytest.mark.parametrize("url, signed_in, console", [
    ("https://app.asana.com/0/my-apps", True, True),
    ("https://app.asana.com/0/developer-console", True, True),
    ("https://app.asana.com/0/home/123", True, False),
    ("https://app.asana.com/-/login", False, False),
    ("http://app.asana.com/0/my-apps", False, False),
    ("https://app.asana.com.invalid.example/0/my-apps", False, False),
    ("https://evil.example/app.asana.com/0/my-apps", False, False),
    ("https://user@evil.example/?app.asana.com", False, False),
])
def test_only_https_app_asana_com_counts(url, signed_in, console):
    """Review P2: a substring check accepted app.asana.com.invalid.example."""
    assert asana_auth._signed_in(url) is signed_in and asana_auth._on_console(url) is console


def test_a_page_that_left_the_console_is_never_read(world, monkeypatch):
    browser = FakeBrowser(pages=["https://app.asana.com/0/my-apps", "https://app.asana.com/0/my-apps",
                                 "https://app.asana.com.invalid.example/0/my-apps"])
    _use(monkeypatch, browser)
    monkeypatch.setattr(asana_auth, "WAIT_CREATE", 0)
    monkeypatch.setattr(asana_auth, "token_from_paste", lambda: "")
    with pytest.raises(SystemExit):
        asana_auth.handle_asana_auth()
    assert browser.polls == 0 and world["store"] == ""


def test_page_scripts_are_removed_afterwards(world, monkeypatch):
    browser = _use(monkeypatch, FakeBrowser())
    asana_auth.handle_asana_auth()
    paths = [shlex.split(l)[1] for l in browser.lines if l.startswith("run_page_script")]
    assert paths and not any(__import__("os").path.exists(p) for p in paths)


def test_the_browser_tab_says_authorization_is_complete_after_the_save(world, monkeypatch, capsys):
    """Like `co auth google`'s callback page; the console with the token on it is replaced."""
    browser = _use(monkeypatch, FakeBrowser())
    asana_auth.handle_asana_auth()
    assert browser.done == ["Asana authorization complete. You may close this tab."]
    assert world["store"] == TOKEN
    verbs = [shlex.split(l)[0] for l in browser.lines]
    done = max(i for i, l in enumerate(browser.lines) if l.startswith("run_page_script"))
    assert verbs[done - 1] == "get_current_url"                           # checked it is still Asana first
    assert "connected as Eric z" in capsys.readouterr().out


def test_a_tab_that_left_asana_is_not_touched(world, monkeypatch):
    browser = _use(monkeypatch, FakeBrowser(pages=["https://app.asana.com/0/my-apps"] * 3
                                                 + ["https://example.com/"]))
    browser.token_after = 1
    asana_auth.handle_asana_auth()
    assert browser.done == [] and world["store"] == TOKEN


def test_a_done_page_that_fails_still_reports_success(world, monkeypatch, capsys):
    browser = _use(monkeypatch, FakeBrowser(done_code=1))
    asana_auth.handle_asana_auth()
    assert browser.done and world["store"] == TOKEN
    assert "connected as Eric z" in capsys.readouterr().out


def test_a_run_that_saved_nothing_still_clears_the_token_tab(world, monkeypatch, capsys):
    """Review of #3034: the new token stayed on screen in the shared browser when the run failed."""
    world["refused"].add(TOKEN)
    browser = _use(monkeypatch, FakeBrowser())
    with pytest.raises(SystemExit):
        asana_auth.handle_asana_auth()
    assert browser.done == [asana_auth.STOPPED_TEXT] and world["store"] == ""

    world["refused"].clear()
    _use(monkeypatch, FakeBrowser(script_code=1))
    monkeypatch.setattr(asana_auth, "token_from_paste", lambda: TOKEN)
    asana_auth.handle_asana_auth()
    assert world["store"] == TOKEN
    assert f"tab {asana_auth.TAB!r} could not be cleared; close it yourself" in capsys.readouterr().out


@pytest.mark.parametrize("error,said", [
    (PermissionError(1, "Operation not permitted", "/Users/x/Library/Application Support/Google/Chrome/Default/Cookies"),
     "Full Disk Access"),
])
def test_chrome_cookies_that_cannot_be_read_fall_back_to_signing_in_in_the_window(monkeypatch, capsys, error, said):
    """Real Mac run 11-12: a terminal without Full Disk Access got a traceback here."""
    from connectonion.cli.commands import browser_import
    monkeypatch.setattr(asana_auth.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "Y")

    def blocked(argv):
        raise error

    monkeypatch.setattr(browser_import, "handle_browser_import", blocked)
    asana_auth._carry_sign_in()                                    # no exception
    out = capsys.readouterr().out
    assert said in out and "sign in in the window instead" in out
    assert "Traceback" not in out and "/Users/x" not in out


def test_the_token_shape_matches_asana_and_nothing_else():
    assert asana_auth.TOKEN_SHAPE.fullmatch(TOKEN)
    for other in ("1220155493282912", "0/123/456", "2/12/34:" + "a" * 32, "Bearer " + TOKEN):
        assert not asana_auth.TOKEN_SHAPE.fullmatch(other)


def test_co_auth_lists_and_routes_asana(monkeypatch):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    called = []
    monkeypatch.setattr(asana_auth, "handle_asana_auth", lambda paste=False: called.append(paste))
    result = CliRunner().invoke(app, ["auth", "asana"])
    assert result.exit_code == 0 and called == [False]                  # the co browser first
    assert CliRunner().invoke(app, ["auth", "asana", "--paste"]).exit_code == 0 and called == [False, True]
    other = CliRunner().invoke(app, ["auth", "google", "--paste"])
    assert other.exit_code == 2 and "only supported for Asana" in other.output
    gone = CliRunner().invoke(app, ["auth", "asana", "--browser"])
    assert gone.exit_code == 2 and called == [False, True]              # the default needs no flag now
    unknown = CliRunner().invoke(app, ["auth", "nope"])
    assert "slack, asana" in unknown.output


# -- the real env file and encrypted store, in a temporary ~/.co -------------------

@pytest.fixture
def real_co(tmp_path, monkeypatch):
    """A temporary global ~/.co with an agent key and a keys.env; Asana and the browser are fakes."""
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "agent.key").write_bytes(bytes(range(32)))
    env = tmp_path / "keys.env"
    monkeypatch.setattr("connectonion.environment.global_config_dir", lambda: tmp_path)
    monkeypatch.setattr("connectonion.environment.selected_env_file", lambda: env)
    monkeypatch.setattr("connectonion.environment.process_environment", lambda: {})
    monkeypatch.setattr(asana_auth, "POLL", 0)
    monkeypatch.setattr(asana_auth, "_carry_sign_in", lambda: None)
    users = {TOKEN: {"gid": "1", "name": "Eric z"}}
    monkeypatch.setattr(asana_auth, "_who", lambda t: (users[t], None) if t in users else
                        (None, AsanaError("Asana rejected ASANA_ACCESS_TOKEN", "co auth asana", status=401)))
    monkeypatch.setattr(asana_auth, "_browser", FakeBrowser())
    return tmp_path, env


def test_real_files_the_stale_file_token_goes_and_the_new_one_is_what_is_read(real_co):
    from connectonion.environment import read_env_file
    from connectonion.secret_store import get
    co_dir, env = real_co
    env.write_text(f"OTHER=kept\nASANA_ACCESS_TOKEN={OLD}\n")
    asana_auth.handle_asana_auth()
    assert read_env_file(env) == {"OTHER": "kept"}
    assert get(co_dir, "ASANA_ACCESS_TOKEN") == TOKEN
    assert asana_auth._in_use(asana_auth._sources()) == (TOKEN, "store")


def test_real_files_an_unwritable_store_stops_before_the_browser(real_co, monkeypatch, capsys):
    co_dir, env = real_co
    (co_dir / "keys").chmod(0o500)
    browser = FakeBrowser()
    monkeypatch.setattr(asana_auth, "_browser", browser)
    try:
        with pytest.raises(SystemExit):
            asana_auth.handle_asana_auth()
    finally:
        (co_dir / "keys").chmod(0o700)
    assert browser.lines == [] and "not writable" in capsys.readouterr().err


def test_real_files_no_agent_key_stops_before_the_browser(real_co, monkeypatch, capsys):
    co_dir, env = real_co
    (co_dir / "keys" / "agent.key").unlink()
    browser = FakeBrowser()
    monkeypatch.setattr(asana_auth, "_browser", browser)
    with pytest.raises(SystemExit):
        asana_auth.handle_asana_auth()
    err = capsys.readouterr().err
    assert browser.lines == [] and "Next: co auth  then co auth asana" in err
    assert "co init" not in err                       # one Next, the one for this command group


def _loaded_into_this_process(monkeypatch, value):
    """What load_environment() does with a keys.env value: os.environ, marked as ours."""
    from connectonion import environment
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", value)
    monkeypatch.setitem(environment._loaded, "ASANA_ACCESS_TOKEN", value)


def _damage_store(co_dir):
    from connectonion.secret_store import _file_for
    path = _file_for(co_dir, "ASANA_ACCESS_TOKEN")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"v": 1, "index": 0, "ct": "bm90IGEgc2VhbGVkIGJveA=="}\n')
    return path


def test_real_files_this_process_reads_the_new_token_too(real_co, monkeypatch):
    """Review P2: connected, yet _token() in the same process still returned the old file value."""
    from connectonion import environment
    from connectonion.useful_tools.asana import _token
    co_dir, env = real_co
    monkeypatch.setattr("connectonion.environment.process_environment",
                        lambda: {k: v for k, v in __import__("os").environ.items()
                                 if environment._loaded.get(k) != v})
    env.write_text(f"ASANA_ACCESS_TOKEN={OLD}\n")
    _loaded_into_this_process(monkeypatch, OLD)
    asana_auth.handle_asana_auth()
    assert _token() == TOKEN
    assert "ASANA_ACCESS_TOKEN" not in env.read_text()


def test_real_files_a_shell_export_in_this_process_is_never_rewritten(real_co, monkeypatch, capsys):
    from connectonion import environment
    monkeypatch.setattr("connectonion.environment.process_environment",
                        lambda: {k: v for k, v in __import__("os").environ.items()
                                 if environment._loaded.get(k) != v})
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", OLD)          # exported, not loaded by us
    with pytest.raises(SystemExit):
        asana_auth.handle_asana_auth()
    assert __import__("os").environ["ASANA_ACCESS_TOKEN"] == OLD
    assert "unset ASANA_ACCESS_TOKEN" in capsys.readouterr().err


def test_real_files_a_damaged_store_under_a_working_token_is_never_opened(real_co, monkeypatch, capsys):
    """Review P2: a broken lower-priority record stopped co auth asana although the env file token works."""
    co_dir, env = real_co
    _damage_store(co_dir)
    env.write_text(f"ASANA_ACCESS_TOKEN={TOKEN}\n")
    monkeypatch.setattr("connectonion.secret_store.get", lambda *a: pytest.fail("store opened"))
    asana_auth.handle_asana_auth()
    assert "already connected as Eric z" in capsys.readouterr().out


def test_real_files_a_damaged_store_that_is_needed_is_replaced(real_co, capsys):
    """Review P2: the suggested co env unset never touched the encrypted record; a new token replaces it."""
    from connectonion.secret_store import get
    co_dir, env = real_co
    _damage_store(co_dir)
    asana_auth.handle_asana_auth()
    out = capsys.readouterr().out
    assert "cannot be opened" in out and "a new token will replace it" in out
    assert get(co_dir, "ASANA_ACCESS_TOKEN") == TOKEN
    assert "co env unset" not in out



# -- the co browser first; --paste never touches it -------------------------------

def test_paste_never_uses_the_co_browser(world, monkeypatch, capsys):
    """Review of #3063: the browser is the default, and --paste is the way around it entirely."""
    opened = []
    monkeypatch.setattr(asana_auth.webbrowser, "open", lambda url: opened.append(url) or True)
    monkeypatch.setattr(asana_auth.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(asana_auth.getpass, "getpass", lambda prompt="": TOKEN)
    browser = _use(monkeypatch, FakeBrowser())
    asana_auth.handle_asana_auth(paste=True)
    out = capsys.readouterr()
    assert browser.lines == [] and world["store"] == TOKEN
    assert opened == ["https://app.asana.com/0/my-apps"]
    assert "connected as Eric z" in out.out and TOKEN not in out.out + out.err


def _signs_in(browser, domains=("app.asana.com", "asana.com")):
    """What copying the Chrome sign-in (or signing in in the window) leaves in the co browser."""
    def carry():
        browser.cookies += list(domains)
    return carry


def test_an_asana_sign_in_this_run_brought_is_cleared_again(world, monkeypatch):
    browser = _use(monkeypatch, FakeBrowser())
    carried = []
    monkeypatch.setattr(asana_auth, "_carry_sign_in", lambda: (carried.append(1), _signs_in(browser)()))
    asana_auth.handle_asana_auth()
    assert carried == [1] and world["store"] == TOKEN
    assert browser.cookies == [] and set(browser.cleared) == {"app.asana.com", "asana.com"}
    clears = [i for i, l in enumerate(browser.lines) if l == "cookies clear"]
    for i in clears:                       # each clear only after a go_to an Asana site and a check of where it landed
        assert browser.lines[i - 1] == "get_current_url" and browser.lines[i - 2].startswith("go_to https://")


def test_an_asana_sign_in_the_co_browser_already_had_is_left_alone(world, monkeypatch):
    browser = _use(monkeypatch, FakeBrowser(cookies=["app.asana.com"]))
    monkeypatch.setattr(asana_auth, "_carry_sign_in", lambda: pytest.fail("nothing to copy"))
    asana_auth.handle_asana_auth()
    assert world["store"] == TOKEN and browser.cookies == ["app.asana.com"]
    assert "cookies clear" not in browser.lines


def test_a_stopped_run_clears_the_tab_and_the_sign_in_too(world, monkeypatch, capsys):
    browser = _use(monkeypatch, FakeBrowser(token_after=10 ** 9))
    monkeypatch.setattr(asana_auth, "_carry_sign_in", _signs_in(browser))
    monkeypatch.setattr(asana_auth, "WAIT_CREATE", 0)
    monkeypatch.setattr(asana_auth, "token_from_paste", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(SystemExit) as exit_:
        asana_auth.handle_asana_auth()
    assert exit_.value.code == 130 and world["store"] == ""
    # Over before the paste waited: the tab says so and the sign-in is gone while the person pastes.
    assert browser.done[-1] == asana_auth.FALLBACK_TEXT and browser.cookies == []
    assert "may already exist in Asana" in capsys.readouterr().err


def test_a_page_that_left_asana_is_never_cleared(world, monkeypatch, capsys):
    """`cookies clear` clears the tab's current site: a redirect elsewhere must not lose that site's login."""
    browser = _use(monkeypatch, FakeBrowser(redirect="https://mail.example/"))
    monkeypatch.setattr(asana_auth, "_carry_sign_in", _signs_in(browser, ("app.asana.com",)))
    asana_auth.handle_asana_auth()
    assert "cookies clear" not in browser.lines and browser.cookies == ["app.asana.com"]
    assert "1 asana.com cookie site(s) are still in the co browser" in capsys.readouterr().out


def test_each_run_keeps_its_own_state(world, monkeypatch, capsys):
    """Review of #3034: a module-level PROGRESS carried one run's form into the next."""
    assert not hasattr(asana_auth, "PROGRESS")
    _use(monkeypatch, FakeBrowser(token_after=10 ** 9))
    monkeypatch.setattr(asana_auth, "WAIT_CREATE", 0)
    monkeypatch.setattr(asana_auth, "token_from_paste", lambda: "")
    with pytest.raises(SystemExit):
        asana_auth.handle_asana_auth()
    assert "may already exist" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        asana_auth.handle_asana_auth(paste=True)         # paste, no form: nothing may exist
    assert "may already exist" not in capsys.readouterr().err


def test_co_auth_help_says_what_asana_copies_and_where_the_token_goes():
    """Review of #3034: the help said tokens go to the env file and never mentioned Chrome cookies."""
    from click import unstyle
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    text = " ".join(unstyle(CliRunner().invoke(app, ["auth", "--help"]).output).split())
    assert "co auth asana" in text and "encrypted" in text
    assert "Chrome cookies for asana.com" in text and "removes them afterwards" in text
    assert "--paste" in text and "co browser is not used at all" in text


def test_default_run_end_to_end_on_a_fake_console(world, monkeypatch, capsys):
    """Review of #3063: the default path, start to finish: sign-in carried, form named, token read,
    checked and saved, the tab replaced by one line, and the Asana cookies this run brought cleared."""
    browser = _use(monkeypatch, FakeBrowser(token_after=2))
    order = []
    monkeypatch.setattr(asana_auth, "_carry_sign_in",
                        lambda: (order.append(("carry", list(browser.cookies))), _signs_in(browser)()))
    asana_auth.handle_asana_auth()
    out = capsys.readouterr()
    assert order == [("carry", [])]                          # copied only after seeing it held no Asana sign-in
    assert browser.lines.index("cookies ls --all --domain asana.com --json") < browser.lines.index(
        next(l for l in browser.lines if l.startswith("go_to")))
    assert world["store"] == TOKEN and browser.polls == 2
    assert set(browser.done) == {asana_auth.DONE_TEXT}       # the token is not left on screen
    last_go_to = max(i for i, l in enumerate(browser.lines) if l.startswith("go_to"))
    assert browser.lines[last_go_to] == "go_to about:blank"   # after clearing, the line is the last page
    assert any(l.startswith("run_page_script") for l in browser.lines[last_go_to:])
    assert browser.cookies == [] and set(browser.cleared) == {"app.asana.com", "asana.com"}
    assert "co auth asana --paste skips the browser" in out.out
    assert f"named it 'co on {asana_auth._host()} " in out.out
    assert "connected as Eric z" in out.out and TOKEN not in out.out + out.err


class _NoCookieAnswer(FakeBrowser):
    """A co browser that opens but cannot say which cookies it holds."""

    def __call__(self, line, tab=asana_auth.TAB):
        if line.startswith("cookies ls"):
            self.lines.append(line)
            return 1, "Error: cookies unavailable"
        return super().__call__(line, tab)


@pytest.mark.parametrize("browser", [FakeBrowser(open_code=1), _NoCookieAnswer()],
                         ids=["co-browser-unavailable", "cookies-unknown"])
def test_when_the_co_browser_cannot_be_used_it_falls_back_to_paste_and_copies_nothing(
        world, monkeypatch, capsys, browser):
    _use(monkeypatch, browser)
    monkeypatch.setattr(asana_auth, "_carry_sign_in", lambda: pytest.fail("no cookies may be copied"))
    monkeypatch.setattr(asana_auth, "token_from_paste", lambda: TOKEN)
    asana_auth.handle_asana_auth()
    out = capsys.readouterr().out
    assert "Paste the token instead" in out and world["store"] == TOKEN
    assert "cookies clear" not in browser.lines and not any(l.startswith("go_to") for l in browser.lines)
    assert "may already exist" not in out                    # no form opened, so no token was made


def test_paste_with_a_browser_that_would_fail_never_touches_it(world, monkeypatch):
    browser = _use(monkeypatch, FakeBrowser(open_code=1))
    monkeypatch.setattr(asana_auth, "token_from_paste", lambda: TOKEN)
    asana_auth.handle_asana_auth(paste=True)
    assert browser.lines == [] and world["store"] == TOKEN


# -- review of #3063: clean-up before the paste, cookies, own tab, pipes, the form ---------

def test_a_failed_browser_is_cleaned_up_before_the_paste_waits(world, monkeypatch):
    """The tab and a copied sign-in must not stay while the person is still pasting."""
    browser = _use(monkeypatch, FakeBrowser(token_after=10 ** 9))
    monkeypatch.setattr(asana_auth, "_carry_sign_in", _signs_in(browser))
    monkeypatch.setattr(asana_auth, "WAIT_CREATE", 0)
    seen = {}

    def paste():
        seen["done"], seen["cookies"] = list(browser.done), list(browser.cookies)
        return TOKEN

    monkeypatch.setattr(asana_auth, "token_from_paste", paste)
    asana_auth.handle_asana_auth()
    assert seen["done"] and seen["done"][-1] == asana_auth.FALLBACK_TEXT and seen["cookies"] == []
    assert world["store"] == TOKEN
    assert browser.done.count(asana_auth.FALLBACK_TEXT) == len(browser.done)   # cleaned once, not again


def test_a_tab_that_cannot_be_seen_at_the_end_is_handed_to_the_person(world, monkeypatch, capsys):
    class LostTab(FakeBrowser):
        def __call__(self, line, tab=asana_auth.TAB):
            if line == "get_current_url" and self.polls >= 1:
                self.lines.append(line)
                return 1, "Error: target closed"
            return super().__call__(line, tab)

    _use(monkeypatch, LostTab())
    asana_auth.handle_asana_auth()
    assert f"Could not see the co browser tab {asana_auth.TAB!r}; close it yourself" in capsys.readouterr().out


def test_asana_cookies_without_a_sign_in_fall_back_to_paste_instead_of_waiting(world, monkeypatch, capsys):
    """A sign-in typed now would be mixed with cookies it already had and could not be cleared alone."""
    browser = _use(monkeypatch, FakeBrowser(pages=["https://app.asana.com/-/login"], cookies=["asana.com"]))
    monkeypatch.setattr(asana_auth, "_carry_sign_in", lambda: pytest.fail("nothing may be copied"))
    monkeypatch.setattr(asana_auth, "WAIT_SIGN_IN", 10 ** 6)
    monkeypatch.setattr(asana_auth, "token_from_paste", lambda: TOKEN)
    asana_auth.handle_asana_auth()
    out = capsys.readouterr().out
    assert "has Asana cookies but is not signed in" in out and "Sign in to Asana in the browser" not in out
    assert "cookies clear" not in browser.lines and browser.cookies == ["asana.com"]
    assert world["store"] == TOKEN


@pytest.mark.parametrize("answer", ["", "{}", "null", "[1]", '{"cookies": []}', "not json"])
def test_a_cookie_answer_that_is_not_a_list_counts_as_unknown(answer, world, monkeypatch):
    class OddAnswer(FakeBrowser):
        def __call__(self, line, tab=asana_auth.TAB):
            if line.startswith("cookies ls"):
                self.lines.append(line)
                return 0, answer
            return super().__call__(line, tab)

    browser = _use(monkeypatch, OddAnswer())
    monkeypatch.setattr(asana_auth, "_carry_sign_in", lambda: pytest.fail("nothing may be copied"))
    monkeypatch.setattr(asana_auth, "token_from_paste", lambda: TOKEN)
    asana_auth.handle_asana_auth()
    assert world["store"] == TOKEN and "cookies clear" not in browser.lines
    assert not any(l.startswith("go_to") for l in browser.lines)


def test_the_new_token_is_named_after_this_computer_and_the_day(world, monkeypatch):
    sent = []
    browser = _use(monkeypatch, FakeBrowser())
    real_run = asana_auth._run
    monkeypatch.setattr(asana_auth, "_run", lambda path, args: (sent.append(args), real_run(path, args))[1])
    monkeypatch.setattr(asana_auth, "_host", lambda: "studio")
    asana_auth.handle_asana_auth()
    form = next(a for a in sent if "name" in a)
    assert form["name"].startswith("co on studio 20") and form["hint"] == asana_auth.PAGE_HINT
    assert browser.lines and world["store"] == TOKEN


def _pipe(monkeypatch, data=None):
    import io, os
    read, write = os.pipe()
    if data is not None:
        os.write(write, data.encode())
    stdin = io.TextIOWrapper(io.FileIO(read, "r"))
    monkeypatch.setattr(asana_auth.sys, "stdin", stdin)
    return write


def test_a_pipe_that_sends_the_token_is_read(world, monkeypatch):
    import os
    os.close(_pipe(monkeypatch, TOKEN + "\n"))
    assert asana_auth.token_from_paste() == TOKEN


def test_an_open_pipe_that_sends_nothing_stops_instead_of_hanging(world, monkeypatch, capsys):
    """A chat runner keeps stdin open and never writes: the paste must not wait for ever."""
    import os
    write = _pipe(monkeypatch)
    monkeypatch.setattr(asana_auth, "PIPE_WAIT", 0.05)
    _use(monkeypatch, FakeBrowser())
    try:
        with pytest.raises(SystemExit) as exit_:
            asana_auth.handle_asana_auth(paste=True)
    finally:
        os.close(write)
    err = capsys.readouterr().err
    assert exit_.value.code == 1 and world["store"] == ""
    assert "No token arrived on standard input" in err and "No input; nothing was saved" in err
