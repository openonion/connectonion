"""Unit tests for the humanized input layer (connectonion/useful_tools/browser_tools/humanize.py).

These assert the *shape* of the emitted events — curved multi-step moves, a real
down→up dwell, per-char typing, off-center targeting, and cursor continuity between
actions — without a real browser. That shape is what defeats behavioral fingerprinting.
"""

import math

import pytest

from connectonion.useful_tools.browser_tools import humanize


class FakeMouse:
    def __init__(self, log):
        self._log = log

    def move(self, x, y):
        self._log.append(("move", x, y))

    def down(self, button="left", click_count=1):
        self._log.append(("down", button, click_count))

    def up(self, button="left", click_count=1):
        self._log.append(("up", button, click_count))

    def wheel(self, dx, dy):
        self._log.append(("wheel", dx, dy))


class FakeKeyboard:
    def __init__(self, log):
        self._log = log

    def type(self, text):
        self._log.append(("type", text))

    def press(self, key):
        self._log.append(("press", key))


class FakePage:
    """Records every low-level input call humanize makes."""
    def __init__(self):
        self.log = []
        self.mouse = FakeMouse(self.log)
        self.keyboard = FakeKeyboard(self.log)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    # Humanize sleeps between events for realism; skip the wall-clock cost in tests.
    monkeypatch.setattr(humanize.time, "sleep", lambda *_: None)
    # Fresh cursor memory per test so start positions are deterministic-ish.
    humanize._cursor.clear()


def _kinds(log):
    return [e[0] for e in log]


def test_move_emits_many_steps_ending_on_target():
    page = FakePage()
    humanize.move(page, 400, 300)
    moves = [e for e in page.log if e[0] == "move"]
    assert len(moves) >= 8, "a human move is a multi-step path, not a teleport"
    # Path ends on the requested point.
    assert moves[-1][1] == pytest.approx(400, abs=1)
    assert moves[-1][2] == pytest.approx(300, abs=1)


def test_move_path_is_curved_not_straight():
    page = FakePage()
    humanize.move(page, 500, 0)
    pts = [(x, y) for (kind, x, y) in page.log if kind == "move"]
    # Curvature = max perpendicular distance of the path from the straight line between its
    # own first and last sampled points. Robust to the random start offset (unlike an
    # absolute-y check, which flaked when the path happened to run near-vertical).
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1.0
    max_perp = max(abs((px - x0) * dy - (py - y0) * dx) / length for px, py in pts)

    # Relative to the chord, not an absolute pixel count. move() starts from a
    # random offset, so ~3% of paths are under 50px end to end, and on that scale
    # a perfectly good bow is well under one pixel — which is what made the old
    # `> 1` assertion fail about 0.3% of runs with nothing wrong.
    #
    # Measured over 20,000 paths: the absolute form failed 61 times, this one
    # failed 0.
    assert max_perp / length > 0.01, (
        f"path should bow off the straight line, not run straight "
        f"(deviation {max_perp:.3f}px over a {length:.1f}px chord)"
    )


def test_click_moves_then_presses_with_dwell_order():
    page = FakePage()
    humanize.click(page, 200, 200)
    kinds = _kinds(page.log)
    assert "move" in kinds
    assert kinds.index("down") < kinds.index("up")
    assert kinds.index("move") < kinds.index("down"), "cursor arrives before pressing"


def test_click_targets_off_center_inside_box():
    page = FakePage()
    box = {"x": 100, "y": 100, "width": 200, "height": 100}
    humanize.click(page, 0, 0, box=box)
    last_move = [e for e in page.log if e[0] == "move"][-1]  # lands on the click point
    x, y = last_move[1], last_move[2]
    # Inside the box...
    assert 100 <= x <= 300 and 100 <= y <= 200
    # ...but not required to be the exact center (jitter applied).
    assert not (x == 200 and y == 150)


def test_double_click_presses_twice_with_incrementing_click_count():
    page = FakePage()
    humanize.double_click(page, 50, 50)
    downs = [e for e in page.log if e[0] == "down"]
    assert len(downs) == 2
    # click_count must go 1 then 2, or the browser won't fire a real dblclick.
    assert [d[2] for d in downs] == [1, 2]
    assert [u[2] for u in page.log if u[0] == "up"] == [1, 2]


def test_right_click_uses_right_button():
    page = FakePage()
    humanize.click(page, 10, 10, button="right")
    assert ("down", "right", 1) in page.log and ("up", "right", 1) in page.log


def test_type_text_is_per_character():
    page = FakePage()
    humanize.type_text(page, "hello")
    typed = [e[1] for e in page.log if e[0] == "type"]
    assert typed == ["h", "e", "l", "l", "o"], "typed one char at a time, not in bulk"


def test_scroll_emits_many_small_wheel_ticks_summing_to_target():
    page = FakePage()
    humanize.scroll(page, 1000)
    wheels = [e for e in page.log if e[0] == "wheel"]
    assert len(wheels) >= 6, "a human scroll is many small wheel ticks, not one jump"
    dys = [dy for (_, dx, dy) in wheels]
    assert all(abs(dy) <= 170 for dy in dys), "each tick is a small delta"
    assert sum(dys) == 1000, "ticks sum to the requested distance"


def test_scroll_up_nets_to_negative_target():
    page = FakePage()
    humanize.scroll(page, -600)
    dys = [dy for (kind, dx, dy) in page.log if kind == "wheel"]
    # Net displacement is the target; most ticks go up, but an overshoot-correct can add a
    # small downward nudge at the end.
    assert sum(dys) == -600
    assert sum(1 for dy in dys if dy < 0) > sum(1 for dy in dys if dy > 0)


def test_needs_ime_flags_cjk_not_latin():
    assert humanize._needs_ime("你") and humanize._needs_ime("好")
    assert humanize._needs_ime("こ")   # hiragana
    assert humanize._needs_ime("한")   # hangul
    assert not humanize._needs_ime("a")
    assert not humanize._needs_ime(" ")
    assert not humanize._needs_ime("1")


def test_segments_splits_cjk_and_latin_runs():
    segs = humanize._segments("hi 你好 ok")
    assert segs == [(False, "hi "), (True, "你好"), (False, " ok")]


def test_segments_all_latin_is_one_run():
    assert humanize._segments("hello") == [(False, "hello")]


def test_type_text_latin_still_per_character_keystroke():
    # Latin text must still go key-by-key through the keyboard (not the IME path).
    page = FakePage()
    humanize.type_text(page, "hi")
    assert [e[1] for e in page.log if e[0] == "type"] == ["h", "i"]


def test_type_text_cjk_paste_checks_the_active_field_without_crashing(monkeypatch):
    page = FakePage()
    lengths = iter((0, 2))
    page.evaluate = lambda _script: next(lengths)
    monkeypatch.setattr(humanize, "_clipboard_set_argv", lambda _text: ["pbcopy"])
    monkeypatch.setattr(humanize, "_clipboard_get", lambda: "saved")
    monkeypatch.setattr(humanize, "_clipboard_set", lambda _text: True)
    monkeypatch.setattr(humanize.platform, "system", lambda: "Darwin")

    humanize.type_text(page, "你好")

    assert ("press", "Meta+v") in page.log


def test_cursor_position_is_remembered_between_actions():
    page = FakePage()
    humanize.move(page, 400, 400)
    assert humanize._cursor[page] == pytest.approx((400, 400), abs=1)
    # A second move starts its curve from the remembered point, not a fresh teleport.
    page.log.clear()
    humanize.move(page, 410, 410)
    first_step = next(e for e in page.log if e[0] == "move")
    assert abs(first_step[1] - 400) < 30 and abs(first_step[2] - 400) < 30


# ---------------------------------------------------------------------------
# #1877: an empty rich-text editor must not get CJK text twice.
# ---------------------------------------------------------------------------

ZERO_WIDTH = "﻿"


class EditorPage:
    """A focused rich-text editor with a working OS clipboard.

    An empty Slate/Feishu/Lark editor is not empty text: its block holds a
    zero-width placeholder that the first insert replaces. That is what made a
    landed paste grow the field by one less than the text, read as a refusal,
    and retyped the same words through the IME (#1877).
    """

    def __init__(self, content, clipboard, accepts_paste=True):
        self.content = content
        self.clipboard = clipboard
        self.accepts_paste = accepts_paste
        self.log = []
        self.keyboard = self
        self.context = self

    def _insert(self, text):
        self.content = self.content.replace(ZERO_WIDTH, "") + text

    def type(self, ch):
        self.log.append(("type", ch))
        self._insert(ch)

    def press(self, key):
        self.log.append(("press", key))
        if key in ("Meta+v", "Control+v") and self.accepts_paste:
            self._insert(self.clipboard["value"])

    def new_cdp_session(self, _page):
        return self

    def send(self, method, payload):
        self.log.append(("cdp", method, payload))
        if method == "Input.insertText":
            self._insert(payload["text"])

    def evaluate(self, script):
        # Answer whichever question the paste check asks of the focused field.
        return len(self.content) if ".length" in script else self.content


@pytest.fixture
def os_clipboard(monkeypatch):
    clipboard = {"value": "saved"}
    monkeypatch.setattr(humanize, "_clipboard_set_argv", lambda _text: ["pbcopy"])
    monkeypatch.setattr(humanize, "_clipboard_get", lambda: clipboard["value"])
    monkeypatch.setattr(humanize, "_clipboard_set",
                        lambda text: clipboard.__setitem__("value", text) or True)
    monkeypatch.setattr(humanize.platform, "system", lambda: "Darwin")
    humanize._cdp.clear()
    return clipboard


@pytest.mark.parametrize("before", [ZERO_WIDTH, "Q: "], ids=["empty-editor", "non-empty-editor"])
@pytest.mark.parametrize("text", ["你好，世界", "hello, world", "数据管线测试岗评分最高的3个人是谁？"],
                         ids=["chinese", "ascii", "issue-1877"])
def test_keyboard_type_enters_text_once_in_a_rich_editor(os_clipboard, before, text):
    page = EditorPage(before, os_clipboard)

    humanize.type_text(page, text)

    assert page.content == before.replace(ZERO_WIDTH, "") + text
    assert os_clipboard["value"] == "saved"  # the user's clipboard comes back


def test_a_refused_paste_still_falls_back_to_the_ime(os_clipboard):
    # A paste-blocked field (password, paste-disabled form) leaves its text unchanged;
    # that, and only that, sends the run through the IME composition path.
    page = EditorPage("", os_clipboard, accepts_paste=False)

    humanize.type_text(page, "你好")

    assert page.content == "你好"
    assert [e[1] for e in page.log if e[0] == "cdp"].count("Input.insertText") == 2
