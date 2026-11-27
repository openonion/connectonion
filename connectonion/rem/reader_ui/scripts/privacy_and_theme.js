// ---- Privacy levels (#2840 slice 1; owner, 2026-11-19: «隐私级别过滤的那么一个按钮…跟翻译的按钮…在右上角…某些内容默认是蒙版或者
// 默认是消失的…分到一级二级三级») ----
// One source of truth, privacyLevel: "all" shows every labelled passage; "cover" (this computer's default) shows
// [personal] and keeps each [sensitive] passage behind a curtain lifted one at a time; "public" takes [personal] and
// [sensitive] out of the page entirely, for screen sharing. A snapshot or remote reader starts at "public".
// :root carries hide-private for "public" (every existing rule reads it) and privacy-cover for "cover".
const PRIVACY_LEVELS = ["all", "cover", "public"];
Object.assign(UI.zh, { "Show all": "全部显示", "Cover sensitive": "遮住敏感", "Public only": "只看公开", "Privacy": "隐私",
  "Personal and sensitive passages are shown.": "私人和敏感内容都显示。",
  "Personal shown; each sensitive passage is covered until you tap it.": "私人内容显示；每段敏感内容先遮住，点一下才显示。",
  "Personal and sensitive passages are taken out, for sharing your screen.": "私人和敏感内容都拿掉，适合共享屏幕。",
  "Sensitive · tap to show": "敏感 · 点一下显示", "A sensitive item (covered)": "一件敏感的事（已遮住，在「显示」里选全部显示可看）", "Sensitive": "敏感", "Personal passage": "私人", "All": "全部", "Covered": "遮敏感", "Public": "公开", "Display": "显示", "Language": "语言", "1 passage hidden": "1 处已隐藏", "{n} passages hidden": "{n} 处已隐藏" });
const PRIVACY_WORDS = { all: ["Show all", "Personal and sensitive passages are shown.", "All"],
  cover: ["Cover sensitive", "Personal shown; each sensitive passage is covered until you tap it.", "Covered"],
  public: ["Public only", "Personal and sensitive passages are taken out, for sharing your screen.", "Public"] };
let privacyLevel = "cover";
// This computer: a file opened here, or the live reader on loopback. The phone and the relay are elsewhere.
function onThisComputer() { return location.protocol === "file:" || /^(127\.0\.0\.1|localhost|\[::1\])$/.test(location.hostname); }
function privacyDefault() { return REM?.shared || !onThisComputer() ? "public" : "cover"; }
function applyPrivacyClasses() {
  const root = document.documentElement;
  root.classList.toggle("hide-private", privacyLevel === "public");
  root.classList.toggle("privacy-cover", privacyLevel === "cover");
}
let privacyRemoved = false;  // whether Public only has taken passages out of the page since it was drawn
function setPrivacy(level, { save = true, redraw: again = true } = {}) {
  // Shared and remote readers only *start* at Public only; whoever is looking may still choose.
  const prevLevel = privacyLevel;
  const wasPublic = typeof document !== "undefined" && !!document.documentElement?.classList?.contains("hide-private");
  privacyLevel = PRIVACY_LEVELS.includes(level) ? level : privacyDefault();
  applyPrivacyClasses();
  const isPublic = privacyLevel === "public";
  if (save) readerStorage("co-rem-privacy", privacyLevel);
  renderPrivacyControl();
  renderDisplayMenu();
  if (!again || !REM) return;
  const maskChanged = (prevLevel === "all") !== (privacyLevel === "all") && (REM.records || []).some(r => r.private);
  if ((privacyLevel !== "public" && privacyRemoved) || maskChanged || prevLevel !== privacyLevel && isPublic) {
    // Passages Public only took out, or private-title masks toggled (#3387, #3436), redraw cleanly from the notebook.
    privacyRemoved = false;
    drawKeepingView(true);
  } else {
    if (privacyLevel !== "cover") uncurtain(document);
    applyPrivacy(document.body);
  }
  document.querySelectorAll(".activity-list").forEach(list => list.refreshActivity?.());
  document.querySelectorAll(".session-find").forEach(bar => bar.refreshSessionFind?.());
  const query = new URLSearchParams(location.hash.slice(1)).get("q");
  if (query) search(query);
  refreshFocusExpansion();
  if (wasPublic !== isPublic && REM.records.some(r => r.private && ["knowledge", ...STATEMENT_CATEGORIES].includes(r.category))) render();
}
function uncurtain(root) {
  for (const node of root.querySelectorAll(".curtain")) {
    node.classList.remove("curtain", "lifted");
    for (const name of ["role", "aria-label", "tabindex", "data-curtain", "data-curtain-short", "title"]) node.removeAttribute(name);
  }
}
// The old switch and every "Show labelled passages" button now go through the levels.
function togglePrivate() { setPrivacy(document.documentElement.classList.contains("hide-private") ? "all" : "public"); }
function revealLabelled() { setPrivacy("all"); }
function renderPrivacyControl() {
  const button = document.getElementById("privacy-level");
  if (!button) return;
  const [word, , short] = PRIVACY_WORDS[privacyLevel];
  // The state in words; a phone's top bar has room for its short word.
  // The short word in the bar (公开 / 遮敏感 / 全部); the full word and its meaning in the title and menu (rc34 check).
  button.replaceChildren(el("span", { class: "pl-short", text: t(short) }));
  button.title = t(PRIVACY_WORDS[privacyLevel][1]);
  button.setAttribute("aria-label", t("Privacy") + ": " + t(word));
  button.onclick = event => { event.stopPropagation(); togglePrivacyMenu(); };
}
function togglePrivacyMenu(open) {
  const button = document.getElementById("privacy-level"), host = button.parentElement;
  const shown = host.querySelector(".privacy-menu");
  if (shown || open === false) { shown?.remove(); button.setAttribute("aria-expanded", "false"); return; }
  const menu = el("ul", { class: "privacy-menu", role: "menu", "aria-label": t("Privacy") }, [
    ...PRIVACY_LEVELS.map(level => {
      const item = el("button", { type: "button", role: "menuitemradio", "aria-checked": String(level === privacyLevel), "data-level": level },
        [el("span", { text: t(PRIVACY_WORDS[level][0]) }), el("small", { text: t(PRIVACY_WORDS[level][1]) })]);
      item.onclick = () => { togglePrivacyMenu(false); setPrivacy(level); button.focus({ preventScroll: true }); };
      return el("li", {}, [item]);
    }),
    el("li", { class: "privacy-legend", role: "presentation" }, [
      el("span", {}, [el("i", { class: "personal", "aria-hidden": "true" }), t("Personal passage")]),
      el("span", {}, [el("i", { class: "sensitive", "aria-hidden": "true" }), t("Sensitive")])
    ])
  ]);
  host.appendChild(menu);
  button.setAttribute("aria-expanded", "true");
  menu.querySelector('[aria-checked="true"]').focus({ preventScroll: true });
}
// A labelled passage: one the markdown marked [personal] or [sensitive]. Raw source excerpts and conversation
// messages are .private too, but carry no label; they keep their own rule (hidden at Public only by CSS).
function labelled(node) { return node.hasAttribute("data-level") || !!node.querySelector(".privacy-tag, [data-level]"); }
// A labelled passage's level: its own data-level, else the strongest label inside it.
function passageLevel(node) {
  return node.dataset.level || (node.querySelector('[data-level="sensitive"], .privacy-tag.sensitive') ? "sensitive" : "personal");
}
// Applied to whatever the page draws (a MutationObserver below), so every place gets it: pages, cards, sheets,
// search, side cards, tag pages.
// The net under every place that draws page words as plain text, a title or an aria-label without going through
// inline() (a relation reason was one, #3425): a raw [personal]/[sensitive] mark is a label, never a word, so it is
// taken out at every level, and the element that held it becomes a passage at that level, which the rules below then
// curtain (遮敏感) or remove (只看公开). A title or aria-label that held one is dropped below 全部显示.
const RAW_MARK = /[ \t]*[\[［](personal|sensitive)[\]］]/gi;
function sweepRawMarks(root) {
  const txt = root.textContent || "";
  const hasBracketText = txt.includes("[") || txt.includes("［");
  if (hasBracketText) {
    const marked = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      // A session quote is the owner's own typing, kept literally, a typed "[personal]" included (test_rem_sessions).
      if (!/[\[［](?:personal|sensitive)[\]］]/i.test(node.nodeValue) || node.parentElement?.closest("textarea, input, code, pre, script, style, .session-quote")) continue;
      marked.push(node);
    }
    for (const node of marked) {
      const level = /[\[［]sensitive[\]］]/i.test(node.nodeValue) ? "sensitive" : "personal";
      node.nodeValue = node.nodeValue.replace(RAW_MARK, "");
      const host = node.parentElement;
      if (host && !host.closest("[data-level]")) { host.classList.add("private"); host.dataset.level = level; }
    }
  }
  const attrSel = '[title*="["], [title*="［"], [aria-label*="["], [aria-label*="［"]';
  for (const el of [...(root.matches?.(attrSel) ? [root] : []), ...(root.querySelectorAll ? root.querySelectorAll(attrSel) : [])]) {
    for (const name of ["title", "aria-label"]) {
      const value = el.getAttribute(name);
      if (!value || !/[\[［](?:personal|sensitive)[\]］]/i.test(value)) continue;
      if (privacyLevel === "all") el.setAttribute(name, value.replace(RAW_MARK, "")); else el.removeAttribute(name);
    }
  }
}
function applyPrivacy(root) {
  if (!(root instanceof Element)) return;
  sweepRawMarks(root);
  if (privacyLevel === "all") return;
  const within = selector => [...(root.matches(selector) ? [root] : []), ...root.querySelectorAll(selector)];
  if (privacyLevel === "cover") {
    for (const node of within(".private")) {
      if (!labelled(node) || node.closest(".curtain") || node.parentElement?.closest(".private")) continue;
      node.dataset.level = passageLevel(node);
      if (node.dataset.level !== "sensitive") continue;
      node.classList.add("curtain");
      Object.assign(node, { tabIndex: 0 });
      node.setAttribute("role", "button");
      node.setAttribute("data-curtain", t("Sensitive · tap to show"));
      node.setAttribute("data-curtain-short", t("Sensitive"));
      node.setAttribute("aria-label", t("Sensitive · tap to show"));
      node.title = t("Sensitive · tap to show");
    }
    return;
  }
  // Public only: the passages leave the page, and each place says how many it lost.
  const lost = new Map();
  for (const node of within(".private, li.private-item, .private-entry, .privacy-only > .privacy-content")) {
    if (!node.isConnected && node !== root) continue;
    if (node.classList.contains("private") && !labelled(node)) continue;
    const quiet = node.closest(".privacy-only") || node.classList.contains("private-entry");
    const place = node.parentElement?.closest(".deep-note, .entry, .qcard, .pcard, dialog, #main");
    if (place && !quiet) lost.set(place, (lost.get(place) || 0) + 1);
    if (node === root) { node.replaceChildren(); node.hidden = true; } else mendAfterRemoving(node);
    privacyRemoved = true;
  }
  pruneEmptyPublicSections(root);
  for (const [place, n] of lost) {
    if (!place.isConnected && place !== root) continue;
    if (place.matches("li, td")) continue;  // a row's own gap says it; a line per row would be noise
    const line = place.querySelector(":scope > .privacy-count") || place.appendChild(el("p", { class: "privacy-count" }));
    const total = Number(line.dataset.n || 0) + n;
    line.dataset.n = total;
    line.textContent = t(total === 1 ? "1 passage hidden" : "{n} passages hidden", { n: total });
  }
}
// #3417: At Public only, any container or section whose ONLY content was private vanishes completely — heading included.
function pruneEmptyPublicSections(root) {
  if (!(root instanceof Element) || typeof document === "undefined") return;
  const within = selector => [...(root.matches(selector) ? [root] : []), ...root.querySelectorAll(selector)];
  const emptyText = node => {
    const clone = node.cloneNode(true);
    clone.querySelectorAll(".heading-anchor, .privacy-count, .private-history-notice, .private-hidden-notice").forEach(n => n.remove());
    return !/[\p{L}\p{N}]/u.test(clone.textContent || "");
  };
  for (const list of within("ul, ol, dl, p, blockquote")) {
    if (!list.isConnected || list.matches(".privacy-menu, .toc")) continue;
    if (list.matches("ul, ol, dl") && ![...list.children].some(c => !c.hidden && !emptyText(c))) { list.remove(); privacyRemoved = true; }
    else if (list.matches("p, blockquote") && !list.classList.contains("privacy-count") && emptyText(list) && !list.querySelector("img, svg, input, button")) { list.remove(); privacyRemoved = true; }
  }
  for (const block of within(".block-insight, .block-threads, .block-history, .block-standing, .person-threads, .focus-facts, .relation-list, .document-list")) {
    if (block.isConnected && emptyText(block)) { block.remove(); privacyRemoved = true; }
  }
  // Flat headings in .note (h2 followed by siblings until next h2): remove h3s first, then h2s with no public content after them.
  for (const level of ["H3", "H2"]) {
    for (const h of within(level.toLowerCase())) {
      if (!h.isConnected || !h.parentElement?.matches(".note, .entry-text")) continue;
      let cur = h.nextElementSibling, hasContent = false;
      while (cur && cur.tagName !== "H2" && !(level === "H3" && cur.tagName === "H3")) {
        if (!cur.hidden && !cur.classList.contains("privacy-count") && !emptyText(cur)) { hasContent = true; break; }
        cur = cur.nextElementSibling;
      }
      if (!hasContent) {
        if (h.id) document.querySelectorAll(`.toc a[href$="&h=${encodeURIComponent(h.id)}"], .jump a[href$="&h=${encodeURIComponent(h.id)}"]`).forEach(a => a.closest("li")?.remove());
        h.remove();
        privacyRemoved = true;
      }
    }
  }
  for (const sec of within(".entry-sec, .focus-section, .widget:not(.others):not(.tnext), .ov-page section:not(.ov-stage)")) {
    if (!sec.isConnected) continue;
    const clone = sec.cloneNode(true);
    clone.querySelectorAll("h1, h2, h3, h4, .wt, .activity-head, .activity-filters, .activity-more, .relation-description, .privacy-count, .private-history-notice, .private-hidden-notice").forEach(n => n.remove());
    if (!/[\p{L}\p{N}]/u.test(clone.textContent || "")) {
      const id = sec.id || sec.querySelector("h2[id], h3[id]")?.id;
      if (id) document.querySelectorAll(`.toc a[href$="&h=${encodeURIComponent(id)}"], .jump a[href$="&h=${encodeURIComponent(id)}"]`).forEach(a => a.closest("li")?.remove());
      sec.remove();
      privacyRemoved = true;
    }
  }
}
// A passage taken out of a sentence leaves the text either side to read on: the space before the punctuation that
// followed it goes, and an English sentence it opened starts with a capital ("classes. it will close", rc36).
function mendAfterRemoving(node) {
  const before = node.previousSibling, after = node.nextSibling;
  node.remove();
  if (after?.nodeType !== Node.TEXT_NODE) return;
  const opened = !before || (before.nodeType === Node.TEXT_NODE && /(^|[.!?]["”’')]?)\s*$/.test(before.nodeValue));
  if (opened) after.nodeValue = after.nodeValue.replace(/^(\s*)([a-z])/, (m, gap, letter) => gap + letter.toUpperCase());
  if (before?.nodeType === Node.TEXT_NODE && /^\s*[.,;:!?。，；：！？]/.test(after.nodeValue)) {
    before.nodeValue = before.nodeValue.trimEnd();
    after.nodeValue = after.nodeValue.trimStart();
  }
}
function liftCurtain(node) {
  node.classList.add("lifted");
  for (const name of ["role", "aria-label", "tabindex", "title"]) node.removeAttribute(name);
}

function redrawMountedGraph() {
  if (typeof graphDraw !== "function" || !document.querySelector(".gx-map")) return;
  if (graphState?.fg) {
    const paper = getComputedStyle(document.documentElement).getPropertyValue("--paper").trim();
    if (paper) graphState.fg.backgroundColor(paper);
    if (typeof graph3dPaint === "function") graph3dPaint();
  }
  graphDraw();
}
function setTheme(mode) {
  if (mode === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = mode;
  readerStorage("co-rem-theme", mode);
  renderRail(railActive());
  redrawMountedGraph();
}
const REM_SKINS = [["porcelain", "Porcelain"], ["klein", "Klein"], ["onion", "Onion"], ["classic", "Classic"]];
function setSkin(skin) {
  const valid = REM_SKINS.some(([k]) => k === skin) ? skin : "porcelain";
  if (valid === "porcelain") delete document.documentElement.dataset.skin;
  else document.documentElement.dataset.skin = valid;
  readerStorage("co-rem-skin", valid);
  renderSettings();
  redrawMountedGraph();
}
readerStorage("co-rem-skin").then(saved => {
  if (saved && REM_SKINS.some(([k]) => k === saved) && saved !== "porcelain") {
    document.documentElement.dataset.skin = saved;
    if (document.getElementById("foot")?.childElementCount) renderSettings();
  }
});
Object.assign(UI.zh, {
  "Skin": "皮肤", "Porcelain": "冷瓷青翠", "Klein": "克莱因蓝", "Onion": "洋葱书系", "Classic": "经典黑白",
  "Porcelain skin": "冷瓷青翠皮肤", "Klein skin": "克莱因蓝皮肤", "Onion skin": "洋葱书系皮肤", "Classic skin": "经典黑白皮肤",
  "Skin: {skin}": "切换皮肤：{skin}"
});

// ---------- helpers ----------
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function el(tag, attrs, children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else if (v === true) node.setAttribute(k, "");
    else node.setAttribute(k, v);
  }
  for (const child of children || []) if (child != null) node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  return node;
}
const CATEGORY_LABEL = {
  people: "People", orgs: "Organisations", devices: "Devices", projects: "Projects", skills: "Skills", knowledge: "Knowledge", keys: "Keys",
  opportunities: "Opportunities", decisions: "Decisions", principles: "Principles", works: "Works",
  agenda: "Agenda", sessions: "Agent sessions", notes: "AI notes", logs: "Maps"
};
// notes/ and logs/ are what co rem wrote about its own work: read under Activity, not counted as memory.
const ACTIVITY = new Set(["notes", "logs"]);
function memoryCategories() { return REM.categories.filter(c => !ACTIVITY.has(c)); }
// A skill's run report is opened from its skill page, never listed on its own.
function skillReport(r) { return r.path.startsWith("logs/skill-runs-"); }
function categoryHref(c) { return ACTIVITY.has(c) ? "#view=activity" : "#c=" + c; }
function categoryName(c) { return ACTIVITY.has(c) ? t("Activity") : label(c); }
function label(c) { return t(CATEGORY_LABEL[c] || c); }
function singular(c) { return t(({ people: "Person", orgs: "Organisation", devices: "Device", skills: "Skill", projects: "Project", decisions: "Decision", principles: "Principle" })[c] || CATEGORY_LABEL[c]?.replace(/s$/, "") || c); }
const BY_PATH = true;
function byPath(path) { const recs = REM?.records || [], c = byPath._c; if (!c || c[0] !== recs || c[1] !== recs.length) byPath._c = [recs, recs.length, new Map(recs.map(r => [r.path, r]))]; return byPath._c[2].get(path); }
// Services still on a people page (census.py) are left off like held pages (#2008).
function privateTopicHidden(r) { return r.private && ["knowledge", ...STATEMENT_CATEGORIES].includes(r.category) && document.documentElement.classList.contains("hide-private"); }
function listedRecords() { const recs = REM.records || [], hide = typeof document !== "undefined" && !!document.documentElement?.classList?.contains("hide-private"), c = listedRecords._c; if (c && c[0] === recs && c[1] === recs.length && c[2] === hide) return c[3]; const all = recs.filter(r => !privateTopicHidden(r) && !r.catalog_parent && !r.needs_review && !r.unnamed && !r.service && !ACTIVITY.has(r.category) && r.path !== "skills/catalog/index.md"), byCat = new Map(); for (const r of all) if (r.category !== "people" || r.path !== REM.owner) (byCat.get(r.category) || byCat.set(r.category, []).get(r.category)).push(r); listedRecords._c = [recs, recs.length, hide, all, byCat]; return all; }
function inCategory(category) { listedRecords(); return listedRecords._c[4].get(category) || []; }
// A list shows what the address's tag filter keeps (#3093): the list views read their rows through this.
function listRows(category) {
  const { tag, category: shown, record, query, src } = route();
  const all = inCategory(category);
  const rows = tag && shown === category && !record && !query && TAG_LISTS.includes(category) ? tagged(all, tag) : all;
  // 来源 (#3346): People by where the owner talks with them, mail or WeChat.
  return category === "people" && src && shown === category ? rows.filter(r => personSources(r).includes(src)) : rows;
}
// WeChat beside mail on People (#3346, #3347): when the owner last talked with someone on WeChat, and whether a page
// is an address-book friend with nothing to read yet. The night's map keeps both (onboard.activity / onboard.idle).
function chatActivity(r) { return (REM.chat_activity || {})[r.path] || null; }
function restingFriends() { return REM._resting || (REM._resting = new Set(REM.idle_people || [])); }
function wechatPage(r) { return !!chatActivity(r) || restingFriends().has(r.path); }
function personSources(r) {
  return [recordEmails(r).length || r.mail?.mails ? "mail" : "", wechatPage(r) ? "wechat" : ""].filter(Boolean);
}
const isoDay = value => (String(value || "").match(/\d{4}-\d{2}-\d{2}/) || [""])[0];
// A WeChat-only friend the owner has not talked with in 90 days: People keeps the table for recent contact.
function quietFriend(r) {
  const chat = chatActivity(r);
  if (!chat || personSources(r).includes("mail")) return false;
  const asOf = REM.as_of || "";
  if (REM._quiet?.asOf !== asOf) REM._quiet = { asOf, cutoff: calendarDay(new Date(Date.parse(asOf || new Date().toISOString()) - 90 * 864e5).toISOString()) };
  return calendarDay(chat.last) < REM._quiet.cutoff;
}
function peopleExclusions() {
  const people = REM.records.filter(r => r.category === "people");
  return { held: people.filter(r => r.needs_review).length,
    service: people.filter(r => r.service && !r.needs_review).length };
}
// The default notebook needs no --root; another shows `~/` for home, which only expands unquoted.
function href(r) { return r.path?.startsWith("tag:") ? tagHref(r.path.slice(4)) : "#r=" + encodeURIComponent(r.path); }
