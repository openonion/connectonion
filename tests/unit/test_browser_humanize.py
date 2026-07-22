"""Unit tests for the humanized input layer (connectonion/useful_tools/browser_tools/humanize.py).

These assert the *shape* of the emitted events — curved multi-step moves, a real
down→up dwell, per-char typing, off-center targeting, and cursor continuity between
actions — without a real browser. That shape is what defeats behavioral fingerprinting.
"""

import pytest

from connectonion.useful_tools.browser_tools import humanize


class FakeMouse:
    def __init__(self, log):
        self._log = log

    def move(self, x, y):
        self._log.append(("move", x, y))

    def down(self, button="left"):
        self._log.append(("down", button))

    def up(self, button="left"):
        self._log.append(("up", button))


class FakeKeyboard:
    def __init__(self, log):
        self._log = log

    def type(self, text):
        self._log.append(("type", text))


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
    humanize.move(page, 500, 0)  # horizontal target — a straight path would keep y≈0
    ys = [y for (kind, x, y) in page.log if kind == "move"]
    assert max(abs(y) for y in ys) > 1, "path should bow off the straight line"


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


def test_double_click_presses_twice():
    page = FakePage()
    humanize.double_click(page, 50, 50)
    assert _kinds(page.log).count("down") == 2
    assert _kinds(page.log).count("up") == 2


def test_right_click_uses_right_button():
    page = FakePage()
    humanize.click(page, 10, 10, button="right")
    assert ("down", "right") in page.log and ("up", "right") in page.log


def test_type_text_is_per_character():
    page = FakePage()
    humanize.type_text(page, "hello")
    typed = [e[1] for e in page.log if e[0] == "type"]
    assert typed == ["h", "e", "l", "l", "o"], "typed one char at a time, not in bulk"


def test_cursor_position_is_remembered_between_actions():
    page = FakePage()
    humanize.move(page, 400, 400)
    assert humanize._cursor[page] == pytest.approx((400, 400), abs=1)
    # A second move starts its curve from the remembered point, not a fresh teleport.
    page.log.clear()
    humanize.move(page, 410, 410)
    first_step = next(e for e in page.log if e[0] == "move")
    assert abs(first_step[1] - 400) < 30 and abs(first_step[2] - 400) < 30
