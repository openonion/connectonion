// ---------- tags (#3093): one vocabulary over every page; a tag is a page of the pages that carry it ----------
// The vocabulary is REM.tags ({slug: {label, kind, aliases, count}}); a page's slugs are r.tags; an open item's are
// its queue row's tags. Resolution follows tags.resolve in Python: slug, then normalised label, then an alias.
Object.assign(UI.zh, { "1 page with this tag is new or changed": "有 1 个带这个标签的页面是新的或改过", "{n} pages with this tag are new or changed": "有 {n} 个带这个标签的页面是新的或改过", "Open the tag page →": "打开标签页 →", "Tag page": "标签页", "Tags": "标签", "Tag": "标签", "Tag: {label}": "标签：{label}", "1 page carries this tag": "1 页带这个标签",
  "{n} pages carry this tag": "{n} 页带这个标签", "No page carries this tag yet": "还没有页面带这个标签", "No such tag": "没有这个标签",
  "Filter by tag": "按标签筛选", "All": "全部", "Tag {label}": "标签 {label}", "More tags": "更多" });
function tagNorm(text) {
  return String(text || "").trim().toLowerCase().replace(/^tag:/, "").replace(/[^\p{L}\p{N}\s_-]/gu, "").replace(/[\s_]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
}
function tagResolve(text) {
  const wanted = tagNorm(text), vocabulary = REM.tags || {};
  if (!wanted) return null;
  if (vocabulary[wanted]) return wanted;
  return Object.keys(vocabulary).find(slug => tagNorm(vocabulary[slug].label) === wanted || (vocabulary[slug].aliases || []).some(alias => tagNorm(alias) === wanted)) || null;
}
function tagLabel(slug) { return REM.tags?.[slug]?.label || slug; }
// A tag is a link to a page (#3140): the person, organisation, project or topic page it names; only a tag with
// no page yet opens the list of pages that carry it.
function tagHref(slug) {
  const page = REM.tags?.[slug]?.page, r = page && byPath(page);
  return r ? href(r) : "#q=" + encodeURIComponent("tag:" + slug);
}
// A merged chip (#3157: one company under a short and a full name) filters by any of its tags: "acme,acme-foods".
function tagged(records, slug) {
  if (!slug) return records;
  const slugs = String(slug).split(",");
  return records.filter(r => (r.tags || []).some(tag => slugs.includes(tag)));
}
// A page's tags as quiet links, each to its tag page; nothing when it has none.
function tagLinks(r, said = []) {
  // A page is never its own tag (rc34 hunt: an organisation's row listed the organisation): the tag that names this
  // page is what the page is, so the row shows only the other nodes it links to. Nor is a tag the head already says
  // (rc35 hunt: a person's organisation was her dek's link and again her first tag): `said` is those pages and words.
  const already = new Set(said.filter(Boolean).map(word => tagNorm(String(word))));
  const repeats = slug => already.has(tagNorm(REM.tags[slug].page || "")) || already.has(tagNorm(tagLabel(slug)));
  const slugs = (r.tags || []).filter(slug => REM.tags?.[slug] && REM.tags[slug].page !== r.path && !repeats(slug));
  return slugs.length ? el("span", { class: "tag-links" }, slugs.map(slug => el("a", { class: "tag-link", href: tagHref(slug), text: tagLabel(slug) }))) : null;
}
// One row of a page's tags under its title, on every kind (owner, 2026-11-19): the same links the person card shows,
// each opening the page the tag names or the tag's own page. Nothing when the page has no tag.
function pageTagRow(r, said = []) {
  const links = tagLinks(r, [r.title, ...said]);
  return links ? el("p", { class: "page-tags" }, [el("span", { class: "page-tags-label", text: t("Tags") }), links]) : null;
}
// The tag page: every page carrying it, grouped by kind, each group with its count (#3093 point 2).
// The tag's page: knowledge/<slug>.md, or the knowledge entry named for the tag (tag_nodes.node_record).
function tagWritten(slug) {
  const page = REM.tags?.[slug]?.page;
  if (page?.startsWith("knowledge/")) return byPath(page) || null;
  const names = new Set([slug, tagLabel(slug)].map(name => String(name).toLowerCase()));
  return (REM.records || []).find(r => r.path === "knowledge/" + slug + ".md")
    || (REM.records || []).find(r => r.category === "knowledge" && names.has(String(r.title || "").toLowerCase())) || null;
}
// Its words without what code adds: the title (the tag page has its own), the Tags line, the member list, the Sources.
function tagProse(r) {
  return String(r.text || "").replace(/^# [^\n]*\n/, "").replace(/^- Tags:[^\n]*\n/m, "").split(/\n## (?:Pages|Sources)[ \t]*\n/)[0].trim();
}
function tagPage(slug) {
  const main = document.getElementById("main");
  main.textContent = "";
  main.appendChild(el("div", { class: "eyebrow", text: t("Tag") }));
  if (!slug) { main.appendChild(el("h1", { text: t("No such tag") })); return; }
  const pages = tagged(listedRecords().concat(REM.records.filter(r => r.category === "sessions")), slug)
    .filter((r, i, all) => all.findIndex(x => x.path === r.path) === i && r.path !== tagWritten(slug)?.path);
  main.appendChild(el("h1", { class: "tag-title", text: tagLabel(slug) }));
  // The tag page REM wrote from these pages (#3140, `co rem tag`): what the tag is, how its pages connect, when.
  const written = tagWritten(slug);
  if (written) main.appendChild(el("article", { class: "tag-written note", "aria-label": t("Tag page") }, [
    el("div", { html: markdown(tagProse(written), written.path) }),
    el("a", { class: "tag-written-open", href: href(written), text: t("Open the tag page →") })]));
  main.appendChild(el("p", { class: "lede", text: pages.length ? t(pages.length === 1 ? "1 page carries this tag" : "{n} pages carry this tag", { n: pages.length })
    : t("No page carries this tag yet") }));
  const order = ["people", "orgs", "devices", "projects", "sessions", "skills", "decisions", "knowledge", "principles"];
  for (const kind of order) {
    const group = pages.filter(r => r.category === kind);
    if (!group.length) continue;
    main.appendChild(el("section", { class: "tag-group" }, [sectionHead(label(kind), String(group.length)),
      el("ul", { class: "hits" }, group.map(r => row(r, { kind: false, hideZeroUsage: true })))]));
  }
}
// A list's tag chips: the tags its pages carry, with counts, most used first; one tap filters, a second clears.
// The row is labelled (#3157, P大: "筛选两排都叫『全部』，我刚点的是哪个全部？"). A chip leads with a name a person
// reads: a course or project code (digits, capitals, dashes) or a bare domain goes by its organisation's or tag page's
// own title when the notebook has one, and otherwise waits under 更多 instead of heading the row. One company under
// a short and a full name is one chip.
const CHIP_CODE = /^(?=\S*\d)[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*$/, CHIP_DOMAIN = /^(?:[a-z0-9-]+\.)+[a-z]{2,}$/i;
function chipCoded(name) { return CHIP_CODE.test(name) || CHIP_DOMAIN.test(name); }
function orgForDomain(domain) {
  const d = domain.toLowerCase(), dashed = d.replace(/\./g, "-");
  return inCategory("orgs").find(org => org.path.split("/").pop().replace(/\.md$/, "").replace(/-[0-9a-f]{6,}$/, "") === dashed
    || (rawSection(org, "Domains") || "").toLowerCase().includes(d)) || null;
}
// A course or team page titled by its code alone ("3900", "9900-F13D-BREAD", "3900/9900") says what it is wherever an
// organisation's name shows (rc18 hunt: bare codes headed the graph and the org tree): "课程 3900", "团队 9900-F13D-BREAD".
// A code page whose kind REM does not know yet keeps its code. The one rule for coded organisation names.
function codedOrgName(r) {
  const title = String(r?.title || "").trim(), kind = r?.unit_kind || "";
  if (!r?.path?.startsWith("orgs/") || !kind || !CHIP_CODE.test(title)) return null;
  const word = orgT(kind);
  return t("{kind} {code}", { kind: uiLanguage === "en" ? word[0].toUpperCase() + word.slice(1) : word, code: title });
}
function privateMaskNo(path) {
  if (!path) return "";
  const rec = typeof byPath === "function" ? byPath(path) : (REM?.records || []).find(r => r.path === path);
  if (rec?.masked_number) return String(rec.masked_number);
  const all = [...new Set([...(REM?.records || []).filter(r => r.private).map(r => r.path),
    ...(REM?.graph?.nodes || []).filter(n => n.private).map(n => n.id)])].sort();
  const idx = all.indexOf(path);
  return idx >= 0 ? String(idx + 1) : "";
}
function privateMaskLabel(r) {
  const no = privateMaskNo(r?.path || r?.id);
  return t("Personal item") + (no ? " " + no : "");
}
// Any page's name in a link: masked when private below Show all (#3387), else coded org name or title.
function pageName(r) {
  if (r?.private && privacyLevel !== "all") return privateMaskLabel(r);
  return codedOrgName(r) || r?.title;
}
function chipName(slug) {
  const label = tagLabel(slug).trim();
  if (!chipCoded(label)) return { name: label, readable: true };
  const page = REM.tags?.[slug]?.page ? byPath(REM.tags[slug].page) : tagWritten(slug);
  const title = String(codedOrgName(page) || page?.title || "").trim();
  if (title && !chipCoded(title)) return { name: title, readable: true };
  const org = CHIP_DOMAIN.test(label) ? orgForDomain(label) : null;
  return org ? { name: orgName(org), readable: true } : { name: label, readable: false };
}
const CHIP_SUFFIX = /\b(?:pty|ltd|limited|inc|llc|corp|corporation|co|company|gmbh|pte)\b\.?/gi;
function chipSameCompany(a, b) {
  const page = slug => REM.tags?.[slug]?.page || "", kind = slug => REM.tags?.[slug]?.kind || "";
  if (page(a.slug).startsWith("orgs/") && page(a.slug) === page(b.slug)) return true;
  if (kind(a.slug) !== "org" || kind(b.slug) !== "org") return false;
  const norm = name => name.toLowerCase().replace(CHIP_SUFFIX, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  return norm(a.name) === norm(b.name) || startsWords(a.name, b.name) || startsWords(b.name, a.name);
}
function tagBar(c, records) {
  const members = new Map();
  for (const r of records) for (const slug of r.tags || []) if (REM.tags?.[slug]) (members.get(slug) || members.set(slug, new Set()).get(slug)).add(r.path);
  const active = route().tag;
  const chips = [];
  for (const [slug, paths] of [...members].sort((a, b) => b[1].size - a[1].size)) {
    const chip = { slug, paths: new Set(paths), ...chipName(slug) };
    const same = chip.readable && chips.find(other => other.readable && chipSameCompany(other, chip));
    if (!same) { chips.push({ ...chip, slugs: [slug] }); continue; }
    same.slugs.push(slug);
    for (const path of paths) same.paths.add(path);
    if (chip.name.length > same.name.length) same.name = chip.name;
  }
  const keyOf = chip => chip.slugs.join(",");
  const shown = chips.filter(chip => chip.paths.size > 1 || keyOf(chip) === active || chip.slugs.includes(active));
  const allReadable = shown.filter(chip => chip.readable).sort((a, b) => b.paths.size - a.paths.size);
  const readable = allReadable.slice(0, 12);
  const coded = [...allReadable.slice(12), ...shown.filter(chip => !chip.readable).sort((a, b) => b.paths.size - a.paths.size)];
  if (!readable.length && !coded.length) return null;
  const curParams = new URLSearchParams(location.hash.slice(1));
  const extra = ["v", "family", "src"].filter(k => curParams.get(k)).map(k => `&${k}=${encodeURIComponent(curParams.get(k))}`).join("");
  const base = "#c=" + c + extra;
  const link = chip => {
    const on = keyOf(chip) === active || (chip.slugs.length === 1 && chip.slugs[0] === active);
    return el("a", { class: "chip" + (on ? " on" : ""), href: on ? base : base + "&tag=" + encodeURIComponent(keyOf(chip)),
      "aria-current": on ? "true" : null, title: chip.slugs.map(tagLabel).join(" · ") }, [chip.name, " ", el("span", { class: "chip-n", text: String(chip.paths.size) })]);
  };
  const more = coded.length ? el("details", { class: "chip-more" + (coded.some(chip => keyOf(chip) === active || chip.slugs.includes(active)) ? " on" : "") }, [
    el("summary", { class: "chip" }, [t("More tags"), " ", el("span", { class: "chip-n", text: String(coded.length) })]),
    el("div", { class: "chip-more-list" }, coded.map(link))]) : null;
  if (more?.classList.contains("on")) more.open = true;
  return el("nav", { class: "open-chips tag-bar", "aria-label": t("Filter by tag") }, [
    el("span", { class: "bar-label", text: t("Tags") }),
    el("a", { class: "chip" + (active ? "" : " on"), href: base, "aria-current": active ? null : "true", text: t("All") }),
    ...readable.map(link), more]);
}
const TAG_LISTS = ["people", "orgs", "devices", "projects", "skills", "decisions", "principles"];
function calendarDay(iso) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(iso))) return String(iso);
  const d = new Date(iso);
  if (isNaN(d)) return "";
  // One formatter per time zone: building one per call made a 1,400-person People table measurably slower (#3346).
  const zone = REM.status?.timezone || "UTC";
  // Kept on the function itself, so it travels with calendarDay wherever the function is used alone.
  if (calendarDay.zone !== zone) Object.assign(calendarDay, { zone, format: new Intl.DateTimeFormat("en-US", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }) });
  const parts = calendarDay.format.formatToParts(d);
  const part = type => parts.find(p => p.type === type).value;
  return part("year") + "-" + part("month") + "-" + part("day");
}
function fmtDate(iso) {
  if (!iso) return "";
  const day = calendarDay(iso), d = new Date(day + "T00:00:00Z");
  if (isNaN(d)) return "";
  const today = calendarDay(REM.as_of || new Date().toISOString());
  const days = Math.round((new Date(today + "T00:00:00Z") - d) / 86400000);
  if (days >= 0 && days <= 7) {
    if (uiLanguage === "zh") return days === 0 ? "今天" : days === 1 ? "昨天" : days + " 天前";
    return days === 0 ? "Today" : days === 1 ? "Yesterday" : days + " days ago";
  }
  return d.toLocaleDateString(uiLocale(), { timeZone: "UTC", ...(day.slice(0, 4) !== today.slice(0, 4) ? { year: "numeric" } : {}), month: "short", day: "numeric" });
}
// The calendar date alone ("Oct 29", "10月29日"): for dates inside a sentence, where "3 days ago" would not read.
function calendarDate(day, locale = uiLocale()) {
  const d = new Date(day + "T00:00:00Z"), today = calendarDay(REM.as_of || new Date().toISOString());
  return isNaN(d) ? day : d.toLocaleDateString(locale, { timeZone: "UTC", ...(day.slice(0, 4) !== today.slice(0, 4) ? { year: "numeric" } : {}), month: "short", day: "numeric" });
}
// One language per line: a date takes the language of the sentence around it, not the interface's.
function datesInProse(text) {
  const locale = /\p{Script=Han}/u.test(text) ? "zh-CN" : "en-US";
  return String(text).replace(/\b\d{4}-\d{2}-\d{2}\b/g, day => calendarDate(day, locale));
}
function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? iso : fmtDate(iso) + " · " + d.toLocaleTimeString(uiLocale(), { hour: "2-digit", minute: "2-digit", timeZone: REM.status?.timezone || "UTC" });
}
function shortDate(day) {
  return fmtDate(day);
}
function num(n) { return n == null ? t("unknown") : Number(n).toLocaleString(); }
function compact(n) { return n == null ? "—" : n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e4 ? Math.round(n / 1e3) + "k" : String(n); }
function resolve(from, path) {
  const base = from.split("/").slice(0, -1);
  for (const part of path.split("/")) {
    if (part === "..") base.pop();
    else if (part !== "." && part !== "") base.push(part);
  }
  return base.join("/");
}
// The queued line says where the page really stands (#3420). "Queued for tonight" sat on 1,241 pages while a
// night completed 3 to 10: 今晚 only inside the measured nightly pace, otherwise the place and an estimate.
function queuedLine(r) {
  const place = r.queue_place, pace = REM.night_throughput;
  if (!place) return t("Page queued for a future night");
  if (pace && place <= pace) return t("Page queued for tonight");
  if (!pace) return t("In the queue at #{n}", { n: place.toLocaleString() });
  const nights = Math.ceil(place / pace);
  if (nights <= 30) return t("In the queue at #{n} · at about {k} pages a night, within about {d} nights", { n: place.toLocaleString(), k: pace, d: nights });
  // Months away, the exact place only discourages: say how far and the way forward. 调查 starts this page's
  // investigation now (POST /rem/investigate, `co rem investigate PAGE --enrich`), so the hint is only offered where
  // that button works; in a snapshot it is off.
  const far = t(nights > 365 ? "Far back in the queue — over a year at the current pace" : "Far back in the queue — months at the current pace");
  return liveHere() ? far + t(" · investigate it now to see it sooner") : far;
}

function safeHref(from, raw) {
  const target = raw.trim();
  if (target.startsWith("/rem/task-file?")) return { href: target, external: false };
  if (/^(https?:|file:|mailto:)/i.test(target)) return { href: target, external: true };
  if (target.startsWith("/") && !target.startsWith("//"))
    return { href: "file://" + target.split("/").map(encodeURIComponent).join("/"), external: true };
  if (target.startsWith("#")) return { href: "#r=" + encodeURIComponent(from) + "&h=" + encodeURIComponent(target.slice(1)), external: false };
  if (/\.md(#.*)?$/i.test(target) && !/^[a-z]+:/i.test(target)) {
    const path = resolve(from, target.split("#")[0]);
    if (byPath(path)) return { href: "#r=" + encodeURIComponent(path) + (target.includes("#") ? "&h=" + encodeURIComponent(target.split("#")[1]) : ""), external: false };
  }
  return null;
}
function copyToClipboard(text, btn, successMsg) {
  const original = btn.textContent;
  const done = msg => { btn.textContent = t(msg); btn.classList.add("done"); setTimeout(() => { btn.textContent = original; btn.classList.remove("done"); }, 1500); };
  if (!navigator.clipboard) { done(t("Select and copy")); return; }
  navigator.clipboard.writeText(text).then(() => done(successMsg || t("Copied")), () => done(t("Copy failed")));
}
// Status as a moon phase: full when investigated, half with some findings, new when only mapped.
const MOON = {
  "Investigated": '<circle cx="6" cy="6" r="5" fill="currentColor"/>',
  "Partly investigated": '<circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M6 1a5 5 0 0 1 0 10z" fill="currentColor"/>',
  "Mapped": '<circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" stroke-width="1.2"/>'
};
function moon(status) {
  const span = el("span", { "aria-hidden": "true", html: '<svg class="moon" viewBox="0 0 12 12">' + (MOON[status] || MOON.Mapped) + "</svg>" });
  return span.firstChild;
}

// ---------- markdown (small, escape-first) ----------
// The page being rendered: its numbered sources, so a claim's [n] can name its source.
let CITES = { from: "", sources: {} };
function citationSource(r, n) {
  if (!r) return "";
  return r.path === CITES.from ? CITES.sources[n] || "" : sourceList(r).find(s => s.n === n)?.text || "";
}
function citationId(r, n) {
  return sourceId(citationSource(r, n), r && sourceList(r).find(s => s.n === n)?.plain);
}
function sourceChannel(kind) {
  // A context without a kind (a web capture from an older Host) names no channel rather than throwing: the throw
  // left a web source's card with its header alone (rc35 hunt).
  kind = String(kind || "");
  if (!kind) return "";
  return t(({ gmail: "Gmail", outlook: "Outlook", codex: "Session", claude: "Session", "project-source": "Repo", whatsapp: "WhatsApp", web: "Web" })[kind]
    || (/^(codex|claude)[- ]/.test(kind) ? "Session" : kind.charAt(0).toUpperCase() + kind.slice(1)));
}
// A web source is named for a person, never by its URL-encoded query (rc35 hunt: "duckduckgo.com/?q=%22…"): a saved
// page by its own title, a search as "DuckDuckGo search: "…"", anything else by its site and decoded path.
function isWebSource(id) {
  return /^https?:\/\//i.test(id || "") && URL.canParse(id);
}
function webSource(id, context) {
  const SEARCH_ENGINES = { google: "Google", duckduckgo: "DuckDuckGo", bing: "Bing", "search.brave": "Brave", baidu: "Baidu", yandex: "Yandex" };
  const url = new URL(id), site = url.hostname.replace(/^www\./, "");
  if (context?.title) return { site, title: context.title };
  const engine = Object.entries(SEARCH_ENGINES).find(([key]) => site.startsWith(key + "."))?.[1];
  const query = ["q", "query", "wd", "text", "p"].map(key => url.searchParams.get(key)).find(Boolean) || "";
  if (engine && query) return { site, title: t("{engine} search: {query}", { engine,
    query: uiLanguage === "zh" ? query.replace(/"([^"]*)"/g, "“$1”") : query }) };
  const decoded = [url.pathname, url.search].map(part => { const text = part.replace(/\+/g, " ");
    return /%[0-9a-f]{2}/i.test(text) && !/%(?![0-9a-f]{2})/i.test(text) ? decodeURIComponent(text) : text; }).join("");
  return { site, title: site + (decoded === "/" ? "" : decoded.replace(/\/$/, "")) };
}
function sourceSender(context) {
  const from = context.participants?.from;
  const sender = (Array.isArray(from) ? from[0] : from) || context.sender || "";
  const page = byPath(sender);
  if (page) return page.path === REM.owner ? t("you") : page.title.split(/\s+/)[0];
  if (/\/|\.md/i.test(sender)) return "";
  const who = mailbox(sender);
  if (!who.address) return "";
  const person = personByAddress(who.address), owner = byPath(REM.owner);
  if (owner && (person === owner || owner.index?.emails?.some(address => address.toLowerCase() === who.address))) return t("you");
  const name = person?.title || who.name;
  return /\/|\.md/i.test(name) ? "" : name.split(/\s+/)[0];
}
function chipLabel(r, n) {
  const text = citationSource(r, n), id = citationId(r, n);
  if (!id) return t("source {n}", { n });
  const context = (REM.source_context || {})[id];
  const kind = context?.source || id.split(":")[0] || /\b(gmail|outlook|codex|claude|project-source|whatsapp)\b/i.exec(text)?.[1]?.toLowerCase() || "";
  const day = context?.time ? calendarDay(context.time) : /\d{4}-\d{2}-\d{2}/.exec(text)?.[0];
  const when = day ? fmtDate(day) : "";
  // A link is named by its site ("duckduckgo.com, Nov 17"), never "Https".
  if (isWebSource(id)) return [webSource(id, context).site, when].filter(Boolean).join(", ");
  const label = [context && sourceSender(context), sourceChannel(kind), when].filter(Boolean);
  return label.join(", ") || t("source {n}", { n });
}
function citationDate(r, n) {
  const text = citationSource(r, n), context = (REM.source_context || {})[citationId(r, n)];
  const day = context?.time ? calendarDay(context.time) : /\d{4}-\d{2}-\d{2}/.exec(text)?.[0];
  return day ? fmtDate(day) : t("source {n}", { n });
}
// A value's citations: one chip each, or one run when there are more than two or when two would print the
// same date side by side ("11月8日 11月8日" on a project fact, rc44 hunt).
function citeChips(ns, from) {
  const r = byPath(from);
  const same = ns.length === 2 && citationDate(r, ns[0]) === citationDate(r, ns[1]);
  return ns.length > 2 || same ? citeRun(ns, from) : ns.map(n => citeChip(n, from)).join("");
}
function citeRun(ns, from) {
  return citeChip(ns[0], from, true, false, ns);
}
function citeChip(n, from, showDescription = true, visibleLabel = false, ns = [n]) {
  const r = byPath(from), text = citationSource(r, n), context = (REM.source_context || {})[citationId(r, n)];
  const label = ns.map(number => {
    const text = citationSource(r, number);
    return !citationId(r, number) && text ? text : chipLabel(r, number);
  }).join("; "), missing = ns.some(number => {
    const text = citationSource(r, number);
    const id = citationId(r, number);
    return !text || (id && !(REM.source_context || {})[id]);
  });
  const when = citationDate(r, n), full = when === t("source {n}", { n }) ? when : chipLabel(r, n);
  const subject = context?.subject || REM.conversations?.[context?.thread]?.subject;
  // The chip's title and aria-label are the reader's words (#3410: "Source: …" in a Chinese reader).
  const tip = t("Source: {label}", { label }) + (subject ? t(", subject “{subject}”", { subject }) : "")
    + (missing ? t(", original not in this snapshot") : "") + (ns.length > 1 ? t(", {n} sources for this line", { n: ns.length }) : "");
  return '<a class="cite' + (ns.length > 1 ? " run" : "") + (missing ? " missing" : "") + '" href="#r=' + esc(encodeURIComponent(from)) + "&amp;h=src-" + n.toLowerCase() +
    '" data-sources="' + ns.join(" ") + '" title="' + esc(tip) + '" aria-label="' + esc(tip) + '">' + '<span class="cite-full">' + esc(full) + (ns.length > 1 ? " +" + (ns.length - 1) : "") + '</span><span class="cite-short">' + esc(when) + (ns.length > 1 ? " +" + (ns.length - 1) : "") + "</span><sup class=\"cite-number\">" + esc(n) + "</sup></a>";
}
// Pages are written about "the user"; the reader is read by them. At render time
// only (the Markdown keeps its wording, and Copy Markdown copies it as written)
// "the user" becomes "you", with the verb that follows agreeing: "the user has
// not signed" reads "you have not signed", "the user's" reads "your".
const YOU_VERBS = { has: "have", is: "are", was: "were", does: "do", "hasn't": "haven't", "isn't": "aren't", "wasn't": "weren't", "doesn't": "don't" };
// Words after "the user" that end in s and are not verbs: "owes the user its proposal".
const NOT_VERBS = new Set(["its", "as", "was", "has", "yes", "plus", "thus", "less", "unless", "always", "perhaps", "sometimes", "whereas", "towards", "afterwards", "nevertheless", "regardless", "across", "besides"]);
function plural(verb) {
  if (YOU_VERBS[verb.toLowerCase()]) return YOU_VERBS[verb.toLowerCase()];
  if (/(?:ss|us|is)$/i.test(verb) || !/s$/i.test(verb) || NOT_VERBS.has(verb.toLowerCase())) return null;  // not a third-person verb
  if (/[^aeiou]ies$/i.test(verb)) return verb.slice(0, -3) + "y";
  if (/(?:sh|ch|x|z|o)es$/i.test(verb)) return verb.slice(0, -2);
  return verb.slice(0, -1);
}
// "the user" opening a clause is its subject, so a second verb after "and"/"but"
// agrees too: "the user runs events and has asked" reads "you run events and have
// asked" (1.9.2b1). Only verbs that are never plural nouns: "invoices and receipts" stays.
const CLAUSE_START = /(?:^|[.;:!?(—–,>。！？；：，（]\s*|\b(?:and|but|or|that|when|while|because|if|since|until|after|before|whether|so)\s+)$/i;
const ALSO_VERBS = new Set([...Object.keys(YOU_VERBS), "owes", "says", "asks", "wants", "expects", "prefers", "agrees", "replies", "writes", "thinks", "knows", "seems"]);
// A question puts the verb before "the user", and it agrees too: "Has the user
// collected the card?" reads "Have you collected the card?" (#2908). Only at a
// clause or question-word start: "The signer is the user." stays "is".
function youify(text) {
  const cap = (t, s) => t === "T" ? s[0].toUpperCase() + s.slice(1) : s;
  return String(text)
    .replace(/\b(has|is|was|does|hasn['’]t|isn['’]t|wasn['’]t|doesn['’]t)(?= the user\b(?!['’-]))/gi, (m, verb, at, all) => {
      const before = all.slice(0, at), agreed = YOU_VERBS[verb.toLowerCase().replace("’", "'")].replace("'", verb.includes("’") ? "’" : "'");
      return CLAUSE_START.test(before) || /\b(?:what|when|where|why|how|who|whom|which)\s+$/i.test(before) ? cap(verb[0] === verb[0].toUpperCase() ? "T" : "t", agreed) : m;
    })
    .replace(/\b([Tt])he user(?:'s|’s)/g, (m, t) => cap(t, "your"))
    .replace(/\b([Tt])he user (?:(still|also|now|then|already|never|often|usually|[a-z]+ly) )?([a-z]+(?:['’]t)?)\b/g, (m, t, adverb, word, at, all) => {
      const verb = plural(word.replace("’", "'"));
      const subject = CLAUSE_START.test(all.slice(0, at)) ? "\u0004" : "";
      return cap(t, "you") + subject + " " + (adverb ? adverb + " " : "") + (verb || word);
    })
    .replace(/\u0004((?:(?!\b(?:and|but|or|yet)\b)[^.;!?。！？；\u0004])*?\b(?:and|but|or|yet) (?:(?:still|also|now|then|already|never|[a-z]+ly) )?)([a-z]+(?:['’]t)?)\b/g,
      (m, between, word) => between + (ALSO_VERBS.has(word.replace("’", "'").toLowerCase()) ? plural(word.replace("’", "'")) : word))
    .replace(/\u0004/g, "")
    .replace(/\b([Tt])he user\b(?!-)/g, (m, t) => cap(t, "you"));  // "the user-facing copy" stays
}
// Session summaries are stored with the role word: "The owner asked…", "Owner 询问…". The reader says
// You / 你 at display time and the notebook keeps its words. Only the subject of a finished act at the
// start of a sentence changes: "the owner of the repo", "is the owner", "The owner Ida…", present tense
// ("The owner wants" would need "You want") and "Mara（owner）" can name someone else, so they stay.
function ownerAsYou(text) {
  const did = /(^|[.!?]\s+)(?:The owner|Owner)\s+(?=(?:[a-z]+ed|said|sent|made|wrote|gave|took|told|chose|set|put|kept|left|met|paid|found|got|brought|ran|began|saw|led|built|read|spent|won|lost)\b)/g;
  const didZh = /(^|[。！？]\s*)Owner\s*(?=询问|要求|提出|确认|表示|决定|批准|同意|指出|说明|提到|选择|发送|上传|打开|补充|追问|反馈|分享|转发|安排|指示|让|请)/g;
  return String(text || "").replace(did, "$1You ").replace(didZh, "$1你");
}
// Privacy labels trail a sentence or clause in either writing system. Keep
// code and link targets atomic so a filename's dot cannot expose its prefix.
function privatePassages(text, replace) {
  const protectedParts = [];
  const protect = part => {
    protectedParts.push(part);
    return "\u0005" + (protectedParts.length - 1) + "\u0005";
  };
  const restore = value => value.replace(/\u0005(\d+)\u0005/g, (_, i) => protectedParts[i]);
  let value = String(text).replace(/`[^`\n]*`|\[[^\]\n]+\]\(((?:[^()\s]|\([^()\s]*\))+)\)/g, protect);
  value = value.replace(/“[^”\n]*”|「[^」\n]*」|"[^"\n]*"|&quot;(?:(?!&quot;)[^\n])*&quot;/g,
    quote => quote.replace(/[.!?;:,。！？；：，]/g, protect));
  value = value.replace(/&(?:#\d+|#x[\da-f]+|\w+);/g, protect);
  // A mark that opens a line labels the whole line, as a trailing one labels its sentence (#3410). The passage regex
  // below reads a mark only after its words, so a leading "[sensitive] …" showed the raw mark and left its words bare.
  value = value.replace(/(^|\n)([ \t]*(?:[-*•][ \t]+)?)([\[［](?:personal|sensitive)[\]］])[ \t]*([^\n]+)/gi,
    (m, start, bullet, mark, rest) => start + bullet + protect(replace(restore(rest) + " " + mark, /sensitive/i.test(mark) ? "sensitive" : "personal")));
  // Decimal numbers, email addresses and domains do not start a new sentence.
  value = value.replace(/(?<=[\p{L}\p{N}])\.(?=[\p{L}\p{N}])/gu, protect);
  value = value.replace(/(?<=^|[\n.!?;:,。！？；：，](?:\s*[\[［](?:personal|sensitive|W?\d+)[\]］])*\s*)(?!\s|[\[［](?:personal|sensitive|W?\d+)[\]］])([^\n.!?。！？]*?[.!?;:,。！？；：，]?)\s*[\[［](personal|sensitive)[\]］]((?:\s*[\[［](?:personal|sensitive|W?\d+)[\]］])*)([.!?;:,。！？；：，]?)/gi,
    (passage, sentence, level) => replace(restore(passage), level.toLowerCase()));
  return restore(value);
}
// The text with its labelled passages taken out, mended where they stood: no space left before the punctuation that
// followed, and an English sentence the cut left starting lowercase starts with a capital again ("…classes. it will
// close" from "…classes. Funding ends in May [sensitive], it will close"; rc36 privacy fixer).
function unlabelled(text) {
  return mendCuts(privatePassages(text, () => "\u0006"));
}
function mendCuts(text) {
  return String(text)
    .replace(/(^|[.!?]["”’')]?)([ \t]*)\u0006+[ \t]*([a-z])/gm, (m, end, gap, letter) => end + (end ? " " : gap) + letter.toUpperCase())
    .replace(/[ \t]*\u0006+[ \t]*(?=[.,;:!?。，；：！？]|$)/gm, "")
    .replace(/([ \t]?)\u0006+[ \t]*/g, "$1");
}
function hasPrivacy(text) {
  return /[\[［](?:personal|sensitive)[\]］]/i.test(text);
}
function inline(text, from) {
  let s = esc(String(text ?? "").replace(/<\/?artifact-content-authored-by-others\s*\/?>/gi, ""));
  const codes = [];
  s = s.replace(/`([^`]+)`/g, (m, c) => { codes.push(c); return "\u0001" + (codes.length - 1) + "\u0001"; });
  const links = [];
  s = s.replace(/\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)/g, (m, lbl, url) => {
    const rawUrl = url.replace(/&amp;/g, "&");
    const link = safeHref(from, rawUrl);
    // A page that is not in the notebook: say so, rather than look like a link that does nothing (#2054).
    if (!link) return /\.md(#.*)?$/i.test(url) ? '<span class="dead-link" title=t("This page is no longer in the notebook")>' + lbl + "</span>" : lbl;
    const target = !link.external && typeof resolve === "function" ? byPath(resolve(from || "", rawUrl.split("#")[0])) : null;
    if (target && privateTopicHidden(target)) return esc(privateMaskLabel(target));
    const shown = target?.private && privacyLevel !== "all" ? esc(pageName(target)) : lbl;
    const attrs = link.external ? ' target="_blank" rel="noopener noreferrer"' : "";
    links.push('<a href="' + esc(link.href) + '"' + attrs + ">" + shown + "</a>");
    return "\u0002" + (links.length - 1) + "\u0002";
  });
  // A page named in the notebook's own file syntax reads as its name, linked when the page exists (#3318).
  // The text is escaped already and a page title is not: undo the one, escape the result once.
  s = pageWords(s, (target, name) => {
    if (target && privateTopicHidden(target)) return esc(privateMaskLabel(target));
    if (target?.private && privacyLevel !== "all") {
      const masked = esc(pageName(target));
      links.push('<a href="' + esc(href(target)) + '">' + masked + "</a>");
      return "\u0002" + (links.length - 1) + "\u0002";
    }
    name = esc(name.replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&"));
    if (!target) return name;
    links.push('<a href="' + esc(href(target)) + '">' + name + "</a>");
    return "\u0002" + (links.length - 1) + "\u0002";
  });
  if (uiLanguage === "zh") s = s.replace(/\bUnknown\b/g, t("Unknown"));
  s = privatePassages(s, (passage, level) => '<span class="private" data-level="' + level + '">' +
    passage.replace(/[\[［](personal|sensitive)[\]］]/gi, (_, tag) => '<span class="privacy-tag ' + tag.toLowerCase() + '">' + esc(t(tag.toLowerCase() === "sensitive" ? "Sensitive" : "Personal passage")) + '</span>') + '</span>');
  // A mark the passage rule could not attach to its words (one beside a citation, one inside a link's text) is still a
  // label, never a word: printed raw it showed even at 只看公开 (#3425). The line it sits on is covered at its level,
  // whole, because the words it labels are not known; covering too much is safe, showing them is not.
  const stray = /[\[［](personal|sensitive)[\]］]/gi;
  if (stray.test(s.replace(/<span class="privacy-tag[^"]*">[^<]*<\/span>/g, ""))) {
    const level = /[\[［]sensitive[\]］]/i.test(s) ? "sensitive" : "personal";
    s = '<span class="private" data-level="' + level + '">' + s.replace(stray, "").replace(/[ \t]{2,}/g, " ") + '</span>';
  }
  // Full-width citation brackets carry the same source ids.
  s = s.replace(/［(W?\d{1,3})］/g, "[$1]");
  // Adjacent claim numbers share one quiet marker: one chip says how many, and names them on hover.
  s = youify(s);
  const runs = [];
  s = s.replace(/(?:\s*\[W?\d{1,3}\]){2,}/g, run => { runs.push(citeRun(run.match(/W?\d{1,3}/g), from)); return "\u0003" + (runs.length - 1) + "\u0003"; });
  s = s.replace(/\s*\[(W?\d{1,3})\]/g, (m, n) => citeChip(n, from));
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, "$1<em>$2</em>");
  s = s.replace(/\u0002(\d+)\u0002/g, (m, i) => links[i]);
  s = s.replace(/\u0003(\d+)\u0003/g, (m, i) => runs[i]);
  s = s.replace(/\u0001(\d+)\u0001/g, (m, i) => shortHash(codes[i]) === codes[i] ? "<code>" + codes[i] + "</code>"
    : '<code title="' + codes[i] + '">' + shortHash(codes[i]) + "</code>");
  return tetherCitations(uncertainCitations(quoteSpans(s)));
}
function uncertainCitations(html) {
  if (!html.includes('class="cite')) return html;
  const box = el("span", { html });
  let previous = null;
  for (const cite of box.querySelectorAll("a.cite")) {
    const range = document.createRange();
    if (previous) range.setStartAfter(previous); else range.setStart(box, 0);
    range.setEndBefore(cite);
    const fragment = el("span", {}, [range.cloneContents()]);
    fragment.querySelectorAll("code, .privacy-tag").forEach(node => node.remove());
    const sentence = fragment.textContent.trim().replace(/[.!?。！？]+$/, "").split(/[.!?。！？]\s*/).pop();
    if (/\b(?:unknown|not established|unconfirmed|not supplied)\b|\bwhether\b[^.!?。]*\bis\b|未知|尚未确认|未确认|未提供/i.test(sentence)) {
      moveCitationEnding(box, cite);
      cite.before(document.createTextNode(" "), el("span", { class: "uncertain-marker", role: "img", text: "◌", title: t("Not confirmed by the sources"), "aria-label": t("Not confirmed by the sources") }), document.createTextNode("\u200a"));
    }
    previous = cite;
  }
  return box.innerHTML;
}
function moveCitationEnding(box, cite) {
  const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
  let end = null;
  while (walker.nextNode() && !cite.contains(walker.currentNode)) {
    if (walker.currentNode.textContent.trim() && !walker.currentNode.parentElement.closest("code, .privacy-tag, .cite, .uncertain-marker")) end = walker.currentNode;
  }
  const punctuation = end && /([.!?。！？])\s*$/.exec(end.textContent);
  if (!punctuation) return;
  end.textContent = end.textContent.slice(0, punctuation.index);
  cite.after(document.createTextNode(punctuation[1]));
}
// Keep a word and marker together; an oversized word can still wrap inside the tether.
function tetherCitations(html) {
  if (!html.includes('class="cite')) return html;
  const box = el("span", { html });
  for (const cite of box.querySelectorAll("a.cite")) {
    const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
    let before = null;
    while (walker.nextNode() && !cite.contains(walker.currentNode)) {
      if (walker.currentNode.textContent.replace(/\u2060/g, "").trim() && !walker.currentNode.parentElement.closest(".privacy-tag, .cite, .uncertain-marker")) before = walker.currentNode;
    }
    if (!before) continue;
    const cjk = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}][^\p{L}\p{N}\s]*\s*$/u.exec(before.textContent);
    const word = cjk || /\S+\s*$/.exec(before.textContent);
    const after = cite.nextSibling, punctuation = after?.nodeType === Node.TEXT_NODE && /^\s*([.!?,;:。！？；：，])/u.exec(after.textContent);
    if (punctuation) after.textContent = after.textContent.replace(/^\s+/, "");
    // A joiner preserves nested emphasis, links and quoted spans without splitting their markup.
    if (before.parentElement !== cite.parentElement) {
      cite.before(document.createTextNode("\u2060"));
      if (punctuation) after.textContent = "\u2060" + after.textContent;
      continue;
    }
    const range = document.createRange();
    range.setStart(before, word.index);
    if (punctuation) range.setEnd(after, 1); else range.setEndAfter(cite);
    const tether = el("span", { class: "cite-tether" });
    tether.appendChild(range.extractContents());
    const inner = el("span", { class: "cite-word" }, [tether.firstChild]);
    tether.prepend(inner);
    range.insertNode(tether);
  }
  return box.innerHTML;
}
// Walk rendered prose so quotation marks in attributes and code stay untouched.
// Ranges retain links, citation chips and privacy spans inside a quotation.
function quoteSpans(html) {
  // Attribute quotes are markup; escaped straight quotes can be prose.
  if (!/“|「|&quot;|"/.test(html.replace(/<[^>]*>/g, ""))) return html;
  const body = document.createElement("span");
  body.innerHTML = html;
  const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT), nodes = [];
  let text = "";
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.parentElement.closest("code")) { text += "\n"; continue; }
    if (node.parentElement.closest(".cite, .privacy-tag")) continue;
    nodes.push({ node, start: text.length, end: text.length + node.length });
    text += node.data;
  }
  const quotes = [...text.matchAll(/“[^”\n]{6,}”|"[^"\n]{6,}"|「[^」\n]{6,}」/g)];
  for (const quote of quotes.reverse()) {
    const start = quote.index, end = start + quote[0].length;
    const first = nodes.find(n => n.start <= start && n.end > start);
    const last = nodes.find(n => n.start < end && n.end >= end);
    if (first.node.parentElement.closest(".private") !== last.node.parentElement.closest(".private")) continue;
    const range = document.createRange();
    range.setStart(first.node, start - first.start);
    range.setEnd(last.node, end - last.start);
    const said = el("span", { class: "said" });
    said.appendChild(range.extractContents());
    range.insertNode(said);
  }
  return body.innerHTML;
}
// A 40+ character digest is an id to copy, not to read: show its first 12 characters.
function shortHash(text) {
  return text.replace(/\b([0-9a-f]{12})[0-9a-f]{28,}\b/gi, "$1…");
}
const UNKNOWN_TEXT = /^(?:Unknown\s*—\s*(?:not investigated yet|not verified)|未知\s*[—–-]+\s*尚未(?:调查|核实|验证))/i;
// Only the placeholder: "Unknown — not verified. The latest session, 2026-06-09, …" is a finding (1.9.2b1).
const UNFILLED_LINE = /^(?:Unknown\s*—\s*(?:not investigated yet|not verified)|未知\s*[—–-]+\s*尚未(?:调查|核实|验证))[.;。；]?\s*(?:\[W?\d+\]\s*)*$/i;

function markdownList(lines, start, from) {
  const marker = /^( *)([-*+]|\d+[.)])\s+(.*)$/;
  const first = marker.exec(lines[start]);
  const indent = first[1].length, ordered = /^\d/.test(first[2]);
  const tag = ordered ? "ol" : "ul", items = [];
  let i = start;
  while (i < lines.length) {
    const item = marker.exec(lines[i]);
    if (!item || item[1].length !== indent || /^\d/.test(item[2]) !== ordered) break;
    const contentIndent = lines[i].length - item[3].length;
    const body = [item[3]];
    i++;
    while (i < lines.length) {
      if (!lines[i].trim()) {
        let next = i + 1;
        while (next < lines.length && !lines[next].trim()) next++;
        if (next === lines.length || lines[next].search(/\S/) <= indent) break;
        body.push(""); i++; continue;
      }
      const spaces = lines[i].search(/\S/);
      if (spaces <= indent) break;
      body.push(lines[i].slice(Math.min(spaces, contentIndent))); i++;
    }
    // An item that is only a section's name ("- Who they are. [1]" under Open questions: the old 仍不明确 leak) is the
    // reader's word, said through the same table as the headings and the opening line (art director on #3416).
    const itemContent = body.join("\n").replace(/^([A-Z][a-z]+(?: [a-z]+){0,4})\.?((?:\s*\[W?\d{1,3}\])*)\s*$/,
      (m, name, cites) => sectionWords(name) !== name ? sectionWords(name).replace(/。$/, "") + cites : m);
    const itemClass = UNKNOWN_TEXT.test(itemContent.trim()) ? ' class="unknown-item"' : "";
    items.push("<li" + itemClass + ">" + markdown(itemContent, from) + "</li>");
  }
  const startAt = ordered ? ' start="' + parseInt(first[2], 10) + '"' : "";
  return { html: "<" + tag + startAt + ">" + items.join("") + "</" + tag + ">", next: i };
}

// A fenced block drawn with box characters or arrows is a diagram: set on a dotted plate.
const DIAGRAM = /[─│┌┐└┘├┤┬┴┼→←↑↓▶▼]|-->|->|\+-{2,}|\|\s{2,}\S|^\s*v\s*$/m;
function codeBlock(code, info) {
  const lang = (info || "").trim().split(/\s+/)[0].toLowerCase();
  const diagram = (!lang || lang === "text" || lang === "ascii" || lang === "txt") && DIAGRAM.test(code);
  const cap = diagram ? t("Diagram") : lang && lang !== "text" ? lang : "";
  return '<div class="code-block' + (diagram ? " diagram" : "") + '">' + (cap ? '<span class="cap" aria-hidden="true">' + esc(cap) + "</span>" : "") +
    '<pre tabindex="0" aria-label="' + t(diagram ? "Diagram" : "Code block") + '"><code>' + esc(code) +
    '</code></pre>' + (diagram ? '<span class="pan-hint">' + t("Swipe diagram sideways to see all steps →") + '</span>' : '') +
    '<button class="code-copy" type="button" aria-label="' + t("Copy code") + '">' + t("Copy") + '</button></div>';
}

function markdown(text, from) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  let i = 0;
  const para = [];
  const flush = () => {
    if (para.length) {
      const pText = para.join(" ");
      const pClass = UNKNOWN_TEXT.test(pText.trim()) ? ' class="unknown-item"' : "";
      out.push("<p" + pClass + ">" + inline(pText, from) + "</p>");
      para.length = 0;
    }
  };
  while (i < lines.length) {
    const line = lines[i];
    let m;
    if ((m = /^\s{0,3}(`{3,}|~{3,})/.exec(line))) {
      flush();
      const code = [];
      const info = line.slice(m[0].length);
      const close = new RegExp("^\\s{0,3}" + m[1][0] + "{" + m[1].length + ",}\\s*$");
      i++;
      while (i < lines.length && !close.test(lines[i])) code.push(lines[i++]);
      i++;
      out.push(codeBlock(code.join("\n"), info));
      continue;
    }
    if ((m = /^(#{1,6})\s+(.*)$/.exec(line))) {
      flush();
      const level = Math.min(m[1].length + 1, 6);
      // A section heading is the reader's word: a known one reads in the reader's language, with its English kept as
      // the anchor so a section link does not change with the language (#3416: 「Open questions」 in a Chinese reader).
      const name = m[2].trim(), said = uiLanguage === "zh" && /^[A-Z][A-Za-z ]{1,40}$/.test(name) && t(name) !== name ? t(name) : "";
      out.push("<h" + level + (said ? ' data-anchor="' + esc(name) + '"' : "") + ">" + (said ? esc(said) : inline(m[2], from)) + "</h" + level + ">");
      i++; continue;
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { flush(); out.push("<hr>"); i++; continue; }
    if (/^>\s?/.test(line)) {
      flush();
      const quote = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ""));
      out.push("<blockquote>" + markdown(quote.join("\n"), from) + "</blockquote>");
      continue;
    }
    if (/^ *([-*+]|\d+[.)])\s+/.test(line)) {
      flush();
      const list = markdownList(lines, i, from);
      out.push(list.html); i = list.next;
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      flush();
      const cells = l => l.trim().replace(/^\||\|$/g, "").split("|").map(c => inline(c.trim(), from));
      const head = cells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]));
      out.push('<div class="table-scroll" role="region" aria-label="Table" tabindex="0"><table><thead><tr>' + head.map(c => "<th>" + c + "</th>").join("") + "</tr></thead><tbody>" +
        rows.map(r => "<tr>" + r.map(c => "<td>" + c + "</td>").join("") + "</tr>").join("") + "</tbody></table></div>");
      continue;
    }
    if (line.trim() === "") { flush(); i++; continue; }
    para.push(line.trim());
    i++;
  }
  flush();
  return out.join("\n");
}

function splitTrailers(text) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const body = [], related = [], sources = [];
  let fence = null;
  for (const line of lines) {
    const t = line.trim();
    const marker = /^[ \t]*(`{3,}|~{3,})/.exec(line);
    if (marker) {
      if (!fence) fence = marker[1];
      else if (new RegExp("^" + fence[0] + "{" + fence.length + ",}\\s*$").test(t)) fence = null;
      body.push(line); continue;
    }
    if (fence) { body.push(line); continue; }
    // Code-owned lines: the Tags line is the tag row under the title (#3140), the Investigation stamp is the button's.
    // A masked page's number (masked.py) is the graph's label, not prose.
    if (/^-\s*Tags:/.test(t) || /^Investigation:/.test(t) || /^Masked:\s*\d+\s*$/.test(t)) continue;
    if (/^(related|相关|相关页面|相关链接|相关项目|相关人物|相关决定|相关待办)[:：]/i.test(t)) related.push(t.replace(/^[^:：]+[:：]\s*/, ""));
    else if (/^(sources?|来源)[:：]/i.test(t)) sources.push(t.replace(/^[^:：]+[:：]\s*/, ""));
    else body.push(line);
  }
  return { body: body.join("\n"), related: related.join(", "), sources: sources.join(", ") };
}

function sourceLabel(id) {
  const parts = id.split(":");
  const opaque = /^(?:[0-9a-f]{32,}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$/i;
  if (/\.[^/\\]+$/.test(parts.at(-1)) || !parts.some(part => opaque.test(part))) return id;
  const context = REM.source_context?.[id];
  const session = /^(codex|claude-code):/.exec(id);
  if (session && context?.time) return t(session[1] === "codex" ? "Codex session" : "Claude Code session") + " · " + threadDate(calendarDay(context.time));
  return parts.map(part => opaque.test(part) ? part.slice(0, 8) + "…" : part).join(":");
}
function sourceChips(text) {
  const chips = [];
  for (const part of text.split(/,\s*(?=[a-z][a-z-]*:)/i)) {
    const m = /^([a-z][a-z-]*:[^\s(]+)\s*(?:\(([^)]*)\))?/i.exec(part.trim());
    if (!m) continue;
    const chip = el("span", { class: "chip", text: sourceLabel(m[1]), title: m[1] });
    if (m[2]) chip.appendChild(el("span", { class: "d", text: m[2] }));
    chips.push(chip);
  }
  return chips;
}

// A mapped page's unanswered sections, each a heading over "Unknown — not investigated yet", filled a skill page
// with one empty section after another (rc48 hunt: 9 of 16). They fold into one line at the end that names them;
// a section with anything else in it stays where it is.
function foldUnfilled(note) {
  const empty = [];
  for (const h of [...note.querySelectorAll(":scope > h2")]) {
    const body = [];
    for (let n = h.nextElementSibling; n && n.tagName !== "H2"; n = n.nextElementSibling) body.push(n);
    const words = body.map(n => n.textContent.replace(/\s+/g, " ").trim()).filter(Boolean);
    if (!words.length || !words.every(w => UNFILLED_LINE.test(w.replace(/^[-*•]\s*/, "")))) continue;
    empty.push(h.textContent.trim());
    h.remove(); body.forEach(n => n.remove());
  }
  if (empty.length) note.appendChild(el("p", { class: "unfilled-sections", text: t("Still unknown: ") + empty.map(name => t(name)).join(" · ") }));
  return empty;
}
// ---------- what a page knows (#1836) ----------
// A mapped page is a template: every heading is there and most answers are
// "Unknown — not investigated yet". Shown as written, every page led with what
// the assistant does not know. Views read pages through known(): unknown lines
// are dropped, a heading left empty is named once at the end with the command
// that fills it, and lists rank by last contact instead of by the first
// character of an email address. An unknown answer written as a bare line
// (a mapped skill's sections) is dropped the same as one written as a bullet.
const UNKNOWN_LINE = /^\s*(?:[-*]\s*)?(?:[^:：\n]{1,40}[:：]\s*)?(?:unknown|not known|未知)(?:\s*(?:[—–(:.;。；-]|\[\d+\]).*)?\s*$/i;
// Sections every mapped page fills from metadata alone: they are not findings.
const MECHANICAL = new Set(["facts", "contact", "history", "uncertainties", "sources", "people here", "domains"]);
// What mapping writes where an answer will go (files.py): a placeholder, not a finding.
const PLACEHOLDER = /identity unverified|classification unassessed|^\s*[-*]\s*\(none yet\)\s*$/i;
const STAMP = /^Investigation:[^\n]*$/m;
// Markers the notebook's own tools leave in a page (<!-- rem-usage -->): not text.
const COMMENT = /<!--[\s\S]*?-->/g;
// A person page's lead as mapping writes it (files.py PERSON_LEAD, #1974): a slot, not a finding.
const UNFILLED_LEAD = /^(?:Unknown\s*—\s*not investigated yet\.?(?:\s*Last contact[:：]\s*Unknown\.?)?|未知\s*[—–-]+\s*尚未调查[。.]?)$/i;
const KNOWN = new Map();
function known(r) {
  const uiLang = typeof uiLanguage !== "undefined" ? uiLanguage : "en";
  const variant = (r.shown || "") + "\0" + (r.readLanguage ?? (uiLang === "en" ? (r.shown || "") : uiLang));
  let bucket = KNOWN.get(r.path);
  const cached = bucket?.[variant];
  if (cached && cached.text === r.text && cached.mail === r.mail && cached.last_activity === r.last_activity) return cached.value;
  const stamp = (STAMP.exec(r.text) || [""])[0];
  const body = (r.category === "sessions" ? r.text : splitTrailers(r.text).body.replace(COMMENT, ""))
    .replace(/^#[^\n]*\n?/, "").replace(STAMP, "");
  const title = r.title.trim().toLowerCase();
  const repeatsTitle = line => (/^\s*[-*]\s*[^:：\n]{1,40}[:：]\s*(.+)$/.exec(line) || [])[1]?.trim().toLowerCase() === title;
  const kept = [], missing = [];
  let intro = "";
  for (const part of body.split(/^(?=## )/m)) {
    const head = /^## ([^\n]*)\n?/.exec(part);
    // A mapped lead now carries the last contact (#2059): show that, not the placeholder before it.
    if (!head) { intro = UNFILLED_LEAD.test(part.trim()) ? "" : part.trim().replace(/^Unknown\s*—\s*not investigated yet\.\s*/i, ""); continue; }
    const text = r.category === "sessions" ? part.slice(head[0].length) : part.slice(head[0].length).split("\n").filter(line => {
      // Keep a specific missing outcome readable, without promoting it to a task.
      const explanation = /^\s*(?:[-*]\s*)?Unknown\s*[—:.()]\s*\S/i.test(line)
        && !UNFILLED_LINE.test(line.replace(/^\s*[-*]\s*/, ""));
      return (!UNKNOWN_LINE.test(line) || explanation) && !PLACEHOLDER.test(line) && !repeatsTitle(line);
    }).join("\n").trim();
    if (text) kept.push({ title: head[1].trim(), text });
    else if (!MECHANICAL.has(head[1].trim().toLowerCase())) missing.push(head[1].trim());
  }
  const learned = !!intro || kept.some(k => !MECHANICAL.has(k.title.toLowerCase()));
  // The page's own status line (files.py note_pass) says whether an
  // investigation pass ran; a page can still hold findings from before one.
  const investigated = /\binvestigated\b/.test(stamp.replace(/not investigated yet/, "")) || (!stamp && !missing.length);
  // Written or not is the census's answer (census.py), the one co rem status
  // counts with: a mapped skill's description or a project's paths read here
  // as findings, and "174 with findings" meant three written pages (#2008).
  const status = r.category === "sessions" ? "" : r.written === undefined ? (investigated ? "Investigated" : learned ? "Partly investigated" : "Mapped")
    : !r.written ? "Mapped" : investigated ? "Investigated" : "Partly investigated";
  // The page's own last activity (census.py), never the file's mtime: a map
  // rewrites every project page, and "Recently active" dated them all today.
  const mapLast = r.category === "people" ? (r.mail?.last || "") : "";
  const last = r.category === "skills" ? (skillUsage(r)?.last || "") : r.last_activity !== undefined ? (r.last_activity || mapLast)
    : (/\blast(?: contact)?[:：]\s*(\d{4}-\d{2}-\d{2})/i.exec(r.text) || [])[1] || mapLast || String(r.updated || "").slice(0, 10);
  const summary = r.category === "sessions" ? [parseFacts(r).get("Agent")?.[0]?.value, r.session_time,
    plainLine(parseFacts(r).get("Project")?.[0]?.value || "")].filter(Boolean).join(" · ")
    : plainLine((intro ? { text: intro } : kept.find(k => !MECHANICAL.has(k.title.toLowerCase())) || { text: "" }).text);
  const k = { intro, kept, missing, status, last, summary, stamp: stamp.replace(/^Investigation:\s*/, "") };
  if (!bucket) KNOWN.set(r.path, bucket = Object.create(null));
  bucket[variant] = { text: r.text, mail: r.mail, last_activity: r.last_activity, value: k };
  return k;
}
function mappedContact(r) { return r.category === "people" && r.path !== REM.owner && known(r).status === "Mapped" && !parseFacts(r).get("Last contact")?.length && !!(r.last_activity || r.mail?.last); }
// The first readable line of some Markdown, without its markup or claim numbers.
// Stored text names pages the way files do: [[orgs/acme-1a2b3c4d5e.md]], or a bare people/…-<hex>.md.
// The owner reads a page's name, never its file (#3318, the same class as #3286's review question).
// `link(path, name)` lets an HTML caller turn a page it knows into a link; text callers get the name.
function pageWords(text, link) {
  const pathOf = raw => String(raw).trim().replace(/^(?:\.\.?\/)+/, "");
  const record = path => typeof byPath === "function" ? byPath(pathOf(path)) : null;
  const words = path => pathOf(path).split("/").pop().replace(/\.md$/i, "").replace(/-[0-9a-f]{8,}$/i, "").replace(/[-_]+/g, " ").trim();
  // A link that names a coded course or team by its bare code says what it is (codedOrgName).
  const coded = (path, label) => { const r = record(path), name = typeof codedOrgName === "function" ? codedOrgName(r) : null;
    return name && (!label || label.trim() === r.title.trim()) ? name : null; };
  const name = (path, label) => coded(path, label) || (label && label.trim()) || record(path)?.title || words(path) || pathOf(path);
  const out = (path, label) => link ? link(record(path), name(path, label)) : name(path, label);
  return String(text ?? "")
    .replace(/\[\[\s*([^\]|#]+?)\s*(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]/g, (m, path, label) => out(path, label))
    .replace(/(?<![\w/.(\[-])((?:\.\.?\/)*(?:people|orgs|devices|projects|knowledge|skills|decisions|topics|tags)\/[\w.\/-]+?\.md)(?![\w/])/g,
      (m, path) => out(path));
}
function plainLine(text, keepPrivate = false) {
  const clean = String(keepPrivate ? text : unlabelled(text)).replace(/<\/?artifact-content-authored-by-others\s*\/?>/gi, "");
  const line = clean.split("\n").map(l => l.replace(/^\s*#+\s*/, "").replace(/^\s*(?:[-*]|\d+[.)])\s*/, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/\s*[\[［]W?\d{1,3}[\]］]/g, "").replace(/[*`>]/g, "").trim()).find(Boolean);
  return line ? youify(pageWords(line)) : "";
}
// Display only: parsers and claim comparisons keep the original marker words.
function displayLine(text) {
  const line = plainLine(text);
  return uiLanguage === "zh" ? line.replace(/\bUnknown\b/g, t("Unknown")) : line;
}
function summaryLine(text) {
  return displayLine(text).replace(/^(?:Now|Pattern|At stake|Changed|现在|规律|关键所在|变化|利害|模式)[:：]\s*/i, "");
}
function section(r, name) { return known(r).kept.find(s => s.title.toLowerCase() === name); }
function byActivity(a, b) {
  const auto = r => /\(automated candidate\)$/.test(r.title) ? 1 : 0;
  // Pages with findings before outlines: a mapped page's date is when the
  // mapper wrote it, which would otherwise outrank a real last contact.
  const rank = r => ({ "Investigated": 0, "Partly investigated": 1 })[known(r).status] ?? 2;
  return auto(a) - auto(b) || rank(a) - rank(b) || known(b).last.localeCompare(known(a).last) || a.title.localeCompare(b.title);
}
function statusPill(r) {
  if (r.category === "sessions") return null;
  const st = known(r).status;
  // A skill's research state ("Source reviewed", "Getting to know them") is nothing the owner can act on (sprint 13).
  if (st === "Investigated" || r.category === "skills") return null;
  const label = ({Mapped: "Getting to know them", "Partly investigated": "More to learn"})[st] || st;
  return el("span", { class: "pill status" + (st === "Mapped" ? " mapped" : ""), title: st === "Partly investigated" ? t("Some sections are filled from sources; the rest are not investigated yet.") : known(r).stamp || label }, [moon(st), t(label)]);
}

