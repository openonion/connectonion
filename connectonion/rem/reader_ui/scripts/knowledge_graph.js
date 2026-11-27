// ---------- graph and topics (sprint 11): a settled map, topic records, local graphs ----------
// One layout over every real link, kept still so the owner learns where things sit; a search
// or a click turns it into the neighbourhood of one record (art direction, knowledge round 1).
const GRAPH_UI_ZH = {
  "Show the map in 2D": "用平面图显示", "Show the map in 3D": "用立体图显示", "Drawing the map in 3D…": "正在画立体图……",
  "Knowledge graph": "知识图谱", "Knowledge": "知识", "People": "人物", "Organisations": "组织", "Projects": "项目",
  "Skills · decisions": "技能 · 决定", "Sessions": "会话", "All": "全部", "People and orgs": "人和组织",
  "Tags": "标签", "Tag": "标签", "1 tag": "1 个标签", "{n} tags": "{n} 个标签",

  "Search people, organisations, knowledge": "搜索人、组织、知识，看它连着谁", "Clear focus": "清除聚焦",
  "A bigger mark has more links": "记号越大，连接越多", "{n} sessions folded into their projects": "{n} 个会话折进了项目",
  "{n} records link to nothing yet": "{n} 条还没连上任何记录", "Show the {n} unlinked records": "查看这 {n} 条", "Not linked yet": "还没连上的记录",

  "{n} links": "{n} 条连接", "Open page": "打开这一页", "Open knowledge page": "打开知识页",
  "Open person page": "打开人物页", "Open organisation page": "打开组织页", "Open project page": "打开项目页",
  "Depth": "深度", "1 hop": "1 层", "2 hops": "2 层", "Direct links only": "只看直接相连", "{n} more further out": "再远 {n} 条",
  "{n} more": "其余 {n} 个", "Personal": "个人事项", "Person": "人物", "Organisation": "组织", "Project": "项目", "Skill · decision": "技能 · 决定", "Session": "会话", "Zoom in": "放大", "Zoom out": "缩小", "Fit": "适应窗口",
  "Last mentioned": "最近提到", "First mentioned": "首次提到", "Aliases": "别名", "About": "关于",
  "In the knowledge graph": "知识图谱（相关部分）", "Open in the knowledge graph →": "在知识图谱中打开 →", "{n} directly linked": "{n} 条直接相连",
  "Related knowledge": "相关知识", "{n} shared records": "{n} 条共同记录", "REM is not sure": "REM 还不确定",
  "Linked here": "链接到这里", "Where you stand": "你现在在哪", "Timeline": "时间线", "Open threads": "还没结的线",
  "Maybe related": "可能也相关", "Only the words match; REM did not count these as links.": "只是字面相同，REM 没把它们算成链接。",
  "Confirm in Questions & connections →": "去「问题与连接」里确认 →",
  "people": "位相关的人", "orgs": "个组织", "projects": "个项目", "sessions mention it": "个会话提到", "decisions": "条决定",
  "Also named in {n} sessions and {m} skills": "另有 {n} 个会话、{m} 个技能提到它", "Also named in {n} sessions and 1 skill": "另有 {n} 个会话、1 个技能提到它",
  "Also named in {n} sessions": "另有 {n} 个会话提到它",
  "REM has not written this page yet · named in {n} records since {date}": "REM 还没写这一页 · 从 {date} 起在 {n} 条记录里出现",
  "REM has not written this page yet": "REM 还没写这一页",
  "{n} mentions, from {first} to {last}": "{n} 次提到，从 {first} 到 {last}",
  "{n} records": "{n} 条记录",
  "REM files knowledge from your records on its night run.": "REM 会在夜里那一轮从已有记录里整理知识。",
  "Explore linked records →": "探索相连的记录 →",
  "Tag pages": "标签页", "1 tag page": "1 个标签页", "{n} tag pages": "{n} 个标签页", "Knowledge here": "相关知识", "Not in the knowledge graph yet": "知识图谱里还没有它",
  "Nothing links here yet": "还没有记录链接到这里", "Decisions": "决定",
  "1 knowledge entry": "1 条知识", "{n} knowledge entries": "{n} 条知识", "1 person": "1 个人", "{n} people": "{n} 个人",
  "1 organisation": "1 个组织", "{n} organisations": "{n} 个组织", "1 project": "1 个项目", "{n} projects": "{n} 个项目",
  "1 skill or decision": "1 条技能或决定", "{n} skills and decisions": "{n} 条技能和决定", "1 session": "1 个会话", "{n} sessions": "{n} 个会话",
  " link ": "连着 ", " links ": "连着 ", ", with ": "，另有 ", " link to each other": "互相连着", ", ": "、", " and ": "和 ", ".": "。",
  "The busiest is ": "最忙的是 ", ", with {n} links.": "（{n} 条连接）。"
};
function graphT(key, values = {}) {
  const words = uiLanguage === "zh" ? GRAPH_UI_ZH[key] : null;
  return (words || key).replace(/\{(\w+)\}/g, (match, name) => values[name] ?? match);
}
const GRAPH_ORDER = ["knowledge", "people", "orgs", "projects", "notes", "sessions"];
const GRAPH_NAME = { knowledge: "Knowledge", people: "People", orgs: "Organisations", projects: "Projects", notes: "Skills · decisions", sessions: "Sessions" };
// A count in words, beside its shape: [one, many]. The sentence over the map and the panel both read these.
const GRAPH_COUNT = { knowledge: ["1 tag page", "{n} tag pages"], people: ["1 person", "{n} people"], orgs: ["1 organisation", "{n} organisations"],
  projects: ["1 project", "{n} projects"], notes: ["1 skill or decision", "{n} skills and decisions"], sessions: ["1 session", "{n} sessions"],
  tags: ["1 tag", "{n} tags"] };
function graphCount(k, n) { return graphT(GRAPH_COUNT[k][n === 1 ? 0 : 1], { n }); }
const GRAPH_ONE = { knowledge: "Tag", people: "Person", orgs: "Organisation", projects: "Project", notes: "Skill · decision", sessions: "Session" };
const GRAPH_TABS = [["all", "All"], ["people", "People and orgs"], ["projects", "Projects"], ["knowledge", "Knowledge"]];
function graphKind(kind) { return GRAPH_NAME[kind] ? kind : "notes"; }
function graphPhone() { return innerWidth < 720; }
function graphCss(name) { return getComputedStyle(document.querySelector(".gx") || document.documentElement).getPropertyValue(name).trim(); }
// The canvas cannot read var(), so each graph role names the sheet token it is painted with.
// Kinds differ by shape, not hue: ink for what the graph is about, grey for people, notes and sessions.
// Pencil means REM's inference and nothing here is inferred, so the graph does not use it. A private
// record keeps its kind's shape, drawn as an outline with a slash through it.
const GRAPH_TONE = { bg: "--paper", ink: "--ink", ink2: "--grey",
  knowledge: "--ink", people: "--grey", orgs: "--ink", projects: "--ink", notes: "--grey", sessions: "--grey", tags: "--ink",
  edge: "--rule", topicEdge: "--grey" };
// One outline per kind, shared by the canvas and the SVG glyphs: [kind] -> path in a box of radius r around (x, y).
function graphOutline(k, x, y, r) {
  if (k === "orgs") return `M${x - r} ${y - r}h${2 * r}v${2 * r}h${-2 * r}Z`;
  if (k === "projects") return `M${x} ${y - r * 1.25}L${x + r * 1.25} ${y}L${x} ${y + r * 1.25}L${x - r * 1.25} ${y}Z`;
  if (k === "notes") return `M${x} ${y - r * 1.15}L${x + r * 1.1} ${y + r * .8}L${x - r * 1.1} ${y + r * .8}Z`;
  if (k === "sessions") return `M${x - r * 1.2} ${y - r * .4}h${2.4 * r}v${.8 * r}h${-2.4 * r}Z`;  // a session is a stretch of time
  return `M${x - r} ${y}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0Z`;
}
// A private mark is an outline, which vanishes at a session's small radius; below this it is drawn larger.
const GRAPH_PRIVATE_MIN = 4;
function graphSlash(x, y, r) { return `M${x - r * 1.1} ${y + r * 1.1}L${x + r * 1.1} ${y - r * 1.1}`; }

// ---------- the model: nodes, edges, adjacency and one settled layout ----------
let GRAPH = null;
function graphModel() {
  if (GRAPH && GRAPH.source === REM.graph) return GRAPH;
  const source = REM.graph || { nodes: [], edges: [] };
  const records = new Map(REM.records.map(r => [r.path, r]));
  // Each tag is a node, linked to the pages that carry it (graph.tags, #3093); its "record" opens the tag page.
  // One kind of point, the page (#3140): a tag only adds edges between the pages carrying it and its page.
  const nodes = source.nodes.map(n => ({ ...n, k: graphKind(n.kind), r: records.get(n.id) }));
  const byId = new Map(nodes.map(n => [n.id, n]));
  // Two masked pages never read as one (#3385: four rows said "Personal"). Each page carries its number, given once
  // in the order pages were first masked (masked.py, "Masked: N"); the reader only reads it. A legacy page with none
  // yet follows the highest stored number, by path, without writing anything.
  const masked = nodes.filter(n => n.private), stored = n => +(/^Masked:[ \t]*(\d+)[ \t]*$/m.exec(n.r?.text || "")?.[1] || 0);
  let next = Math.max(0, ...masked.map(stored));
  for (const n of masked.sort((a, b) => (a.id < b.id ? -1 : 1))) n.maskNo = stored(n) || ++next;
  const edges = source.edges.concat(source.tags?.edges || []).filter(e => byId.has(e.source) && byId.has(e.target)).map(e => ({ s: e.source, t: e.target, k: e.kind }));
  const adj = new Map();
  for (const e of edges) for (const [a, b] of [[e.s, e.t], [e.t, e.s]]) (adj.get(a) || adj.set(a, new Set()).get(a)).add(b);
  const linked = nodes.filter(n => adj.has(n.id));
  const sim = graphLayout(linked, edges, byId);
  GRAPH = { source: REM.graph, nodes, byId, edges, adj, linked, sim, isolated: nodes.filter(n => !adj.has(n.id)) };
  return GRAPH;
}
function graphDegree(n) { return GRAPH.adj.get(n.id)?.size || 0; }
// A labelled-private record keeps its name only on this Mac and only while passages are shown.
// A private page's name on the knowledge graph shows only at "Show all": a label cannot be curtained (#2840).
function graphHidden(n) { return n.private && (!n.r || privacyLevel !== "all"); }
// The name in the reading language when the page has a current translation: its translated heading.
function graphTitle(n) {
  // Masking wins for a private page (#3385); a course or team code reads as one after that (#3389).
  if (graphHidden(n)) return graphT("Personal") + (n.maskNo ? " " + n.maskNo : "");
  const coded = codedOrgName(n.r);
  if (coded) return coded;
  const translated = uiLanguage !== "en" && /^# +(.+)$/m.exec(n.r?.translations?.[uiLanguage] || "")?.[1];
  return topicName(translated || n.r?.title || n.title || n.id).replace(" (automated candidate)", "");
}
function topicName(title) { return title.replace(/\s*\[personal\]\s*$/i, ""); }
// Width counts Latin letters; a CJK glyph is as wide as two.
function graphWidth(text) { return [...text].reduce((sum, ch) => sum + (/[\u2e80-\ua4cf\uac00-\ud7af\uf900-\ufaff\uff00-\uffef\u{20000}-\u{3ffff}]/u.test(ch) ? 2 : 1), 0); }
// A name on up to `max` lines of `per` letters, cut only between words (#3085: four of five labels ended
// mid-phrase). A CJK title has no spaces and any glyph is a boundary, so a word wider than a line is split by glyph.
function graphLines(text, per = 22, max = 1) {
  if (max === 1 && graphWidth(text) > per && /[0-9a-zA-Z]{4,}.*[-/].*[0-9a-zA-Z]{2,}/.test(text) && [...text].length > 12) {
    const g = [...text];
    text = g.slice(0, 7).join("") + "…" + g.slice(-4).join("");
  }
  const parts = text.replace(/\s*\([^)]*\)\s*$/, "").split(/\s+/).flatMap(word => graphWidth(word) > per ? [...word].map((ch, i) => (i ? "" : " ") + ch) : [" " + word]);
  const lines = [""], said = (from, to) => parts.slice(from, to).join("").trimStart();
  let from = 0;
  for (const [i, part] of parts.entries()) {
    const line = lines.at(-1), next = line ? line + part : part.trimStart();
    if (graphWidth(next) <= per) { lines[lines.length - 1] = next; continue; }
    if (lines.length < max) { lines.push(part.trimStart()); from = i; continue; }
    let end = i;  // the ellipsis takes a letter's room
    while (end - from > 1 && graphWidth(said(from, end)) > per - 1) end--;
    lines[lines.length - 1] = said(from, end) + "…";
    return { lines, text: said(0, end) + "…" };
  }
  return { lines, text: said(0) };
}
function graphShort(text, n = 22) { return graphLines(text, n).lines[0]; }
function graphRadius(n) {
  const d = GRAPH.adj.get(n.id)?.size || 0;
  if (n.k === "sessions") return 1.8;
  if (n.k === "knowledge") return Math.min(17, 6 + Math.sqrt(d) * 1.25);
  return Math.max(3, Math.min(14, 2.6 + Math.sqrt(d) * 1.5));
}
// How far a mark's outline reaches from its centre: a diamond and a triangle reach past their radius.
function graphReach(n) { return (n.private ? Math.max(graphRadius(n), GRAPH_PRIVATE_MIN) : graphRadius(n)) * ({ projects: 1.25, notes: 1.15, sessions: 1.2 }[n.k] || 1); }
const GRAPH_LABELS = 12, GRAPH_LINE = 15;
// The most-linked records that are not knowledge entries: the ones the fitted map names. The owner is every
// page's hub by definition, so ranking him says nothing (sprint 15).
function graphHubs(nodes, degree, count = GRAPH_LABELS) {
  return nodes.filter(n => n.k !== "knowledge" && n.k !== "sessions" && !(REM.owner && n.id === REM.owner)).sort((a, b) => degree(b) - degree(a)).slice(0, count);
}
// d3-force from a fixed start is deterministic: the same notebook always lands in the same place. A mark that
// will carry a name keeps clear ground around it, so its label has somewhere to sit that is not another mark.
function graphLayout(nodes, edges, byId) {
  if (!nodes.length || typeof d3 === "undefined") return null;
  const links = edges.map(e => ({ source: e.s, target: e.t, k: e.k }));
  const size = new Map(nodes.map(n => [n.id, 0]));
  for (const l of links) for (const id of [l.source, l.target]) size.set(id, size.get(id) + 1);
  const radius = n => n.k === "knowledge" ? Math.min(17, 6 + Math.sqrt(size.get(n.id)) * 1.25) : Math.max(3, Math.min(14, 2.6 + Math.sqrt(size.get(n.id)) * 1.5));
  // Entries last: the last strip cleared in a pass is the surest to be clear, and an entry is always named.
  const named = [...graphHubs(nodes, n => size.get(n.id)), ...nodes.filter(n => n.k === "knowledge")];
  const room = graphNameRoom(nodes, named, radius);
  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(l => l.k === "topic" ? 90 : 46).strength(l => l.k === "topic" ? .06 : .5))
    .force("charge", d3.forceManyBody().strength(-80).distanceMax(460))
    .force("x", d3.forceX().strength(.022)).force("y", d3.forceY().strength(.06))
    .force("collide", d3.forceCollide(n => radius(n) + 2.5))
    .force("names", room).stop().tick(320);
  // The other forces have the last word in a tick and can leave a mark in a strip: the strips have it here.
  for (let pass = 0; pass < 6; pass++) room();
  // Kept, stopped and settled: a drag wakes it, so a pulled mark tows what it links (#3309).
  return sim.alpha(0);
}
// A force that keeps the strip to the right of a named mark empty, where its name is written: any other mark
// in the strip is pushed out above or below it. The strip is as long as the name at the map's fitted size.
function graphNameRoom(nodes, named, radius) {
  const strips = named.map(n => {
    const top = n.k === "knowledge", { lines } = graphLines(topicName(n.title || ""), top ? 28 : 24, top ? 2 : 1);
    return { n, w: Math.max(...lines.map(graphWidth)) * 6.4 + 14, h: lines.length * GRAPH_LINE / 2 + 5 };
  });
  const reach = strip => radius(strip.n) * 1.25 + strip.w;
  return () => {
    // Two names that would be written over each other move their marks apart, up and down.
    for (const a of strips) for (const b of strips) {
      const dy = b.n.y - a.n.y, over = a.h + b.h + 2 - Math.abs(dy);
      if (a === b || over <= 0 || b.n.x > a.n.x + reach(a) || a.n.x > b.n.x + reach(b)) continue;
      b.n.y += over / 4 * (dy < 0 ? -1 : 1);
      a.n.y -= over / 4 * (dy < 0 ? -1 : 1);
    }
    for (const strip of strips) for (const m of nodes) {
      const { n, h } = strip, r = radius(m) * 1.25 + 2, dx = m.x - n.x, dy = m.y - n.y;
      if (m !== n && dx > -r && dx < reach(strip) + r && Math.abs(dy) < h + r) m.y += (h + r - Math.abs(dy)) * (dy < 0 ? -1 : 1);
    }
  };
}

// ---------- the view ----------
const graphState = { focus: "", depth: 1, tab: "all", T: null, near1: new Set(), near2: new Set(), dim: "2d", hover: "", drag: null, dragged: false, fg: null, frameMs: [] };
function graphVisible(n) {
  if (!GRAPH.adj.has(n.id)) return false;
  if (graphState.focus && (n.id === graphState.focus || graphState.near1.has(n.id) || (graphState.depth > 1 && graphState.near2.has(n.id)))) return true;
  const tab = graphState.tab;
  if (tab === "people") return n.k === "people" || n.k === "orgs";
  if (tab === "projects") return n.k === "projects" || n.k === "sessions";
  if (tab === "knowledge") return n.k === "knowledge" || [...GRAPH.adj.get(n.id)].some(id => GRAPH.byId.get(id).k === "knowledge");
  return true;
}
function graphFocusSets() {
  const { focus, depth } = graphState;
  graphState.near1 = new Set(focus ? GRAPH.adj.get(focus) || [] : []);
  graphState.near2 = new Set();
  if (focus && depth > 1) for (const id of graphState.near1) for (const far of GRAPH.adj.get(id) || []) if (far !== focus && !graphState.near1.has(far)) graphState.near2.add(far);
}
function graphAlpha(n) {
  const { focus, near1, near2 } = graphState;
  if (!focus || n.id === focus || near1.has(n.id)) return 1;
  return near2.has(n.id) ? .5 : .07;
}
// Knowledge holds two ways to look (#2996): the graph of how every record links, and its entries, one per topic.
// It opens on the graph (#3085): the rail's #c=knowledge draws it, and only an address that names the entries
// (#c=knowledge&view=entries) opens the list. With nothing linked yet the graph would be an empty canvas, so
// the entries show instead.
function knowledgeShowsGraph({ category: c, view }) { return view === "graph" || c === "all" || (c === "knowledge" && view !== "entries"); }
function knowledgeGraph() {
  if (graphModel().linked.length) graphView();
  else topicList();
}
function knowledgeHead(mode) {
  const ways = [["graph", "Knowledge graph", "#view=graph"], ["entries", "Tag pages", "#c=knowledge&view=entries"]];
  return el("div", { class: "knowledge-head" }, [el("h1", { text: label("knowledge") }),
    el("nav", { class: "knowledge-switch theme-switch", "aria-label": label("knowledge") }, ways.map(([key, name, link]) =>
      el("a", { href: link, class: "theme-btn" + (mode === key ? " active" : ""), ...(mode === key ? { "aria-current": "page" } : {}), "data-text": graphT(name), text: graphT(name) })))]);
}
function graphView() {
  const main = document.getElementById("main");
  main.textContent = "";
  const model = graphModel(), params = new URLSearchParams(location.hash.slice(1));
  const asked = params.get("focus") || "";
  graphState.focus = model.adj.has(asked) ? asked : "";
  graphState.preview = "";
  graphState.depth = params.get("depth") === "2" ? 2 : 1;
  // A phone cannot show two hundred marks a thumb could hit (#3085): it draws the knowledge entries and what
  // they link directly, which is the Knowledge filter; with no entry yet it draws everything.
  graphState.tab = graphPhone() && model.linked.some(n => n.k === "knowledge") ? "knowledge" : "all";
  graphFocusSets();
  graph3dStop();
  graphState.dim = graphDimFor();
  graphState.hover = "";
  // The engine is fetched from the Host the first time 3D opens; until it arrives the map says so, never blank.
  if (graphState.dim === "3d" && typeof ForceGraph3D !== "function") {
    const waiting = el("p", { class: "gx-loading", text: graphT("Drawing the map in 3D…") });
    main.appendChild(el("div", { class: "gx gx-map", "data-space": "3d" }, [graphHead(model), waiting]));
    graph3dLoad().then(ok => {
      if (!ok) graphState.no3d = true;
      if (waiting.isConnected) graphView();
    });
    return;
  }
  const box = el("div", { class: "gx gx-map" }, [graphHead(model), el("div", { class: "gx-stage" }, [el("canvas", { class: "gx-canvas", "aria-label": graphT("Knowledge graph"), role: "img", tabindex: "0" }),
    el("div", { class: "gx-tip", hidden: "" })]), el("div", { class: "gx-foot" }, [graphLegend(model), graphZoom()]), el("aside", { class: "gx-panel", "aria-live": "polite" })]);
  main.appendChild(box);
  if (!model.linked.length) { box.querySelector(".gx-stage").replaceWith(el("p", { class: "gx-empty", text: graphT("Nothing links here yet") })); return; }
  graphListen();
  // WebGL that will not start (no GPU, blocked, a lost context) leaves the 2D map, never a blank stage.
  if (graphState.dim === "3d" && !graph3dStart(box)) { graphState.dim = "2d"; graphState.no3d = true; }
  box.dataset.space = graphState.dim;
  graphDimsShow();
  graphBind(box);
  graphPanel();
  graphResize();
  graphFit();
  graphReturn();
  graphDraw();
  if (graphState.dim === "2d") graphLive();
}
function graphHead(model) {
  const search = el("input", { type: "search", class: "gx-search", placeholder: graphT("Search people, organisations, knowledge"), "aria-label": graphT("Search people, organisations, knowledge"), autocomplete: "off" });
  const tabs = el("div", { class: "gx-tabs", role: "tablist" }, GRAPH_TABS.map(([key, name]) =>
    el("button", { type: "button", role: "tab", "data-tab": key, "aria-selected": String(key === "all"), text: graphT(name) })));
  return el("header", { class: "gx-head" }, [el("div", { class: "gx-top" }, [knowledgeHead("graph"),
    el("div", { class: "gx-bar" }, [el("div", { class: "gx-find" }, [search, el("button", { type: "button", class: "gx-clear", "aria-label": graphT("Clear focus"), text: "✕", hidden: "" }),
      el("ul", { class: "gx-results", role: "listbox", hidden: "" })]), tabs, graph3dOffered() ? graphDims() : null])]), graphSays(model), graph3dKey(model)]);
}
// On the map a kind is drawn as its shape in 2D and its colour in 3D; the words beside the map say it the same way.
function graphMarkFor(k, size, privateNode = false) { return graphState.dim === "3d" ? graph3dDot(k, privateNode) : graphGlyph(k, size, privateNode); }
function graphKey(k, n) { return el("span", { class: "gx-key" }, [graphMarkFor(k, 13), graphCount(k, n)]); }
function graphListed(parts) {
  return parts.flatMap((part, i) => [i ? graphT(i === parts.length - 1 ? " and " : ", ") : null, part]);
}
// The first second (#3085): one sentence, counted from the map, that says what it shows. Each kind stands in
// it beside its shape, so the sentence is also the key: no mark on the map is a shape alone, and the key is
// where a newcomer starts reading, not under the fold. No instructions.
function graphSays(model) {
  const count = {};
  for (const n of model.linked) count[n.k] = (count[n.k] || 0) + 1;
  const key = k => graphKey(k, count[k]), others = ["people", "projects", "orgs"].filter(k => count[k]).map(key);
  const hub = graphHubs(model.linked.filter(n => !graphHidden(n)), graphDegree, 1)[0];
  const open = hub && el("button", { type: "button", text: graphTitle(hub) });
  if (open) open.onclick = () => graphFocus(hub.id);
  return el("p", { class: "gx-says" }, [
    ...(count.knowledge ? [key("knowledge"), graphT(count.knowledge === 1 ? " links " : " link "), ...graphListed(others)] : [...graphListed(others), graphT(" link to each other")]),
    ...(count.notes ? [graphT(", with "), key("notes")] : []), graphT("."), " ",
    open ? el("span", { class: "gx-busiest" }, [graphT("The busiest is "), open, graphT(", with {n} links.", { n: graphDegree(hub) })]) : null]);
}
// Under the map, quietly: what size means, and what the map does not draw.
function graphLegend(model) {
  const folded = REM.graph?.folded_sessions || 0, alone = {};
  for (const n of model.isolated) alone[n.k] = (alone[n.k] || 0) + 1;
  const breakdown = Object.entries(alone).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, n]) => graphCount(k, n)).join(" · ");
  return el("footer", { class: "gx-legend" }, [el("span", { text: graphT("A bigger mark has more links") }),
    folded ? el("span", { text: graphT("{n} sessions folded into their projects", { n: folded }) }) : null,
    model.isolated.length ? graphUnlinked(model, breakdown) : null]);
}
// The records the map does not draw are one click away, as a list to open, never 372 dots (#3161). Tags give most of
// them a link once the night tags them (#3093).
function graphUnlinked(model, breakdown) {
  const open = el("button", { type: "button", class: "gx-unlinked", text: graphT("Show the {n} unlinked records", { n: model.isolated.length }) });
  open.onclick = () => {
    const kinds = new Map();
    for (const n of model.isolated.filter(n => !graphHidden(n))) (kinds.get(n.k) || kinds.set(n.k, []).get(n.k)).push(n);
    openListSheet(graphT("Not linked yet"), el("div", { class: "gx-unlinked-list" }, [...kinds].map(([k, list]) =>
      el("section", {}, [el("h3", { text: graphCount(k, list.length) }), el("ul", {}, list.slice(0, 200).map(n =>
        el("li", {}, [n.r ? el("a", { href: href(n.r), text: graphTitle(n) }) : el("span", { text: graphTitle(n) })])))]))));
  };
  return el("span", {}, [graphT("{n} records link to nothing yet", { n: model.isolated.length }) + ": " + breakdown + " · ", open]);
}
function graphZoom() {
  return el("div", { class: "gx-zoom" }, [["+", "Zoom in", 1.4], ["−", "Zoom out", 1 / 1.4], ["⤢", "Fit", 0]].map(([text, name, by]) =>
    el("button", { type: "button", "data-zoom": String(by), "aria-label": graphT(name), title: graphT(name), text })));
}
// An SVG glyph per kind: the same shape on the map, the legend, the lists and the local graph.
function graphGlyph(kind, size = 14, privateNode = false) {
  const h = size / 2, r = size * .36, k = graphKind(kind);
  return svgEl("svg", { class: "gx-glyph", width: size, height: size, viewBox: `0 0 ${size} ${size}`, "aria-hidden": "true" }, [graphSvgMark(k, h, h, r, privateNode, "none")]);
}

// ---------- canvas ----------
function graphCanvas() { return document.querySelector(".gx-map .gx-canvas"); }
function graphResize() {
  graphStage();
  const canvas = graphCanvas(), rect = canvas.getBoundingClientRect(), dpr = devicePixelRatio || 1;
  canvas.width = rect.width * dpr; canvas.height = rect.height * dpr;
  canvas.getContext("2d").setTransform(dpr, 0, 0, dpr, 0, 0);
  graphState.W = rect.width; graphState.H = rect.height;
  if (graphState.dim === "3d") graph3dSize();
}
function graphMark(ctx, n, x, y, r, colours) {
  if (n.private) r = Math.max(r, GRAPH_PRIVATE_MIN);
  const colour = colours[n.k], shape = new Path2D(graphOutline(n.k, x, y, r));
  if (n.private) {
    ctx.fillStyle = colours.bg; ctx.fill(shape); ctx.lineWidth = 1.4; ctx.strokeStyle = colour; ctx.stroke(shape);
    ctx.stroke(new Path2D(graphSlash(x, y, r)));
    if (n.k === "knowledge") { ctx.beginPath(); ctx.arc(x, y, r * .38, 0, 2 * Math.PI); ctx.fillStyle = colour; ctx.fill(); }
  } else if (n.k === "knowledge") {
    ctx.fillStyle = colours.bg; ctx.fill(shape); ctx.lineWidth = Math.max(2, r * .26); ctx.strokeStyle = colour; ctx.stroke(shape);
    ctx.beginPath(); ctx.arc(x, y, r * .38, 0, 2 * Math.PI); ctx.fillStyle = colour; ctx.fill();
  } else if (n.k === "projects") { ctx.fillStyle = colours.bg; ctx.fill(shape); ctx.lineWidth = 1.6; ctx.strokeStyle = colour; ctx.stroke(shape); }
  else { ctx.fillStyle = colour; ctx.fill(shape); }
}
// The same mark as SVG for the legend, the lists and the local graph.
function graphSvgMark(k, x, y, r, privateNode, ground = "var(--paper)") {
  if (privateNode) r = Math.max(r, GRAPH_PRIVATE_MIN);
  const tone = `var(${GRAPH_TONE[k]})`, d = graphOutline(k, x, y, r);
  if (privateNode) return svgEl("g", {}, [svgEl("path", { d, fill: ground, stroke: tone, "stroke-width": 1.4 }),
    svgEl("path", { d: graphSlash(x, y, r), stroke: tone, "stroke-width": 1.4 }),
    k === "knowledge" ? svgEl("circle", { cx: x, cy: y, r: r * .4, fill: tone }) : null]);
  if (k === "knowledge") return svgEl("g", {}, [svgEl("path", { d, fill: ground, stroke: tone, "stroke-width": 2 }), svgEl("circle", { cx: x, cy: y, r: r * .4, fill: tone })]);
  if (k === "projects") return svgEl("path", { d, fill: ground, stroke: tone, "stroke-width": 1.5 });
  return svgEl("path", { d, fill: tone });
}
function graphColours() {
  return Object.fromEntries(Object.entries(GRAPH_TONE).map(([role, token]) => [role, graphCss(token)]));
}
function graphDraw() {
  if (graphState.dim === "3d") { graph3dPaint(); graph3dNames(); return; }
  const canvas = graphCanvas();
  if (!canvas) return;
  const started = performance.now();
  const ctx = canvas.getContext("2d"), T = graphState.T, colours = graphColours(), { focus, near1, near2, preview } = graphState;
  const lit = graphLit();
  ctx.save();
  ctx.clearRect(0, 0, graphState.W, graphState.H);
  ctx.translate(T.x, T.y); ctx.scale(T.k, T.k);
  for (const e of GRAPH.edges) {
    const a = GRAPH.byId.get(e.s), b = GRAPH.byId.get(e.t);
    if (!graphVisible(a) || !graphVisible(b)) continue;
    const on = (focus && (e.s === focus || e.t === focus)) || (preview && (e.s === preview || e.t === preview));
    const outer = focus && !on && ((near1.has(e.s) && near2.has(e.t)) || (near2.has(e.s) && near1.has(e.t)));
    const pointed = lit && lit.has(e.s) && lit.has(e.t) && (e.s === graphState.hover || e.t === graphState.hover);
    ctx.globalAlpha = (on || pointed ? .75 : outer ? .3 : focus ? .04 : 1) * (lit && !pointed ? .25 : 1);
    ctx.strokeStyle = on || pointed ? colours.ink : e.k === "topic" ? colours.topicEdge : colours.edge;
    ctx.lineWidth = (on ? 1.3 : .8) / Math.sqrt(T.k);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }
  const order = GRAPH.linked.filter(graphVisible).sort((a, b) => graphAlpha(a) - graphAlpha(b) || graphRadius(a) - graphRadius(b));
  for (const n of order) {
    ctx.globalAlpha = graphAlpha(n) * graphHoverAlpha(n, lit);
    graphMark(ctx, n, n.x, n.y, graphRadius(n), colours);
    if (n.id === focus || n.id === preview) { ctx.beginPath(); ctx.arc(n.x, n.y, graphRadius(n) + 6 / T.k, 0, 2 * Math.PI); ctx.lineWidth = 1.5 / T.k; ctx.strokeStyle = colours.ink; ctx.stroke(); }
  }
  ctx.restore();
  graphLabels(ctx, order, colours);
  graphState.frameMs.push(performance.now() - started);
  if (graphState.frameMs.length > 240) graphState.frameMs.shift();
}
// Which marks carry a name (#3085): every knowledge entry, then the most-linked other records: twelve when the
// whole map is fitted, more as he zooms in (the count grows with the area the zoom opens). A phone's fitted map
// names only the entries. A focused map names the record and what it links directly.
function graphLabelBudget() {
  const base = graphPhone() ? 3 : GRAPH_LABELS, zoom = graphState.T.k / (graphState.fitK || graphState.T.k);
  return zoom < 1.1 ? base : Math.round(Math.max(base, 6) * zoom * zoom);
}
function graphNamed(order) {
  const { focus, near1 } = graphState, shown = order.filter(n => graphAlpha(n) >= .4 && !graphHidden(n)), byLinks = (a, b) => graphDegree(b) - graphDegree(a);
  if (focus) return shown.filter(n => n.id === focus || near1.has(n.id)).sort((a, b) => (b.id === focus) - (a.id === focus) || (b.k === "knowledge") - (a.k === "knowledge") || byLinks(a, b));
  return [...shown.filter(n => n.k === "knowledge").sort(byLinks), ...graphHubs(shown, graphDegree, graphLabelBudget())];
}
// Every mark on screen as a box, so a label can keep off them.
function graphMarkBoxes() {
  const { T, focus } = graphState;
  return GRAPH.linked.filter(n => graphVisible(n) && graphAlpha(n) >= .4).map(n => {
    const x = T.applyX(n.x), y = T.applyY(n.y), r = graphReach(n) * T.k + (n.id === focus ? 7 : 1);
    return { id: n.id, box: [x - r, y - r, x + r, y + r] };
  });
}
function graphBoxesMeet(a, b) { return a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1]; }
// Right of its mark, else left, below, above: the first place inside the map that touches no other label and no
// other mark. With none free a record goes unnamed (pointing at it still says its name); an entry or the focused
// record is always named, at the place that covers the fewest marks.
function graphLabelSpot(n, w, h, taken, marks, must) {
  const { T, W, H } = graphState, x = T.applyX(n.x), y = T.applyY(n.y), r = graphReach(n) * T.k + (n.id === graphState.focus ? 11 : 5);
  const right = W - graphPanelWidth();
  const spots = [[x + r, y - h / 2], [x - r - w, y - h / 2], [x - w / 2, y + r], [x - w / 2, y - r - h]].map(([left, top], side) => {
      // A name that must be written is slid back inside the map's edge rather than dropped.
      if (must) { left = Math.max(0, Math.min(left, right - w)); top = Math.max(0, Math.min(top, H - h)); }
      return { side, box: [left, top, left + w, top + h] };
    }).filter(spot => spot.box[0] >= 0 && spot.box[2] <= right && spot.box[1] >= 0 && spot.box[3] <= H && !taken.some(box => graphBoxesMeet(spot.box, box)));
  const covers = spot => marks.filter(mark => mark.id !== n.id && graphBoxesMeet(spot.box, mark.box)).length;
  return spots.find(spot => !covers(spot)) || (must && spots.sort((a, b) => covers(a) - covers(b))[0]) || null;
}
function graphLabelText(ctx, lines, { side, box }, ink, ground) {
  // A plate of paper under the name: the links it crosses stay faint behind it instead of striking it through.
  ctx.globalAlpha = .82; ctx.fillStyle = ground; ctx.fillRect(box[0], box[1], box[2] - box[0], box[3] - box[1]); ctx.globalAlpha = 1;
  ctx.textAlign = ["left", "right", "center", "center"][side];
  const x = [box[0] + 2, box[2] - 2, (box[0] + box[2]) / 2, (box[0] + box[2]) / 2][side];
  lines.forEach((line, i) => {
    const y = box[1] + 1 + GRAPH_LINE / 2 + i * GRAPH_LINE;
    ctx.lineWidth = 3.5; ctx.strokeStyle = ground; ctx.strokeText(line, x, y);
    ctx.fillStyle = ink; ctx.fillText(line, x, y);
  });
}
// What was named is kept on graphState.labels, so a test can read what the canvas drew.
function graphLabels(ctx, order, colours) {
  const marks = graphMarkBoxes(), taken = [];
  const font = graphCss("--font"), size = graphCss("--s-meta"), weight = [graphCss("--w-regular"), graphCss("--w-bold")];
  ctx.textBaseline = "middle"; ctx.lineJoin = "round";
  graphState.labels = [];
  for (const n of graphNamed(order)) {
    const top = n.k === "knowledge" || n.id === graphState.focus;
    ctx.font = `${weight[+top]} ${size} ${font}`;
    const { lines, text } = graphLines(graphTitle(n), top ? (graphPhone() ? 22 : 28) : 20, top ? (graphPhone() ? 3 : 2) : 1);
    const spot = graphLabelSpot(n, Math.max(...lines.map(line => ctx.measureText(line).width)) + 4, lines.length * GRAPH_LINE + 2, taken, marks, top);
    if (!spot) continue;
    taken.push(spot.box);
    graphState.labels.push({ id: n.id, text, box: spot.box });
    graphLabelText(ctx, lines, spot, top ? colours.ink : colours.ink2, colours.bg);
  }
  ctx.textAlign = "left";
}
function graphPanelWidth() { return graphPhone() ? 0 : 396; }
// The map ends at the window's foot (#3085: it was as tall as the window but began under the top bar, so its
// key and the end of its panel were under the fold). The panel hangs beside the map, as tall as its list and
// never taller than the map. On a phone the map leaves room under it for the panel's first lines above the tab bar.
function graphStage() {
  const map = document.querySelector(".gx-map"), stage = map.querySelector(".gx-stage"), panel = map.querySelector(".gx-panel");
  const top = map.getBoundingClientRect().top + scrollY;
  if (graphPhone()) {
    map.style.height = panel.style.top = panel.style.maxHeight = "";
    // Nothing selected: the map ends above the tab bar and nothing is under it. A selected record's name and
    // its way in take the 180 px under a shorter map.
    panel.hidden = !graphState.focus;
    stage.style.height = Math.max(240, innerHeight - top - stage.offsetTop - 88 - (graphState.focus ? 180 : 0)) + "px";
    return;
  }
  stage.style.height = "";
  panel.hidden = false;
  map.style.height = Math.max(520, innerHeight - top) + "px";
  panel.style.top = stage.offsetTop + 8 + "px";
  panel.style.maxHeight = stage.offsetHeight - 16 + "px";
}
// Fit what is shown, leaving room for the heading above, the panel at the right and the legend below.
function graphFit() {
  if (graphState.dim === "3d") return graph3dFit();
  const { focus, near1, near2, W, H } = graphState, phone = graphPhone();
  const ids = focus ? new Set([focus, ...near1, ...near2]) : null;
  const points = GRAPH.linked.filter(n => ids ? ids.has(n.id) : graphVisible(n));
  if (!points.length) return;
  const [x0, x1] = d3.extent(points, n => n.x), [y0, y1] = d3.extent(points, n => n.y);
  const L = phone ? 28 : 40, R = phone ? 28 : graphPanelWidth() + 24, top = 24, bottom = 24;
  const k = Math.min((W - L - R) / ((x1 - x0) || 1), (H - top - bottom) / ((y1 - y0) || 1), ids ? 2 : 4) * (ids ? .8 : .92);
  if (!ids) graphState.fitK = k;
  graphState.T = d3.zoomIdentity.translate(L + (W - L - R) / 2 - k * (x0 + x1) / 2, top + (H - top - bottom) / 2 - k * (y0 + y1) / 2).scale(k);
  if (graphState.zoom) d3.select(graphCanvas()).call(graphState.zoom.transform, graphState.T);
}
// A pointer must be on the mark; a thumb only near it: on a phone a mark answers within 22 px of its centre
// (a 44 px target however small it is drawn), a knowledge entry before anything else in reach.
function graphHit(event) {
  const canvas = graphCanvas(), rect = canvas.getBoundingClientRect(), T = graphState.T, thumb = graphPhone() ? 22 / T.k : 0;
  const x = T.invertX(event.clientX - rect.left), y = T.invertY(event.clientY - rect.top);
  const reach = GRAPH.linked.filter(n => graphVisible(n) && graphAlpha(n) >= .4).map(n => ({ n, d: Math.hypot(n.x - x, n.y - y) }))
    .filter(({ n, d }) => d < Math.max(graphRadius(n) + 4 / T.k, thumb));
  return reach.sort((a, b) => (thumb ? (b.n.k === "knowledge") - (a.n.k === "knowledge") : 0) || a.d - b.d)[0]?.n || null;
}
function graphBind(box) {
  const canvas = box.querySelector(".gx-canvas");
  // On a phone one finger scrolls the page past the map; two fingers move and zoom it.
  const fingers = event => !graphPhone() || !event.touches || event.touches.length > 1;
  // A press on a mark picks the mark up (#3309); a press on paper pans.
  graphState.zoom = d3.zoom().scaleExtent([.2, 8]).filter(event => (!event.ctrlKey || event.type === "wheel") && !event.button && fingers(event)
      && !(event.type === "mousedown" && graphHit(event)))
    .on("zoom", event => { graphState.T = event.transform; graphDraw(); });
  d3.select(canvas).call(graphState.zoom).on("dblclick.zoom", null);
  // One click opens the record's page (#3095: focusing it and then pressing Open was two). Pointing at a mark is
  // what previews it in the panel; a click on empty paper lets go of whatever was focused.
  canvas.addEventListener("click", event => {
    if (graphState.dragged) { graphState.dragged = false; return; }
    const n = graphHit(event); if (n) graphOpen(n); else graphFocus("");
  });
  canvas.addEventListener("mousemove", event => {
    if (graphState.drag) return;
    const n = graphHit(event); graphTip(event, n); graphPoint(n); graphHover(n);
  });
  graphDragBind(canvas);
  canvas.addEventListener("keydown", event => { if (event.key === "Enter" && graphState.focus) graphOpen(GRAPH.byId.get(graphState.focus)); });
  canvas.addEventListener("mouseleave", () => { box.querySelector(".gx-tip").hidden = true; if (!graphState.drag) graphHover(null); });
  for (const button of box.querySelectorAll("[data-zoom]")) button.onclick = () => {
    const by = Number(button.dataset.zoom);
    if (graphState.dim === "3d") return graph3dZoom(by);
    if (by) d3.select(canvas).transition().duration(matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 160).call(graphState.zoom.scaleBy, by);
    else { graphFit(); graphDraw(); }
  };
  for (const tab of box.querySelectorAll("[data-tab]")) tab.onclick = () => {
    graphState.tab = tab.dataset.tab;
    box.querySelectorAll("[data-tab]").forEach(other => other.setAttribute("aria-selected", String(other === tab)));
    if (graphState.dim === "3d") graph3dData();
    graphDraw();
  };
  for (const button of box.querySelectorAll("[data-dim]")) button.onclick = () => graphChooseDim(button.dataset.dim);
  graphSearchBind(box);
}
function graphTip(event, n) {
  const tip = document.querySelector(".gx-map .gx-tip"), rect = graphCanvas().getBoundingClientRect();
  graphCanvas().style.cursor = n ? "pointer" : "";
  tip.hidden = !n;
  if (!n) return;
  tip.textContent = graphTitle(n) + " · " + graphT("{n} links", { n: graphDegree(n) });
  tip.style.left = event.clientX - rect.left + 12 + "px";
  tip.style.top = event.clientY - rect.top - 30 + "px";
}
// The record's page, leaving the graph's address naming this mark: the browser's Back returns to the graph with
// the mark focused, and the pan and zoom he left are kept for that return. A mark with no page is only focused.
function graphOpen(n) {
  if (!n.r) return graphFocus(n.id);
  clearTimeout(graphState.dwell);
  history.replaceState(null, "", "#view=graph&focus=" + encodeURIComponent(n.id));
  graphState.left = { focus: n.id, T: graphState.T, width: innerWidth };
  location.hash = href(n.r);
}
function graphReturn() {
  const left = graphState.left;
  graphState.left = null;
  if (graphState.dim === "3d") return;
  if (!left || left.focus !== graphState.focus || left.width !== innerWidth) return;
  graphState.T = left.T;
  d3.select(graphCanvas()).call(graphState.zoom.transform, left.T);
}
// Pointing at a mark for a moment shows it in the panel and rings it, without moving the map or dimming the
// rest (a dimmed mark could not be pointed at next). It stays until another mark is pointed at, so the panel
// can be reached with the pointer.
function graphPoint(n) {
  clearTimeout(graphState.dwell);
  if (!n || n.id === (graphState.preview || graphState.focus)) return;
  graphState.dwell = setTimeout(() => { graphState.preview = n.id; graphPanel(); graphDraw(); }, 140);
}
// Focus lives in the URL, so a topic page's "open in graph" lands focused; no re-render on change.
function graphFocus(id) {
  graphState.focus = id;
  graphState.preview = "";
  graphFocusSets();
  const hash = "#view=graph" + (id ? "&focus=" + encodeURIComponent(id) : "") + (id && graphState.depth > 1 ? "&depth=2" : "");
  history.replaceState(null, "", hash);
  const search = document.querySelector(".gx-search"), clear = document.querySelector(".gx-clear");
  search.value = id ? graphTitle(GRAPH.byId.get(id)) : "";
  clear.hidden = !id;
  graphPanel();
  graphResize();
  graphFit();
  graphDraw();
}
function graphMatches(query) {
  const words = query.trim().toLocaleLowerCase();
  if (!words) return [];
  const names = n => [graphTitle(n), ...(n.r?.topic?.aliases || [])].join(" ").toLocaleLowerCase();
  return GRAPH.linked.filter(n => !graphHidden(n) && n.k !== "sessions" && names(n).includes(words))
    .sort((a, b) => (b.k === "knowledge") - (a.k === "knowledge") || graphDegree(b) - graphDegree(a)).slice(0, 8);
}
function graphSearchBind(box) {
  const input = box.querySelector(".gx-search"), list = box.querySelector(".gx-results"), clear = box.querySelector(".gx-clear");
  input.value = graphState.focus ? graphTitle(GRAPH.byId.get(graphState.focus)) : "";
  clear.hidden = !graphState.focus;
  const pick = id => { list.hidden = true; input.blur(); graphFocus(id); };
  input.oninput = () => {
    const found = graphMatches(input.value);
    list.replaceChildren(...found.map(n => {
      const item = el("li", { role: "option", "data-id": n.id }, [graphMarkFor(n.k, 14, n.private), el("span", { text: graphTitle(n) }), el("small", { text: graphT(GRAPH_NAME[n.k]) })]);
      item.onmousedown = event => { event.preventDefault(); pick(n.id); };
      return item;
    }));
    list.hidden = !found.length;
  };
  input.onkeydown = event => {
    if (event.key === "Enter" && list.firstChild) pick(list.firstChild.dataset.id);
    if (event.key === "Escape") { list.hidden = true; input.blur(); }
  };
  input.onblur = () => { list.hidden = true; };
  clear.onclick = () => graphFocus("");
}

// ---------- the panel: the whole map's guide, or one record and what it connects ----------
function graphItem(n, meta) {
  const item = el("button", { type: "button", class: "gx-item", "data-id": n.id }, [graphMarkFor(n.k, 14, n.private),
    el("span", { class: "gx-item-body" }, [el("b", { text: graphTitle(n) }), meta ? el("small", { text: meta }) : null])]);
  item.onclick = () => graphFocus(n.id);
  return item;
}
function graphLast(n) {
  const r = n.r;
  if (!r) return "";
  return r.topic?.last || r.last_activity || r.mail?.last || "";
}
function graphRole(n) {
  const r = n.r;
  if (!r || graphHidden(n)) return "";
  if (n.k === "people") return plainLine(String(facts(r).role || "")).split(/[.;。]/)[0];
  return "";
}
function graphPanel() {
  const panel = document.querySelector(".gx-map .gx-panel");
  const shown = graphState.preview || graphState.focus;
  panel.replaceChildren(...(shown ? graphPanelFocus(GRAPH.byId.get(shown)) : graphPanelGuide()));
}
// What a record ties together, in words: "15 people · 9 projects · 2 organisations".
function graphTies(n) {
  const count = {};
  for (const id of GRAPH.adj.get(n.id) || []) { const k = GRAPH.byId.get(id).k; count[k] = (count[k] || 0) + 1; }
  return ["people", "projects", "orgs", "knowledge", "notes"].filter(k => count[k]).map(k => graphCount(k, count[k])).join(" · ");
}
// A record's own first sentence: a knowledge entry's What it is, anything else's lead.
function graphSummary(n) {
  if (!n.r || graphHidden(n)) return "";
  const line = n.k === "knowledge" ? plainLine(topicKnown(n.r, "what it is")) : summaryLine(known(n.r).summary);
  return /^Unknown\b/.test(line) ? "" : line.length > 220 ? line.slice(0, 217) + "…" : line;
}
// With nothing selected (#3085): the knowledge entries, each with its whole title and what it ties together,
// then the busiest pages under a rule. No instructions (#2994), and the card is as tall as the list.
function graphPanelGuide() {
  const topics = GRAPH.linked.filter(n => n.k === "knowledge").sort((a, b) => graphDegree(b) - graphDegree(a));
  const hubs = graphHubs(GRAPH.linked.filter(n => !graphHidden(n)), graphDegree, 5);
  return [el("div", { class: "gx-panel-body gx-panel-guide" }, [
      ...topics.map(n => graphItem(n, graphTies(n))),
      topics.length && hubs.length ? el("hr", { class: "gx-rule" }) : null,
      ...hubs.map(n => graphItem(n, graphT("{n} links", { n: graphDegree(n) }) + " · " + graphT(GRAPH_ONE[n.k])))])];
}
function graphGroups(ids) {
  const groups = new Map(GRAPH_ORDER.map(k => [k, []]));
  for (const id of ids) groups.get(GRAPH.byId.get(id).k).push(GRAPH.byId.get(id));
  for (const list of groups.values()) list.sort((a, b) => graphLast(b).localeCompare(graphLast(a)) || graphDegree(b) - graphDegree(a));
  return [...groups].filter(([, list]) => list.length);
}
function graphOpenLabel(n) {
  return graphT({ knowledge: "Open knowledge page", people: "Open person page", orgs: "Open organisation page", projects: "Open project page" }[n.k] || "Open page");
}
function graphPanelFocus(n) {
  const groups = graphGroups(GRAPH.adj.get(n.id) || []), phone = graphPhone(), focused = n.id === graphState.focus;
  const counts = groups.filter(([k]) => k !== "sessions" && k !== "notes").map(([k, list]) => el("span", {}, [el("b", { text: String(list.length) }), graphT(GRAPH_NAME[k])]));
  const sub = n.k === "knowledge" ? (graphLast(n) ? graphT("Last mentioned") + " " + fmtDate(graphLast(n)) : "") : graphRole(n);
  const summary = graphSummary(n);
  const depth = el("div", { class: "gx-depth" }, [el("span", { text: graphT("Depth") }), ...[1, 2].map(d => {
    const button = el("button", { type: "button", "aria-pressed": String(graphState.depth === d), text: graphT(d === 1 ? "1 hop" : "2 hops") });
    button.onclick = () => { graphState.depth = d; graphFocus(n.id); };
    return button;
  }), el("span", { class: "gx-quiet", text: graphState.depth === 2 ? graphT("{n} more further out", { n: graphState.near2.size }) : graphT("Direct links only") })]);
  const lists = groups.flatMap(([k, list]) => {
    const max = phone ? 3 : k === "people" ? 6 : 4;
    return [el("h3", {}, [graphT(GRAPH_NAME[k]), el("span", { text: String(list.length) })]),
      ...list.slice(0, max).map(m => graphItem(m, (k === "people" && graphRole(m)) || (graphLast(m) ? fmtDate(graphLast(m)) : ""))),
      list.length > max ? el("p", { class: "gx-more", text: graphT("{n} more", { n: list.length - max }) }) : null];
  });
  return [el("div", { class: "gx-panel-head" }, [el("span", { class: "gx-kicker" }, [graphMarkFor(n.k, 12, n.private), graphT(GRAPH_ONE[n.k])]),
      el("h2", { text: graphTitle(n) }), summary ? el("p", { class: "gx-summary", text: summary }) : null, sub ? el("p", { text: sub }) : null, el("div", { class: "gx-counts" }, counts),
      n.r ? el("a", { class: "gx-open", href: href(n.r), text: graphOpenLabel(n) + " →" }) : null, focused ? depth : null]),
    el("div", { class: "gx-panel-body" }, lists)];
}
// Listeners are added the first time the map opens, so loading the reader registers nothing for it.
function graphListen() {
  if (graphState.listening) return;
  graphState.listening = true;
  addEventListener("resize", () => { if (document.querySelector(".gx-map .gx-canvas")) { graphResize(); graphFit(); graphDraw(); } });
  document.addEventListener("visibilitychange", () => {
    const fg = graphState.fg;
    if (fg) document.hidden ? fg.pauseAnimation() : fg.resumeAnimation();
    if (document.hidden) GRAPH?.sim?.stop();
  });
  addEventListener("keydown", event => {
    if (event.key === "/" && document.querySelector(".gx-map") && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      event.preventDefault(); event.stopImmediatePropagation(); document.querySelector(".gx-search").focus();
    }
  }, true);
}

// ---------- the map moves (#3309) ----------
// Owner, 2026-11-22: «乱七八糟一团……不能拽着一个东西动». The map is live: a mark can be picked up and what it
// links follows it, pointing at a mark lights its neighbourhood, and on a computer that can draw it the map is
// three-dimensional and turns slowly until he touches it. Reduced motion keeps every result and drops the motion.
function graphReduced() { return matchMedia("(prefers-reduced-motion: reduce)").matches; }
// The pointed mark and what it links, or null: the 2D draw and the 3D paint both fade everything else.
function graphLit() {
  const id = graphState.hover;
  return id ? new Set([id, ...(GRAPH.adj.get(id) || [])]) : null;
}
// A mark outside the pointed neighbourhood fades but stays where a pointer can reach it (graphHit ignores this).
function graphHoverAlpha(n, lit = graphLit()) { return !lit || lit.has(n.id) ? 1 : .3; }
function graphHover(n) {
  const id = n ? n.id : "";
  if (id === graphState.hover) return;
  graphState.hover = id;
  const stage = graphState.dim === "3d" ? document.querySelector(".gx-map .gx-3d") : graphCanvas();
  if (stage) stage.dataset.hover = id;
  graphDraw();
}
// The 2D simulation was settled once and kept: each tick a drag causes is drawn.
function graphLive() {
  const sim = GRAPH.sim;
  if (!sim) return;
  sim.on("tick.draw", () => {
    if (graphState.dim !== "2d" || !graphCanvas()) return sim.stop();
    graphDraw();
  });
}
function graphDragBind(canvas) {
  const at = event => {
    const rect = canvas.getBoundingClientRect(), T = graphState.T;
    return [T.invertX(event.clientX - rect.left), T.invertY(event.clientY - rect.top)];
  };
  const pick = (n, point) => {
    graphState.drag = { n, x: point.clientX, y: point.clientY, moved: false };
    n.fx = n.x; n.fy = n.y;
    graphHover(n);
  };
  const move = point => {
    const drag = graphState.drag;
    if (!drag) return;
    // A press that never moves is a click: the map is only woken once the mark is really pulled.
    if (!drag.moved && Math.hypot(point.clientX - drag.x, point.clientY - drag.y) > 3) {
      drag.moved = true;
      if (!graphReduced()) GRAPH.sim?.alphaTarget(.3).restart();
    }
    [drag.n.fx, drag.n.fy] = at(point);
    if (graphReduced()) { drag.n.x = drag.n.fx; drag.n.y = drag.n.fy; graphDraw(); }
  };
  const drop = () => {
    const drag = graphState.drag;
    if (!drag) return;
    graphState.drag = null;
    graphState.dragged = drag.moved;
    drag.n.fx = drag.n.fy = null;
    if (!drag.moved) return;
    // Reduced motion settles in one step and draws the result; otherwise the map eases back on its own.
    if (graphReduced()) { GRAPH.sim?.tick(80); graphDraw(); } else GRAPH.sim?.alphaTarget(0);
  };
  canvas.addEventListener("mousedown", event => {
    if (event.button || graphState.dim !== "2d") return;
    const n = graphHit(event);
    if (n) { event.preventDefault(); pick(n, event); }
  });
  addEventListener("mousemove", event => { if (graphState.drag) move(event); });
  addEventListener("mouseup", drop);
  // On a phone a long press picks a mark up; a finger that moves first is scrolling the page past the map.
  let hold = null;
  const letGo = () => { clearTimeout(hold?.timer); hold = null; };
  canvas.addEventListener("touchstart", event => {
    letGo();
    if (event.touches.length !== 1) return;
    const touch = event.touches[0], n = graphHit(touch);
    if (!n) return;
    hold = { clientX: touch.clientX, clientY: touch.clientY };
    hold.timer = setTimeout(() => { if (hold) pick(n, hold); }, 450);
  }, { passive: true });
  canvas.addEventListener("touchmove", event => {
    const touch = event.touches[0];
    if (graphState.drag) { event.preventDefault(); move(touch); return; }
    if (hold && Math.hypot(touch.clientX - hold.clientX, touch.clientY - hold.clientY) > 8) letGo();
  }, { passive: false });
  canvas.addEventListener("touchend", () => { letGo(); drop(); });
  canvas.addEventListener("touchcancel", () => { letGo(); drop(); });
}

// ---------- 2D or 3D ----------
const GRAPH_DIM_KEY = "co-rem-graph-dim";
let GRAPH_WEBGL = null;
function graphWebGL() {
  if (GRAPH_WEBGL === null) {
    const probe = document.createElement("canvas");
    GRAPH_WEBGL = !!(probe.getContext("webgl2") || probe.getContext("webgl"));
  }
  return GRAPH_WEBGL;
}
function graphChosenDim() {
  try { return localStorage.getItem(GRAPH_DIM_KEY) || ""; } catch { return ""; }
}
// 3D is offered on a computer reading the live reader with WebGL: the Host serves the engine, so an offline
// snapshot draws the 2D map, and a phone does too (it never carries the engine or shows the switch).
function graph3dOffered() { return liveHere() && !!REM.graph_3d && !graphState.no3d && !graphPhone() && graphWebGL(); }
// Where it is offered a computer opens in 3D, reduced motion opens the 2D map, and the owner's choice wins.
function graphDimFor() {
  const chosen = graphChosenDim();
  if (!graph3dOffered() || chosen === "2d") return "2d";
  if (chosen === "3d") return "3d";
  return graphReduced() ? "2d" : "3d";
}
function graphDims() {
  return el("div", { class: "gx-dims", role: "group", "aria-label": graphT("Knowledge graph") },
    [["2d", "2D", "Show the map in 2D"], ["3d", "3D", "Show the map in 3D"]].map(([dim, text, name]) =>
      el("button", { type: "button", "data-dim": dim, "aria-pressed": "false", "aria-label": graphT(name), title: graphT(name), text })));
}
function graphDimsShow() {
  for (const button of document.querySelectorAll(".gx-map [data-dim]")) button.setAttribute("aria-pressed", String(button.dataset.dim === graphState.dim));
}
function graphChooseDim(dim) {
  try { localStorage.setItem(GRAPH_DIM_KEY, dim); } catch { /* a private window keeps no choice; this view still switches */ }
  graphState.left = null;
  graphView();
}

// ---------- the 3D map (#3309) ----------
// three.js and d3-force-3d, one pinned build (vendor/3d-force-graph-1.80.2.min.js, licences beside it), served by
// the Host at REM.graph_3d and loaded the first time the map opens in 3D; the reader never fetches anything else.
// Tag pages take the one accent; the four other kinds share one lightness so none shouts (#3309 review).
const GRAPH_3D_TONE = { knowledge: "--green", people: "--kind-people", orgs: "--kind-orgs", projects: "--kind-projects", notes: "--kind-notes", sessions: "--kind-notes" };
let GRAPH_3D_LOAD = null;
function graph3dLoad() {
  if (typeof ForceGraph3D === "function") return Promise.resolve(true);
  GRAPH_3D_LOAD = GRAPH_3D_LOAD || new Promise(resolve => {
    const script = el("script", { src: REM.graph_3d });
    script.onload = () => resolve(typeof ForceGraph3D === "function");
    script.onerror = () => resolve(false);
    document.head.appendChild(script);
  });
  return GRAPH_3D_LOAD;
}
// The colour a kind wears in 3D, and its legend: sessions share the notes' grey, so four colours plus the accent.
function graph3dKind(k) { return k === "sessions" ? "notes" : k; }
function graph3dDot(k, privateNode = false) { return el("span", { class: "gx-dot" + (privateNode ? " private" : ""), "data-kind": graph3dKind(k), "aria-hidden": "true" }); }
function graph3dKey(model) {
  const kinds = GRAPH_ORDER.filter(k => k !== "sessions" && model.linked.some(n => graph3dKind(n.k) === k));
  return el("p", { class: "gx-key3d" }, kinds.map(k => el("span", {}, [graph3dDot(k), graphT(GRAPH_NAME[k])])));
}
function graph3dTones() {
  const tones = Object.fromEntries(Object.entries(GRAPH_3D_TONE).map(([kind, token]) => [kind, graphCss(token)]));
  return { ...tones, bg: graphCss("--paper"), ink: graphCss("--ink"), edge: graphCss("--grey"), topicEdge: graphCss("--rule") };
}
// The 2D layout gives each mark its x and y; depth comes from its name, so the same notebook opens the same way.
function graph3dDepth(id) {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.codePointAt(0)) | 0;
  return ((h % 160) + 160) % 160 - 80;
}
function graph3dStart(box) {
  const make = typeof ForceGraph3D === "function" ? ForceGraph3D : null;
  if (!make) return false;
  const stage = box.querySelector(".gx-stage");
  const holder = el("div", { class: "gx-3d", tabindex: "0", role: "img", "aria-label": graphT("Knowledge graph") });
  const names = el("div", { class: "gx-3d-names", "aria-hidden": "true" });
  stage.append(holder, names);
  let fg;
  try {
    fg = make({ controlType: "orbit" })(holder);
  } catch (error) {
    // A WebGL context the browser refuses: the 2D map is drawn instead (the caller falls back).
    console.warn("REM: the 3D map could not start; drawing the 2D map.", error);
    holder.remove(); names.remove();
    return false;
  }
  const tones = graph3dTones(), reduced = graphReduced();
  graphState.fg = fg;
  graphState.nodes3 = new Map();
  graphState.hubs3 = new Set([...graphHubs(GRAPH.linked, graphDegree, 8).map(n => n.id), ...GRAPH.linked.filter(n => n.k === "knowledge").map(n => n.id)]);
  graphState.rotate3 = !reduced;
  graphState.settled3 = false;
  graphState.fitted3 = false;
  graphState.fitDist3 = 0;
  box.querySelector(".gx-canvas").hidden = true;
  fg.backgroundColor(tones.bg).showNavInfo(false)
    .nodeId("id").nodeRelSize(4.5).nodeResolution(16)
    .nodeVal(d => 1.5 + graphDegree(d.n) * (d.n.k === "knowledge" ? 1.6 : 1))
    .nodeColor(d => tones[d.n.k] || tones.notes)
    .nodeOpacity(.95)
    .nodeLabel(() => "")
    .linkColor(l => l.k === "topic" ? tones.topicEdge : tones.edge)
    .linkOpacity(.45).linkWidth(0)
    .onNodeHover(d => { holder.style.cursor = d ? "pointer" : ""; graph3dRotate(!d); graphHover(d ? d.n : null); })
    .onNodeClick(d => graphOpen(d.n))
    // A released mark rejoins the map rather than staying pinned where it was dropped.
    .onNodeDragEnd(d => { d.fx = d.fy = d.fz = undefined; })
    .onBackgroundClick(() => { if (graphState.focus) graphFocus(""); })
    .onEngineTick(() => { if ((graphState.focus || graphState.hover) && !graphState._painted3) { graph3dPaint(); graphState._painted3 = true; } graph3dNames(); })
    .onEngineStop(() => { graphState.settled3 = true; if (!graphState.fitted3) { graphState.fitted3 = true; graph3dFit(); } })
    .d3AlphaDecay(.028)
    .warmupTicks(reduced ? 400 : 0).cooldownTicks(reduced ? 0 : Infinity);
  // d3-force-3d's defaults (charge -30, link 30) pull a notebook into a tight ball; the 2D map's spacing reads.
  fg.d3Force("charge").strength(-90).distanceMax(500);
  fg.d3Force("link").distance(l => l.k === "topic" ? 70 : 36);
  graph3dData();
  const controls = fg.controls();
  controls.autoRotate = graphState.rotate3;
  controls.autoRotateSpeed = .45;
  controls.addEventListener("change", graph3dNames);
  // The slow turn is for a map nobody is touching: the first press or scroll stops it for good.
  const still = () => { graphState.rotate3 = false; controls.autoRotate = false; };
  holder.addEventListener("pointerdown", still);
  holder.addEventListener("wheel", still, { passive: true });
  holder.addEventListener("keydown", event => { if (event.key === "Enter" && graphState.focus) graphOpen(GRAPH.byId.get(graphState.focus)); });
  clearInterval(graphState.watch3);
  graphState.watch3 = setInterval(() => { if (!holder.isConnected) graph3dStop(); }, 1000);
  return true;
}
function graph3dStop() {
  clearInterval(graphState.watch3);
  const fg = graphState.fg;
  graphState.fg = null;
  graphState.nodes3 = null;
  graphState.hubs3 = null;
  if (!fg) return;
  fg.pauseAnimation();
  fg._destructor?.();
}
// A pointed mark stops the turn so it does not drift out from under the pointer.
function graph3dRotate(on) {
  const fg = graphState.fg;
  if (fg) fg.controls().autoRotate = on && graphState.rotate3;
}
// What the filters show, keeping each mark's object (and so its place) across a change of filter.
function graph3dData() {
  const fg = graphState.fg;
  if (!fg) return;
  const shown = GRAPH.linked.filter(graphVisible), ids = new Set(shown.map(n => n.id)), kept = graphState.nodes3;
  const nodes = shown.map(n => kept.get(n.id) || kept.set(n.id, { id: n.id, n, x: n.x, y: n.y, z: graph3dDepth(n.id) }).get(n.id));
  const links = GRAPH.edges.filter(e => ids.has(e.s) && ids.has(e.t)).map(e => ({ source: e.s, target: e.t, k: e.k }));
  fg.graphData({ nodes, links });
}
function graph3dSize() {
  const fg = graphState.fg, holder = document.querySelector(".gx-map .gx-3d"), names = document.querySelector(".gx-map .gx-3d-names");
  if (!fg || !holder) return;
  const right = graphPanelWidth() ? graphPanelWidth() + 24 : 0;
  for (const box of [holder, names]) box.style.right = right + "px";
  const rect = holder.getBoundingClientRect();
  fg.width(rect.width).height(rect.height);
}
function graph3dFit(whole = false) {
  const fg = graphState.fg;
  if (!fg) return;
  const id = whole ? "" : graphState.focus, d = id && graphState.nodes3?.get(id);
  const camera = fg.camera(), from = camera.position.clone();
  const marks = fg.graphData().nodes.filter(n => n.x !== undefined);
  if (!marks.length) return;
  const centre = graph3dCentroid(marks, from);
  if (d && d.x !== undefined) return graph3dFlyTo(d, centre);
  const toward = from.clone().sub(centre);
  if (toward.lengthSq() < 1e-6) toward.set(0, 0, 1);
  toward.normalize();
  // The bulk (95th percentile) fills about 87% of the inner area; every mark, its size included, stays inside it.
  const need = () => Math.max(graph3dCover(marks, centre) / .87, graph3dCover(marks, centre, 1, true));
  const dist = graph3dDistance(centre, toward, need, from.distanceTo(centre) || 600);
  graphState.fitDist3 = dist;
  graph3dMove(centre.clone().addScaledVector(toward, dist), centre);
}
function graph3dCentroid(marks, like) {
  const c = like.clone().set(0, 0, 0);
  for (const n of marks) { c.x += n.x; c.y += n.y; c.z += n.z; }
  return c.multiplyScalar(1 / marks.length);
}
// The distance from `aim`, looking along `toward`, at which `need()` comes to 1 (it scales with the distance):
// measured, not guessed (three passes), then the camera is put back, so the eased move starts where it stands.
function graph3dDistance(aim, toward, need, start) {
  const camera = graphState.fg.camera(), from = camera.position.clone(), turn = camera.quaternion.clone();
  let dist = start;
  for (let pass = 0; pass < 3; pass++) {
    camera.position.copy(aim).addScaledVector(toward, dist);
    camera.lookAt(aim);
    camera.updateMatrixWorld();
    const scale = need();
    if (!scale) break;
    dist *= scale;
  }
  camera.position.copy(from);
  camera.quaternion.copy(turn);
  camera.updateMatrixWorld();
  return dist;
}
// Search and focus (#3309 review): the hit and its one-hop neighbours fill about 60% of the stage, seen from
// outside the cloud along the line from its centre through the hit, never so close the hit fills the screen.
function graph3dFlyTo(d, centre) {
  // A search is a touch too: the slow turn stops, or it would carry the found page away.
  graphState.rotate3 = false;
  graphState.fg.controls().autoRotate = false;
  const camera = graphState.fg.camera(), hit = camera.position.clone().set(d.x, d.y, d.z);
  const group = [d, ...[...(GRAPH.adj.get(d.id) || [])].map(id => graphState.nodes3.get(id)).filter(n => n && n.x !== undefined)];
  const aim = graph3dCentroid(group, hit), toward = hit.clone().sub(centre);
  if (toward.length() < 1) toward.copy(camera.position).sub(centre);
  toward.normalize();
  const radius = d.__threeObj?.geometry?.parameters?.radius || 6;
  const nearest = 2 * radius / (.15 * 2 * Math.tan(camera.fov * Math.PI / 360));  // the hit at most 15% of the stage's height
  const dist = group.length > 1 ? graph3dDistance(aim, toward, () => graph3dCover(group, aim, 1, true) / .6, (graphState.fitDist3 || 600) * .5) : nearest * 2;
  graph3dMove(aim.clone().addScaledVector(toward, Math.max(dist, nearest)), aim);
}
// One camera move, eased in and out over 700 ms; reduced motion jumps. A newer move replaces one still running.
function graph3dMove(to, aim) {
  const fg = graphState.fg, camera = fg.camera(), controls = fg.controls();
  cancelAnimationFrame(graphState.move3);
  if (graphReduced()) return fg.cameraPosition({ x: to.x, y: to.y, z: to.z }, { x: aim.x, y: aim.y, z: aim.z }, 0);
  const from = camera.position.clone(), look = controls.target.clone(), started = performance.now();
  const ease = t => t < .5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
  graphState.moving3 = true;
  const step = now => {
    if (graphState.fg !== fg) return;
    const t = Math.min(1, (now - started) / 700), k = ease(t), at = from.clone().lerp(to, k), on = look.clone().lerp(aim, k);
    fg.cameraPosition({ x: at.x, y: at.y, z: at.z }, { x: on.x, y: on.y, z: on.z }, 0);
    if (t < 1) graphState.move3 = requestAnimationFrame(step);
    else graphState.moving3 = false;
  };
  graphState.move3 = requestAnimationFrame(step);
}
// How much of the stage the marks take up: the larger of their height and width shares.
// How much of the stage the marks take up around `aim`: twice their 95th-percentile offset from it on each axis,
// so one outlying mark may sit at the edge instead of shrinking the whole map to fit it (#3309 review).
// The inner area the 3D map is fitted into, in stage pixels (#3309 review): room for the legend line and 12 px
// under it at the top, 12 px in from every other edge. Outliers may touch it; none sits on the legend or is cut.
function graph3dRoom() {
  const fg = graphState.fg, W = fg.width(), H = fg.height();
  const holder = document.querySelector(".gx-map .gx-3d"), key = document.querySelector(".gx-map .gx-key3d");
  let top = 12;
  if (holder && key && key.offsetParent) {
    const k = key.getBoundingClientRect(), h = holder.getBoundingClientRect();
    top = Math.max(0, k.bottom - h.top) + k.height + 12;
  }
  return { left: 12, top, right: W - 12, bottom: H - 12 };
}
// How far the marks reach toward the inner area's edges around `aim`, as a share of the room on each side (1 is
// touching): the given quantile of the marks, so the 95th percentile lets one outlier stand apart from the fit,
// and `edges` adds each mark's drawn radius so a whole sphere is counted, not its centre.
function graph3dCover(marks, aim, quantile = .95, edges = false) {
  const fg = graphState.fg, room = graph3dRoom();
  if (!marks.length || room.right <= room.left || room.bottom <= room.top) return 0;
  const camera = fg.camera(), H = fg.height(), tan = Math.tan(camera.fov * Math.PI / 360);
  const centre = fg.graph2ScreenCoords(aim.x, aim.y, aim.z);
  const reach = marks.map(n => {
    const at = fg.graph2ScreenCoords(n.x, n.y, n.z), dx = at.x - centre.x, dy = at.y - centre.y;
    const r = edges ? (n.__threeObj?.geometry?.parameters?.radius || 4) * H / (2 * tan * Math.max(1, camera.position.distanceTo(n))) : 0;
    const across = dx >= 0 ? (dx + r) / Math.max(1, room.right - centre.x) : (r - dx) / Math.max(1, centre.x - room.left);
    const down = dy >= 0 ? (dy + r) / Math.max(1, room.bottom - centre.y) : (r - dy) / Math.max(1, centre.y - room.top);
    return Math.max(across, down);
  }).sort((a, b) => a - b);
  return reach[Math.min(reach.length - 1, Math.floor(reach.length * quantile))];
}
function graph3dZoom(by) {
  const fg = graphState.fg;
  if (!fg) return;
  if (!by) return graph3dFit(true);
  const camera = fg.camera().position, target = fg.controls().target, k = 1 / by;
  fg.cameraPosition({ x: target.x + (camera.x - target.x) * k, y: target.y + (camera.y - target.y) * k, z: target.z + (camera.z - target.z) * k },
    undefined, graphReduced() ? 0 : 200);
}
// three-forcegraph shares one material per colour; each mark gets its own once, so fading one fades only it.
// Knowledge entries and the busiest records carry a soft halo, drawn from the mark's own classes.
function graph3dOwn() {
  const fg = graphState.fg;
  if (!fg) return;
  const { nodes, links } = fg.graphData();
  for (const d of nodes) {
    const mark = d.__threeObj;
    if (!mark?.material || mark.userData.own) continue;
    mark.material = mark.material.clone();
    mark.userData.own = true;
    if (graphState.hubs3.has(d.id)) graph3dGlow(mark);
  }
  for (const l of links) {
    const line = l.__lineObj;
    if (!line?.material || line.userData.own) continue;
    line.material = line.material.clone();
    line.userData.own = true;
  }
}
function graph3dGlow(mark) {
  const Halo = mark.constructor, Paint = mark.material.constructor;
  const paint = new Paint({ transparent: true, opacity: .07, depthWrite: false });
  paint.color.copy(mark.material.color);
  const halo = new Halo(mark.geometry, paint);
  halo.scale.multiplyScalar(1.55);
  halo.userData.halo = true;
  mark.add(halo);
}
// Pointing at a mark (or a focused one) keeps it and its neighbours bright and fades the rest.
function graph3dPaint() {
  const fg = graphState.fg;
  if (!fg) return;
  graph3dOwn();
  const key = graphState.hover || graphState.focus;
  const lit = key ? new Set([key, ...(GRAPH.adj.get(key) || [])]) : null;
  const mid = key && graphState.depth > 1 ? graphState.near2 : null;
  const { nodes, links } = fg.graphData();
  for (const d of nodes) {
    const mark = d.__threeObj;
    if (!mark?.userData.own) continue;
    const on = !lit || lit.has(d.id), onMid = !on && !!mid?.has(d.id);
    mark.material.transparent = true;
    mark.material.opacity = on ? .95 : onMid ? .52 : .12;
    for (const child of mark.children) if (child.userData.halo) child.material.opacity = on ? .07 : onMid ? .04 : .01;
  }
  for (const l of links) {
    const line = l.__lineObj;
    if (!line?.userData.own) continue;
    const ends = [l.source?.id ?? l.source, l.target?.id ?? l.target];
    line.material.transparent = true;
    line.material.opacity = !lit ? .45 : ends.includes(key) ? .9 : .04;
  }
  const holder = document.querySelector(".gx-map .gx-3d");
  if (holder) holder.dataset.lit = key || "";
}
// Names ride above the 3D map: the pointed or focused mark first, then the knowledge entries, the busiest
// records and the focused mark's neighbours, each only where it overlaps no name already placed. A private page
// shows its name only when pointed at, and then only as "Personal".
// Who keeps a name when names collide (#3309 review): the search hit or pointed mark, then its neighbours, then
// tag pages by degree, then everything else by degree; within a tier the mark nearer the camera first. A name that
// loses is hidden, never cut short and never drawn over another.
function graph3dNameOrder(candidates, key, camera) {
  const around = key ? GRAPH.adj.get(key) || new Set() : new Set();
  const tier = d => d.id === key ? 0 : around.has(d.id) ? 1 : d.n.k === "knowledge" ? 2 : 3;
  const degree = d => tier(d) >= 2 ? graphDegree(d.n) : 0;
  return [...candidates].sort((a, b) => tier(a) - tier(b) || degree(b) - degree(a) || camera.distanceToSquared(a) - camera.distanceToSquared(b));
}
function graph3dNames() {
  const fg = graphState.fg, layer = document.querySelector(".gx-map .gx-3d-names");
  if (!fg || !layer) return;
  graph3dOwn();
  const key = graphState.hover || graphState.focus, around = key ? GRAPH.adj.get(key) || new Set() : new Set(), hubs = graphState.hubs3;
  const camera = fg.camera().position, nodes = fg.graphData().nodes.filter(d => d.x !== undefined);
  // Closer than the fitted view, the marks nearest the camera are named too, more the closer it gets.
  const zoom = graphState.fitDist3 ? graphState.fitDist3 / camera.distanceTo(fg.controls().target) : 1;
  const near = zoom < 1.15 ? new Set() : new Set(nodes.filter(d => !graphHidden(d.n))
    .sort((a, b) => camera.distanceToSquared(a) - camera.distanceToSquared(b)).slice(0, Math.round(6 * zoom * zoom)).map(d => d.id));
  const extra = key && graphState.depth > 1 ? graphState.near2 : new Set();
  const wanted = graph3dNameOrder(nodes.filter(d => d.id === key || (!graphHidden(d.n) && ((key ? false : hubs.has(d.id)) || around.has(d.id) || extra.has(d.id) || (!key && near.has(d.id))))), key, camera);
  const W = layer.clientWidth, H = layer.clientHeight, shown = new Map([...layer.children].map(span => [span.dataset.id, span])), placed = [];
  for (const d of wanted) {
    const at = fg.graph2ScreenCoords(d.x, d.y, d.z), title = graphTitle(d.n), whole = d.id === key || hubs.has(d.id);
    // Every name is whole, wrapped to two lines as on the 2D map; one that would need cutting takes one long line.
    const wrapped = graphLines(title, Math.max(28, Math.ceil(graphWidth(title) / 2) + 2), 2);
    const lines = wrapped.text.endsWith("…") ? [title] : wrapped.lines;
    const box = [at.x + 8, at.y - 11, at.x + 22 + Math.max(...lines.map(graphWidth)) * 7, at.y - 11 + lines.length * 17 + 4];
    if (box[0] < 0 || box[2] > W || box[1] < 0 || box[3] > H) continue;
    if (d.id !== key && placed.some(other => graphBoxesMeet(box, other))) continue;
    placed.push(box);
    const label = lines.join("\n");
    let span = shown.get(d.id);
    if (span && span.dataset.text !== label) { span.remove(); span = null; }
    if (span) shown.delete(d.id);
    else layer.appendChild(span = el("span", { class: "gx-3d-name" + (whole ? " hub" : ""), "data-id": d.id, "data-text": label },
      lines.map(line => el("span", { text: line }))));
    span.style.transform = `translate(${Math.round(at.x)}px, ${Math.round(at.y)}px)`;
  }
  for (const span of shown.values()) span.remove();
}
// ---------- topics: the list, and a topic page as a record ----------
function topicRecords() { return inCategory("knowledge"); }
function topicLinked(r) {
  const model = graphModel();
  return [...(model.adj.get(r.path) || [])].map(id => model.byId.get(id)).filter(n => n.r);
}
// Knowledge is the notebook's wiki (#2996): one entry per topic, the most linked first, each row showing the
// people, organisations and projects it ties together, so the list itself says what an entry is.
function topicList() {
  const main = document.getElementById("main"), items = topicRecords();
  main.textContent = "";
  const rows = items.map(r => ({ r, linked: topicRows(r).map(row => row.n), last: r.topic?.last || "" }))
    .sort((a, b) => b.linked.length - a.linked.length || b.last.localeCompare(a.last));
  main.appendChild(el("div", { class: "gx gx-topics" }, [knowledgeHead("entries"),
    items.length ? el("ul", { class: "gx-rows" }, rows.map(topicEntry))
      : el("p", { class: "gx-quiet-line gx-filed", text: graphT("REM files knowledge from your records on its night run.") }),
    items.length > 0 && items.length < 3 && graphModel().linked.length
      ? el("p", { class: "gx-quiet-line" }, [el("a", { href: "#view=graph", text: graphT("Explore linked records →") })]) : null]));
}
function topicEntry({ r, linked, last }) {
  const shown = linked.slice(0, 4);
  return el("li", {}, [el("a", { class: "gx-entry", href: href(r) }, [graphGlyph("knowledge", 16, r.private),
      el("span", { class: "gx-row-body" }, [el("b", { text: topicName(r.title) }), el("small", { text: topicAliases(r).slice(1, 5).join(" · ") })])]),
    el("span", { class: "gx-entry-links" }, [...shown.map(n => el("a", { href: href(n.r), title: graphT(GRAPH_ONE[n.k]) }, [graphGlyph(n.k, 12, n.private), graphShort(graphTitle(n), 18)])),
      linked.length > shown.length ? el("span", { class: "gx-row-meta", text: "+" + (linked.length - shown.length) }) : null]),
    last ? el("time", { class: "gx-row-meta", datetime: last, text: fmtDate(last) }) : null]);
}
function topicAliases(r) { return r.topic?.aliases?.length ? r.topic.aliases : [r.title]; }
function topicKnown(r, name) {
  const text = section(r, name)?.text || "";
  return listItems(text).length || plainLine(text) ? text : "";
}
// One row per linked record: what it is, the sentence that names the topic, and when.
function topicRows(r) {
  const own = new Map((r.relations || []).filter(rel => rel.kind === "linked").map(rel => [rel.path, { sentence: rel.basis, date: "" }]));
  const said = new Map((r.topic?.mentions || []).map(m => [m.path, m]));
  return topicLinked(r).filter(n => n.k !== "sessions" && n.k !== "knowledge").map(n => ({ n, ...(own.get(n.id) || said.get(n.id) || { sentence: "", date: "" }) }))
    .sort((a, b) => (b.date || "").localeCompare(a.date || "") || graphDegree(b.n) - graphDegree(a.n));
}
function topicSentence(text, aliases) {
  const span = el("span", { class: "gx-said" });
  const words = aliases.filter(Boolean).map(a => a.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).sort((a, b) => b.length - a.length);
  const parts = words.length ? text.split(new RegExp("(" + words.join("|") + ")", "gi")) : [text];
  span.append(...parts.map((part, i) => i % 2 ? el("b", { text: part }) : document.createTextNode(part)));
  return span;
}
function topicRow({ n, sentence, date }, aliases) {
  const role = n.private ? "" : graphRole(n) || (n.k === "orgs" ? plainLine(String(facts(n.r).domain || "")) : "");
  return el("li", { class: "gx-link-row" }, [graphGlyph(n.k, 14, n.private), el("div", { class: "gx-row-body" }, [
    el("div", { class: "gx-row-name" }, [el("a", { href: href(n.r), text: graphTitle(n) }), role ? el("small", { text: role }) : null]),
    sentence && !n.private ? el("p", {}, [topicSentence(plainLine(sentence), aliases)]) : null]),
    date ? el("time", { datetime: date, text: fmtDate(date) }) : null]);
}
function topicGroup(kind, rows, aliases) {
  const max = 6, rest = rows.slice(max);
  const more = rest.length ? el("button", { type: "button", class: "gx-more", text: graphT("{n} more", { n: rest.length }) + ": " + rest.slice(0, 4).map(row => graphShort(graphTitle(row.n), 16)).join("、") + (rest.length > 4 ? " …" : "") + " ›" }) : null;
  const list = el("ul", { class: "gx-link-rows" }, rows.slice(0, max).map(row => topicRow(row, aliases)));
  if (more) more.onclick = () => { list.append(...rest.map(row => topicRow(row, aliases))); more.remove(); };
  return el("div", { class: "gx-group" }, [el("h3", {}, [graphT(kind === "notes" ? "Decisions" : GRAPH_NAME[kind]), el("span", { text: String(rows.length) })]), list, more]);
}
function topicLinks(r) {
  const rows = topicRows(r), aliases = topicAliases(r);
  const topic = r.topic || {};
  const quiet = topic.sessions ? el("p", { class: "gx-quiet-line" }, [el("a", { href: "#q=" + encodeURIComponent(aliases[0]),
    text: topic.skills ? graphT(topic.skills === 1 ? "Also named in {n} sessions and 1 skill" : "Also named in {n} sessions and {m} skills", { n: topic.sessions, m: topic.skills }) : graphT("Also named in {n} sessions", { n: topic.sessions }) })]) : null;
  if (!rows.length) return el("section", { class: "gx-sec" }, [el("h2", { text: graphT("Linked here") }), el("p", { class: "gx-quiet-line", text: graphT("Nothing links here yet") }), quiet]);
  const groups = ["people", "projects", "orgs", "notes"].map(k => [k, rows.filter(row => row.n.k === k)]).filter(([, list]) => list.length);
  return el("section", { class: "gx-sec" }, [el("h2", {}, [graphT("Linked here"), el("span", { text: String(rows.length) })]),
    ...groups.map(([k, list]) => topicGroup(k, list, aliases)), quiet]);
}
// Time as a line: every dated mention is a dot; no labels to read, only where it clusters.
function topicTimeline(r) {
  const dates = topicRows(r).map(row => row.date).filter(Boolean).sort();
  const written = topicKnown(r, "timeline");
  if (!dates.length && !written) return null;
  const parts = [el("h2", { text: graphT("Timeline") })];
  if (dates.length > 1) {
    const first = Date.parse(dates[0]), span = Math.max(1, Date.parse(dates.at(-1)) - first);
    const svg = svgEl("svg", { class: "gx-time", viewBox: "0 0 600 36", preserveAspectRatio: "none", "aria-hidden": "true" }, [
      svgEl("line", { x1: 0, y1: 18, x2: 600, y2: 18 }),
      ...dates.map(day => svgEl("circle", { cx: 4 + 592 * (Date.parse(day) - first) / span, cy: 18, r: 4 }))]);
    parts.push(svg, el("div", { class: "gx-time-ends" }, [el("span", { text: fmtDate(dates[0]) }),
      el("span", { text: graphT("{n} mentions, from {first} to {last}", { n: dates.length, first: fmtDate(dates[0]), last: fmtDate(dates.at(-1)) }) }), el("span", { text: fmtDate(dates.at(-1)) })]));
  }
  if (written) parts.push(el("div", { class: "gx-prose", html: markdown(written, r.path) }));
  return el("section", { class: "gx-sec" }, parts);
}
function topicDoubtful(r) {
  const doubtful = (r.topic?.doubtful || []).map(d => ({ ...d, n: GRAPH.byId.get(d.record) })).filter(d => d.n?.r);
  if (!doubtful.length) return null;
  const asked = (REM.reviews || []).some(review => review.status === "pending" && review.subjects?.[0] === r.path);
  return el("section", { class: "gx-sec" }, [el("h2", {}, [graphT("Maybe related"), el("span", { text: String(doubtful.length) })]),
    el("p", { class: "gx-quiet-line", text: graphT("Only the words match; REM did not count these as links.") }),
    el("ul", { class: "gx-link-rows" }, doubtful.slice(0, 6).map(d => topicRow({ n: d.n, sentence: d.sentence, date: "" }, topicAliases(r)))),
    asked ? el("a", { class: "gx-link", href: "#reviews=1", text: graphT("Confirm in Questions & connections →") }) : null]);
}
function topicRelated(r) {
  const mine = new Set(topicLinked(r).map(n => n.id));
  const others = topicRecords().filter(other => other.path !== r.path && !privateTopicHidden(other))
    .map(other => ({ other, shared: topicLinked(other).filter(n => mine.has(n.id)).length }))
    .filter(({ shared }) => shared).sort((a, b) => b.shared - a.shared).slice(0, 3);
  return others.length ? [el("h4", { text: graphT("Related knowledge") }), el("ul", { class: "gx-rail-list" }, others.map(({ other, shared }) =>
    el("li", {}, [el("a", { href: href(other) }, [graphGlyph("knowledge", 12, other.private), topicName(pageName(other))]), el("small", { text: graphT("{n} shared records", { n: shared }) })])))] : [];
}
function topicUnsure(r) {
  const items = listItems(section(r, "uncertainties")?.text || "").map(line => plainLine(line)).filter(line => line && !/^Unknown\b/.test(line)).slice(0, 2);
  return items.length ? [el("h4", { text: graphT("REM is not sure") }), el("ul", { class: "gx-rail-list" }, items.map(item => el("li", { text: item })))] : [];
}
// ---------- an entry: a knowledge page, a decision, a principle (#3097) ----------
// One reading, like a reference-book article: the title, the page's own text once, its notes at the end. The owner
// saw a knowledge entry printed twice (a top block whose "summary" fell back to the whole body, then Full memory
// with the same text), a Sources list after every section, and identifiers where a sentence should be.
const ENTRY_KINDS = new Set(["knowledge", "decisions", "principles"]);
const ENTRY_ZH = {
  "Drawn from your notebook": "出自你的笔记", "Show identifiers": "显示标识符", "Hide identifiers": "收起标识符",
  "Coding session": "编码会话", "Mail from {who}": "{who}的邮件", "Mail": "邮件", "WhatsApp from {who}": "{who}的 WhatsApp 消息",
  "WhatsApp message": "WhatsApp 消息", "Back to where the text cites this": "回到正文引用的地方", "Also known as {names}": "又名 {names}",
  "Updated {date}": "更新于 {date}", "{n} sources": "{n} 个来源", "1 source": "1 个来源", "Why": "为什么", "What it cost": "代价",
  "Linked from {list}": "{list}链接到这里", "{n} people": "{n} 个人", "1 person": "1 个人", "{n} organisations": "{n} 个组织",
  "1 organisation": "1 个组织", "{n} projects": "{n} 个项目", "1 project": "1 个项目", "named in {n} sessions": "{n} 个会话提到它",
  "named in 1 session": "1 个会话提到它", "last mentioned {date}": "最近一次提到是 {date}", "Still unknown: {names}": "还不知道：{names}",
  "On this page": "本页内容"
};
function entryT(key, values = {}) {
  const words = uiLanguage === "zh" && ENTRY_ZH[key] || t(key);
  return words.replace(/\{(\w+)\}/g, (match, name) => values[name] ?? match);
}
// The page as written, cut into what a reader sees apart: the text by section, the pages each section is drawn
// from, and every Sources block (at either heading level) with the stretch of text it defines numbers for.
function entryParse(body) {
  const sections = [{ title: "", lines: [], drawn: [] }], scopes = [[]], aka = [];
  let mode = "text";
  for (const line of body.split("\n")) {
    const head = /^(#{2,3})\s+(.*?)\s*$/.exec(line), name = (head ? head[2] : line).trim().toLowerCase();
    const item = /^\s*(?:[-*+]|\d+[.)])\s+(.*)$/.exec(line);
    const alias = !head && sections.length === 1 && /^\s*-?\s*(?:also known as|aka|别名)[:：]\s*(.*)$/i.exec(line);
    const next = head && /^(?:sources?|来源)$/.test(name) ? "sources" : (head ? name === "drawn from" : /^drawn from[:：]$/.test(name)) ? "drawn"
      : head?.[1].length === 2 ? "section" : alias ? "alias" : !line.trim() && mode !== "text" ? mode
      : mode === "sources" && !head ? "source" : mode === "drawn" && item ? "link" : "text";
    // Text after a Sources block starts a new stretch: its marks belong to the next block.
    if (mode === "sources" && !["sources", "source"].includes(next) && scopes.at(-1).length) scopes.push([]);
    if (next === "section") sections.push({ title: head[2], lines: [], drawn: [] });
    else if (next === "alias") aka.push(...alias[1].split(/\s*[;；]\s*/).filter(Boolean));
    else if (next === "source") scopes.at(-1).push(line.trim());
    else if (next === "link") sections.at(-1).drawn.push(item[1].trim());
    else if (next === "text") sections.at(-1).lines.push({ text: line, scope: scopes.length - 1 });
    mode = next === "source" ? "sources" : next === "link" ? "drawn" : ["section", "alias"].includes(next) ? (next === "section" ? "text" : mode) : next;
  }
  return { sections, scopes, aka };
}
// One list for the whole page. A page with a single Sources block keeps the numbers it was written with, so the
// page and Copy Markdown agree; with several, the list is numbered again in reading order and a source that two
// sections cite is listed once. Lines without a number are kept as unnumbered notes.
function entryNumbers(scopes) {
  const keep = scopes.filter(defs => defs.length).length < 2, sources = [], notes = [], seen = new Map();
  const maps = scopes.map(defs => {
    const map = new Map();
    for (const line of defs) {
      const m = /^(?:[-*+]\s+)?(?:[\[［](W?\d{1,3})[\]］]|(\d{1,3})[.)])\s*(.*)$/.exec(line);
      if (!m) { notes.push(line.replace(/^[-*+]\s+/, "")); continue; }
      const old = m[1] || m[2], text = m[2] ? m[3] : m[3].replace(/[*`]/g, ""), key = sourceId(text, !!m[2]) || text;
      if (map.has(old)) continue;
      const n = keep ? old : seen.get(key) || String(sources.length + 1);
      if (keep || !seen.has(key)) sources.push({ n, text, ...(m[2] ? { plain: true } : {}) });
      seen.set(key, n); map.set(old, n);
    }
    return map;
  });
  return { maps, sources, notes };
}
function entryModel(body) {
  const { sections, scopes, aka } = entryParse(body), { maps, sources, notes } = entryNumbers(scopes);
  // A mark is defined by its own stretch's Sources; text with no Sources of its own reads the nearest definition.
  // A number nothing defines stays as words: it must never borrow another source's number.
  const number = (scope, old) => maps[scope].size ? maps[scope].get(old) : maps.findLast(map => map.has(old))?.get(old);
  const line = ({ text, scope }) => {
    const marked = text.replace(/[\[［](W?\d{1,3})[\]］]/g, (m, old) => "[" + (number(scope, old) || old + "​") + "]");
    // A line that is wholly the owner's quoted words (and its marks) is set as a quote.
    return /^\s*[“「][^\n]*[”」]\s*(?:\[[^\]]+\]\s*)*$/.test(marked) ? "\n> " + marked.trim() + "\n" : marked;
  };
  const read = sections.map(s => ({ title: s.title, text: s.lines.map(line).join("\n").trim(), drawn: s.drawn }));
  return { aka, sections: read.filter(s => s.text || s.drawn.length), sources, notes };
}
// What the reader shows of a page: unknown lines, the stamp and tool markers are already out (known()).
function entryBody(r) {
  const k = known(r);
  return [k.intro, ...k.kept.map(s => "## " + s.title + "\n" + s.text)].join("\n\n");
}
const ENTRY = new WeakMap();
function entryOf(r) {
  const held = ENTRY.get(r);
  if (held?.text === r.text) return held.model;
  const model = entryModel(entryBody(r));
  ENTRY.set(r, { text: r.text, model });
  return model;
}
// A source in words: what it is, who it is from, when. The identifier stays behind the row.
function entrySourceWords(source) {
  const id = sourceId(source.text, source.plain), context = (REM.source_context || {})[id], kind = (context?.source || id.split(":")[0]).toLowerCase();
  const day = context?.time ? calendarDay(context.time) : /\d{4}-\d{2}-\d{2}/.exec(source.text)?.[0];
  const who = context ? sourceSender(context) : "";
  const what = /^(?:codex|claude)/.test(kind) ? entryT("Coding session") : /^(?:gmail|outlook)/.test(kind) ? entryT(who ? "Mail from {who}" : "Mail", { who })
    : kind === "whatsapp" ? entryT(who ? "WhatsApp from {who}" : "WhatsApp message", { who }) : id ? sourceChannel(kind) : source.text;
  return [what, day ? calendarDate(day) : ""].filter(Boolean).join(uiLanguage === "zh" ? "，" : ", ");
}
function entrySourceRow(r, source, refs) {
  const origin = safeHref(r.path, "../" + (/originating page:\s*([\w./-]+\.md)/.exec(source.text)?.[1] || "")), words = entrySourceWords(source);
  const backs = (refs.get(source.n) || []).map(id => el("a", { class: "entry-back", href: href(r) + "&h=" + id, "aria-label": entryT("Back to where the text cites this"), text: "↩" }));
  return el("li", { ...(source.n ? { id: "src-" + source.n.toLowerCase() } : {}), title: source.text }, [el("span", { class: "entry-n", text: source.n || "·" }),
    el("span", { class: "entry-what" }, [origin && byPath(decodeURIComponent(origin.href.slice(3))) ? el("a", { href: origin.href, text: words }) : words, ...backs]),
    el("code", { class: "entry-id", text: source.text })]);
}
// Sources once, last: one list for every section, each row in words, back-links to the marks that cite it.
function entrySources(r, model, refs) {
  const trailer = model.sources.length ? [] : splitTrailers(r.text).sources.split(/,\s*/).filter(Boolean);
  const rows = [...model.sources, ...[...model.notes, ...trailer].map(text => ({ n: "", text }))];
  if (!rows.length) return null;
  const out = el("section", { class: "entry-sources" }), ids = el("button", { type: "button", class: "entry-ids", "aria-pressed": "false", text: entryT("Show identifiers") });
  ids.onclick = () => {
    const shown = out.classList.toggle("show-ids");
    ids.setAttribute("aria-pressed", String(shown));
    ids.textContent = entryT(shown ? "Hide identifiers" : "Show identifiers");
  };
  out.append(el("div", { class: "entry-sources-head" }, [el("h2", { id: "sources", text: t("Sources") }), ids]), el("ol", {}, rows.map(source => entrySourceRow(r, source, refs))));
  return out;
}
// Marks are raised numbers; a run of marks is written out so each one reaches its own note, and every mark has
// an address its note can link back to.
function entryMarks(r, box) {
  for (const run of box.querySelectorAll("a.cite.run")) run.outerHTML = run.dataset.sources.split(" ").map(n => citeChip(n, r.path)).join("");
  const refs = new Map();
  for (const mark of box.querySelectorAll("a.cite")) {
    const n = mark.dataset.sources, ids = refs.get(n) || refs.set(n, []).get(n);
    mark.id = "ref-" + n.toLowerCase() + (ids.length ? "-" + (ids.length + 1) : "");
    ids.push(mark.id);
  }
  return refs;
}
// The notebook pages a section rests on: where the learning came from, apart from the evidence under Sources.
function entryDrawn(r, items, label = "Drawn from your notebook") {
  return el("aside", { class: "entry-drawn" }, [el("span", { class: "entry-label", text: entryT(label) }),
    el("ul", {}, items.map(item => el("li", { html: inline(item, r.path) })))]);
}
// A date in a sentence reads as a date ("27 Aug"), in the sentence's own language. The owner's quoted words and
// anything inside a path or a link keep the characters they were written with.
function entryDates(text) {
  const day = /(?<![\w/.-])\d{4}-\d{2}-\d{2}(?![\w-]|\.\w)/g;
  return text.split("\n").map(line => /^\s*>/.test(line) ? line
    : line.replace(day, found => calendarDate(found, /\p{Script=Han}/u.test(line) ? "zh-CN" : "en-US"))).join("\n");
}
function entrySection(r, s, ids) {
  const out = el("section", { class: "entry-sec" });
  if (s.title) {
    const base = s.title.toLowerCase().replace(/[^\p{L}\p{N}_\s-]/gu, "").trim().replace(/\s+/g, "-") || "section";
    let id = base, n = 1;
    while (ids.has(id)) id = base + "-" + n++;
    ids.add(id);
    out.appendChild(el("h2", { id, html: inline(entryT(s.title), r.path) }));
  }
  out.insertAdjacentHTML("beforeend", markdown(entryDates(s.text), r.path));
  if (s.drawn.length) out.appendChild(entryDrawn(r, s.drawn));
  return out;
}
// What links to a knowledge entry, in words, and only what is above zero: four counters reading 0 said nothing.
function entryCounts(r) {
  const rows = topicRows(r), topic = r.topic || {}, count = kind => rows.filter(row => row.n.k === kind).length;
  const one = (n, single, many) => n ? entryT(n === 1 ? single : many, { n }) : "";
  const linked = [one(count("people"), "1 person", "{n} people"), one(count("orgs"), "1 organisation", "{n} organisations"), one(count("projects"), "1 project", "{n} projects")].filter(Boolean);
  const parts = [linked.length ? entryT("Linked from {list}", { list: linked.join(uiLanguage === "zh" ? "、" : ", ") }) : "",
    one(topic.sessions || 0, "named in 1 session", "named in {n} sessions")].filter(Boolean);
  if (!parts.length) return null;
  if (topic.last) parts.push(entryT("last mentioned {date}", { date: fmtDate(topic.last) }));
  return el("p", { class: "entry-counts", text: capFirst(parts.join(" · ")) });
}
function entryHead(r, model, written) {
  const topic = r.category === "knowledge", title = topic ? topicName(r.title) : r.title, same = text => text.toLowerCase().replace(/\s+/g, "");
  const aka = [...new Map([...model.aka, ...(r.topic?.aliases || [])].map(name => [same(name), name])).values()].filter(name => same(name) !== same(title) && same(name) !== same(r.title));
  const first = topic ? topicRows(r).map(row => row.date).filter(Boolean).sort()[0] : "";
  const unwritten = written ? "" : first ? graphT("REM has not written this page yet · named in {n} records since {date}", { n: topicRows(r).length, date: fmtDate(first) }) : graphT("REM has not written this page yet");
  const sources = model.sources.length;
  return el("header", { class: "gx-topic-head" }, [el("a", { class: "gx-crumb", href: categoryHref(r.category), text: categoryName(r.category) }),
    el("div", { class: "gx-topic-name" }, [topic ? graphGlyph("knowledge", 32, r.private) : null, el("h1", { class: "gx-statement", text: title })]),
    aka.length ? el("p", { class: "entry-aka", text: entryT("Also known as {names}", { names: aka.join(" · ") }) }) : null,
    unwritten ? el("p", { class: "gx-lede", text: unwritten }) : null,
    el("p", { class: "entry-meta" }, [entryT("Updated {date}", { date: fmtDate(r.updated) }),
      sources ? " · " : null, sources ? el("a", { href: href(r) + "&h=sources", text: entryT(sources === 1 ? "1 source" : "{n} sources", { n: sources }) }) : null]),
    pageTagRow(r), topic ? entryCounts(r) : null,
    // A tag page has the same Investigate control (#3140): it reads every page carrying the tag.
    topic ? investigateControl(r) : null]);
}
function permissionsPanel(r) {
  if (!((r.category === "people" && r.path !== REM.owner) || r.category === "orgs")) return null;
  const sec = section(r, "permissions") || section(r, "context flow");
  const factItems = (parseFacts(r).get("Permissions") || []).map(i => i.value).filter(Boolean);
  const lines = sec ? listItems(sec.text).filter(l => !isCalm(l)) : factItems;
  if (lines.length) {
    return panel("Permissions", [el("ul", { class: "perm-list" }, lines.map(line => el("li", { html: inline(line, r.path) })))]);
  }
  return panel("Permissions", [el("p", { class: "perm-empty", text: t("No permissions inferred yet") })]);
}
function pageJumpBar(r, toc) {
  if (toc.length < 2) return null;
  const preview = toc.slice(0, 3).map(item => item.title).join(" · ");
  const jump = el("details", { class: "jump" }, [
    el("summary", { text: (uiLanguage === "zh" ? "本页 · " : "On this page · ") + preview }),
    el("ul", {}, toc.map(item => el("li", {}, [el("a", { href: href(r) + "&h=" + encodeURIComponent(item.id), text: item.title })])))
  ]);
  jump.addEventListener("click", ev => { if (ev.target.closest("a")) jump.open = false; });
  return jump;
}
let pageNavObserver = null;
function bindPageNavObserver(main) {
  if (pageNavObserver) { pageNavObserver.disconnect(); pageNavObserver = null; }
  if (typeof IntersectionObserver === "undefined") return;
  const links = [...main.querySelectorAll(".page-nav .toc a[data-target]")];
  if (!links.length) return;
  const byId = new Map(links.map(a => [a.dataset.target, a]));
  const targets = [...byId.keys()].map(id => document.getElementById(id)).filter(Boolean);
  if (!targets.length) return;
  const activate = id => {
    for (const [tid, link] of byId) link.classList.toggle("active", tid === id);
  };
  activate(targets[0].id);
  pageNavObserver = new IntersectionObserver(entries => {
    const visible = entries.filter(e => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
    if (visible.length) { activate(visible[0].target.id); return; }
    const above = targets.filter(t => t.getBoundingClientRect().top <= 120);
    if (above.length) activate(above.at(-1).id);
  }, { rootMargin: "-48px 0px -65% 0px", threshold: [0, 1] });
  for (const target of targets) pageNavObserver.observe(target);
}
function collectColumnToc(main, usedIds = new Set()) {
  const out = [];
  for (const h of main.querySelectorAll("h2")) {
    if (h.closest(".page-nav, dialog, .jump")) continue;
    const rawTitle = h.cloneNode(true);
    rawTitle.querySelectorAll(".heading-anchor, .deep-hint").forEach(n => n.remove());
    rawTitle.querySelectorAll("span").forEach(s => { if (s.previousSibling) s.before(" "); });
    const title = rawTitle.textContent.replace(/\s+/g, " ").trim();
    if (!title) continue;
    if (!h.id) {
      const base = (h.dataset.anchor || title).toLowerCase().replace(/[^\p{L}\p{N}_\s-]/gu, "").replace(/\s+/g, "-") || "section";
      let id = base, n = 1;
      while (usedIds.has(id) || document.getElementById(id)) id = base + "-" + n++;
      h.id = id;
    }
    usedIds.add(h.id);
    out.push({ title, id: h.id });
  }
  return out;
}
function entryRail(r) {
  const topic = r.category === "knowledge";
  // A page nothing links to has no place in the graph to show: no card saying so.
  const parts = [graphModel().adj.has(r.path) ? graphLocal(r) : null, ...(topic ? [...topicRelated(r), ...topicUnsure(r)] : [])].filter(Boolean);
  return parts.length ? el("div", { class: "gx gx-rail", "aria-label": graphT("About") }, parts) : null;
}
function entryFoot(r) {
  const path = el("button", { class: "btn-action copy-path", type: "button", text: t("Copy the file path"), title: r.path });
  path.onclick = () => copyToClipboard(REM.root + "/" + r.path, path, t("Path copied"));
  const copy = el("button", { class: "btn-action", type: "button", text: t("Copy Markdown"), title: t("Copy the page as written, unknowns included") });
  copy.onclick = () => copyToClipboard(r.text, copy, t("Markdown copied"));
  return el("div", { class: "page-foot" }, [path, copy, languageBar(r)]);
}
// What a knowledge entry gathers besides its own words: the records that link to it, when, and what only shares the
// word. A page that names its sources under Drawn from does not list the same pages again as "Linked here".
function entryGathered(r, text, written) {
  if (r.category !== "knowledge") return [];
  const drawn = new Set([...text.querySelectorAll(".entry-drawn a")].map(a => a.getAttribute("href")));
  const more = topicRows(r).some(row => !row.n.r || !drawn.has(href(row.n.r)));
  return [!written || more ? topicLinks(r) : null, topicTimeline(r), topicDoubtful(r)];
}
function entryPage(r) {
  graphModel();
  const k = known(r), model = entryOf(r), ids = new Set(["sources"]), related = splitTrailers(r.text).related;
  const drawnTimeline = r.category === "knowledge" && !!topicTimeline(r);
  const sections = model.sections.filter(s => !(drawnTimeline && s.title.toLowerCase() === "timeline"));
  const text = el("div", { class: "entry-text note" }, sections.map(s => entrySection(r, s, ids)));
  if (related) text.appendChild(entryDrawn(r, [related], "Related"));
  const refs = entryMarks(r, text), written = model.sections.length > 0;
  const missing = k.missing.length ? el("p", { class: "entry-missing", text: entryT("Still unknown: {names}", { names: k.missing.map(name => t(name)).join(uiLanguage === "zh" ? "、" : ", ") }) }) : null;
  const srcBlock = entrySources(r, model, refs);
  const headNode = entryHead(r, model, written);
  const bodyCol = el("div", { class: "gx-main" }, [text, ...entryGathered(r, text, written), missing, threadDecisionHistory(r), srcBlock, entryFoot(r)]);
  return el("article", { class: "gx gx-topic entry" }, [headNode, el("div", { class: "gx-grid no-rail" }, [bodyCol])]);
}
// A deep link to a note, a mark or a heading: bring it to the middle of the page and light it briefly.
function entryReveal(heading) {
  const target = heading && (document.getElementById(heading) || document.getElementById(heading.toLowerCase()));
  if (!target) return;
  target.scrollIntoView({ block: /^(?:src|ref)-/.test(target.id) ? "center" : "start" });
  if (/^(?:src|ref)-/.test(target.id)) target.classList.add("flash");
}

// ---------- a local graph for a record's rail: one hop, kind shapes, labels for the few that matter ----------
function graphLocal(r) {
  const model = graphModel(), centre = model.byId.get(r.path);
  if (!centre || !model.adj.has(r.path)) return el("section", { class: "gx-local" }, [el("h4", { text: graphT("In the knowledge graph") }), el("p", { class: "gx-quiet-line", text: graphT("Not in the knowledge graph yet") })]);
  const ring = [...model.adj.get(r.path)].map(id => model.byId.get(id))
    .sort((a, b) => GRAPH_ORDER.indexOf(a.k) - GRAPH_ORDER.indexOf(b.k) || graphTitle(a).localeCompare(graphTitle(b)));
  const W = 236, H = 200, cx = W / 2, cy = H / 2, labelled = new Set([...ring].sort((a, b) => graphDegree(b) - graphDegree(a)).slice(0, 5).map(n => n.id));
  const marks = [], lines = [], labels = [];
  ring.forEach((n, i) => {
    const angle = -Math.PI / 2 + 2 * Math.PI * i / ring.length, radius = ring.length > 18 && i % 2 ? 58 : ring.length <= 6 ? 60 : 82;
    const x = cx + Math.cos(angle) * radius, y = cy + Math.sin(angle) * radius;
    lines.push(svgEl("line", { x1: cx, y1: cy, x2: x, y2: y, class: n.k === "knowledge" || centre.k === "knowledge" ? "topic" : "" }));
    marks.push(graphLocalMark(n, x, y, n.k === "knowledge" ? 5 : 3.6));
    const text = labelled.has(n.id) && !n.private ? graphLocalLabel(graphTitle(n), x, W, Math.cos(angle) >= 0) : "";
    if (text) labels.push(svgEl("text", { x: x + (Math.cos(angle) >= 0 ? 7 : -7), y: y + 4, "text-anchor": Math.cos(angle) >= 0 ? "start" : "end" }, [document.createTextNode(text)]));
  });
  const svg = svgEl("svg", { class: "gx-local-svg", width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": graphT("In the knowledge graph") }, [svgEl("g", { class: "gx-local-lines" }, lines), ...marks,
    graphLocalMark(centre, cx, cy, 7, true), svgEl("text", { x: cx, y: cy + 21, "text-anchor": "middle", class: "centre" }, [document.createTextNode(graphShort(graphTitle(centre), 16))]), ...labels]);
  return el("section", { class: "gx-local" }, [el("h4", { text: graphT("In the knowledge graph") }), svg,
    el("div", { class: "gx-local-foot" }, [el("span", { text: graphT("{n} directly linked", { n: ring.length }) }), el("a", { href: "#view=graph&focus=" + encodeURIComponent(r.path), text: graphT("Open in the knowledge graph →") })])]);
}
// A label gets the room between its 7px offset and the card's edge (about 6.5 per letter), not a fixed 18;
// under three letters it is only "…", so none.
function graphLocalLabel(title, x, W, right) {
  const room = Math.floor(((right ? W - x : x) - 7) / 6.5);
  return room < 3 ? "" : graphShort(title, Math.min(18, room));
}
function graphLocalMark(n, x, y, r, centre = false) {
  const title = graphTitle(n);
  const hit = svgEl("circle", { cx: x, cy: y, r: 12, fill: "transparent" });
  const shape = graphSvgMark(n.k, x, y, n.k === "sessions" ? Math.min(r, 4) : r, n.private);
  const link = svgEl("a", { ...(centre ? { class: "centre" } : {}), "aria-label": title,
    href: n.r ? href(n.r) : "#view=graph&focus=" + encodeURIComponent(n.id) }, [svgEl("title", {}, [document.createTextNode(title)]), hit, shape]);
  return link;
}
function graphRailAttach(main, r) {
  if (!["people", "orgs", "projects"].includes(r.category) || !REM.graph?.nodes) return;
  const model = graphModel();
  if (!model.adj.has(r.path)) return;
  const rail = graphLocal(r, model);
  const deep = main.querySelector(".deep-note");
  const target = deep ? (deep.querySelector(".side") || deep.querySelector(".body") || deep) : null;
  if (target) target.append(rail);
  else main.append(rail);
}
function graphRailBlock(r) {
  if (!["people", "orgs", "projects"].includes(r.category) || !REM.graph?.nodes) return null;
  const model = graphModel();
  if (!model.adj.has(r.path)) return null;
  const topics = [...model.adj.get(r.path)].map(id => model.byId.get(id)).filter(n => n.k === "knowledge" && n.r && !privateTopicHidden(n.r));
  return el("div", { class: "gx gx-attach" }, [graphLocal(r), topics.length ? el("p", { class: "gx-topic-line" }, [el("span", { text: graphT("Knowledge here") + " " }),
    ...topics.flatMap((n, i) => [i ? "、" : "", el("a", { href: href(n.r), text: graphTitle(n) })])]) : null]);
}
function attachPageNav(main, r, extraPanels = []) {
  const toc = collectColumnToc(main);
  if (main.querySelector("#sources") && !toc.some(item => item.id === "sources")) toc.push({ title: t("Sources"), id: "sources" });
  const tocNode = toc.length ? tocPanel([el("ul", { class: "toc" }, toc.map(item =>
    el("li", {}, [el("a", { href: href(r) + "&h=" + encodeURIComponent(item.id), "data-target": item.id, text: item.title })])))]) : null;
  const permNode = permissionsPanel(r);
  const navChildren = [tocNode, permNode, ...extraPanels].filter(Boolean);
  const jump = pageJumpBar(r, toc);
  if (jump) {
    const anchor = main.querySelector(":scope > .page-head, .person-head, .ov-say, .gx-topic > header");
    if (anchor) anchor.after(jump);
  }
  if (navChildren.length) {
    main.appendChild(el("aside", { class: "page-nav", "aria-label": t("About this page") }, navChildren));
    bindPageNavObserver(main);
  }
}

