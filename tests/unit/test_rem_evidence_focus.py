"""Pure handler regressions: no browser, page navigation, or private sources."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node is required for isolated reader JavaScript checks")
TEMPLATE = Path(__file__).resolve().parents[2] / "connectonion/rem/reader.html"


def run_handler(nodes, active, *, shift=False, key="Tab", width=390):
    text = TEMPLATE.read_text()
    start = text.index('document.addEventListener("keydown", event => {\n  const panel = document.getElementById("evidence-panel");')
    end = text.index('\nwindow.addEventListener("hashchange", closeEvidence);', start)
    script = r'''
const vm = require('node:vm');
const data = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
let handler, focused = data.active, prevented = false, closed = false;
const nodes = data.nodes.map(n => ({...n,
  matches: selector => selector === ':disabled' && !!(n.disabled || n.inheritedDisabled),
  getClientRects: () => n.hidden ? [] : [1],
  focus: () => { if (!n.disabled && !n.inheritedDisabled) focused = n.id; }
}));
const panel = {parentElement: {hidden: false}, querySelectorAll: () => nodes,
  focus: () => { focused = 'panel'; }};
const document = {getElementById: () => panel,
  activeElement: nodes.find(n => n.id === data.active),
  addEventListener: (name, callback) => { handler = callback; }};
vm.runInNewContext(data.handler, {document, innerWidth: data.width,
  closeEvidence: () => { closed = true; }});
handler({key: data.key, shiftKey: data.shift, preventDefault: () => { prevented = true; }});
process.stdout.write(JSON.stringify({focused, prevented, closed}));
'''
    result = subprocess.run([NODE, "-e", script], input=json.dumps({"nodes": nodes, "active": active,
                            "shift": shift, "key": key, "width": width, "handler": text[start:end]}),
                            text=True, capture_output=True, check=True, timeout=10)
    return json.loads(result.stdout)


def controls(**next_state):
    return [{"id": "close", "tabIndex": 0}, {"id": "find", "tabIndex": 0},
            {"id": "next", "tabIndex": 0, **next_state}]


@pytest.mark.parametrize("width", [390, 768, 1099])
def test_tab_from_find_wraps_when_next_match_is_disabled(width):
    assert run_handler(controls(disabled=True), "find", width=width) == {
        "focused": "close", "prevented": True, "closed": False}


def test_shift_tab_from_close_reaches_last_enabled_control():
    assert run_handler(controls(disabled=True), "close", shift=True)["focused"] == "find"


@pytest.mark.parametrize("excluded", [{"tabIndex": -1}, {"hidden": True}, {"inheritedDisabled": True}])
def test_focus_loop_excludes_controls_outside_keyboard_order(excluded):
    nodes = controls(**excluded)
    assert run_handler(nodes, "close", shift=True)["focused"] == "find"


def test_enabled_next_match_remains_in_keyboard_order():
    assert run_handler(controls(), "find")["prevented"] is False
    assert run_handler(controls(), "next")["focused"] == "close"
    assert run_handler(controls(), "close", shift=True)["focused"] == "next"


def test_no_eligible_controls_keeps_focus_on_panel():
    result = run_handler([{"id": "disabled", "disabled": True, "tabIndex": 0}], "disabled")
    assert result["focused"] == "panel" and result["prevented"] is True


@pytest.mark.parametrize("width", [1100, 1440])
def test_desktop_panel_does_not_trap_tab(width):
    assert run_handler(controls(disabled=True), "find", width=width)["prevented"] is False


def test_escape_still_closes_source_context():
    assert run_handler(controls(disabled=True), "find", key="Escape")["closed"] is True
