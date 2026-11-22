"""The knowledge graph is alive (#3309; opt in with CO_REM_BROWSER_TEST=1).

Owner, 2026-11-22: «各个点就是随机生成……乱七八糟一团……不能拽着一个东西动». The 2D map was a force layout
run 320 steps offline and frozen, so nothing could be picked up and nothing moved. Now a computer opens it in
3D (three.js + d3-force-3d, vendored, never fetched): it settles live, a dragged mark tows its neighbours, a
click opens the page, pointing lights a neighbourhood. A phone, reduced motion and a browser without WebGL get
the 2D map, which is live too. The notebooks are invented: tests/fixtures/rem_graph_notebook.py, and a
generated 300-mark map for the frame budget.
"""

import os
import random
import statistics
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

PIN_2D = "try { localStorage.setItem('co-rem-graph-dim', '2d'); } catch (e) {}"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from rem_graph_notebook import build
    from connectonion.rem.reader import render
    tmp = tmp_path_factory.mktemp("live-graph")
    path = tmp / "reader.html"
    path.write_text(render(build(tmp / "rem"), local=True), encoding="utf-8")
    return path.as_uri()


@pytest.fixture(scope="module")
def api():
    from patchright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        yield playwright


def js(page, script, arg=None):
    return page.evaluate(script, arg, isolated_context=False)


def big_map(seed=7):
    """About 300 marks: entries, people, organisations, projects and notes, linked the way a notebook is."""
    rng = random.Random(seed)
    kinds = [("knowledge", 20), ("people", 120), ("orgs", 40), ("projects", 60), ("notes", 60)]
    nodes = [{"id": f"{kind}/{kind}-{i:03d}.md", "kind": kind, "title": f"{kind.title()} {i}"}
             for kind, count in kinds for i in range(count)]
    by = {kind: [n["id"] for n in nodes if n["kind"] == kind] for kind, _ in kinds}
    edges = []
    for person in by["people"]:
        edges += [{"source": person, "target": rng.choice(by["orgs"]), "kind": "link"},
                  {"source": person, "target": rng.choice(by["projects"]), "kind": "link"},
                  {"source": person, "target": rng.choice(by["knowledge"]), "kind": "topic"}]
    for project in by["projects"] + by["notes"]:
        edges.append({"source": project, "target": rng.choice(by["knowledge"]), "kind": "topic"})
    return {"nodes": nodes, "edges": edges}


def open_graph(api, uri, *, width=1440, args=(), reduced=False, pin_2d=False, synthetic=None, mobile=False):
    browser = api.chromium.launch(channel="chrome", headless=True, args=list(args))
    context = browser.new_context(viewport={"width": width, "height": 900 if width > 400 else 844}, locale="en-US",
                                  reduced_motion="reduce" if reduced else "no-preference",
                                  is_mobile=mobile, has_touch=mobile)
    if pin_2d:
        context.add_init_script(PIN_2D)
    page = context.new_page()
    page.browser_handle = browser
    page.errors, page.requests = [], []
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    page.on("request", lambda request: page.requests.append(request.url) if not request.url.startswith(("file:", "data:", "blob:")) else None)
    page.route("http*://**/*", lambda route: route.abort())
    try:
        page.goto(uri)
        page.locator("#nav a").first.wait_for(state="attached")
        if synthetic:
            js(page, "graph => { REM.graph = graph; GRAPH = null; }", synthetic)
        js(page, "() => { location.hash = '#view=graph'; }")
        page.locator(".gx-map").first.wait_for(timeout=60000)
        page.wait_for_timeout(150)
    except Exception:
        browser.close()  # one browser that failed to open must not hang every later test on the shared driver
        raise
    return page


def close(page):
    errors = page.errors
    page.browser_handle.close()
    assert not errors, errors


def positions_3d(page):
    return js(page, "() => Object.fromEntries(graphState.fg.graphData().nodes.map(d => [d.id, [d.x, d.y, d.z]]))")


def wait_settled_3d(page, seconds=20):
    page.wait_for_function("() => graphState.settled3 === true", timeout=seconds * 1000, polling=200)


def screen_of(page, node_id):
    """Where a 3D mark is drawn on the screen, in page coordinates."""
    return js(page, """id => { const d = graphState.nodes3.get(id), box = document.querySelector('.gx-3d').getBoundingClientRect();
      const at = graphState.fg.graph2ScreenCoords(d.x, d.y, d.z); return [box.left + at.x, box.top + at.y]; }""", node_id)


def moved(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** .5


def test_a_computer_opens_the_map_in_3d_and_it_settles_live(api, built):
    page = open_graph(api, built)
    try:
        assert js(page, "() => graphState.dim") == "3d"
        assert js(page, "() => !!document.querySelector('.gx-3d canvas') && document.querySelector('.gx-canvas').hidden")
        assert js(page, "() => document.querySelector('[data-dim=\"3d\"]').getAttribute('aria-pressed')") == "true"
        before = positions_3d(page)
        page.wait_for_timeout(500)
        after = positions_3d(page)
        assert max(moved(before[k], after[k]) for k in before) > 1, "the map animates into place, it is not frozen"
        assert js(page, "() => graphState.fg.controls().autoRotate") is True, "an untouched map turns slowly"
        assert page.locator(".gx-3d-name").count() >= 3, "entries and the busiest records carry names"
    finally:
        close(page)


def test_dragging_a_3d_mark_tows_a_neighbour_and_a_click_opens_its_page(api, built):
    page = open_graph(api, built)
    try:
        wait_settled_3d(page)
        # A mark with a page, few links and a neighbour: pulling it must visibly pull that neighbour.
        mark, near = js(page, """() => { const d = graphState.fg.graphData().nodes.filter(d => d.n.r && GRAPH.adj.get(d.id).size <= 3)
          .sort((a, b) => GRAPH.adj.get(a.id).size - GRAPH.adj.get(b.id).size)[0]; return [d.id, [...GRAPH.adj.get(d.id)][0]]; }""")
        x, y = screen_of(page, mark)
        page.mouse.move(x, y)
        page.wait_for_timeout(250)
        pointed = js(page, "() => graphState.hover")
        assert pointed, "pointing at a mark lights it"
        assert js(page, "() => graphState.fg.controls().autoRotate") is False, "a pointed mark stops the turn"
        mark = pointed
        near = js(page, "id => [...GRAPH.adj.get(id)][0]", mark)
        lit = js(page, "id => new Set([id, ...GRAPH.adj.get(id)]).size", mark)
        dim = js(page, "() => graphState.fg.graphData().nodes.filter(d => d.__threeObj.material.opacity < .5).length")
        assert dim == js(page, "() => graphState.fg.graphData().nodes.length") - lit, "pointing fades everything outside the neighbourhood"
        x, y = screen_of(page, mark)
        start = positions_3d(page)
        page.mouse.down()
        for step in range(1, 13):
            page.mouse.move(x + step * 12, y + step * 6)
            page.wait_for_timeout(16)
        page.wait_for_timeout(400)
        mid = positions_3d(page)
        page.mouse.up()
        assert moved(start[mark], mid[mark]) > 5, "the dragged mark follows the pointer"
        assert moved(start[near], mid[near]) > 1, "its neighbour is towed along by the link"
        # A click, not a drag, opens the page of whatever mark is under the pointer.
        page.wait_for_timeout(1200)
        under = ""
        for _ in range(20):
            x, y = screen_of(page, mark)
            page.mouse.move(x + 1, y)
            page.mouse.move(x, y)
            page.wait_for_timeout(120)
            under = js(page, "() => graphState.hover")
            if under:
                break
        assert under, "the pointer finds the mark again after the drag"
        has_page = js(page, "id => !!GRAPH.byId.get(id).r", under)
        expected = js(page, "id => href(GRAPH.byId.get(id).r)", under) if has_page else None
        page.mouse.click(x, y)
        page.wait_for_timeout(300)
        if has_page:
            assert js(page, "() => location.hash") == expected
        else:
            assert js(page, "() => graphState.focus") == under
    finally:
        close(page)


def test_nothing_is_fetched_the_3d_engine_is_part_of_the_page(api, built):
    page = open_graph(api, built)
    try:
        wait_settled_3d(page)
        assert js(page, "() => typeof ForceGraph3D") == "function"
        assert page.requests == [], page.requests
        # Inert until asked: other pages carry the engine as text and never run it.
        assert js(page, "() => document.getElementById('graph-3d-src').type") == "text/plain"
    finally:
        close(page)


def test_without_webgl_the_map_is_drawn_in_2d_and_nothing_breaks(api, built):
    page = open_graph(api, built, args=("--disable-webgl", "--disable-3d-apis"))
    try:
        assert js(page, "() => graphState.dim") == "2d"
        assert js(page, "() => !document.querySelector('.gx-3d') && !document.querySelector('.gx-canvas').hidden")
        assert js(page, "() => GRAPH.linked.length") > 0 and js(page, "() => graphState.T !== null")
        assert js(page, "() => document.querySelector('[data-dim=\"3d\"]').disabled") is True
    finally:
        close(page)


def test_reduced_motion_opens_the_2d_map_and_nothing_moves_by_itself(api, built):
    page = open_graph(api, built, reduced=True)
    try:
        assert js(page, "() => graphState.dim") == "2d"
        before = js(page, "() => GRAPH.linked.map(n => [n.x, n.y])")
        page.wait_for_timeout(600)
        assert js(page, "() => GRAPH.linked.map(n => [n.x, n.y])") == before
        # Chosen 3D under reduced motion: settled before it is shown, and it never turns.
        page.locator('[data-dim="3d"]').click()
        page.locator(".gx-3d canvas").wait_for()
        assert js(page, "() => graphState.fg.controls().autoRotate") is False
        first = positions_3d(page)
        page.wait_for_timeout(600)
        assert max(moved(first[k], v) for k, v in positions_3d(page).items()) < .01
    finally:
        close(page)


def test_the_2d_map_lets_a_mark_be_dragged_and_lights_its_neighbourhood(api, built):
    page = open_graph(api, built, pin_2d=True)
    try:
        assert js(page, "() => graphState.dim") == "2d"
        mark, near, far = js(page, """() => { const n = GRAPH.linked.filter(graphVisible).filter(n => GRAPH.adj.get(n.id).size <= 3 && n.k !== 'knowledge')[0];
          const lit = new Set([n.id, ...GRAPH.adj.get(n.id)]); return [n.id, [...GRAPH.adj.get(n.id)][0], GRAPH.linked.find(m => !lit.has(m.id)).id]; }""")
        x, y = js(page, """id => { const n = GRAPH.byId.get(id), box = graphCanvas().getBoundingClientRect();
          return [box.left + graphState.T.applyX(n.x), box.top + graphState.T.applyY(n.y)]; }""", mark)
        page.mouse.move(x, y)
        page.wait_for_timeout(100)
        assert js(page, "() => graphCanvas().dataset.hover") == mark
        assert js(page, "ids => [graphHoverAlpha(GRAPH.byId.get(ids[0])), graphHoverAlpha(GRAPH.byId.get(ids[1]))]", [near, far]) == [1, .3]
        start = js(page, "ids => ids.map(id => [GRAPH.byId.get(id).x, GRAPH.byId.get(id).y])", [mark, near])
        page.mouse.down()
        for step in range(1, 16):
            page.mouse.move(x + step * 10, y + step * 5)
            page.wait_for_timeout(16)
        page.wait_for_timeout(300)
        mid = js(page, "ids => ids.map(id => [GRAPH.byId.get(id).x, GRAPH.byId.get(id).y])", [mark, near])
        assert moved(start[0], mid[0]) > 20, "the mark is under the pointer"
        assert moved(start[1], mid[1]) > 1, "its neighbour follows"
        page.mouse.up()
        page.wait_for_function("() => GRAPH.sim.alpha() < GRAPH.sim.alphaMin()", timeout=10000, polling=100)
        assert js(page, "() => location.hash") == "#view=graph", "a drag is not a click: no page opened"
    finally:
        close(page)


def test_on_300_marks_a_2d_drag_draws_each_frame_in_under_16_ms(api, built):
    page = open_graph(api, built, pin_2d=True, synthetic=big_map())
    try:
        assert js(page, "() => GRAPH.linked.length") >= 290
        mark = js(page, "() => GRAPH.linked.filter(graphVisible).find(n => n.k === 'people').id")
        x, y = js(page, """id => { const n = GRAPH.byId.get(id), box = graphCanvas().getBoundingClientRect();
          return [box.left + graphState.T.applyX(n.x), box.top + graphState.T.applyY(n.y)]; }""", mark)
        page.mouse.move(x, y)
        js(page, "() => { graphState.frameMs.length = 0; }")
        page.mouse.down()
        for step in range(1, 61):
            page.mouse.move(x + step * 3, y + step * 2)
            page.wait_for_timeout(16)
        page.mouse.up()
        frames = js(page, "() => graphState.frameMs.slice()")
        print(f"\n2D drag on {js(page, '() => GRAPH.linked.length')} marks: {len(frames)} frames, "
              f"mean {statistics.mean(frames):.2f} ms, p95 {sorted(frames)[int(len(frames) * .95)]:.2f} ms")
        assert len(frames) > 20 and statistics.mean(frames) < 16
    finally:
        close(page)


def test_on_300_marks_the_3d_map_keeps_its_frame_rate_while_a_mark_is_dragged(api, built):
    page = open_graph(api, built, synthetic=big_map())
    try:
        assert js(page, "() => graphState.dim") == "3d"
        wait_settled_3d(page, seconds=30)
        js(page, """() => { window.__frames = []; let last = performance.now();
          const loop = now => { window.__frames.push(now - last); last = now; if (window.__frames.length < 400) requestAnimationFrame(loop); };
          requestAnimationFrame(loop); }""")
        mark = js(page, "() => graphState.fg.graphData().nodes.find(d => d.n.k === 'people').id")
        x, y = screen_of(page, mark)
        page.mouse.move(x, y)
        page.wait_for_timeout(150)
        page.mouse.down()
        for step in range(1, 61):
            page.mouse.move(x + step * 3, y + step * 2)
            page.wait_for_timeout(16)
        page.mouse.up()
        page.wait_for_timeout(300)
        frames = js(page, "() => window.__frames.slice(5)")
        mean, p95 = statistics.mean(frames), sorted(frames)[int(len(frames) * .95)]
        print(f"\n3D drag on {js(page, '() => graphState.fg.graphData().nodes.length')} marks: {len(frames)} frames, "
              f"mean interval {mean:.2f} ms ({1000 / mean:.0f} fps), p95 {p95:.2f} ms")
        assert mean < 25, "the 3D map stays smooth (about 60 fps on this Mac; 40 fps is the floor)"
    finally:
        close(page)


def test_a_phone_draws_the_2d_map_and_a_long_press_picks_a_mark_up(api, built):
    page = open_graph(api, built, width=390, mobile=True)
    try:
        assert js(page, "() => graphState.dim") == "2d"
        assert page.locator(".gx-dims").is_visible(), "the 2D/3D switch is on the phone too"
        mark = js(page, "() => GRAPH.linked.filter(graphVisible).find(n => n.k === 'knowledge').id")
        x, y = js(page, """id => { const n = GRAPH.byId.get(id), box = graphCanvas().getBoundingClientRect();
          return [box.left + graphState.T.applyX(n.x), box.top + graphState.T.applyY(n.y)]; }""", mark)
        start = js(page, "id => [GRAPH.byId.get(id).x, GRAPH.byId.get(id).y]", mark)
        cdp = page.context.new_cdp_session(page)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        page.wait_for_timeout(600)
        for step in range(1, 11):
            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x + step * 6, "y": y + step * 3}]})
            page.wait_for_timeout(20)
        moved_to = js(page, "id => [GRAPH.byId.get(id).x, GRAPH.byId.get(id).y]", mark)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        assert moved(start, moved_to) > 10, "a long press then a move carries the mark"
    finally:
        close(page)
