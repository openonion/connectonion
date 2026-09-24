"""Unit tests for the `co browser network` and `co browser cookies` verbs.

LLM-Note: Tests for AsyncBrowserCore.network / AsyncBrowserCore.cookies and the daemon's token parsing

What it tests:
- `--key value` reaches a verb the same as `--key=value`; a bare bool flag stays a switch
- network requests filters by --type list and --status 2xx/400-499; a bad spec is a usage error
- network har start/stop names the file after the tab, writes valid HAR 1.2, shapes values unless --raw, is 0600
- a second har start does not discard the first recording; har stop with nothing recording says what to run
- cookies default to the tab's current site, --all widens, set/clear/save/load round-trip, values shaped
- a tab with no page open is told how to name a site instead of listing every cookie

Components under test:
- connectonion/useful_tools/browser_tools/_async_browser.py (network, cookies)
- connectonion/useful_tools/browser_tools/_async_network.py (HAR, cookies rendering)
- connectonion/cli/browser_agent/daemon.py (_split_tokens)
"""

import asyncio
import inspect
import json
import os
import stat
from pathlib import Path

import pytest

from connectonion.cli.browser_agent import daemon
from connectonion.useful_tools.browser_tools import _async_network as net
from connectonion.useful_tools.browser_tools._async_browser import AsyncBrowserCore


def run(coro):
    return asyncio.run(coro)


# ---- the daemon's token parsing ------------------------------------------------

def test_a_value_flag_takes_the_next_word_and_a_switch_does_not():
    params = list(inspect.signature(AsyncBrowserCore.network).parameters.values())[1:]

    positional, kwargs = daemon._split_tokens(
        ["requests", "--type", "xhr,fetch", "--status", "4xx", "--json", "--limit", "5"], params)

    assert positional == ["requests"]
    assert kwargs == {"type": "xhr,fetch", "status": "4xx", "json": True, "limit": "5"}


def test_a_switch_before_a_positional_leaves_the_positional_alone():
    params = list(inspect.signature(AsyncBrowserCore.network).parameters.values())[1:]

    positional, kwargs = daemon._split_tokens(["request", "--raw", "7"], params)

    assert positional == ["request", "7"]
    assert kwargs == {"raw": True}


def test_without_parameters_the_old_rules_hold():
    # Verbs whose signature is not passed keep `--flag` as True, as before.
    assert daemon._split_tokens(["x.com", "--full-page", "--index=2"]) == (
        ["x.com"], {"full_page": True, "index": "2"})


# ---- a core with fake Playwright objects -----------------------------------------

class FakeContext:
    """The subset of a Playwright BrowserContext the cookie verbs use."""

    def __init__(self, cookies):
        self.jar = [dict(c) for c in cookies]

    async def cookies(self, urls=None):
        if not urls:
            return [dict(c) for c in self.jar]
        hosts = {url.split("/")[2] for url in urls}
        return [dict(c) for c in self.jar if c["domain"].lstrip(".") in hosts]

    async def add_cookies(self, cookies):
        for cookie in cookies:
            if "url" in cookie:
                cookie = dict(cookie, domain=cookie["url"].split("/")[2], path="/")
                cookie.pop("url")
            self.jar.append(dict(cookie))

    async def clear_cookies(self, name=None, domain=None, path=None):
        self.jar = [c for c in self.jar if not (
            (name is None or c["name"] == name)
            and (domain is None or c["domain"] == domain)
            and (path is None or c["path"] == path))]


class FakePage:
    def __init__(self, url):
        self.url = url


JAR = [
    {"name": "sid", "value": "s3cr3t-session-value", "domain": "shop.test", "path": "/",
     "expires": -1, "httpOnly": True, "secure": True, "sameSite": "Lax"},
    {"name": "theme", "value": "dark", "domain": "shop.test", "path": "/",
     "expires": -1, "httpOnly": False, "secure": False, "sameSite": "Lax"},
    {"name": "other", "value": "elsewhere", "domain": "other.test", "path": "/",
     "expires": -1, "httpOnly": False, "secure": False, "sameSite": "Lax"},
]


@pytest.fixture
def core(tmp_path):
    browser = AsyncBrowserCore(headless=True)
    browser.browser = FakeContext(JAR)
    browser._pages["shop"] = FakePage("https://shop.test/cart")
    browser._network = net.NetworkLog(home=tmp_path)
    browser._bind_session("shop")
    return browser


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b'{"ok":true}'):
        self.status = status
        self.status_text = "OK" if status == 200 else "Not Found"
        self.ok = 200 <= status < 300
        self._headers = headers or {"content-type": "application/json"}
        self._body = body

    async def all_headers(self):
        return dict(self._headers)

    async def body(self):
        return self._body


class FakeRequest:
    def __init__(self, url, *, kind="xhr", method="GET", response=None, headers=None, post_data=None):
        self.url = url
        self.method = method
        self.resource_type = kind
        self.headers = headers or {"accept": "*/*"}
        self.post_data = post_data
        self.timing = {"startTime": 1789769685953.0, "responseEnd": 120.0}
        self._response = response or FakeResponse()

    async def response(self):
        return self._response


def capture(browser, request, key="shop"):
    run(browser._network._on_finished(request, key))


# ---- network requests -------------------------------------------------------------

def test_requests_filters_by_a_type_list_and_a_status_range(core):
    capture(core, FakeRequest("https://shop.test/api/a"))
    capture(core, FakeRequest("https://shop.test/api/b", kind="fetch", response=FakeResponse(404)))
    capture(core, FakeRequest("https://shop.test/app.js", kind="script",
                              response=FakeResponse(headers={"content-type": "text/javascript"})))

    listed = run(core.network("requests", type="xhr,fetch", status="4xx"))

    rows = [line for line in listed.splitlines() if line[:1].isdigit()]
    assert len(rows) == 1 and "/api/b" in rows[0]


def test_a_status_spec_that_means_nothing_is_a_usage_error_not_an_empty_list(core):
    with pytest.raises(ValueError, match="200, 2xx or 400-499"):
        run(core.network("requests", status="4x"))


def test_asking_for_a_request_that_is_not_there_names_the_listing_command(core):
    with pytest.raises(ValueError, match="co browser -t shop network requests"):
        run(core.network("request", "99"))


# ---- network har --------------------------------------------------------------------

def test_har_is_saved_under_the_tab_s_name_as_valid_har_1_2(core, tmp_path):
    run(core.network("har", "start"))
    capture(core, FakeRequest("https://shop.test/api/cart?id=7", method="POST", post_data='{"qty":2}',
                              headers={"cookie": "sid=s3cr3t-session-value; theme=dark",
                                       "content-type": "application/json"}))

    said = run(core.network("har", "stop"))

    files = list((Path.home() / ".co" / "browser" / "har").glob("shop-*.har"))
    assert len(files) == 1 and str(files[0]) in said
    har = json.loads(files[0].read_text())["log"]
    assert har["version"] == "1.2"
    entry = har["entries"][0]
    assert entry["request"]["method"] == "POST"
    assert entry["request"]["queryString"] == [{"name": "id", "value": "7"}]
    assert entry["request"]["postData"] == {"mimeType": "application/json", "text": '{"qty":2}'}
    assert entry["response"]["status"] == 200 and entry["response"]["statusText"] == "OK"
    assert entry["response"]["content"]["text"] == '{"ok":true}'
    assert entry["startedDateTime"].endswith("Z") and entry["time"] == 120


def test_har_shapes_cookie_and_header_values_unless_raw(core, tmp_path):
    secret = {"cookie": "sid=s3cr3t-session-value", "authorization": "Bearer " + "t" * 40}
    run(core.network("har", "start"))
    capture(core, FakeRequest("https://shop.test/api/me", headers=secret))
    run(core.network("har", "stop", str(tmp_path / "shaped.har")))
    run(core.network("har", "start"))
    capture(core, FakeRequest("https://shop.test/api/me", headers=secret))
    run(core.network("har", "stop", str(tmp_path / "raw.har"), raw=True))

    shaped = (tmp_path / "shaped.har").read_text()
    assert "s3cr3t-session-value" not in shaped and "t" * 40 not in shaped
    assert json.loads(shaped)["log"]["entries"][0]["request"]["cookies"] == [
        {"name": "sid", "value": "<20 chars>"}]
    assert "s3cr3t-session-value" in (tmp_path / "raw.har").read_text()


def test_a_har_file_is_readable_by_its_owner_only(core, tmp_path):
    target = tmp_path / "left-open.har"
    target.write_text("old")
    os.chmod(target, 0o644)
    run(core.network("har", "start"))

    run(core.network("har", "stop", str(target)))

    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_content_all_embeds_binary_as_base64_and_none_embeds_nothing(core, tmp_path):
    image = FakeRequest("https://shop.test/logo.png", kind="image",
                        response=FakeResponse(headers={"content-type": "image/png"}, body=b"\x89PNG"))
    run(core.network("har", "start", content="all"))
    capture(core, image)
    run(core.network("har", "stop", str(tmp_path / "all.har")))
    run(core.network("har", "start", content="none"))
    capture(core, FakeRequest("https://shop.test/api/a"))
    run(core.network("har", "stop", str(tmp_path / "none.har")))

    everything = json.loads((tmp_path / "all.har").read_text())["log"]["entries"][0]["response"]["content"]
    assert everything["encoding"] == "base64" and everything["text"] == "iVBORw=="
    bare = json.loads((tmp_path / "none.har").read_text())["log"]["entries"][0]["response"]["content"]
    assert "text" not in bare and bare["size"] == len(b'{"ok":true}')


def test_text_content_widens_to_scripts_while_recording_and_not_otherwise(core, tmp_path):
    def script():
        return FakeRequest("https://shop.test/app.js", kind="script",
                           response=FakeResponse(headers={"content-type": "text/javascript"},
                                                 body=b"console.log(1)"))
    capture(core, script())
    assert core._network.find("shop", 1)["resp_body"] is None, "outside a recording, scripts are listed only"

    run(core.network("har", "start"))
    capture(core, script())
    run(core.network("har", "stop", str(tmp_path / "s.har")))

    content = json.loads((tmp_path / "s.har").read_text())["log"]["entries"][0]["response"]["content"]
    assert content["text"] == "console.log(1)"


def test_a_second_start_keeps_the_first_recording(core):
    run(core.network("har", "start"))
    capture(core, FakeRequest("https://shop.test/api/first"))

    with pytest.raises(ValueError, match="already recording"):
        run(core.network("har", "start"))

    assert len(core._network.har_state("shop")["entries"]) == 1


def test_stopping_a_tab_that_is_not_recording_says_how_to_start(core):
    with pytest.raises(ValueError, match="co browser -t shop network har start"):
        run(core.network("har", "stop"))


def test_one_tab_s_recording_never_contains_another_tab_s_traffic(core, tmp_path):
    run(core.network("har", "start"))
    capture(core, FakeRequest("https://shop.test/mine"))
    capture(core, FakeRequest("https://other.test/theirs"), key="other")

    run(core.network("har", "stop", str(tmp_path / "t.har")))

    urls = [e["request"]["url"] for e in json.loads((tmp_path / "t.har").read_text())["log"]["entries"]]
    assert urls == ["https://shop.test/mine"]


def test_a_big_body_goes_into_the_har_whole_not_as_its_preview(core, tmp_path):
    big = b'"' + b"x" * (net.INLINE_LIMIT + 10) + b'"'
    run(core.network("har", "start"))
    capture(core, FakeRequest("https://shop.test/api/big", response=FakeResponse(body=big)))

    run(core.network("har", "stop", str(tmp_path / "big.har")))

    text = json.loads((tmp_path / "big.har").read_text())["log"]["entries"][0]["response"]["content"]["text"]
    assert len(text) == len(big)


# ---- cookies ------------------------------------------------------------------------------

def test_cookies_default_to_the_tab_s_site_and_shape_values(core):
    listed = run(core.cookies())

    assert "sid\tshop.test" in listed and "theme\tshop.test" in listed
    assert "other.test" not in listed
    assert "s3cr3t-session-value" not in listed
    assert "--raw" in listed


def test_all_widens_to_every_site_and_raw_shows_values(core):
    listed = run(core.cookies(all=True, raw=True))

    assert "other.test" in listed and "s3cr3t-session-value" in listed


def test_set_uses_the_tab_s_site_and_clear_removes_only_that_site(core):
    run(core.cookies("set", "promo", "abc"))
    assert any(c["name"] == "promo" and c["domain"] == "shop.test" for c in core.browser.jar)

    run(core.cookies("clear"))

    assert [c["domain"] for c in core.browser.jar] == ["other.test"]


def test_save_writes_a_private_storage_state_that_load_reads_back(core, tmp_path):
    said = run(core.cookies("save"))
    saved = Path.home() / ".co" / "browser" / "cookies" / "shop.json"
    assert str(saved) in said
    assert stat.S_IMODE(saved.stat().st_mode) == 0o600
    assert {c["name"] for c in json.loads(saved.read_text())["cookies"]} == {"sid", "theme"}

    core.browser.jar = []
    run(core.cookies("load", str(saved)))

    assert {c["name"] for c in core.browser.jar} == {"sid", "theme"}


def test_a_tab_with_no_site_open_is_told_how_to_name_one(core):
    core._bind_session("empty")

    with pytest.raises(ValueError, match="co browser -t empty go_to <url>"):
        run(core.cookies())


def test_a_request_that_finished_before_har_start_stays_out_of_the_recording(core):
    # Found on real Chrome: the handler reads a body asynchronously, so a page
    # loaded just before `har start` was appended just after it and landed in
    # the HAR. A recording holds what happened while it was on.
    before = core._network._start_record(FakeRequest("https://shop.test/login", kind="document"), "shop")
    before["at"] -= 1  # the event fired before the recording began
    run(core.network("har", "start"))

    core._network._append("shop", before)

    assert core._network.har_state("shop")["entries"] == []
    assert core._network.find("shop", 1)["url"] == "https://shop.test/login", "the list still has it"
