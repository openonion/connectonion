"""Phone knowledge graph labels, middle-truncation, tap-to-inspect, and mini-graph accessibility (#3390)."""

import json
import re
import shutil
import subprocess

import pytest

from connectonion.rem.reader_template import read_part


def _kg_js() -> str:
    return read_part("scripts/knowledge_graph.js")


def _match(pattern: str, text: str, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    assert match is not None, f"pattern {pattern!r} not found in scripts/knowledge_graph.js"
    return match.group(0)


def _kg_function(name: str) -> str:
    return _match(r"function " + re.escape(name) + r"\(.*?\n\}", _kg_js(), re.S)


def _graph_cut() -> str:
    text = _kg_js()
    return "\n".join([
        _match(r"function graphWidth\(.*", text),
        _match(r"function graphLines\(.*?\n\}", text, re.S),
        _match(r"function graphShort\(.*", text),
    ])


def _run_node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not installed; it runs the reader's JavaScript")
    assert node is not None
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_phone_names_the_three_highest_degree_records_without_overlap():
    text = _kg_js()
    script = text[text.index("const GRAPH_LABELS"):text.index("// d3-force")]
    script += text[text.index("function graphLabelBudget"):text.index("function graphPanelWidth")]
    script += "\n" + _kg_function("graphMiddleTruncate") + "\n" + _graph_cut() + "\n"
    script += _match(r"function graphPhone\(.*", text) + "\n"
    out = _run_node(script + """
      const innerWidth = 390, REM = {}, nodes = [1, 4, 2, 3, 6].map(id => ({id, x: 55, y: id * 45}));
      const GRAPH = {linked: nodes}, graphState = {T: {k: 1, applyX: x => x, applyY: y => y}, W: 390, H: 240};
      const graphDegree = n => n.id, graphTitle = n => String(n.id), graphAlpha = () => 1,
        graphHidden = () => false, graphVisible = () => true, graphReach = () => 5,
        graphPanelWidth = () => 0, graphCss = () => "";
      graphLabels({measureText: () => ({width: 20}), fillRect() {}, strokeText() {}, fillText() {}}, nodes, {});
      const labels = graphState.labels;
      console.log(JSON.stringify([graphLabelBudget(), labels.map(l => l.id),
        labels.some((l, i) => labels.slice(i + 1).some(other => graphBoxesMeet(l.box, other.box)))]));
    """)
    assert out == [3, [4, 3, 2], False]


def test_phone_click_previews_an_unnamed_record_and_opens_a_named_or_focused_one():
    out = _run_node(_kg_function("graphBind") + """
      const graphState = {focus: "", labels: [{id: "named"}]}, actions = [], listeners = {};
      const d3 = {zoom: () => d3, scaleExtent: () => d3, filter: () => d3, on: () => d3,
        select: () => d3, call: () => d3};
      const graphPhone = () => true, graphHit = event => event.node,
        graphFocus = id => { graphState.focus = id; actions.push(["focus", id]); },
        graphOpen = n => actions.push(["open", n.id]),
        graphDragBind = () => {}, graphSearchBind = () => {};
      graphBind({querySelectorAll: () => [], querySelector: () => ({addEventListener: (k, fn) => listeners[k] = fn})});
      for (const node of [{id: "unnamed"}, {id: "unnamed"}, {id: "named"}, null]) listeners.click({node});
      console.log(JSON.stringify(actions));
    """)
    assert out == [["focus", "unnamed"], ["open", "unnamed"], ["open", "named"], ["focus", ""]]


def test_local_mark_names_and_enlarges_the_focus_link():
    out = _run_node(_kg_function("graphLocalMark") + """
      const graphTitle = n => n.id, graphSvgMark = () => ({}), document = {createTextNode: s => s};
      const svgEl = (tag, attrs, children) => ({tag, attrs, children});
      const link = graphLocalMark({id: "Ada"}, 10, 20, 4);
      console.log(JSON.stringify([link.attrs, link.children[1]]));
    """)
    link, hit = out
    assert link == {"aria-label": "Ada", "href": "#view=graph&focus=Ada"}
    assert hit["tag"] == "circle" and hit["attrs"]["class"] == "gx-hit" and hit["attrs"]["r"] >= 12
    assert hit["attrs"]["fill"] == "transparent" and hit["attrs"]["pointer-events"] == "all"


def test_local_graph_shrinks_hit_radius_on_dense_rings_to_avoid_overlap():
    out = _run_node(
        "const GRAPH_ORDER = ['knowledge', 'people', 'orgs', 'projects', 'notes', 'sessions'];\n"
        + _graph_cut() + "\n"
        + _kg_function("graphLocalLabel") + "\n"
        + _kg_function("graphLocalMark") + "\n"
        + _kg_function("graphLocal") + "\n"
        + """
      const centre = {id: "people/a.md", k: "people", r: {path: "people/a.md"}};
      const peers = Array.from({length: 24}, (_, i) => ({id: `people/p${i}.md`, k: "people", r: {path: `people/p${i}.md`}}));
      const nodes = [centre, ...peers];
      const byId = new Map(nodes.map(n => [n.id, n]));
      const adj = new Map([[centre.id, new Set(peers.map(p => p.id))]]);
      const graphModel = () => ({byId, adj});
      const graphDegree = () => 1, graphTitle = n => n.id, graphT = s => s, href = r => "#r=" + r.path;
      const graphSvgMark = () => ({tag: "path"}), document = {createTextNode: s => s};
      const el = (tag, attrs, children) => ({tag, attrs, children});
      const svgEl = (tag, attrs, children) => ({tag, attrs, children});
      const section = graphLocal({path: centre.id});
      const svg = section.children[1];
      const links = svg.children.filter(c => c && c.tag === "a" && !c.attrs.class);
      const hits = links.map(a => ({label: a.attrs["aria-label"], hit: a.children[1].attrs}));
      console.log(JSON.stringify({count: links.length, allNamed: hits.every(h => !!h.label),
        maxR: Math.max(...hits.map(h => h.hit.r)), minR: Math.min(...hits.map(h => h.hit.r))}));
    """)
    assert out["count"] == 24
    assert out["allNamed"] is True
    assert 0 < out["minR"] <= out["maxR"] <= 13


def test_canvas_label_keeps_both_ends_within_its_width():
    cut = _kg_function("graphMiddleTruncate")
    result = _run_node(_graph_cut() + "\n" + cut + "\n" + _kg_function("graphItem") + "\n" + _kg_function("graphTip") + """
      const name = "团队 1234-COMP3900-PEAR", title = graphMiddleTruncate(name), node = {id: name};
      const graphTitle = n => n.id, graphMarkFor = () => null, el = (tag, attrs, children) => ({attrs, children});
      const tip = {style: {}}, document = {querySelector: () => tip};
      const graphCanvas = () => ({style: {}, getBoundingClientRect: () => ({left: 0, top: 0})});
      const graphDegree = () => 1, graphT = () => "1 link";
      graphTip({clientX: 0, clientY: 0}, node);
      console.log(JSON.stringify([title, graphWidth(title), graphItem(node).children[1].children[0].attrs.text,
        tip.textContent, graphMiddleTruncate("𠀀".repeat(11))]));
    """)
    assert result[0].startswith("团队 1234…") and result[0].endswith("PEAR")
    assert result[1] <= 20
    assert result[2:] == ["团队 1234-COMP3900-PEAR", "团队 1234-COMP3900-PEAR · 1 link", "𠀀" * 5 + "…" + "𠀀" * 4]
