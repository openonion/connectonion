// A decision, knowledge entry or principle is titled by what it says, so its title follows the reader's language
// wherever it is shown: list, head, search, graph (#3142, owner 2026-11-19: «decision 的标题为什么是英文的呢？»).
// People, organisations and projects are titled by names, which stay as written. Links go by path, never title.
const STATEMENT_CATEGORIES = ["decisions", "knowledge", "principles"];
function localiseTitles() {
  for (const r of REM.records || []) {
    if (!STATEMENT_CATEGORIES.includes(r.category)) continue;
    r.title_original ??= r.title;
    const translated = uiLanguage !== "en" ? (r.translations?.[uiLanguage] || "") : "";
    const head = /^# (.+)$/m.exec(translated);
    const title = head ? head[1].trim() : r.title_original;
    // A privacy label is never printed in a title (#3159): the page keeps it; the list hides the title in private
    // mode like any labelled passage.
    r.private = r.private || hasPrivacy(title);
    r.title = title.replace(/\s*[\[［](?:personal|sensitive)[\]］]/gi, "").trim();
  }
}
function render() {
  if (!REM) return;
  const cur = route();
  if (cur.view !== "open" || cur.item) document.querySelector(".bau-toast")?.remove();
  localiseTitles();
  listedRecords._c = null;
  renderLangProgress();
  threadEntries.cacheEnabled = true;
  const state = route();
  // An opened page with no Chinese version is asked for at once (live reader); its state is the top bar's (#3143).
  if (state.record && byPath(state.record)) translationQueued(byPath(state.record));
  if (!detailReady && needsDetails(state)) {
    renderRail(railActive());
    document.getElementById("main").replaceChildren(el("p", { role: "status", text: t("Loading…") }));
    loadDetails().then(render, error => {
      detailLoad = null;
      if (!needsDetails(route())) return;
      const retry = el("button", { type: "button", text: t("Try again") });
      retry.onclick = render;
      document.getElementById("main").replaceChildren(el("p", { role: "alert", text: error.message }), retry);
    });
    return;
  }
  cacheChineseInterface();
  for (const r of REM.records) swapLanguage(r, r.readLanguage ?? (uiLanguage === "en" ? "" : uiLanguage));
  // A session whose title came from a labelled turn is named in the reader's own words, in its current language.
  for (const r of REM.records) if (r.session_title_hidden) Object.defineProperty(r, "title", { get: () => t("This session's content is hidden"), configurable: true });
  memoryPass = lastPass();
  document.documentElement.lang = uiLanguage;
  document.getElementById("nav").setAttribute("aria-label", t("Categories"));
  document.getElementById("q").placeholder = t("Search");
  document.getElementById("q").setAttribute("aria-label", t("Search the notebook"));
  document.querySelector(".skip").textContent = t("Skip to content");
  document.querySelector(".search .kbd").setAttribute("aria-label", t("Command palette"));
  const { record: r, category: c, query, related, heading, view, reviews } = route();
  renderRail(railActive());
  renderCrumb(route());
  const box = document.getElementById("q");
  if (!(document.activeElement === box && box.value.trim() === (query || "")) && box.value !== (query || "")) box.value = query || "";
  const curHash = typeof location !== "undefined" ? location.hash : "";
  if (curHash !== "#today-calendar") window.scrollTo(0, 0);
  document.getElementById("main").classList.toggle("wide", !!(c && !r && !query && !reviews && ((COLUMNS[c] || c === "people" || c === "skills") && inCategory(c).length)));
  const reading = r && byPath(r);
  document.getElementById("main").classList.toggle("reading", !query && !reviews && !!reading && ["people", "orgs", "projects", "skills", "devices", "keys", "notes", "agenda", ...ENTRY_KINDS].includes(reading.category) && reading.path !== "skills/catalog/index.md");
  if (reviews) reviewPage();
  else if (query) search(query, related);
  else if (r) record(r, heading);
  else if (view === "open" || view === "changes") taskView(view);
  else if (view === "activity" || c === "logs" || c === "notes") activityView();
  else if (knowledgeShowsGraph({ category: c, view })) knowledgeGraph();
  else if (c === "agenda" || view === "agenda") { todayCal.expanded = true; overview(); document.getElementById("today-calendar")?.scrollIntoView({ block: "start" }); }
  else if (c) { category(c); tagBarInto(c); }
  else { overview(); if (curHash === "#today-calendar") document.getElementById("today-calendar")?.scrollIntoView({ block: "start" }); }
  quietLaterPrimaries(document.getElementById("main"));
  tidyText(document.getElementById("main"));
  document.title = (reviews ? t("Questions & connections") : r ? (privateTopicHidden(byPath(r) || {}) ? t("Hidden labelled passage") : byPath(r)?.title || t("Missing page")) : query ? t("Search: ") + query :
    view === "open" ? t("Open threads") : view === "changes" ? t("Memory changes") : view === "activity" ? t("Activity") : view === "graph" || c === "all" ? label("knowledge") : c ? label(c) : t("Today")) + " · co rem";
  for (const link of document.querySelectorAll("#nav a.active")) link.setAttribute("aria-current", "page");
  const viewKey = r || c || view || (reviews ? "reviews" : query ? "search" : "today");
  if (viewKey !== entranceView) document.querySelectorAll("#main .fresh-label, #main .updated-label, #main .changed-value").forEach(node => node.classList.add("memory-enter"));
  entranceView = viewKey;
  refreshFocusExpansion();
  restoreAfterReload();
}

// Where you are, in the top bar: the day on Today, the list a record belongs to, or the page's name.
function renderCrumb({ record: r, category: c, query, view, reviews }) {
  const page = r && byPath(r);
  const rCat = !page && r ? r.split("/")[0] : "";
  const name = query ? t("Search") : reviews ? t("Questions & connections") : view === "open" ? t("Waiting on you") : view === "changes" ? t("Memory changes")
    : view === "activity" || c === "logs" || c === "notes" ? t("Activity") : view === "agenda" ? label("agenda") : view === "graph" || c === "all" ? label("knowledge") : c ? label(c) : rCat && CATEGORY_LABEL[rCat] ? label(rCat) : todayCrumb();
  document.getElementById("crumb").replaceChildren(page ? el("a", { href: categoryHref(page.category), text: page.category === "notes" ? label("notes") : categoryName(page.category) }) : name);
}
function sourceFind(excerpt, quote) {
  const input = el("input", { type: "search", id: "evidence-find-input", "aria-label": t("Find in archived source") });
  const next = el("button", { type: "button", text: t("Next match"), disabled: "" });
  const status = el("span", { class: "evidence-find-status", role: "status" });
  const original = quote.innerHTML;
  let matches = [], current = 0, term = "";
  function show() {
    const at = matches[current];
    const mark = el("mark", { text: excerpt.slice(at, at + term.length) });
    quote.replaceChildren(document.createTextNode(excerpt.slice(0, at)), mark,
      document.createTextNode(excerpt.slice(at + term.length)));
    status.textContent = t("Match {n} of {m} in the archived excerpt", { n: current + 1, m: matches.length });
    scrollEvidenceSpan(quote.closest(".evidence-panel"), mark);
  }
  input.oninput = () => {
    term = input.value.trim();
    matches = [];
    quote.textContent = excerpt;
    next.disabled = true;
    if (!term) { quote.innerHTML = original; status.textContent = ""; return; }
    const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    matches = [...excerpt.matchAll(new RegExp(escaped, "gi"))].map(match => match.index);
    if (!matches.length) { status.textContent = t("No match in the archived excerpt"); return; }
    current = 0;
    next.disabled = matches.length < 2;
    show();
  };
  next.onclick = () => { current = (current + 1) % matches.length; show(); };
  input.onkeydown = event => { if (event.key === "Enter") { event.preventDefault(); if (!next.disabled) next.click(); } };
  return el("div", { class: "evidence-find" }, [
    el("label", { for: "evidence-find-input", text: t("Find a word or phrase in this source") }),
    el("div", { class: "evidence-find-controls" }, [input, next]), status]);
}

// A mail as a message (#2106): who wrote it, to whom, when, then the words.
function mailbox(text) {
  const m = /^\s*"?([^"<]*?)"?\s*<([^>]+)>\s*$/.exec(text || "");
  const address = (m ? m[2] : text || "").trim().toLowerCase();
  return { name: (m && m[1].trim()) || (!address.includes("@") ? (text || "").trim() : address.split("@")[0]), address };
}
let PEOPLE_BY_ADDRESS = null;
function personByAddress(address) {
  if (!PEOPLE_BY_ADDRESS) {
    PEOPLE_BY_ADDRESS = new Map();
    for (const r of REM.records.filter(r => r.category === "people"))
      for (const field of ["Email", "Handles"])
        for (const i of parseFacts(r).get(field) || [])
          for (const address of i.value.toLowerCase().match(/[\w.+-]+@[\w-]+\.[\w.-]+/g) || [])
            if (!PEOPLE_BY_ADDRESS.has(address) || r.path === REM.owner) PEOPLE_BY_ADDRESS.set(address, r);
  }
  return PEOPLE_BY_ADDRESS.get(address);
}
function avatar(name) {
  const words = name.replace(/[^\p{L}\p{N} ]/gu, " ").trim().split(/\s+/);
  const initials = (words.length > 1 ? words[0][0] + words.at(-1)[0] : (words[0] || "?").slice(0, 2)).toUpperCase();
  return el("span", { class: "msg-avatar", "aria-hidden": "true", text: initials });
}
function personChip(text) {
  const who = mailbox(text), page = personByAddress(who.address);
  const name = page && page.path === REM.owner ? t("you") : page ? page.title : who.name;
  return el(page ? "a" : "span", { class: "msg-person", title: who.address, ...(page ? { href: href(page) } : {}) },
    [avatar(name), el("span", { text: name })]);
}
function messageMeta(context) {
  const to = context.participants?.to || [];
  const people = (Array.isArray(to) ? to : [to]).filter(Boolean).map(text => sourceSender({ sender: text }));
  const sent = context.time ? fmtTime(context.time) : t("Sent date unknown");
  return [people.length ? t("to") + " " + people.join(", ") : "", sent, sourceChannel(context.source)].filter(Boolean).join(", ");
}
function mailMessage(context, quote) {
  const subject = context.subject || REM.conversations?.[context.thread]?.subject;
  const headers = context.participants || {};
  const list = value => (Array.isArray(value) ? value : value ? String(value).split(/,\s*(?=[^,]*@)/) : []).filter(Boolean);
  const from = list(headers.from)[0] || context.sender || "";
  const rows = [["To", list(headers.to)], ["Cc", list(headers.cc)]].filter(([, people]) => people.length);
  return el("article", { class: "msg" }, [
    el("div", { class: "msg-envelope" }, [el("header", { class: "msg-head" }, [el("span", { class: "msg-from" }, [personChip(from),
        el("span", { class: "msg-address", text: mailbox(from).address })]),
      el("time", { class: "msg-time", text: messageMeta(context), title: context.time ? t("Sent at {time}", { time: fmtTime(context.time) }) : t("Sent date unknown") })]),
    ...(subject ? [el("p", { class: "msg-subject evidence-subject", text: subject })] : [])]),
    ...(rows.length ? [el("div", { class: "msg-people evidence-participants" }, rows.map(([label, people]) =>
      el("div", { class: "msg-row" }, [el("span", { class: "msg-label", text: t(label) }), ...people.map(personChip)])))] : []),
    context.body_empty ? el("p", { class: "evidence-empty-body", text: t(context.header_only ? "REM kept who wrote this and when, not the message itself."
      : "The retained message has no body text. Its headers are available.") })
      : el("div", { class: "msg-body" }, [quote])]);
}
// Match original words only; offsets keep whitespace and punctuation intact.
function spanMatch(text, phrase, wholeWords = false) {
  const pattern = phrase.trim().split(/\s+/).map(word => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+");
  const bounded = wholeWords ? "(?<![\\p{L}\\p{N}])" + pattern + "(?![\\p{L}\\p{N}])" : pattern;
  const match = new RegExp(bounded, "iu").exec(text.slice(0, 60000));
  return match ? [match.index, match.index + match[0].length] : null;
}
function supportingSpan(claim, excerpt) {
  const quotes = [...claim.matchAll(/“([^”]{6,})”|"([^"\n]{6,})"/g)];
  for (const quote of quotes) {
    const phrase = quote[1] || quote[2];
    if (phrase.trim().replace(/\s+/g, " ").length < 6) continue;
    const source = spanMatch(excerpt, phrase);
    if (source) return { claim: [quote.index + 1, quote.index + 1 + phrase.length], source };
  }
  if (quotes.length) return null;
  const words = [...claim.matchAll(/[\p{L}\p{N}]+(?:['’][\p{L}\p{N}]+)*/gu)].slice(0, 80);
  for (let length = words.length; length >= 4; length--)
    for (let start = 0; start + length <= words.length; start++) {
      const begin = words[start].index, end = words[start + length - 1].index + words[start + length - 1][0].length;
      const source = spanMatch(excerpt, claim.slice(begin, end), true);
      if (source)
        return { claim: [begin, end], source };
    }
  return null;
}
function markedSpan(text, range) {
  return range ? esc(text.slice(0, range[0])) + '<mark class="span">' + esc(text.slice(...range)) + '</mark>' + esc(text.slice(range[1])) : esc(text);
}
function evidenceText(range) {
  return evidenceWords(range.cloneContents());
}
// The words a quote shows: no chips, labels or a copy button's hidden "Copied" (rc35 hunt: a profile-card row
// quoted as "mara@…Copiedworkmara@…Copiedpersonal"), and each value and its qualifier apart.
function evidenceWords(copy) {
  copy.querySelectorAll(".cite, .privacy-tag, .dir, .age, .when, .pc-done, .pc-cites").forEach(node => node.remove());
  copy.querySelectorAll(".pc-item + .pc-item").forEach(node => node.before(" · "));
  copy.querySelectorAll(".pc-after, .qual").forEach(node => node.before(" "));
  return copy.textContent.replace(/\u2060/g, "").replace(/[ \t]+/g, " ").trim();
}
function sentenceEnds(text) {
  const ends = [0];
  // Quotes and parentheticals are units, including a quote's closing full stop.
  for (const match of text.matchAll(/“[^”]*”|「[^」]*」|"[^"\n]*"|\([^)]*\)|（[^）]*）|[.!?;](?=\s)|[。！？；]/g)) {
    if (match[0].length !== 1) continue;
    if (match[0] === "." && /\b(?:[a-z]\.){2,}$|\b(?:Dr|Mr|Mrs|Ms|Prof|Sr|Jr|St|vs|etc)\.$/i.test(text.slice(0, match.index + 1))) continue;
    ends.push(match.index + 1);
  }
  return ends;
}
function evidenceSentence(trigger, line) {
  const content = line.querySelector(".focus-statement") || line;
  const range = document.createRange();
  range.selectNodeContents(content);
  if (content.contains(trigger)) {
    const chips = [...content.querySelectorAll("a.cite")];
    let first = chips.indexOf(trigger);
    if (first < 0) return "";
    // Every adjacent chip supports the words before the group's first chip.
    for (; first > 0; first--) {
      range.setStartAfter(chips[first - 1]);
      range.setEndBefore(chips[first]);
      if (range.toString().trim()) break;
    }
    range.selectNodeContents(content);
    range.setEndBefore(chips[first]);
    if (first > 0) range.setStartAfter(chips[first - 1]);
  }
  const before = evidenceText(range), start = sentenceEnds(before).at(-1);
  const sentence = before.slice(start).trim();
  if (sentence.length >= 20) return sentence;
  // A short prefix may have its remaining words after the chip.
  range.setEnd(content, content.childNodes.length);
  const text = evidenceText(range), end = sentenceEnds(text).find(at => at >= before.length && at > start);
  return text.slice(start, end).trim();
}
function evidenceLine(trigger) {
  const line = trigger.closest("li, p, dd, blockquote") || trigger.closest(".focus-head") || trigger.parentElement;
  const copy = (line.querySelector(".focus-statement") || line).cloneNode(true);
  const path = new URLSearchParams((trigger?.hash || location.hash || "").slice(1)).get("r");
  const chips = [...line.querySelectorAll("a.cite")].filter(chip => new URLSearchParams(chip.hash.slice(1)).get("r") === path);
  const numbers = chips.flatMap(chip => (chip.dataset.sources || new URLSearchParams(chip.hash.slice(1)).get("h")?.replace("src-", "") || "").split(" "));
  const sentence = evidenceSentence(trigger, line);
  return { text: sentence || evidenceWords(copy), numbers: [...new Set(numbers.filter(Boolean))] };
}
function scrollEvidenceSpan(panel, mark = panel.querySelector(".evidence-original mark.span")) {
  evidenceLayout();
  if (!mark || !mark.getClientRects().length) return;
  const bounds = mark.getBoundingClientRect(), claim = panel.querySelector(".evidence-claim");
  const origin = panel.getBoundingClientRect().top + panel.clientTop - panel.scrollTop;
  const markTop = bounds.top - origin, claimTop = claim.getBoundingClientRect().top - origin;
  const headerHeight = panel.querySelector(".evidence-top").offsetHeight
    + (panel.querySelector(".evidence-find")?.offsetHeight || 0)
    + (panel.querySelector(".msg-envelope")?.offsetHeight || 0);
  // Keep the claim below the header unless the source would stay off-screen.
  const preferred = Math.min(markTop - claimTop - claim.offsetHeight - 16, claimTop - headerHeight - 16);
  const reveal = Math.min(markTop - headerHeight - 16, bounds.bottom - origin - panel.clientHeight + 16);
  panel.scrollTo({ top: Math.max(0, preferred, reveal),
    behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
}
let evidenceTrigger = null;
function evidenceLayout() {
  const panel = document.getElementById("evidence-panel"), narrow = innerWidth < 1100;
  document.querySelector(".app").inert = !!panel && !panel.parentElement.hidden && narrow;
  panel?.setAttribute("aria-modal", String(narrow));
  panel?.style.setProperty("--evidence-top-height", panel.querySelector(".evidence-top").offsetHeight + "px");
  panel?.style.setProperty("--evidence-find-height", (panel.querySelector(".evidence-find")?.offsetHeight || 0) + "px");
}
function closeEvidence() {
  const layer = document.getElementById("evidence-layer");
  if (!layer || layer.hidden) return;
  layer.hidden = true;
  document.querySelectorAll(".tl-e.on").forEach(row => row.classList.remove("on"));
  document.body.classList.remove("evidence-open");
  evidenceLayout();
  evidenceTrigger?.focus({ preventScroll: true });
}
function evidencePanel() {
  let panel = document.getElementById("evidence-panel");
  if (panel) return panel;
  const backdrop = el("div", { class: "evidence-backdrop", "aria-hidden": "true" });
  backdrop.onclick = closeEvidence;
  panel = el("aside", { id: "evidence-panel", class: "evidence-panel", role: "dialog", "aria-label": t("Source context"), tabindex: "-1" });
  document.body.appendChild(el("div", { id: "evidence-layer", class: "evidence-layer", hidden: "" }, [backdrop, panel]));
  return panel;
}
function attachmentPreview(context) {
  const url = context.url || context.file || "", name = context.filename || t("the file");
  if (!/^https?:$/.test(location.protocol) || !url.startsWith("/rem/attachment?")) return null;
  if (context.preview_kind === "pdf" || /\.pdf$/i.test(name)) {
    return el("iframe", { class: "evidence-pdf-frame", src: url, title: name });
  }
  if (context.preview_kind === "image" || /\.(png|jpe?g|gif|webp)$/i.test(name)) {
    return el("img", { class: "evidence-image-preview", src: url, alt: name });
  }
  return null;
}
function evidenceOriginal(context, quote) {
  const mail = /^(gmail|outlook)$/.test(context.source), attachment = context.source === "attachment";
  const structured = attachment && (/\.(xlsx|csv|docx|pptx)$/i.test(context.filename || "")
    || /Sheet:| \| /.test(context.excerpt || ""));
  const original = structured ? el("pre", { class: "evidence-structured", html: quote.innerHTML }) : quote;
  const revision = /:([0-9a-f]{40,64}):(.+)$/.exec(context.origin || "");
  const origin = revision ? revision[2] + " @ " + revision[1].slice(0, 8) : context.origin?.split("/").at(-1) || "";
  return el("div", { class: "evidence-original private" }, [
    ...(!mail ? [el("p", { class: "evidence-meta", text: /^skill-(source|reference)$/.test(context.source) ? t("Instruction excerpt") : [sourceChannel(context.source), sourceSender(context), context.time && fmtTime(context.time)].filter(Boolean).join(" · ") })] : []),
    ...(context.excerpt?.length > 2000 ? [sourceFind(original.textContent, original)] : []),
    ...(attachment ? [attachmentPreview(context)] : []),
    ...(mail ? [mailMessage(context, quote)] : attachment && !context.excerpt ? [] : [original]),
    ...(origin ? [el("p", { class: "evidence-meta", text: origin })] : []),
    ...(revision ? [el("details", { class: "evidence-source-id" }, [el("summary", { text: t("Full source ID") }), el("code", { text: context.origin })])] : []),
    el("p", { class: "evidence-meta", text: [context.captured_at ? t(mail ? "Retrieved" : "Captured") + " " + fmtTime(context.captured_at) : "",
      context.retained_at && !context.captured_at ? t("Archived") + " " + fmtTime(context.retained_at) : "", context.body_format].filter(Boolean).join(" · ") }),
    ...(context.url || context.file ? [el("a", { class: "evidence-open-file", href: context.url || context.file, target: "_blank", rel: "noopener", text: `${t("Open")} ${context.filename || t("the file")} →` })] : []),
    ...(context.mapped_session_folder ? [el("p", { class: "evidence-meta", text: t("Mapped project session folder") + ": " + context.mapped_session_folder + " · " + t("Source routing only; does not verify completion") })] : []),
    ...(context.input_scope ? [el("p", { class: "evidence-input-scope", text: inputScopeText(context.input_scope) })] : []),
    ...(context.truncated ? [el("p", { class: "evidence-meta", text: t("This archived excerpt is truncated; find searches only the text shown.") })] : [])]);
}
function sourceIdentity(context) {
  const from = context.participants?.from;
  const sender = (Array.isArray(from) ? from[0] : from) || context.sender || "";
  return byPath(sender)?.title || sourceSender(context);
}
function openEvidence(r, number, trigger, { fromList = false } = {}) {
  const source = sourceList(r).find(item => item.n.toLowerCase() === number.toLowerCase()) || { n: number.toUpperCase(), text: "" };
  // From the Sources list there is no line of the page to quote: the card is the source alone (#3134).
  const context = (REM.source_context || {})[sourceId(source.text, source.plain)], line = fromList ? { text: "", numbers: [] } : evidenceLine(trigger);
  const numbers = line.numbers.length ? line.numbers : [source.n];
  const excerpt = context?.excerpt || "", span = supportingSpan(line.text, excerpt);
  const panel = evidencePanel(), close = el("button", { type: "button", class: "evidence-close", text: t("Close ×"), "aria-label": t("Close source context") });
  close.onclick = closeEvidence;
  panel.replaceChildren(el("div", { class: "evidence-handle", "aria-hidden": "true" }),
    el("div", { class: "evidence-top" }, [el("span", { text: fromList ? t("Source {n}", { n: source.n }) : t("Source {n} of {m} for this line", { n: numbers.indexOf(source.n) + 1, m: numbers.length }) }), close]),
    ...(fromList || !line.text.trim() ? [] : [el("div", { class: "evidence-claim" }, [el("small", { text: t("On this page") }), el("div", { html: markedSpan(line.text, span?.claim) })])]));
  if (numbers.length > 1) {
    const select = el("select", { class: "evidence-source-select", "aria-label": t("Source for this line") }, numbers.map(n => el("option", { value: n, text: chipLabel(r, n) })));
    select.value = source.n;
    select.onchange = () => openEvidence(r, select.value, trigger);
    panel.insertBefore(select, panel.querySelector(".evidence-claim"));
  }
  const sourceKey = sourceId(source.text, source.plain), web = isWebSource(sourceKey) ? webSource(sourceKey, context) : null;
  // A web source says which page, on which site, read when (rc35 hunt: its card said nothing at all).
  const webDay = web && (context?.captured_at || /\b\d{4}-\d{2}-\d{2}\b/.exec(source.text.slice(sourceKey.length))?.[0] || "");
  panel.appendChild(el("div", { class: "evidence-identity" }, web ? [
    el("p", { class: "evidence-meta", text: [t("Web"), web.site, webDay && fmtDate(webDay)].filter(Boolean).join(" · ") }),
    el("p", { class: "evidence-subject", text: web.title })] : [
    el("p", { class: "evidence-meta", text: context
      ? [sourceIdentity(context), sourceChannel(context.source), context.time && fmtTime(context.time)].filter(Boolean).join(" · ")
      : chipLabel(r, source.n) }),
    context && !/^(gmail|outlook)$/.test(context.source) ? el("p", { class: "evidence-subject", text: context.subject || REM.conversations?.[context.thread]?.subject || "" }) : null]));
  // From a line to its row in the page's source list, and back with the row's "Cited N×" (#3104).
  const band = trigger?.closest?.(".deep-sources") ? null : document.getElementById?.("sources")?.closest?.(".deep-sources");
  if (band?.reveal && r.path === CITES.from && numbers.some(n => document.getElementById("src-" + String(n).toLowerCase()))) {
    const show = el("button", { type: "button", class: "btn-action evidence-in-sources", text: t("Show in sources") });
    show.onclick = () => { closeEvidence(); band.closest("details")?.setAttribute("open", ""); band.reveal(numbers); };
    panel.appendChild(show);
  }
  const sessionSource = sourceId(source.text, source.plain);
  const session = (REM.records || []).find(record => record.category === "sessions" && record.session_messages?.some(message => message.source === sessionSource));
  if (session && session.path !== r.path) {
    const message = session.session_messages.find(message => message.source === sessionSource);
    const link = el("a", { class: "evidence-session-link", href: href(session) + "&h=" + message.id, text: t("Open session transcript →") });
    link.onclick = closeEvidence;
    panel.appendChild(link);
  }
  if (context) {
    const reveal = el("button", { class: "btn-action", type: "button", text: t("Show labelled passages") });
    reveal.onclick = () => { revealLabelled(); close.focus({ preventScroll: true }); scrollEvidenceSpan(panel); };
    panel.appendChild(el("div", { class: "private-hidden-notice" }, [
      el("p", { text: t("Original excerpts are hidden until you show labelled passages.") }), reveal]));
    // `co fetch`'s own URL:/Title: lines repeat what the card's head already says.
    const shown = web ? excerpt.replace(/^(?:(?:URL|Title|Status):[^\n]*\n)+\s*/, "") : excerpt;
    const text = shown + (context.truncated ? "…" : ""), quote = el("blockquote", { html: markedSpan(text, span?.source) });
    panel.appendChild(evidenceOriginal(web ? { ...context, source: "", captured_at: "" } : context, quote));
    if (web) panel.appendChild(webLink(sourceKey));
  } else if (source.text && !sourceId(source.text, source.plain)) {
    panel.appendChild(el("p", { class: "evidence-description", text: source.text }));
  } else panel.append(...missingOriginal(r, number, trigger, { fromList }, sourceId(source.text, source.plain)));
  // The card's own words (who, when, what the source is) in the reader's form; the quoted original stays as written.
  panel.querySelectorAll(".evidence-identity, .evidence-description").forEach(tidyText);
  evidenceTrigger = trigger;
  panel.parentElement.hidden = false;
  document.body.classList.add("evidence-open");
  evidenceLayout();
  panel.scrollTop = 0;
  close.focus({ preventScroll: true });
  scrollEvidenceSpan(panel);
  return true;
}
// A card never opens empty (#3165: 29/40, 32/40 and 40/40 source titles on three real project pages did). The
// snapshot's excerpts share one budget across the notebook, mail first, so the live reader asks its Host for the one
// source it is opening, once, and redraws the card when it comes. Without a Host, or when REM kept nothing, the card
// says so in words and still offers what it can: the web page for a link.
const SOURCE_ASKED = new Set();
function missingOriginal(r, number, trigger, options, id) {
  const parts = [];
  if (id && liveHere() && !SOURCE_ASKED.has(id)) {
    SOURCE_ASKED.add(id);
    fetch("/rem/source?id=" + encodeURIComponent(id)).then(reply => reply.ok ? reply.json() : null).catch(() => null).then(context => {
      const open = document.getElementById("evidence-layer")?.hidden === false && evidenceTrigger === trigger;
      if (context) (REM.source_context = REM.source_context || {})[id] = context;
      if (open) openEvidence(r, number, trigger, options);
    });
    return [el("p", { class: "evidence-unavailable", role: "status", text: t("Getting the original…") })];
  }
  const web = /^https?:\/\//.test(id || "");
  parts.push(el("p", { class: "evidence-unavailable", text: t(web ? "REM kept this link, not a copy of the page." : liveHere()
    ? "REM did not keep a copy of this source." : "The original isn't in this snapshot.") }));
  if (web) parts.push(webLink(id));
  return parts;
}
function webLink(id) {
  return el("a", { class: "btn-action evidence-web", href: id, target: "_blank", rel: "noopener noreferrer", text: t("Open the web page") + " ↗" });
}
function evidenceControls(panel) {
  return [...panel.querySelectorAll('a[href], button, input, select, textarea, summary, [tabindex]')].filter(node =>
    !node.matches(":disabled, [aria-disabled='true']") && node.tabIndex >= 0 &&
    !node.closest("[hidden], [inert], [aria-hidden='true']") && node.getClientRects().length && getComputedStyle(node).visibility === "visible");
}
document.addEventListener("keydown", event => {
  const panel = document.getElementById("evidence-panel");
  if (!panel || panel.parentElement.hidden) return;
  if (event.key === "Escape") { event.preventDefault(); closeEvidence(); }
  if (event.key !== "Tab" || innerWidth >= 1100) return;
  const controls = evidenceControls(panel);
  if (!controls.length) { event.preventDefault(); panel.focus(); return; }
  const first = controls[0], last = controls.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});
window.addEventListener("hashchange", closeEvidence);
window.addEventListener("hashchange", () => {
  document.getElementById("conversation-dialog")?.close();
});
window.addEventListener("resize", evidenceLayout);
// The organisation page's time line follows the window.
window.addEventListener("resize", () => fitNames());
// Soft hyphens are layout: a copied name is the name.
document.addEventListener("copy", event => {
  const text = String(getSelection());
  if (!text.includes("\u00ad") || !event.clipboardData) return;
  event.clipboardData.setData("text/plain", text.replace(/\u00ad/g, ""));
  event.preventDefault();
});
// The projects directory's month labels are re-measured against Today after a resize.
for (const kind of ["pointerover", "focusin"]) document.addEventListener(kind, paTipShow);
for (const kind of ["pointerout", "focusout", "scroll"]) document.addEventListener(kind, paTipHide, true);
// Fixed positioning and measured bounds keep even an unbroken source id on a phone.
function hideCitationTip() { document.getElementById("citation-tip")?.remove(); }
function showCitationTip(event) {
  const cite = event.target.closest("a.cite");
  if (!cite || !cite.title) return;
  hideCitationTip();
  const tip = el("div", { id: "citation-tip", class: "citation-tip", role: "tooltip", text: cite.title });
  document.body.appendChild(tip);
  const bounds = cite.getBoundingClientRect();
  tip.style.left = Math.max(12, Math.min(bounds.left, innerWidth - tip.offsetWidth - 12)) + "px";
  tip.style.top = Math.max(12, Math.min(bounds.bottom + 8, innerHeight - tip.offsetHeight - 12)) + "px";
}
document.addEventListener("pointerover", showCitationTip);
document.addEventListener("focusin", showCitationTip);
document.addEventListener("pointerout", hideCitationTip);
document.addEventListener("focusout", hideCitationTip);
document.addEventListener("click", hideCitationTip);
window.addEventListener("resize", hideCitationTip);
window.addEventListener("scroll", hideCitationTip, true);
window.addEventListener("hashchange", hideCitationTip);
// A citation chip opens its source beside the page and never navigates. Its link names the page whose Sources list
// defines the number, which may not be the page on screen (a relation card, a quoted line). Navigating was the
// fallback whenever that page was not in the snapshot or the card could not open, and the owner landed on someone
// else's page while reading a project (#3165, deep hunt 2026-11-19). Navigation is stopped first; a page that is
// not here says so in the card.
document.addEventListener("click", e => {
  const citation = e.target.closest("a.cite");
  if (!citation) return;
  e.preventDefault();
  const url = new URL(citation.href);
  const params = new URLSearchParams(url.hash.slice(1));
  const path = params.get("r"), number = (params.get("h") || "").replace(/^src-/, "");
  const r = byPath(path);
  if (r) openEvidence(r, number, citation);
  else openMissingSource(number, citation);
});
// The source card for a chip whose page is not in this snapshot (a private or unlisted page): it says so, no jump.
function openMissingSource(number, trigger) {
  const panel = evidencePanel(), close = el("button", { type: "button", class: "evidence-close", text: t("Close ×"), "aria-label": t("Close source context") });
  close.onclick = closeEvidence;
  panel.replaceChildren(el("div", { class: "evidence-handle", "aria-hidden": "true" }),
    el("div", { class: "evidence-top" }, [el("span", { text: t("Source {n}", { n: number.toUpperCase() }) }), close]),
    el("p", { class: "evidence-unavailable", text: t("The page this source belongs to isn't in this snapshot.") }));
  evidenceTrigger = trigger;
  panel.parentElement.hidden = false;
  document.body.classList.add("evidence-open");
  evidenceLayout();
  close.focus({ preventScroll: true });
  return true;
}

const qInput = document.getElementById("q");
const qClear = document.getElementById("q-clear");
let qTimer = null, preSearchHash = "";
qInput.addEventListener("focus", () => {
  const cur = location.hash;
  if (!/^#?q=/.test(cur)) preSearchHash = cur;
});
qInput.addEventListener("input", e => {
  if (e.isComposing) return;
  clearTimeout(qTimer);
  qTimer = setTimeout(() => {
    const q = e.target.value.trim();
    const next = q ? "#q=" + encodeURIComponent(q) : (preSearchHash || "#");
    if (location.hash !== next) {
      history.replaceState(null, "", next);
      render();
    }
  }, 90);
});
qInput.addEventListener("keydown", e => {
  if (e.key === "Enter") {
    clearTimeout(qTimer);
    const q = qInput.value.trim();
    if (q) { history.replaceState(null, "", "#q=" + encodeURIComponent(q)); render(); }
    if (innerWidth <= 640) { qInput.blur(); document.body.classList.remove("searching"); }
  }
});
qClear.addEventListener("click", () => { clearTimeout(qTimer); qInput.value = ""; history.replaceState(null, "", preSearchHash || "#"); render(); qInput.focus(); });

const rail = document.querySelector(".rail");
// The rail refits when the window changes height, and when it crosses to or from the phone's sheet (#3091).
window.addEventListener("resize", fitRail);
const toggle = document.querySelector(".nav-toggle");
function closeNav() { rail.dataset.open = "false"; toggle.setAttribute("aria-expanded", "false"); }
toggle.addEventListener("click", () => {
  const open = toggle.getAttribute("aria-expanded") !== "true";
  // The sheet starts under the header row, wherever the page has scrolled it.
  document.getElementById("rail-menu").style.setProperty("--sheet-top", Math.max(0, rail.getBoundingClientRect().bottom) + "px");
  rail.dataset.open = String(open); toggle.setAttribute("aria-expanded", String(open));
  if (open) document.querySelector("#nav a")?.focus();  // the sheet opens above the tab bar: focus moves into it
});
document.querySelector(".skip").addEventListener("click", e => { e.preventDefault(); document.getElementById("main").focus(); });
document.getElementById("nav").addEventListener("click", e => {
  if (e.target.closest("a")) { closeNav(); document.getElementById("main").focus(); }
});
// 更多 closes when you click anywhere else; on a phone the search bar folds away once it is empty and left.
document.addEventListener("click", e => {
  const menu = document.getElementById("rail-more");
  if (menu && !menu.hidden && !e.target.closest("#rail-more")) { menu.hidden = true; document.querySelector(".nav.more")?.setAttribute("aria-expanded", "false"); }
});
qInput.addEventListener("blur", () => { setTimeout(() => { if (document.activeElement !== qInput && document.activeElement !== qClear) document.body.classList.remove("searching"); }, 120); });
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    if (document.activeElement === qInput) {
      if (qInput.value) { clearTimeout(qTimer); qInput.value = ""; history.replaceState(null, "", preSearchHash || "#"); render(); } else qInput.blur();
      return;
    }
    closeNav();
    if (document.activeElement.closest("#rail-menu")) toggle.focus();
  }
  if (e.key === "/" && !e.ctrlKey && !e.metaKey && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
    e.preventDefault(); qInput.focus();
  }
});
// ---- Command palette (⌘K / Ctrl+K) and Today's keys ---------------------------
// Search people, organisations, projects and pages, or run Today's actions.
function subsequenceScore(word, text) {
  let score = 0, at = -1, run = 0;
  for (const ch of word) {
    const found = text.indexOf(ch, at + 1);
    if (found < 0) return -1;
    run = found === at + 1 ? run + 1 : 0;
    score += 1 + run * 2 + (found === 0 || /[\s\-_/·(]/.test(text[found - 1]) ? 3 : 0);
    at = found;
  }
  return score;
}
// Every word must appear in order inside the text; the words themselves may come in any order.
function fuzzyScore(query, text) {
  const plain = value => value.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
  const words = plain(query).split(/\s+/).filter(Boolean), lower = plain(text);
  if (!words.length) return 0;
  let total = 0;
  for (const word of words) {
    const score = subsequenceScore(word, lower);
    if (score < 0) return -1;
    total += score + (lower.includes(word) ? word.length * 3 : 0);
  }
  return total - lower.length / 100;
}
let paletteRecent = [];
readerStorage("co-rem-palette-recent").then(saved => { paletteRecent = saved ? JSON.parse(saved) : []; });
function rememberPick(id) {
  paletteRecent = [id, ...paletteRecent.filter(item => item !== id)].slice(0, 6);
  readerStorage("co-rem-palette-recent", JSON.stringify(paletteRecent));
}
// A snapshot keeps no mark (markThread), so the palette does not offer one there: a command that does nothing
// would read as a mark that failed (#3018).
function todayActions() {
  return todayGroups(threadEntries().filter(entry => !isDone(entry))).flatMap(({ r }) => {
    const name = threadWho(r);
    return [{ id: "reply:" + r.path, label: t("Draft a reply to {name}", { name }), hint: t("Today"), run: () => onTodayCard(r.path, card => card.reply()) },
      liveHere() ? { id: "done:" + r.path, label: t("Mark {name} done", { name }), hint: t("Today"), run: () => onTodayCard(r.path, card => card.markDone()) } : null].filter(Boolean);
  });
}
function paletteItems() {
  const go = link => () => { location.hash = link; };
  const pages = [["Today", "#"], ["Waiting on you", "#view=open"], ["Memory changes", "#view=changes"]]
    .map(([title, link]) => [t(title), link]).concat(memoryCategories().map(c => [label(c), "#c=" + c]), [[graphT("Knowledge graph"), "#view=graph"]])
    .map(([title, link]) => ({ id: "page:" + link, label: t("Open {page}", { page: title }), hint: t("Page"), run: go(link) }));
  const skins = REM_SKINS.map(([key, name]) => ({ id: "skin:" + key, label: t("Skin: {skin}", { skin: t(name) }), hint: t("Skin"), run: () => setSkin(key) }));
  const themes = [["light", "Light"], ["dark", "Dark"], ["auto", "Auto"]].map(([m, n]) => ({ id: "theme:" + m, label: t("Theme") + ": " + t(n), hint: t("Theme"), run: () => setTheme(m) }));
  const privs = PRIVACY_LEVELS.map(lv => ({ id: "privacy:" + lv, label: t("Privacy") + ": " + t(PRIVACY_WORDS[lv][0]), hint: t("Privacy"), run: () => setPrivacy(lv) }));
  const records = listedRecords().filter(r => ["people", "orgs", "devices", "projects", "knowledge", "keys", "skills", "decisions", "principles", "sessions"].includes(r.category))
    .map(r => ({ id: "r:" + r.path, label: r.title, hint: singular(r.category), run: go(href(r)) }));
  return [...todayActions(), ...pages, ...skins, ...themes, ...privs, ...records];
}
function paletteResults(query, items) {
  if (!query.trim()) {
    const byId = new Map(items.map(item => [item.id, item]));
    const recent = paletteRecent.map(id => byId.get(id)).filter(Boolean).map(item => ({ ...item, recent: true }));
    return [...recent, ...items.filter(item => !paletteRecent.includes(item.id) && !item.id.startsWith("r:"))].slice(0, 12);
  }
  return items.map(item => ({ item, score: fuzzyScore(query, item.label) + (paletteRecent.includes(item.id) ? 2 : 0) }))
    .filter(row => row.score >= 0).sort((a, b) => b.score - a.score).slice(0, 12).map(row => row.item);
}
function onTodayCard(path, act) {
  const run = () => {
    dealCard(path);
    const card = document.querySelector("#main .qcard.focal");
    if (card?.dataset.path === path) act(card);
  };
  if (railActive() === "today") return run();
  window.addEventListener("hashchange", run, { once: true });
  location.hash = "";
}
// A closed dialog leaves the page in its "close" event, which the browser fires a task later. Until then its node is
// still here: only an open one may stop a second ⌘K, or ⌘K right after a pick or Esc did nothing at all.
function dropClosed(id) {
  const old = document.getElementById(id);
  if (old?.open) return false;
  old?.remove();
  return true;
}
function openPalette() {
  if (!dropClosed("palette")) return;
  const items = paletteItems();
  const input = el("input", { type: "text", role: "combobox", "aria-expanded": "true", "aria-controls": "palette-list", autocomplete: "off", spellcheck: "false",
    "aria-label": t("Search or run a command"), placeholder: t("Search people, projects, pages — or type an action") });
  const list = el("ul", { id: "palette-list", role: "listbox" });
  const dialog = el("dialog", { id: "palette", class: "palette", "aria-label": t("Command palette") }, [input, list,
    el("p", { class: "palette-foot", text: t("↑↓ move · Enter open · Esc close") })]);
  let shown = [], active = 0;
  const mark = () => {
    [...list.children].forEach((node, i) => node.setAttribute("aria-selected", String(i === active)));
    list.children[active]?.scrollIntoView({ block: "nearest" });
    input.setAttribute("aria-activedescendant", shown.length ? "palette-" + active : "");
  };
  const pick = item => { rememberPick(item.id); dialog.close(); item.run(); };
  const draw = () => {
    shown = paletteResults(input.value, items);
    list.replaceChildren(...shown.map((item, i) => {
      const option = el("li", { role: "option", id: "palette-" + i }, [el("span", { class: "pl", text: item.label }), el("span", { class: "ph", text: item.recent ? t("Recent") : i && !shown[i - 1].recent && shown[i - 1].hint === item.hint ? "" : item.hint })]);
      option.onclick = () => pick(item);
      option.onmousemove = () => { if (active !== i) { active = i; mark(); } };
      return option;
    }));
    if (!shown.length) list.appendChild(el("li", { class: "palette-empty", text: t("Nothing matches") }));
    mark();
  };
  input.oninput = () => { active = 0; draw(); };
  dialog.addEventListener("keydown", event => {
    if ((event.key === "ArrowDown" || event.key === "ArrowUp") && shown.length) {
      event.preventDefault();
      active = (active + (event.key === "ArrowDown" ? 1 : shown.length - 1)) % shown.length;
      mark();
    }
    if (event.key === "Enter" && shown[active]) { event.preventDefault(); pick(shown[active]); }
  });
  dialog.addEventListener("click", event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });
  // Closing a dialog returns the focus by itself, before the picked command runs; the command may then move it.
  dialog.addEventListener("close", () => dialog.remove());
  document.body.appendChild(dialog);
  dialog.showModal();
  draw();
  input.focus();
}
const SHORTCUTS = [["J / K", "Next or previous card"], ["S", "Skip to the next card"], ["E", "Mark done (the card in focus)"], ["R", "Reply"], ["⌘K", "Search or run a command"], ["/", "Search"], ["?", "These shortcuts"], ["Esc", "Close"]];
function openShortcuts() {
  if (!dropClosed("shortcuts")) return;
  const close = el("button", { type: "button", class: "btn-quiet", text: t("Close") });
  const dialog = el("dialog", { id: "shortcuts", class: "palette shortcuts", "aria-labelledby": "shortcuts-title" }, [
    el("h2", { id: "shortcuts-title", text: t("Keyboard shortcuts") }),
    el("dl", {}, SHORTCUTS.flatMap(([keys, what]) => [el("dt", {}, [el("kbd", { text: keys })]), el("dd", { text: t(what) })])), close]);
  close.onclick = () => dialog.close();
  dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener("close", () => dialog.remove());
  document.body.appendChild(dialog);
  dialog.showModal();
}
function typingIn(target) {
  return !!target?.closest?.("input, textarea, select, [contenteditable='true'], [contenteditable='']");
}
// J/K deal the next or previous card, S skips to the next, R replies. E closes the raised card when the focus is
// in it or in the notice the last E left, so E, E, E works through the deck; from anywhere else it does nothing,
// and nothing again while the card it closed is still leaving. Only on Today, never while typing.
function todayKey(key) {
  const card = document.querySelector("#main .qcard.focal");
  if (!card) return false;
  if (key === "j" || key === "s") dealNext(1);
  else if (key === "k") dealNext(-1);
  else if (key === "r") card.reply();
  else if (!card.classList.contains("leaving") && document.activeElement?.closest("#main .qcard.focal, #done-notice")) card.markDone();
  else return false;
  return true;
}
document.addEventListener("keydown", event => {
  if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === "k") { event.preventDefault(); openPalette(); return; }
  if (event.metaKey || event.ctrlKey || event.altKey || event.defaultPrevented || typingIn(event.target) || document.querySelector("dialog[open]")) return;
  if (event.key === "?") { event.preventDefault(); openShortcuts(); return; }
  const key = event.key.toLowerCase();
  if (key === "e" && event.repeat) return;  // a held E is one press: Undo brings back one card, not a deck
  if (railActive() === "today" && ["j", "k", "e", "r", "s"].includes(key) && todayKey(key)) event.preventDefault();
});
if (!/Mac|iPhone|iPad/.test(navigator.platform || "")) SHORTCUTS[4][0] = "Ctrl K";
document.querySelector(".search .kbd").textContent = SHORTCUTS[4][0];
document.querySelector(".search .kbd").onclick = openPalette;
// The language button is named from the first paint: the first render waits for the saved choices, and the
// button must not sit empty until then. It is called here, with the header's other load-time wiring.
renderLangToggle();
// ---- Languages ---------------------------------------------------------------
// A page read in another language. Translations are made by co ai on the Host
// (rem/translate.py) and cached beside the notebook; the page as written stays
// the record. A snapshot offers only the translations it carries; the live
// reader (served by rem_http.py) can ask the Host for any language.
// The menu offers the owner's own languages first (languages.py: detected from
// their mail and sessions, or `co rem config set languages`), then on a person
// the languages they speak, then the rest under "Other…". The page's own
// language is not offered: "As written" is that.
const READ_LANGUAGES = ["en", "zh", "zh-TW", "ja", "ko", "es", "fr", "de"];
function nativeName(tag) { return new Intl.DisplayNames([tag], { type: "language" }).of(tag) || tag; }
function languageBar(r) {
  const cached = Object.keys(r.translations || {});
  const offered = tag => tag !== r.written_in && (REM.live || cached.includes(tag));
  const yours = [...new Set(REM.your_languages || [])].filter(offered);
  const theirs = [...new Set(r.speaks || [])].filter(tag => offered(tag) && !yours.includes(tag));
  const rest = [...new Set([...READ_LANGUAGES, ...cached])].filter(tag => offered(tag) && !yours.includes(tag) && !theirs.includes(tag));
  if (!yours.length && !theirs.length && !rest.length) return null;
  const option = (tag, prefix) => el("option", { value: tag, text: t(prefix || "") + nativeName(tag) + (cached.includes(tag) ? "" : " · " + t("Translate with co ai")) });
  const select = el("select", { "aria-label": t("Read this page in") }, [el("option", { value: "", text: t("As written") }),
    ...yours.map(tag => option(tag)), ...theirs.map(tag => option(tag, "Their language: ")),
    rest.length ? el("optgroup", { label: t("Other…") }, rest.map(tag => option(tag))) : null]);
  select.value = r.shown || "";
  const status = el("span", { class: "lang-status", role: "status" });
  select.onchange = () => readIn(r, select.value, status, select);
  return el("div", { class: "lang-bar" }, [el("span", { text: t("Read in") }), select, status]);
}
async function readIn(r, tag, status, select) {
  if (!tag || r.translations?.[tag]) return showLanguage(r, tag);
  select.disabled = true;
  status.textContent = t("Translating with co ai… this takes a minute or two.");
  let answer = await askHost({ page: r.path, language: tag });
  while (answer.state === "running") {
    await new Promise(done => setTimeout(done, 2000));
    answer = await askHost({ page: r.path, language: tag });
  }
  select.disabled = false;
  if (answer.state === "failed") { status.textContent = t("Not translated: ") + answer.error; return; }
  (r.translations ||= {})[tag] = answer.text;
  showLanguage(r, tag);
}
function askHost(body) {
  return fetch("/rem/translate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
    .then(response => response.status === 401 ? { state: "failed", error: t("Your session expired. Reload the page.") } : response.json())
    .catch(() => ({ state: "failed", error: t("REM is not answering right now. Try again in a moment.") }));
}
function swapLanguage(r, tag) {
  const shown = tag && r.translations?.[tag] ? tag : "";
  if ((r.shown || "") === shown) return;
  r.original ??= r.text;
  r.text = shown ? r.translations[shown] : r.original;
  r.shown = shown;
}
function showLanguage(r, tag) {
  r.readLanguage = tag;
  swapLanguage(r, tag);
  render();
}

// ---------- a newer render (2026-11-09) ----------
// The Host answers with the page it saved at once and renders a newer one behind
// it. The page reloads onto that through one door, which keeps the view, the
// scroll and open sections; it never reloads over a draft being written, and
// offers a quiet link instead.
const RELOAD_STATE = "co-rem-reload";
const editedFields = new WeakSet();
// A reply being written, or the answer typed into one of its slots.
const EDITABLE = "textarea, [contenteditable], .owner-slot input";
document.addEventListener("input", event => {
  if (event.target.matches?.(EDITABLE)) editedFields.add(event.target);
}, true);
function unsavedDraft() {
  return [...document.querySelectorAll(EDITABLE)]
    .some(node => editedFields.has(node) && (node.value ?? node.textContent).trim());
}
// Only a newer render: an older or equal one (a build that crashed midway) is no reason to reload.
function reloadChoice({ latest, asOf, typing, unsaved }) {
  if (!latest?.as_of || !(new Date(latest.as_of) > new Date(asOf)) || typing) return null;
  return unsaved ? "offer" : "reload";
}
// A section is known by its id, else by its summary; positions move when a render adds rows.
function detailsKey(node) { return node.id ? "#" + node.id : node.querySelector("summary")?.textContent || ""; }
function viewState() {
  return { hash: location.hash, y: scrollY, fields: keptFields(),
    talks: [...OPEN_TALKS].map(([key, panel]) => [key, panel.talkBegin]),
    revealedSessions: [...document.querySelectorAll("[data-revealed-session]")].map(node => node.dataset.revealedSession),
    open: [...document.querySelectorAll("details")].filter(node => node.open).map(detailsKey).filter(Boolean) };
}
// Every field the owner types into carries a stable key (data-keep: the slot, the talk, the review);
// its words, caret and focus ride through a redraw.
function keptFields() {
  return [...document.querySelectorAll("[data-keep]")].filter(node => editedFields.has(node)).map(node => ({
    key: node.dataset.keep, value: node.value, focused: node === document.activeElement,
    start: node.selectionStart ?? null, end: node.selectionEnd ?? null }));
}
function restoreFields(fields) {
  for (const field of fields || []) {
    const node = [...document.querySelectorAll("[data-keep]")].find(other => other.dataset.keep === field.key);
    if (!node) continue;
    editedFields.add(node);
    if (node.value !== field.value) { node.value = field.value; node.dispatchEvent(new Event("input", { bubbles: true })); }
    if (field.focused) { node.focus({ preventScroll: true }); if (field.start !== null) node.setSelectionRange(field.start, field.end); }
  }
}
// Unsent words a redraw could not put back: an edited field in the page with no stable key.
function unkeptWords() {
  const main = document.getElementById("main");
  return [...document.querySelectorAll(EDITABLE)].some(node => main?.contains(node) && !node.dataset.keep
    && editedFields.has(node) && (node.value ?? node.textContent).trim());
}
// A redraw after a sync keeps what the reader opened and where they were. It waits while
// they type or hold unsent words: threadStates is current, and the next render shows it.
// A wait leaves the page behind the notebook, so one quiet mark says 有更新 until it draws.
let redrawSkipped = false, reopenByPosition = false;
function redraw() {
  if (typingIn(document.activeElement) || unsavedDraft()) { redrawSkipped = true; markUpdatesWaiting(); return; }
  drawKeepingView();
}
// byPosition: after a language switch, sections are also reopened by place, since one without an id is known
// by its summary and that changes language. It is done before the scroll goes back.
function drawKeepingView(byPosition = reopenByPosition) {
  redrawSkipped = reopenByPosition = false;
  document.getElementById("updates-waiting")?.remove();
  const state = viewState(), open = byPosition ? [...document.querySelectorAll("#main details")].map(node => node.open) : null;
  render();
  const sections = open ? document.querySelectorAll("#main details") : [];
  if (open && sections.length === open.length) sections.forEach((node, i) => { node.open = open[i]; });
  restoreView(state);
}
// Clicking it draws now and puts typed words back where they were (viewState carries them). A field
// it could not put back holds the mark until that field is done. Pressing it leaves focus in the field.
function markUpdatesWaiting() {
  if (document.getElementById("updates-waiting")) return;
  const mark = el("button", { id: "updates-waiting", type: "button", class: "updates-waiting", text: t("Updates waiting"),
    title: t("Shows when you finish writing. Click to show it now.") });
  mark.onmousedown = event => event.preventDefault();
  mark.onclick = () => { if (!unkeptWords()) drawKeepingView(); };
  document.body.appendChild(mark);
}
// Leaving the field, or the draft being sent or cleared, draws what waited.
function settleRedraw() {
  if (redrawSkipped) setTimeout(redraw, 0);
}
document.addEventListener("focusout", settleRedraw);
setInterval(settleRedraw, 3000);
function reloadOnto() {
  try {
    sessionStorage.setItem(RELOAD_STATE, JSON.stringify(viewState()));
  } catch (error) {
    // Blocked storage: the reload still lands on the same view, at the top.
  }
  location.reload();
}
let pendingRestore = (() => {
  try {
    const saved = JSON.parse(sessionStorage.getItem(RELOAD_STATE) || "null");
    sessionStorage.removeItem(RELOAD_STATE);
    // The row's panel nodes survived redraws, but a newer document needs to reopen them before rendering rows.
    if (saved?.hash === location.hash && liveHere()) {
      for (const [key, begin] of saved.talks || []) OPEN_TALKS.set(key, talkPanel(begin));
    }
    return saved;
  } catch (error) {
    return null;
  }
})();
function restoreView(state) {
  if (!state || state.hash !== location.hash) return false;
  const open = new Set(state.open || []);
  document.querySelectorAll("details").forEach(node => { if (open.has(detailsKey(node))) { node.open = true; node.fill?.(); } });
  // A deferred redraw after the search loses focus must keep an explicit Show.
  const revealed = new Set(state.revealedSessions || []);
  document.querySelectorAll(".session-curtain").forEach(node => {
    if (revealed.has(node.dataset.sessionDay)) node.querySelector("button").click();
  });
  restoreFields(state.fields);
  scrollTo(0, state.y || 0);
  return true;
}
function restoreAfterReload() {
  if (restoreView(pendingRestore)) pendingRestore = null;
}
function offerReload() {
  if (document.getElementById("newer-render")) return;
  const link = el("button", { id: "newer-render", type: "button", class: "btn-quiet", text: t("Newer page · Reload") });
  link.onclick = reloadOnto;
  document.getElementById("main").prepend(el("p", { class: "quiet-line", role: "status" }, [link]));
}
// After an upgrade the Host serves the old saved page until the new release has drawn its own, so a reload too
// early shows the old build again (Mac review of rc33). The page reloads only once the saved page is the
// installed release's; until then it says so and asks again every few seconds.
Object.assign(UI.zh, { "Switching to the new version…": "正在换到新版本…" });
function upgradeState(latest) {
  if (!latest?.installed || !REM?.release || latest.installed === REM.release) return "same";
  if (latest.release === latest.installed) return "ready";
  return latest.building ? "building" : "same";
}
function waitForNewBuild(again = false) {
  if (waitForNewBuild.dismissed || (waitForNewBuild.active && !again)) return;
  waitForNewBuild.active = true;
  waitForNewBuild.tries = (waitForNewBuild.tries || 0) + 1;
  if (!document.getElementById("upgrading")) {
    const dismiss = el("button", { type: "button", class: "lang-act", "aria-label": t("Close"), text: "×" });
    dismiss.onclick = () => { waitForNewBuild.dismissed = true; waitForNewBuild.active = false; document.getElementById("upgrading")?.remove(); };
    document.body.appendChild(el("div", { id: "upgrading", class: "host-lost", role: "status" },
      [el("span", { id: "upgrading-words", text: t("Switching to the new version…") }), dismiss]));
  } else {
    const words = document.getElementById("upgrading-words");
    if (words) words.textContent = t("Switching to the new version…");
  }
  if (waitForNewBuild.tries > 45) {
    waitForNewBuild.active = false;
    document.getElementById("upgrading")?.remove();
    offerReload();
    return;
  }
  setTimeout(async () => {
    if (waitForNewBuild.dismissed) return;
    const latest = await readVersion();
    const st = upgradeState(latest);
    if (st === "ready") reloadOnto();
    else if (st === "building") waitForNewBuild(true);
    else { waitForNewBuild.active = false; document.getElementById("upgrading")?.remove(); }
  }, 4000);
}
async function reconnect() {
  const latest = await readVersion();
  if (upgradeState(latest) === "building") waitForNewBuild();
  else reloadOnto();
}
function readVersion() {
  return fetch("/rem/version").then(response => { hostFound(); return response.ok ? response.json() : null; }, () => { hostLost(); return null; });
}
function showRebuildState(latest) {
  const line = document.getElementById("rendered-at");
  if (!line || !latest) return;
  line.textContent = t("Updated") + " " + fmtTime(REM.as_of) + (latest.failed ? " · " + t("the newest rebuild failed") : "");
  if (latest.failed) line.title = t("Details: {path}", { path: latest.failed.log });
  else line.removeAttribute("title");
}
// The "Updating…" line the Host puts on a saved page stays only while a newer page is really being built.
function clearUpdating(latest) {
  // Found by the end of its id: the Host adds the line only to a stale page, and a current page names it nowhere.
  if (latest && !latest.building && latest.as_of === REM.as_of) document.querySelector('[id$="-updating"]')?.remove();
}
async function checkForNewerRender() {
  if (document.hidden) return;
  const latest = await readVersion();
  showRebuildState(latest);
  clearUpdating(latest);
  const busy = unsavedDraft() || !!document.activeElement?.matches("input, select");
  // An upgrade: reload onto the new build by itself once it is drawn, unless he is typing or has a draft.
  const upgrade = upgradeState(latest);
  if (upgrade === "ready") return busy ? offerReload() : reloadOnto();
  if (upgrade === "building") return waitForNewBuild();
  const choice = reloadChoice({ latest, asOf: REM.as_of, unsaved: unsavedDraft(),
    typing: !!document.activeElement?.matches("input, select") });
  if (choice === "reload") reloadOnto();
  else if (choice === "offer") offerReload();
}
if (REM?.live) {
  setTimeout(checkForNewerRender, 1000);
  setInterval(checkForNewerRender, 30000);
}
window.addEventListener("focus", () => reconcileThreads().then(redraw));
window.addEventListener("online", () => reconcileThreads().then(redraw));
document.addEventListener("keydown", ev => {
  if (ev.key !== "Escape") return;
  const tag = ev.target?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || ev.target?.isContentEditable) return;
  if (document.querySelector("dialog[open]")) return;
  const cur = route();
  if (cur.view !== "open") return;
  if (cur.item) {
    openBatchQueue = null;
    location.hash = openHref({ item: "" });
  } else if (openMultiMode || openSelected.size > 0) {
    openSelected.clear();
    openMultiMode = false;
    redrawKeepingScroll();
  }
});

window.addEventListener("hashchange", render);
// The privacy levels' page-wide wiring (#2840): close the menu, curtain whatever is drawn, lift a curtain.
document.addEventListener("click", event => { if (!event.target.closest?.(".privacy-level-host")) document.querySelector(".privacy-menu") && togglePrivacyMenu(false); });
document.addEventListener("click", event => {
  if (!event.target.closest?.("#lang-progress")) document.querySelector(".lang-menu") && toggleLangMenu(false);
  if (!event.target.closest?.(".display-menu-host")) document.querySelector(".display-pop") && toggleDisplayMenu(false);
});
window.addEventListener("keydown", event => {
  if (event.key !== "Escape") return;
  if (document.querySelector(".lang-menu")) toggleLangMenu(false);
  if (document.querySelector(".display-pop")) toggleDisplayMenu(false);
});
window.addEventListener("keydown", event => { if (event.key === "Escape" && document.querySelector(".privacy-menu")) togglePrivacyMenu(false); });
new MutationObserver(records => { for (const record of records) for (const node of record.addedNodes) applyPrivacy(node); })
  .observe(document.documentElement, { childList: true, subtree: true });
document.addEventListener("click", event => {
  const curtain = event.target.closest?.(".curtain:not(.lifted)");
  if (!curtain || privacyLevel !== "cover") return;
  event.preventDefault(); event.stopPropagation();
  liftCurtain(curtain);
}, true);
window.addEventListener("keydown", event => {
  const curtain = event.target.closest?.(".curtain:not(.lifted)");
  if (!curtain || privacyLevel !== "cover" || !["Enter", " "].includes(event.key)) return;
  event.preventDefault(); event.stopPropagation();
  liftCurtain(curtain);
}, true);
window.addEventListener("resize", refreshFocusExpansion);
readerStorage("co-rem-calm").then(calm => { if (calm === "calm") { document.documentElement.classList.add("calm"); if (REM) renderSettings(); } });
Promise.all([readerStorage("co-rem-ui-language"), readerStorage("co-rem-theme"), readerStorage("co-rem-privacy"), readerStorage("co-rem-people-columns"), readerStorage(doneStorageKey()), readerStorage(threadStorageKey()),
  readerStorage(notDoneStorageKey()), readerStorage(keptOpenStorageKey()), readerStorage("co-rem-org-columns"), readerStorage("co-rem-org-collapsed")]).then(async ([language, theme, privacy, columns, done, saved, notDone, kept, orgSaved, collapsed]) => {
  if (language === "zh" || language === "en") uiLanguage = language;
  peopleColumns = peopleColumnKeys(columns);
  orgTableColumns = orgSaved ? peopleColumnKeys(orgSaved, ORG_COLUMNS) : null;  // none saved: orgsView picks the default, sparse columns left out
  orgCollapsed = new Set((collapsed || "").split("\n").filter(Boolean));
  notDoneKeys = new Set(notDone ? JSON.parse(notDone) : []);
  keptOpen = kept ? JSON.parse(kept) : {};
  const fallback = saved ? JSON.parse(saved) : null;
  pendingThreads = fallback?.pending || Object.fromEntries((done ? JSON.parse(done) : []).map(key => [key, { state: "done" }]));
  notebookThreads = { ...REM.threads };
  threadStates = { ...(REM.live ? REM.threads : { ...REM.threads, ...fallback?.states }), ...pendingThreads };
  REM.threads = threadStates;
  await readerStorage(threadStorageKey(), JSON.stringify({ states: threadStates, pending: pendingThreads }));
  await readerStorage(doneStorageKey(), "[]");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  // The level this device chose, else this computer's default (cover) or a shared or remote reader's (public).
  // A shared snapshot always starts at Public only, whatever this device chose before.
  setPrivacy(!REM?.shared && PRIVACY_LEVELS.includes(privacy) ? privacy : privacyDefault(), { save: false, redraw: false });
  render();
  // Offline snapshots finish loading after the shell without navigation.
  if (!detailReady && !REM.detail_url) {
    await loadDetails();
    render();
  }
  reconcileThreads().then(redraw);
});
