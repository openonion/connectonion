"""Unit tests for the browser network log.

LLM-Note: Tests for connectonion.useful_tools.browser_tools._async_network

What it tests:
- A header value is shaped, not printed: cookies count, bearers keep their scheme, a hex signature says how long it is
- A header nobody standardised (x-sign, x-bogus) is still shaped; content-type and user-agent are printed whole
- Bodies are read for xhr/fetch/document with a textual type, and never for images, fonts or media
- A body over the inline limit goes to a file and the record names it
- Filters, the index that is never reused after a clear, and the per-tab bound

Components under test:
- Module: connectonion/useful_tools/browser_tools/_async_network.py
"""

import asyncio
import json
import time

import pytest

from connectonion.useful_tools.browser_tools import _async_network as net

# ---- shaping ---------------------------------------------------------------

def test_a_cookie_is_counted_not_quoted():
    shaped = net.shape("cookie", "sid=abc123; csrf=deadbeef; theme=dark")

    assert shaped == "<3 pairs, 37 bytes>"
    assert "abc123" not in shaped


def test_a_bearer_keeps_its_scheme_because_the_scheme_is_the_contract():
    shaped = net.shape("authorization", "Bearer " + "x" * 172)

    assert shaped == "Bearer <172 chars>"


def test_a_hex_signature_says_which_hash_made_it():
    assert net.shape("x-sign", "a" * 32) == "<32 hex>"
    assert net.shape("x-sign", "b" * 64) == "<64 hex>"


def test_a_header_nobody_standardised_is_shaped_too():
    # A name list alone would print the one header a reverse engineer most
    # wants shaped, because every site invents its own.
    for name in ("x-bogus", "x-gorgon", "x-session-id", "x-nonce"):
        shaped = net.shape(name, "Zm9vYmFyYmF6cXV1eA" * 3)
        assert shaped.startswith("<") and "Zm9v" not in shaped, name


def test_the_headers_that_reproduce_a_request_are_printed_whole():
    # These are how you rebuild the call; none of them is a secret.
    assert net.shape("content-type", "application/json") == "application/json"
    assert net.shape("accept", "*/*") == "*/*"
    assert net.shape("user-agent", "Mozilla/5.0 (X11; Linux)") == "Mozilla/5.0 (X11; Linux)"
    assert net.shape("referer", "https://example.com/a") == "https://example.com/a"


def test_a_short_value_in_an_unknown_header_is_not_mistaken_for_a_secret():
    assert net.shape("x-request-id", "42") == "42"


# ---- capture ---------------------------------------------------------------

class FakeResponse:
    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self.ok = 200 <= status < 300
        self._headers = headers or {"content-type": "application/json"}
        self._body = body

    async def all_headers(self):
        return dict(self._headers)

    async def body(self):
        return self._body


NO_RESPONSE = object()


class FakeRequest:
    def __init__(self, url="https://x.test/api", method="GET", kind="xhr",
                 response=None, headers=None, post_data=None):
        self.url = url
        self.method = method
        self.resource_type = kind
        self.headers = headers or {"accept": "*/*"}
        self.post_data = post_data
        # As Playwright reports it: startTime is an absolute epoch, every
        # other field is an offset from it.
        self.timing = {"startTime": 1789769685953.0, "responseEnd": 143.0}
        if response is NO_RESPONSE:
            self._response = None
        else:
            self._response = response if response is not None else FakeResponse()

    async def response(self):
        return self._response


def capture(log, request, key=None):
    asyncio.run(log._on_finished(request, key))


@pytest.fixture
def log(tmp_path):
    return net.NetworkLog(home=tmp_path)


def test_an_xhr_json_response_is_read(log):
    capture(log, FakeRequest(response=FakeResponse(body=b'{"ok":true}')))

    record = log.find(None, 1)
    assert record["resp_body"] == '{"ok":true}'
    assert record["status"] == 200
    assert record["duration_ms"] == 143, "responseEnd is already the duration"


def test_an_image_is_listed_and_its_body_is_never_read(log):
    # The bulk of a page's traffic, and none of it is what anybody is after.
    body = b"\x89PNG" + b"\x00" * 5000
    capture(log, FakeRequest(
        url="https://x.test/logo.png", kind="image",
        response=FakeResponse(headers={"content-type": "image/png"}, body=body)))

    record = log.find(None, 1)
    assert record["url"].endswith("logo.png")
    assert record["resp_body"] is None
    assert record["resp_size"] is None


def test_an_xhr_that_returns_a_video_segment_is_also_left_alone(log):
    capture(log, FakeRequest(response=FakeResponse(
        headers={"content-type": "video/mp4"}, body=b"\x00" * 9000)))

    assert log.find(None, 1)["resp_body"] is None


def test_a_body_with_no_content_type_is_still_read(log):
    # Plenty of APIs return JSON and say nothing about it.
    capture(log, FakeRequest(response=FakeResponse(headers={}, body=b"[1,2,3]")))

    assert log.find(None, 1)["resp_body"] == "[1,2,3]"


def test_a_big_body_lands_in_a_file_and_the_record_names_it(log, tmp_path):
    big = b'{"rows":[' + b'0,' * (net.INLINE_LIMIT) + b'0]}'
    capture(log, FakeRequest(response=FakeResponse(body=big)))

    record = log.find(None, 1)
    assert record["truncated"] is True
    assert record["body_file"], "a body over the inline limit must be kept somewhere"
    written = (tmp_path / ".co" / "browser_network").glob("*.txt")
    assert len(record["resp_body"]) == net.PREVIEW_CHARS
    assert any(True for _ in written)


def test_a_body_past_the_file_limit_is_not_stored_at_all(log):
    capture(log, FakeRequest(response=FakeResponse(body=b"x" * (net.FILE_LIMIT + 1))))

    record = log.find(None, 1)
    assert record["body_file"] is None
    assert record["truncated"] is True


def test_a_timing_playwright_could_not_measure_is_not_reported_as_a_number(log):
    request = FakeRequest()
    request.timing = {"startTime": 1789769685953.0, "responseEnd": -1}

    capture(log, request)

    assert log.find(None, 1)["duration_ms"] is None


def test_the_request_body_the_page_posted_is_kept(log):
    capture(log, FakeRequest(method="POST", post_data='{"q":"hello"}'))

    assert log.find(None, 1)["req_body"] == '{"q":"hello"}'


def test_a_lost_body_loses_the_reason_not_the_record(log):
    class Exploding(FakeResponse):
        async def body(self):
            raise RuntimeError("Response body is unavailable for redirect responses")

    capture(log, FakeRequest(response=Exploding()))

    record = log.find(None, 1)
    assert record is not None, "the request still happened"
    assert "unavailable" in record["error"]


def test_a_request_with_no_response_is_recorded_as_such(log):
    # A redirect or a cancelled navigation leaves the request without one.
    capture(log, FakeRequest(response=NO_RESPONSE))

    assert log.find(None, 1)["error"] == "no response"


class FakePage:
    def __init__(self):
        self.handlers = []

    def on(self, event, handler):
        self.handlers.append(event)


def test_attaching_twice_does_not_record_everything_twice(log):
    page = FakePage()

    log.attach(page, None)
    log.attach(page, None)

    assert page.handlers == ["requestfinished", "requestfailed"]


def test_a_page_that_cannot_emit_events_costs_the_log_not_the_navigation(log):
    # Losing the log is one missing diagnostic; raising here would cost the
    # operator the navigation that was the point.
    log.attach(object(), None)

    assert log.select(None) == []


# ---- reading ---------------------------------------------------------------

def three(log):
    capture(log, FakeRequest(url="https://x.test/api/a", method="GET"))
    capture(log, FakeRequest(url="https://x.test/api/b", method="POST"))
    capture(log, FakeRequest(url="https://x.test/static/c", kind="script"))


def test_filters_narrow_by_url_method_and_kind(log):
    three(log)

    assert len(log.select(None, url_contains="/api/")) == 2
    assert len(log.select(None, method="post")) == 1
    assert len(log.select(None, kind="script")) == 1
    assert len(log.select(None)) == 3


def test_the_newest_are_the_ones_kept_when_a_limit_applies(log):
    three(log)

    kept = log.select(None, limit=1)
    assert [record["url"] for record in kept] == ["https://x.test/static/c"]


def test_an_index_printed_before_a_clear_never_means_something_else_after(log):
    three(log)
    dropped = log.clear(None)
    capture(log, FakeRequest(url="https://x.test/after"))

    assert dropped == 3
    assert log.find(None, 1) is None, "cleared records are gone, not renumbered"
    assert log.find(None, 4)["url"] == "https://x.test/after"


def test_one_tab_never_sees_another_tab_s_traffic(log):
    capture(log, FakeRequest(url="https://x.test/mine"), key="a")
    capture(log, FakeRequest(url="https://x.test/theirs"), key="b")

    assert [r["url"] for r in log.select("a")] == ["https://x.test/mine"]
    assert [r["url"] for r in log.select("b")] == ["https://x.test/theirs"]


def test_a_released_tab_takes_its_records_with_it(log):
    capture(log, FakeRequest(), key="a")
    log.forget("a")

    assert log.select("a") == []


def test_the_log_is_bounded_so_a_polling_page_cannot_grow_it_forever(log):
    for _ in range(net.MAX_RECORDS + 25):
        capture(log, FakeRequest())

    assert len(log.select(None, limit=0)) == net.MAX_RECORDS


def test_since_keeps_only_what_happened_inside_the_window(log):
    capture(log, FakeRequest(url="https://x.test/old"))
    log._by_tab[None][0]["at"] = time.time() - 600
    capture(log, FakeRequest(url="https://x.test/new"))

    kept = log.select(None, since=60)
    assert [r["url"] for r in kept] == ["https://x.test/new"]


# ---- rendering -------------------------------------------------------------

def test_the_list_puts_the_id_first_so_cut_f1_feeds_the_other_verb(log):
    three(log)

    lines = net.render_list(log.select(None)).splitlines()
    # The header heads the columns it names; below the rows it read as a stray line.
    assert lines[0].startswith("#\tmethod")
    assert lines[1].split("\t")[0] == "1"


def test_an_empty_log_says_so_rather_than_printing_a_bare_header(log):
    assert net.render_list([]) == "no requests recorded"


def test_the_detail_view_shapes_by_default_and_shows_with_raw(log):
    capture(log, FakeRequest(headers={
        "cookie": "sid=supersecret; a=b",
        "content-type": "application/json",
    }))
    record = log.find(None, 1)

    shaped = net.render_one(record)
    assert "supersecret" not in shaped
    assert "<2 pairs" in shaped
    assert "application/json" in shaped, "the reproducible part stays readable"
    assert "--raw" in shaped

    assert "supersecret" in net.render_one(record, raw=True)


def test_json_output_is_shaped_too_and_round_trips(log):
    capture(log, FakeRequest(headers={"authorization": "Bearer " + "s" * 40}))

    parsed = json.loads(net.render_list(log.select(None), as_json=True))
    assert parsed[0]["req_headers"]["authorization"] == "Bearer <40 chars>"
    assert parsed[0]["method"] == "GET"
