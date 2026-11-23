"""The knowledge graph is alive (#3309; opt in with CO_REM_BROWSER_TEST=1).

Owner, 2026-11-22: «各个点就是随机生成……乱七八糟一团……不能拽着一个东西动». The 2D map was a force layout
run 320 steps offline and frozen, so nothing could be picked up and nothing moved. Now the live reader on a
computer opens it in 3D (three.js + d3-force-3d, vendored, served by the Host, never from a CDN): it settles
live and fits the stage, a dragged mark tows its neighbours, a click opens the page, pointing lights a
neighbourhood, search flies to a page, hubs say their whole names. The offline snapshot, a phone, reduced
motion and a browser without WebGL get the 2D map, which is live too. The notebooks are invented:
tests/fixtures/rem_graph_notebook.py, and a generated 300-mark map for the frame budget.

Here the page is served at http://rem.test/ the way the Host serves it, with the engine at its Host path.
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

BASE = "http://rem.test/"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from rem_graph_notebook import build
    from connectonion.rem.reader import render
    tmp = tmp_path_factory.mktemp("live-graph")
    path = tmp / "reader.html"
    path.write_text(render(build(tmp / "rem"), local=True), encoding="utf-8")
    return path


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


def open_graph(api, built, *, live=True, width=1440, args=(), reduced=False, synthetic=None, mobile=False):
    """The graph as the Host serves it (live) or as the offline snapshot opens from disk."""
    from connectonion.rem.reader import GRAPH_3D, GRAPH_3D_URL
    html, engine = built.read_text(encoding="utf-8"), GRAPH_3D.read_text(encoding="utf-8")
    browser = api.chromium.launch(channel="chrome", headless=True, args=list(args))
    context = browser.new_context(viewport={"width": width, "height": 900 if width > 400 else 844}, locale="en-US",
                                  reduced_motion="reduce" if reduced else "no-preference",
                                  is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.browser_handle = browser
    page.errors, page.requests = [], []
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    page.on("request", lambda request: page.requests.append(request.url) if not request.url.startswith(("file:", "data:", "blob:")) else None)

    def serve(route):
        path = route.request.url[len(BASE) - 1:].split("#")[0]
        if route.request.url.startswith(BASE) and path in ("/", "/rem"):
            return route.fulfill(body=html, content_type="text/html")
        if route.request.url.startswith(BASE) and path == GRAPH_3D_URL:
            return route.fulfill(body=engine, content_type="text/javascript")
        return route.abort()
    context.route("http*://**/*", serve)
    try:
        page.goto(BASE + "rem" if live else built.as_uri())
        page.locator("#nav a").first.wait_for(state="attached")
        if live:  # what the Host's render(live=True) says
            js(page, "url => { REM.live = true; REM.graph_3d = url; }", GRAPH_3D_URL)
        if synthetic:
            js(page, "graph => { REM.graph = graph; GRAPH = null; }", synthetic)
        js(page, "() => { location.hash = '#view=graph'; }")
        page.locator(".gx-map .gx-stage").first.wait_for(timeout=60000)
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


def wait_settled_3d(page, seconds=30):
    page.wait_for_function("() => graphState.settled3 === true", timeout=seconds * 1000, polling=200)
    page.wait_for_timeout(900)  # the eased fit after settling


def screen_of(page, node_id):
    """Where a 3D mark is drawn on the screen, in page coordinates."""
    return js(page, """id => { const d = graphState.nodes3.get(id), box = document.querySelector('.gx-3d').getBoundingClientRect();
      const at = graphState.fg.graph2ScreenCoords(d.x, d.y, d.z); return [box.left + at.x, box.top + at.y]; }""", node_id)


def point_at(page, node_id, tries=20):
    """Move onto a mark until it is the pointed one; returns the mark actually under the pointer."""
    for _ in range(tries):
        x, y = screen_of(page, node_id)
        page.mouse.move(x + 1, y)
        page.mouse.move(x, y)
        page.wait_for_timeout(120)
        under = js(page, "() => graphState.hover")
        if under:
            return under, x, y
    raise AssertionError(f"the pointer never found {node_id}")


def moved(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** .5


def test_the_live_reader_opens_3d_settles_and_fits_the_stage(api, built):
    page = open_graph(api, built)
    try:
        assert js(page, "() => graphState.dim") == "3d"
        assert js(page, "() => !!document.querySelector('.gx-3d canvas') && document.querySelector('.gx-canvas').hidden")
        assert js(page, "() => document.querySelector('[data-dim=\"3d\"]').getAttribute('aria-pressed')") == "true"
        before = positions_3d(page)
        page.wait_for_timeout(500)
        after = positions_3d(page)
        assert max(moved(before[k], after[k]) for k in before) > 1, "the map animates into place, it is not frozen"
        wait_settled_3d(page)
        bulk, edge = js(page, """() => { const n = graphState.fg.graphData().nodes, c = graph3dCentroid(n, graphState.fg.camera().position);
          return [graph3dCover(n, c), graph3dCover(n, c, 1, true)]; }""")
        assert .95 <= max(bulk / .87, edge) <= 1.05, f"settled, the map is fitted to the inner area: bulk {bulk:.2f}, every mark {edge:.2f}"
        assert bulk >= .6 and edge <= 1.02, f"a full map, not a small ball, and nothing past the inner area: {bulk:.2f} / {edge:.2f}"
        smallest = js(page, """() => { const fg = graphState.fg, cam = fg.camera(); return Math.min(...fg.graphData().nodes.map(d => {
          const r = d.__threeObj.geometry.parameters.radius, a = fg.graph2ScreenCoords(d.x, d.y, d.z);
          const right = new cam.position.constructor(1, 0, 0).applyQuaternion(cam.quaternion).multiplyScalar(r);
          const b = fg.graph2ScreenCoords(d.x + right.x, d.y + right.y, d.z + right.z); return Math.hypot(b.x - a.x, b.y - a.y); })); }""")
        assert smallest > 4, f"the smallest mark is drawn over 4 px: {smallest:.1f}"
        assert js(page, "() => graphState.fg.controls().autoRotate") is True, "an untouched map turns slowly"
    finally:
        close(page)


def test_kinds_are_four_quiet_colours_with_one_accent_named_in_a_legend_and_the_list(api, built):
    page = open_graph(api, built)
    try:
        wait_settled_3d(page)
        tones = js(page, "() => Object.values(GRAPH_3D_TONE)")
        assert len(set(tones) - {"--green"}) <= 4 and js(page, "() => GRAPH_3D_TONE.knowledge") == "--green"
        legend = js(page, "() => [...document.querySelectorAll('.gx-key3d > span')].map(s => [s.querySelector('.gx-dot').dataset.kind, s.textContent])")
        assert page.locator(".gx-key3d").is_visible() and 3 <= len(legend) <= 5, legend
        rows = page.locator(".gx-panel .gx-item")
        assert rows.count() > 0 and rows.locator(".gx-dot").count() == rows.count(), "each row carries its kind's dot"
        # The hubs say their whole names: no ellipsis, at most two lines.
        names = js(page, "() => [...document.querySelectorAll('.gx-3d-name.hub')].map(s => [...s.children].map(c => c.textContent))")
        assert names and all(len(lines) <= 2 and not any("…" in line for line in lines) for lines in names), names
        entries = js(page, "() => GRAPH.linked.filter(n => n.k === 'knowledge').map(graphTitle)")
        assert any(" ".join(lines) in entries for lines in names), "an entry's name is shown whole"
    finally:
        close(page)


def test_search_flies_to_the_page_and_lights_it_and_zooming_in_names_more(api, built):
    page = open_graph(api, built)
    try:
        wait_settled_3d(page)
        target = js(page, "() => GRAPH.linked.find(n => n.k === 'orgs' && n.r).id")
        title = js(page, "id => graphTitle(GRAPH.byId.get(id))", target)
        far = js(page, "id => { const d = graphState.nodes3.get(id); return graphState.fg.camera().position.distanceTo(d); }", target)
        # Record the camera's distance to the hit every frame while it travels.
        js(page, """id => { const d = graphState.nodes3.get(id); window.__trip = [];
          const tick = now => { window.__trip.push([now, graphState.fg.camera().position.distanceTo(d)]); if (window.__trip.length < 90) requestAnimationFrame(tick); };
          requestAnimationFrame(tick); }""", target)
        page.locator(".gx-search").fill(title)
        page.locator(".gx-search").press("Enter")
        page.wait_for_timeout(1600)
        assert js(page, "() => graphState.focus") == target
        near = js(page, "id => { const d = graphState.nodes3.get(id); return graphState.fg.camera().position.distanceTo(d); }", target)
        assert near < far * .7, f"the camera flew to the page: {far:.0f} -> {near:.0f}"
        # The hit and its neighbours fill about 60% of the stage, and the hit never fills the screen.
        group = js(page, """id => { const fg = graphState.fg, group = [graphState.nodes3.get(id), ...[...GRAPH.adj.get(id)].map(n => graphState.nodes3.get(n))];
          return graph3dCover(group, graph3dCentroid(group, fg.camera().position)); }""", target)
        assert .5 <= group <= .72, f"the hit and its neighbours frame about 60% of the stage: {group:.2f}"
        share = js(page, """id => { const fg = graphState.fg, d = graphState.nodes3.get(id), cam = fg.camera(), r = d.__threeObj.geometry.parameters.radius;
          const up = new cam.position.constructor(0, 1, 0).applyQuaternion(cam.quaternion).multiplyScalar(r);
          const a = fg.graph2ScreenCoords(d.x - up.x, d.y - up.y, d.z - up.z), b = fg.graph2ScreenCoords(d.x + up.x, d.y + up.y, d.z + up.z);
          return Math.hypot(b.x - a.x, b.y - a.y) / fg.height(); }""", target)
        assert share <= .16, f"the hit is at most about 15% of the stage's height: {share:.2f}"
        # Eased in and out over about 700 ms: it starts and ends slowly and moves fastest in the middle.
        trip = js(page, "() => window.__trip")
        moving = [(t, d) for (t, d), (_, before) in zip(trip[1:], trip) if abs(d - before) > .05]
        assert 550 <= moving[-1][0] - moving[0][0] <= 900, f"the move lasts about 700 ms: {moving[-1][0] - moving[0][0]:.0f}"
        steps = [abs(b[1] - a[1]) for a, b in zip(moving, moving[1:])]
        third = max(1, len(steps) // 3)
        assert max(steps[third:-third]) > max(steps[:third][:2] + steps[-2:]), "slow at both ends, fastest in the middle"
        assert js(page, "() => document.querySelector('.gx-3d').dataset.lit") == target, "the found page is lit"
        assert page.locator(f'.gx-3d-name[data-id="{target}"]').count() == 1, "and named"
        # Back to the whole map, then zoom in: the marks nearest the camera are named too.
        js(page, "() => graphFocus('')")
        page.wait_for_timeout(1200)
        fitted = page.locator(".gx-3d-name").count()
        page.locator('[data-zoom="1.4"]').click()
        page.wait_for_timeout(400)
        page.locator('[data-zoom="1.4"]').click()
        page.wait_for_timeout(600)
        assert page.locator(".gx-3d-name").count() > fitted, "zoomed in, more names"
    finally:
        close(page)


MARKS_ON_SCREEN = """() => { const fg = graphState.fg, h = document.querySelector('.gx-3d').getBoundingClientRect(), cam = fg.camera();
  const tan = Math.tan(cam.fov * Math.PI / 360);
  return fg.graphData().nodes.map(d => { const at = fg.graph2ScreenCoords(d.x, d.y, d.z);
    const r = d.__threeObj.geometry.parameters.radius * fg.height() / (2 * tan * cam.position.distanceTo(d));
    return [d.id, h.left + at.x, h.top + at.y, r]; }); }"""


def offenders(page):
    """Marks whose centre is on the legend line, or whose sphere is cut by the stage's edge."""
    legend = page.locator(".gx-key3d").bounding_box()
    stage = page.locator(".gx-3d").bounding_box()
    bad = []
    for id_, x, y, r in js(page, MARKS_ON_SCREEN):
        on_legend = legend["x"] <= x <= legend["x"] + legend["width"] and legend["y"] <= y <= legend["y"] + legend["height"]
        cut = x - r < stage["x"] or x + r > stage["x"] + stage["width"] or y - r < stage["y"] or y + r > stage["y"] + stage["height"]
        if on_legend or cut:
            bad.append((id_, round(x), round(y), round(r, 1)))
    return bad


def test_settled_no_mark_sits_on_the_legend_or_is_cut_by_the_stage(api, built):
    """#3309 review: the map fits an inner area under the legend line, 12 px in from every edge."""
    page = open_graph(api, built)
    try:
        wait_settled_3d(page)
        for _ in range(3):  # while the map turns slowly
            assert offenders(page) == []
            page.wait_for_timeout(500)
    finally:
        close(page)


def test_an_outlying_mark_touches_the_inner_area_but_is_never_cut(api, built):
    """The bulk is fitted by the 95th percentile, and an outlier is kept whole inside the inner area."""
    page = open_graph(api, built)
    try:
        wait_settled_3d(page)
        js(page, """() => { const fg = graphState.fg, nodes = fg.graphData().nodes, c = graph3dCentroid(nodes, fg.camera().position);
          const leaf = nodes.filter(d => GRAPH.adj.get(d.id).size === 1)[0], spread = Math.max(...nodes.map(d => Math.hypot(d.x - c.x, d.y - c.y, d.z - c.z)));
          leaf.fx = leaf.x = c.x + spread * 2; leaf.fy = leaf.y = c.y; leaf.fz = leaf.z = c.z; graphState.fg.controls().autoRotate = false; graph3dFit(true); }""")
        page.wait_for_timeout(1200)
        edge = js(page, "() => { const n = graphState.fg.graphData().nodes; return graph3dCover(n, graph3dCentroid(n, graphState.fg.camera().position), 1, true); }")
        assert .95 <= edge <= 1.02, f"the outlier touches the inner area's edge: {edge:.2f}"
        assert offenders(page) == [], "and neither it nor any other mark is cut or on the legend"
    finally:
        close(page)


def test_names_follow_the_review_order_and_a_name_that_loses_is_hidden_never_cut(api, built):
    page = open_graph(api, built)
    try:
        wait_settled_3d(page)
        key = js(page, "() => graphState.fg.graphData().nodes.filter(d => d.n.k === 'projects').sort((a, b) => graphDegree(b.n) - graphDegree(a.n))[0].id")
        order = js(page, """key => { const fg = graphState.fg, around = GRAPH.adj.get(key);
          return graph3dNameOrder(fg.graphData().nodes, key, fg.camera().position).map(d => [d.id === key ? 0 : around.has(d.id) ? 1 : d.n.k === 'knowledge' ? 2 : 3,
            d.id, graphDegree(d.n), fg.camera().position.distanceTo(d)]); }""", key)
        tiers = [row[0] for row in order]
        assert tiers == sorted(tiers) and order[0][1] == key, "the hit, then its neighbours, then tag pages, then the rest"
        for tier in (2, 3):
            degrees = [row[2] for row in order if row[0] == tier]
            assert degrees == sorted(degrees, reverse=True), f"tier {tier} by degree"
        for a, b in zip(order, order[1:]):
            if a[0] == b[0] and (a[0] < 2 or a[2] == b[2]):
                assert a[3] <= b[3] + 1e-6, "within a tier, nearer the camera first"
        # Live: point at the mark; its name is shown, no two names overlap, and none is cut short.
        point_at(page, key)
        page.wait_for_timeout(300)
        boxes = js(page, "() => [...document.querySelectorAll('.gx-3d-name')].map(s => { const r = s.getBoundingClientRect(); return [s.dataset.id, r.left, r.top, r.right, r.bottom, s.textContent]; })")
        assert any(b[0] == js(page, "() => graphState.hover") for b in boxes), "the pointed mark is named"
        for i, a in enumerate(boxes):
            assert "…" not in a[5], a[5]
            for b in boxes[i + 1:]:
                assert not (a[1] < b[3] - 1 and a[3] > b[1] + 1 and a[2] < b[4] - 1 and a[4] > b[2] + 1), (a[5], b[5])
    finally:
        close(page)


def test_dragging_a_3d_mark_tows_a_neighbour_and_a_click_opens_its_page(api, built):
    page = open_graph(api, built)
    try:
        wait_settled_3d(page)
        mark = js(page, """() => graphState.fg.graphData().nodes.filter(d => d.n.r && GRAPH.adj.get(d.id).size <= 3)
          .sort((a, b) => GRAPH.adj.get(a.id).size - GRAPH.adj.get(b.id).size)[0].id""")
        mark, x, y = point_at(page, mark)
        assert js(page, "() => graphState.fg.controls().autoRotate") is False, "a pointed mark stops the turn"
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
        under, x, y = point_at(page, mark)
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


def test_the_engine_comes_from_the_host_once_and_nothing_else_is_fetched(api, built):
    from connectonion.rem.reader import GRAPH_3D_URL
    page = open_graph(api, built)
    try:
        wait_settled_3d(page)
        assert js(page, "() => typeof ForceGraph3D") == "function"
        assert all(url.startswith(BASE) for url in page.requests), page.requests
        assert [url for url in page.requests if url.endswith(GRAPH_3D_URL)] == [BASE[:-1] + GRAPH_3D_URL]
        assert "3d-force-graph - https://github.com" not in page.content(), "the page does not carry the engine"
    finally:
        close(page)


def test_the_offline_snapshot_draws_the_2d_map_with_no_switch(api, built):
    page = open_graph(api, built, live=False)
    try:
        assert js(page, "() => graphState.dim") == "2d"
        assert page.locator(".gx-dims").count() == 0, "3D is not offered without the Host, so no switch"
        assert js(page, "() => typeof ForceGraph3D") == "undefined" and page.requests == []
    finally:
        close(page)


def test_without_webgl_the_map_is_drawn_in_2d_and_nothing_breaks(api, built):
    page = open_graph(api, built, args=("--disable-webgl", "--disable-3d-apis"))
    try:
        assert js(page, "() => graphState.dim") == "2d"
        assert js(page, "() => !document.querySelector('.gx-3d') && !document.querySelector('.gx-canvas').hidden")
        assert js(page, "() => GRAPH.linked.length") > 0 and js(page, "() => graphState.T !== null")
        assert page.locator(".gx-dims").count() == 0
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
        page.locator(".gx-3d canvas").wait_for(timeout=30000)
        assert js(page, "() => graphState.fg.controls().autoRotate") is False
        first = positions_3d(page)
        page.wait_for_timeout(600)
        assert max(moved(first[k], v) for k, v in positions_3d(page).items()) < .01
    finally:
        close(page)


def test_the_2d_map_lets_a_mark_be_dragged_and_lights_its_neighbourhood(api, built):
    page = open_graph(api, built, live=False)
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
    page = open_graph(api, built, live=False, synthetic=big_map())
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
        wait_settled_3d(page, seconds=40)
        js(page, """() => { window.__frames = []; let last = performance.now();
          const loop = now => { window.__frames.push(now - last); last = now; if (window.__frames.length < 400) requestAnimationFrame(loop); };
          requestAnimationFrame(loop); }""")
        mark = js(page, "() => graphState.fg.graphData().nodes.find(d => d.n.k === 'people').id")
        mark, x, y = point_at(page, mark)
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


def test_a_phone_draws_the_2d_map_with_no_switch_and_a_long_press_picks_a_mark_up(api, built):
    page = open_graph(api, built, width=390, mobile=True)
    try:
        assert js(page, "() => graphState.dim") == "2d"
        assert page.locator(".gx-dims").count() == 0, "a phone is not offered 3D, so it shows no switch"
        assert not any("3d-force-graph" in url for url in page.requests), "and never fetches the engine"
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
