// ---------- activity: what co rem did, run by run ----------
function pageLink(path) {
  return el("a", { href: "#r=" + encodeURIComponent(path), text: pageName(byPath(path)) || path });
}
// Pages a run looked at and did not write, each with the reason it gave.
function refusalReason(reason) {
  const fact = /^Fact without a citation: (.+); cite the message it came from, or write Unknown$/.exec(reason);
  if (fact) return t("Fact without a citation: {detail}; cite the message it came from, or write Unknown", { detail: fact[1] });
  const match = /^(Cited local file needs a file: source ID and SHA-256|[^:]+): (.+)$/.exec(reason);
  return match ? t(match[1] + ": {detail}", { detail: match[2] }) : t(reason);
}
function unwritten(run) {
  const refused = (run.refusals || []).map(x => ({ k: "Refused", page: x.record, why: (x.errors || []).map(refusalReason).join(uiLanguage === "zh" ? "；" : "; ") }));
  const skipped = (Array.isArray(run.pages) ? run.pages : []).filter(page => page.outcome && page.outcome !== "accepted")
    .map(page => ({ k: "Not written", page: page.page || page.record, why: page.why || page.outcome }));
  // The kept candidate's path is the runner's business, not the reason.
  return [...refused, ...skipped].map(x => ({ ...x, why: refusalReason(String(x.why).replace(/^Candidate rejected, kept at .*?: |^Not written: /, "")) }));
}
function runTrace(run) {
  const pages = run.pages?.length ? run.pages : [run];
  if (!pages.some(page => page.evidence?.length || page.report)) return null;
  const count = pages.reduce((total, page) => total + (page.evidence?.length || 0), 0);
  const trace = el("details", { class: "run-trace" }, [el("summary", { text: count ? t("{n} supplied items · inspection report", { n: count }) : t("Inspection report") })]);
  trace.addEventListener("toggle", () => {
    if (!trace.open || trace.dataset.loaded) return;
    trace.dataset.loaded = "true";
    for (const page of pages) {
      const record = page.page || page.record;
      if (record) trace.appendChild(el("h3", {}, [pageLink(record)]));
      if (page.report) trace.appendChild(el("pre", { text: t("Model's inspection report") + "\n" + page.report }));
      if (!page.evidence?.length) continue;
      trace.appendChild(el("h3", { text: t("Inputs supplied to this run (including context; not proof of inspection)") }));
      trace.appendChild(el("ul", {}, page.evidence.map(item => el("li", { text: [
        item.source, item.file || item.origin, item.timestamp && t("source: ") + item.timestamp,
        item.captured_at && t("captured: ") + item.captured_at,
        item.paths?.join(", ")].filter(Boolean).join(" · ") }))));
    }
  });
  return trace;
}
function runItem(run) {
  const outcome = String(run.outcome || ""), u = run.usage || {};
  const tone = /^(completed|pass)$/i.test(outcome) ? "" : FAILED.test(outcome) ? " warn" : " quiet";
  const li = el("li", { class: FAILED.test(outcome) ? "failed-run" : "" }, [
    el("div", { class: "run-head" }, [el("span", { class: "mono", text: fmtTime(run.started_at) }),
      el("span", { text: t(run.phase || "sync") }), el("span", { class: "pill" + tone, text: t(outcome) })]),
    el("div", { class: "run-meta mono", text: t("{n} read", { n: run.items || 0 }) + (u.input_tokens == null ? "" : " · " + t("{n} in / {m} out tokens", { n: num(u.input_tokens), m: num(u.output_tokens) })) })]);
  if ((run.changed || []).length) li.appendChild(el("div", { class: "run-pages" }, [el("span", { class: "k", text: t("Changed") }), ...run.changed.map(pageLink)]));
  for (const x of unwritten(run)) li.appendChild(el("div", { class: "run-pages" }, [el("span", { class: "k warn", text: t(x.k) }), pageLink(x.page), el("span", { class: "why", text: x.why })]));
  const trace = runTrace(run);
  if (trace) li.appendChild(trace);
  return li;
}
function activityShelf(title, records) {
  if (!records.length) return null;
  return el("details", { class: "activity-shelf" }, [el("summary", { text: t(title) + " · " + records.length }),
    el("ul", { class: "hits" }, records.sort(byActivity).map(r => row(r)))]);
}
function activityView() {
  const main = document.getElementById("main");
  main.textContent = "";
  main.appendChild(el("div", { class: "mobile-back" }, [el("a", { href: "#" }, ["← " + t("Contents")])]));
  main.appendChild(el("div", { class: "eyebrow", text: t("Activity") }));
  main.appendChild(el("h1", { text: t("Activity") }));
  main.appendChild(el("p", { class: "lede", text: t("What co rem did on each run: what it read, the pages it changed, and the ones it would not write.") }));
  main.appendChild(nightBand(false));
  const runs = REM.logs || [];
  main.appendChild(sectionHead("Runs", runs.length ? t("latest {n}", { n: runs.length }) : t("none yet")));
  main.appendChild(runs.length ? el("ol", { class: "activity-runs" }, runs.map(runItem))
    : el("p", { class: "quiet-line", text: t(REM.status?.worker?.enabled ? "No runs yet — queued for tonight" : "No runs yet — background updates off") }));
  const notes = activityShelf("AI notes", REM.records.filter(r => r.category === "notes"));
  if (notes) main.appendChild(notes);
  const maps = activityShelf("Maps", REM.records.filter(r => r.category === "logs" && !skillReport(r)));
  if (maps) main.appendChild(maps);
}

function shellArg(value) { return "'" + String(value).replace(/'/g, "'\\''") + "'"; }
// ---------- 不是人 / 是人 (rc35 check): the owner's word on who is a person ----------
// An assistant that mails from its company's domain led People. The night already moves one out when its company's
// page names it as the assistant (census.assistant_contact); the owner's one click settles the rest. The mark is
// one dated line per address in the notebook's state (threads.mark_person), which the night reads too, and Undo
// or 是人 in the agents and services group takes it back.
Object.assign(UI.zh, { "Not a person": "不是人", "A person": "是人", "Moved out of People · {name}": "已移出人物 · {name}",
  "Back in People · {name}": "已回到人物 · {name}", "{n} agents and services found in mail": "邮件里的 {n} 个助理和服务",
  "Assistants, bots and services: their company's page says so, or you said so. They stay out of People.": "助理、机器人和服务：公司页面这么写，或者你这么说过。它们不进人物。",
  "Not a person: an assistant, a bot or a service": "不是人：是助理、机器人或服务",
  "This person": "这个人", "Put them back in People": "放回人物里", "An assistant, a bot or a service": "是助理、机器人或服务" });
function recordEmails(r) {
  return [...new Set((String(facts(r).email || "").match(/[\w.+-]+@[\w-]+\.[\w.-]+/g) || []).map(address => address.toLowerCase()))];
}
// What 不是人 marks: the page's addresses, or on a page with none (WeChat only) the chat handles on its Handles
// line, the same rule the census reads (#3339). Never names: Also known as holds names too.
function recordMarkHandles(r) {
  const emails = recordEmails(r);
  if (emails.length) return emails;
  // facts() keeps a fixed set of fields; the Handles line is read from the parsed facts themselves.
  const line = [...parseFacts(r)].find(([label]) => label.toLowerCase() === "handles");
  const value = line ? line[1].map(item => item.value).join(", ") : "";
  return [...new Set(value.replace(/\s*\[[^\]]*\]/g, "").split(/[,;]\s*/).map(h => h.trim().toLowerCase())
    .filter(h => /^[a-z][a-z0-9_-]{4,63}$/.test(h)))];
}
async function savePersonMark(addresses, person) {
  for (const address of addresses) {
    const reply = await hostPost("/rem/person", { address, person });
    if (!reply.ok) return false;
    REM.person_marks = reply.marks || {};
  }
  return true;
}
function personMarkNotice(words, undo) {
  document.getElementById("done-notice")?.remove();
  const button = el("button", { type: "button", text: t("Undo") });
  button.onclick = undo;
  document.body.appendChild(el("div", { id: "done-notice", class: "done-notice", role: "status" }, [words, " · ", button, " · ", t("Saved in notebook")]));
  button.focus({ preventScroll: true });
}
// The page's WeChat ids (wxid_… or a WeCom …@openim, or a bare handle on a WeChat page), for ⋯ → 复制微信号 (#3372).
function wechatIds(r) {
  if (!r || r.category !== "people") return [];
  const line = [...parseFacts(r)].find(([label]) => label.toLowerCase() === "handles");
  // One Handles line may hold several, comma separated, with their privacy marks; split as recordMarkHandles does.
  const values = (line ? line[1].map(item => plainLine(item.value)).join(", ") : "").replace(/\s*\[[^\]]*\]/g, "")
    .split(/[,;]\s*/).map(h => h.trim()).filter(Boolean);
  return values.filter(h => /^wxid_|@openim$/i.test(h) || (wechatPage(r) && h && !/@/.test(h)));
}
// One part of a Handles or Also known as value that is a WeChat id: wxid_…, a WeCom …@openim, or on a WeChat page
// a bare handle. Every card that shows a person's handles or aliases drops it (#3372: the fallback facts card of a
// friend who knows no fact yet printed it twice on 1,009 pages, after #3374 had cleaned the profile card only).
function wechatIdPart(r, part) {
  const value = plainLine(String(part ?? "")).replace(/\s*\[[^\]]*\]/g, "").trim();
  return !!value && (/^wxid_|@openim$/i.test(value) || (wechatPage(r) && !/@/.test(value)));
}
// A Handles or Also known as item without its WeChat-id parts; null when nothing readable is left. An alias is a
// name and may be one bare word, so there only the page's own ids go, never every bare word.
function withoutWechatIds(r, item, label) {
  const ids = label === "Also known as" ? new Set(wechatIds(r).map(id => id.toLowerCase())) : null;
  const drop = part => ids ? ids.has(plainLine(part).replace(/\s*\[[^\]]*\]/g, "").trim().toLowerCase())
    || /^wxid_|@openim$/i.test(plainLine(part).trim()) : wechatIdPart(r, part);
  const parts = String(item.value).split(/,\s*/).filter(part => part.trim() && !drop(part));
  return parts.length ? { ...item, value: parts.join(", ") } : null;
}
function wechatCopyItem(r, close) {
  const ids = wechatIds(r);
  if (!ids.length) return null;
  const item = el("button", { type: "button", role: "menuitem", class: "copy-wechat" }, [t("Copy WeChat ID")]);
  item.onclick = async () => {
    try { await navigator.clipboard.writeText(ids[0]); } catch (error) { console.warn("clipboard", error); }
    close?.();
    document.getElementById("done-notice")?.remove();
    const notice = el("div", { id: "done-notice", class: "done-notice", role: "status", text: t("WeChat ID copied") });
    document.body.appendChild(notice);
    setTimeout(() => notice.remove(), 2500);
  };
  return item;
}
// The header ⋯ item on every person page (mail, WeChat only, both): 不是人, or 是人 once the page is set aside.
// Same mark, same notice and Undo as the row button in People.
function personMarkItem(r, close) {
  const addresses = r && r.category === "people" ? recordMarkHandles(r) : [];
  if (!liveHere() || !addresses.length || r.path === REM.owner) return null;
  const aside = !!r.service;
  const item = el("button", { type: "button", role: "menuitem", class: "person-mark", "data-mark": aside ? "person" : "not-person" },
    [t(aside ? "A person" : "Not a person"), el("small", { text: t(aside ? "Put them back in People" : "An assistant, a bot or a service") })]);
  item.onclick = async () => {
    item.disabled = true;
    if (!await savePersonMark(addresses, aside)) { item.disabled = false; return notSavedNotice(() => item.click(), null); }
    r.service_rule ??= !!r.service;
    r.service = !aside;
    close?.();
    render();
    personMarkNotice(t(aside ? "Back in People · {name}" : "Moved out of People · {name}", { name: r.title }), async () => {
      if (!await savePersonMark(addresses, null)) return notSavedNotice(() => {}, null);
      r.service = r.service_rule;
      document.getElementById("done-notice")?.remove();
      render();
    });
  };
  return item;
}
function notPersonButton(r, compact = false) {
  const addresses = recordMarkHandles(r);
  if (!liveHere() || !addresses.length || r.path === REM.owner) return null;
  const button = el("button", { type: "button", class: "not-person" + (compact ? " compact" : ""), title: t("Not a person: an assistant, a bot or a service"), text: t("Not a person") });
  const out = async () => {
    button.disabled = true;
    if (!await savePersonMark(addresses, false)) { button.disabled = false; return notSavedNotice(retryReplacing(out), null); }
    r.service_rule ??= !!r.service;
    r.service = true;
    render();
    personMarkNotice(t("Moved out of People · {name}", { name: r.title }), async () => {
      if (!await savePersonMark(addresses, null)) return notSavedNotice(() => {}, null);
      r.service = r.service_rule;
      document.getElementById("done-notice")?.remove();
      render();
    });
  };
  button.onclick = event => { event.stopPropagation(); out(); };
  return button;
}
// Where an assistant or service waits: a folded group under People, each with 是人 to bring it back.
function machineDirectory() {
  const marks = REM.person_marks || {};
  const pages = REM.records.filter(r => r.category === "people" && r.service && (r.agent || recordMarkHandles(r).some(address => marks[address] === "not-person")));
  const contacts = (REM.contact_candidates || []).filter(row => row.machine);
  if (!pages.length && !contacts.length) return null;
  const back = (row, addresses, done, undone) => {
    if (!liveHere()) return el("span");
    const button = el("button", { type: "button", class: "is-person", text: t("A person") });
    button.onclick = async () => {
      button.disabled = true;
      if (!await savePersonMark(addresses, true)) { button.disabled = false; return notSavedNotice(() => button.click(), null); }
      done();
      render();
      personMarkNotice(t("Back in People · {name}", { name: row }), async () => {
        if (!await savePersonMark(addresses, null)) return notSavedNotice(() => {}, null);
        undone();
        document.getElementById("done-notice")?.remove();
        render();
      });
    };
    return button;
  };
  const rows = [...pages.map(r => el("tr", {}, [el("td", {}, [el("a", { href: href(r), text: r.title })]), el("td", { text: recordMarkHandles(r).join(", ") }),
      el("td", {}, [back(r.title, recordMarkHandles(r), () => { r.service = false; }, () => { r.service = true; })])])),
    ...contacts.map(row => el("tr", {}, [el("td", { text: row.name || row.email }), el("td", { text: row.email }),
      el("td", {}, [back(row.name || row.email, [row.email.toLowerCase()], () => { row.machine = false; }, () => { row.machine = true; })])]))];
  return el("details", { class: "contact-directory machine-directory" }, [
    el("summary", { text: t("{n} agents and services found in mail", { n: rows.length }) }),
    el("div", { class: "directory-body" }, [el("p", { class: "directory-note", text: t("Assistants, bots and services: their company's page says so, or you said so. They stay out of People.") }),
      el("div", { class: "directory-scroll" }, [el("table", {}, [el("tbody", {}, rows)])])])]);
}
function contactDirectory() {
  const candidates = (REM.contact_candidates || []).filter(row => !row.machine);
  const coverage = REM.contact_coverage || {};
  if (!candidates.length && !coverage.incomplete) return null;
  const details = el("details", { class: "contact-directory" });
  details.appendChild(el("summary", { text: t("Others seen in mail · {n}", { n: candidates.length }) }));
  const body = el("div", { class: "directory-body" });
  body.appendChild(el("p", { class: "directory-note", text:
    t("Found in {scope}. These headers have not established a person or a memory page. Search here before deciding whom REM should investigate.", { scope: t(coverage.scope || "mail") }) }));
  if (coverage.incomplete) body.appendChild(el("p", { class: "directory-note warn", text:
    t("Coverage is incomplete: {n} mailbox scan error(s). Retry init before treating this as every contact.", { n: coverage.mailbox_errors }) }));
  const find = el("input", { type: "search", class: "directory-find", "aria-label": t("Search other contacts"), placeholder: t("Find a name or email…") });
  const count = el("span", { class: "mono", "aria-live": "polite" });
  const table = el("table");
  table.appendChild(el("thead", {}, [el("tr", {}, ["Name", "Email", "Last contact", "Mails", "Memory"].map(name => el("th", { scope: "col", text: t(name) })))]));
  const tbody = el("tbody"); table.appendChild(tbody);
  const scroller = el("div", { class: "directory-scroll", role: "region", tabindex: "0", "aria-label": t("Other contacts table") }, [table]);
  const more = el("button", { type: "button", class: "directory-more", text: t("Show more contacts") });
  let limit = 100;
  const draw = () => {
    const needle = find.value.trim().toLowerCase();
    const matched = candidates.filter(row => !needle || (row.name + " " + row.email).toLowerCase().includes(needle));
    tbody.textContent = "";
    for (const row of matched.slice(0, limit)) {
      const name = row.name || row.email;
      tbody.appendChild(el("tr", {}, [
        el("td", { class: "candidate-name", text: name }),
        el("td", {}, [el("a", { class: "candidate-email", href: "mailto:" + row.email, text: row.email })]),
        el("td", { text: row.last ? shortDate(row.last) : "—" }),
        el("td", { text: String(row.mails) }), el("td", { text: t("No memory yet") })]));
    }
    body.querySelector(".empty")?.remove();
    scroller.hidden = !matched.length;
    if (!matched.length) body.appendChild(emptyState("No contact matches this search.", "Clear filters →", "#c=people", () => {
      find.value = ""; limit = 100; draw(); find.focus();
    }));
    count.textContent = t(" · {n} found", { n: matched.length });
    more.hidden = matched.length <= limit;
  };
  find.addEventListener("input", () => { limit = 100; draw(); });
  more.onclick = () => { limit += 100; draw(); };
  body.append(find, count, scroller, more);
  details.appendChild(body); draw();
  return details;
}

// ---------- People and a person: rows, one next step (round 4) ----------
// The person page leads with what is owed and the one thing to do next; the
const PEN_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>';
let notDoneKeys = new Set();
function face(name, size = "") {
  const words = name.replace(/\(.*?\)/g, "").replace(/[^\p{L}\p{N} ]/gu, " ").trim().split(/\s+/).filter(Boolean);
  const first = words[0] || "?";
  const initials = /\p{Script=Han}/u.test(first) ? first[0] : (words.length > 1 ? first[0] + words.at(-1)[0] : first.slice(0, 2)).toUpperCase();
  // One grey for every face: a hue per name was a colour the sheet does not have.
  return el("span", { class: "face" + (size ? " " + size : ""), "aria-hidden": "true", text: initials });
}
function firstName(r) { return r.title.replace(/\(.*?\)/g, "").trim().split(/\s+/)[0]; }
function notDoneStorageKey() { return "co-rem-not-done:" + shortHash(REM.root || ""); }
function queuedReply(entry) { return (REM.today_queue || []).find(row => (row.keys || [row.key]).includes(doneKey(entry)))?.reply; }
function overdueDays(thread) { return thread.due && thread.due < calendarDay(REM.as_of) ? daysSince(thread.due) : 0; }
// A promise whose date passed more than 60 days ago, with no message on its thread for 60 days either, is
// almost always done or dropped, not burning: on real data a months-old promise led Today in red. It
// leaves the count and the red, and Today asks "still open?" instead. 60 is the span after which an undated
// thread goes quiet (today.py), so a dated one gets no less patience. A promise with no dated message at all stays
// live: nothing says the thread went silent. The owner's "still open" is kept on this device with its day
// (keptOpen) and holds for another 60 days, then Today asks again.
const STALE_DAYS = 60;
let keptOpen = {};
function keptOpenStorageKey() { return "co-rem-kept-open:" + shortHash(REM.root || ""); }
function stalePromise(due, since) {
  return !!due && !!since && due < calendarDay(REM.as_of) && daysSince(due) > STALE_DAYS && daysSince(since) > STALE_DAYS;
}
function staleEntry(entry) {
  const kept = keptOpen[doneKey(entry)];
  return !entry.t.returnedAt && !(kept && daysSince(kept) <= STALE_DAYS) && stalePromise(entry.t.due, entry.t.since);
}
function keepStale(entry) {
  keptOpen[doneKey(entry)] = calendarDay(REM.as_of);
  readerStorage(keptOpenStorageKey(), JSON.stringify(keptOpen));
  const scroll = window.scrollY;
  render();
  window.scrollTo(0, scroll);
}
// Your later mail looks like it settled the ask; an overdue promise is never settled by it.
function looksDone(entry) {
  return entry.t.dir === "mine" && !overdueDays(entry.t) && queuedReply(entry)?.state === "replied" && !notDoneKeys.has(doneKey(entry));
}
// The merged queue first; a thread on the page that the queue has not projected yet still shows.
// Today's entries by the person they name, rebuilt only when Today's list is: People asks for every person at once.
function entriesFor(path) {
  const list = threadEntries();
  if (entriesFor.source !== list) {
    entriesFor.source = list;
    entriesFor.index = new Map();
    for (const entry of list) {
      if (entry.t.dir === "third") continue;
      for (const at of new Set([entry.r.path, ...(entry.also || []).map(other => other.path)])) {
        if (!entriesFor.index.has(at)) entriesFor.index.set(at, []);
        entriesFor.index.get(at).push(entry);
      }
    }
  }
  return entriesFor.index.get(path) || [];
}
// The page's own threads can be passed in when they are already parsed (facts(r).open is threads(r).items).
function personEntries(r, items = threads(r).items) {
  const entries = entriesFor(r.path);
  const listed = new Set(entries.flatMap(entry => (entry.members || [entry]).map(doneKey)));
  const own = items.filter(thread => thread.dir !== "third").map(thread => ({ r, t: thread })).filter(entry => !listed.has(doneKey(entry)));
  return [...entries, ...own];
}
function byUrgency(a, b) {
  return (a.t.due || "9999").localeCompare(b.t.due || "9999") || (a.t.since || "").localeCompare(b.t.since || "");
}
// "You owe Alyssa feedback on the demo — “I'll watch…” (date) [18]" -> a title and its evidence.
function owedParts(entry) {
  const text = unlabelled(entry.t.text).replaceAll("**", "");
  const quote = /“([^”]{4,})”|"([^"]{4,})"|「([^」]{4,})」/.exec(text);
  const [head, ...rest] = text.split(/\s+[—–]\s+|\s*[“"「]/);
  const clean = words => withoutDateClutter(plainLine(words), entry.t).replace(/[:：;,，\s]+$/, "");
  const after = quote ? "" : clean(rest.join(" — "));
  return { head: capFirst(clean(head)), quote: quote ? (quote[1] || quote[2] || quote[3]).trim() : "", rest: /[\p{L}\p{N}]/u.test(after) ? after : "" };
}
function replyDuration(seconds) {
  return seconds < 3600 ? t("{n} min", { n: Math.max(1, Math.round(seconds / 60)) })
    : seconds < 48 * 3600 ? t("{n} hours", { n: Math.round(seconds / 3600) }) : t("{n} days", { n: Math.round(seconds / 86400) });
}
function personOrg(r) {
  const cache = r?.path ? (personOrg._cache ??= new Map()) : null;
  const uiLang = typeof uiLanguage !== "undefined" ? uiLanguage : "en";
  const effLang = r?.readLanguage ?? (uiLang === "en" ? (r?.shown || "") : uiLang);
  const cacheKey = cache ? r.path + "\0" + (r.shown || "") + "\0" + effLang + "\0" + (r.text?.length || 0) : "";
  if (cache?.has(cacheKey)) return cache.get(cacheKey);
  const company = String(facts(r).company || "");
  // The page's own words name the organisation (they follow the reading language); the link finds its page.
  const link = /\[([^\]]+)\]\((\.\.\/orgs\/[^)]+\.md)\)/.exec(company);
  const wiki = /\[\[(orgs\/[^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/.exec(company);
  const path = link ? link[2].replace(/^\.\.\//, "") : wiki ? wiki[1].replace(/(?:\.md)?$/, ".md") : r.organisations?.[0];
  const org = path ? byPath(path) : null;
  const full = link ? plainLine(link[1]) : wiki ? plainLine(wiki[2] || org?.title || wiki[1])
    : plainLine(company).replace(/\s*\(from email domain\)$/i, "") || org?.title || "";
  const acronym = /^(.+?)\s*\(([\p{Lu}&]{2,8})\)$/u.exec(full);
  const resolved = knownValue(full) ? orgNamed(r, org, acronym ? acronym[2] : full, acronym ? acronym[1] : "") : null;
  if (cache) cache.set(cacheKey, resolved);
  return resolved;
}
// What People's organisation column and the open list's place chips call a person's organisation (rc35 hunt,
// #3157: a course-group code, two university domains, and one company as both a short and a full name).
function orgNamed(r, org, label, full) {
  const domain = /^(?:[a-z0-9-]+\.)+[a-z]{2,}$/i, title = org?.title.trim() || "";
  const name = label.replace(/\s*[（(][^()（）]*[)）]\s*$/, "") || label;
  // An internal code (digits, capitals and dashes, no space: a course group, a ticket) is never an organisation.
  if (/^(?=\S*\d)[A-Z0-9]+(?:-[A-Z0-9]+)+$/.test(name.trim())) return null;
  if (codedOrgName(org)) return { org, name: orgName(org), full: label };
  // A page linked under a longer label ("Harbour Uni Founders" → Harbour Uni) or under its domain goes by its own name.
  if (org && !domain.test(title) && (domain.test(name) || startsWords(name, title)))
    return { org, name: orgName(org), full: label === orgName(org) ? full : label };
  if (!org) {
    const matches = inCategory("orgs").filter(page => sameCompany(r, page, name));
    if (matches.length === 1) return { org: matches[0], name: orgName(matches[0]), full: label };
  }
  return domain.test(name) ? { org, name: domainName(name), full: label } : { org, name: label, full };
}
// A domain reads as a name, the domain itself kept for the tooltip: "harbour.edu.au" → Harbour, "fernhill.example" → Fernhill.
function domainName(domain) {
  const parts = domain.toLowerCase().split("."), label = parts[0] === "www" ? parts[1] : parts[0];
  return parts.some(part => part === "edu" || part === "ac") && label.length <= 5 ? label.toUpperCase() : label[0].toUpperCase() + label.slice(1);
}
function startsWords(long, short) {
  return long.toLowerCase().startsWith(short.toLowerCase() + " ");
}
function personDomain(r) {
  return (String(facts(r).email).match(/@([\w.-]+\.[a-z]{2,})/i) || [])[1]?.toLowerCase() || "";
}
// One company, one name: a short name and a full one ("Acme" / "Acme Fine Foods") are one organisation when one begins
// the other and the page's domain (or its name run together) is the person's mail domain.
function sameCompany(r, org, name) {
  const title = org.title.trim();
  if (/^(?:[a-z0-9-]+\.)+[a-z]{2,}$/i.test(title) || !(startsWords(title, name) || startsWords(name, title))) return false;
  const domain = personDomain(r), domains = (rawSection(org, "Domains") || "").toLowerCase();
  return !!domain && (domains.includes(domain) || domain.split(".")[0] === title.toLowerCase().replace(/[^a-z0-9]/g, ""));
}
function personProject(r) {
  const link = /\]\((?:\.\.\/)?(projects\/[^)]+\.md)\)/.exec(known(r).intro + "\n" + r.text);
  return link && byPath(link[1]);
}
// The lede names the first role as a title: its value and any qualifier that is part of the title
// ("Events Coordinator (Entrepreneurship)"); provenance ("email signature through …") stays in the tooltip.
function roleLede(items, full, from) {
  if (hasPrivacy(full)) return roleSummary(full, from);
  // Only notes on where the value came from leave the lede; when a role started or ended ("until 2025-06", "former") stays.
  // In any language the page is read in (owner, 2026-11-18: "截至 2026-10-29 的 email 签名" sat under the name).
  const provenance = /\b(?:signature|observed|according to|unverified|inferred|as of|per\s|e-?mail|from (?:mail|domain|metadata))\b|签名|截至|据|来自|^见|观察|推断|未核实|元数据|名录|邮件/i;
  const first = items[0], kept = topLevelParts(first.qualifier || "").filter(part => !provenance.test(part));
  const title = labelWord(first.value) + (kept.length ? " (" + kept.join("; ") + ")" : "");
  return el("span", { title: labelWord(plainLine(full)) }, [el("span", { html: inline(title, from) }),
    items.length > 1 ? el("span", { class: "role-more", text: " +" + (items.length - 1) }) : null]);
}
// A display name says which script it is in, so the browser hyphenates Latin names at its own syllables
// and wraps CJK names between characters.
function nameLang(text) { return /\p{Script=Han}|\p{Script=Hiragana}|\p{Script=Katakana}|\p{Script=Hangul}/u.test(text) ? "zh" : /\p{Script=Latin}/u.test(text) ? "en" : ""; }
// Where the browser has no hyphenation dictionary, a word wider than the screen would push the page sideways.
// Then, and only then, it gets soft hyphens at likely syllable joins (VCV -> V-CV, VCCV -> VC-CV, three consonants split before an onset like "st", digraphs kept).
function softSyllables(word) {
  // "Ostrowski-Berryweather2026": each run of letters gets its own syllables; the hyphen and digits stay as they are.
  if (/[^\p{L}]/u.test(word)) return word.split(/([^\p{L}]+)/u).map((part, i) => i % 2 ? part : softSyllables(part)).join("");
  const vowel = ch => /[aeiouyàáâäãåèéêëìíîïòóôöõùúûüýÿ]/i.test(ch), out = [...word];
  if (out.length < 7 || !/^\p{Script=Latin}+$/u.test(word)) return word;
  const cuts = [];
  for (let i = 1; i < out.length; i++) {
    if (!vowel(out[i - 1])) continue;
    let j = i; while (j < out.length && !vowel(out[j])) j++;
    if (j === i || j >= out.length) continue;
    const digraph = j - i >= 2 && /^(?:ch|sh|th|ph|wh|gh|ck)$/i.test(out[i] + out[i + 1]);
    const onset = j - i >= 3 && /^(?:bl|br|cl|cr|dr|fl|fr|gl|gr|pl|pr|sc|sk|sl|sm|sn|sp|st|sw|tr|tw|wr|kn)$/i.test(out[j - 2] + out[j - 1]);
    const at = j - i === 1 ? i : digraph ? (j - i === 2 ? i : i + 2) : j - i === 2 ? i + 1 : onset ? j - 2 : j - 1;
    if (at >= 2 && out.length - at >= 3) cuts.push(at);
    i = j - 1;
  }
  return out.map((ch, i) => (cuts.includes(i) ? "\u00ad" : "") + ch).join("");
}
function fitNames() {
  for (const node of document.querySelectorAll("#main .r4-name, #main .ov-say h1.ov-name")) {
    const name = node.dataset.name || (node.dataset.name = node.textContent);
    node.textContent = name;
    // Measured without the break-word fallback, which would otherwise hide the overflow it is there to catch.
    node.classList.add("name-measure");
    const overflows = node.scrollWidth > node.clientWidth + 1;
    node.classList.remove("name-measure");
    if (overflows) node.textContent = name.split(/(\s+)/).map(softSyllables).join("");
  }
}
// Who: the name is the page's one display element, in a hero card with their face (a fuse ring when what you
// owe them is overdue), what they are in one line, the one quiet link to Today, and under them the profile card.
function personHead(r) {
  // The same fuse as their face on Today: the days overdue on their card there.
  const group = todayGroups(threadEntries().filter(entry => !isDone(entry))).find(group => group.r.path === r.path);
  const late = group ? groupLate(group) : 0;
  // Sprint 23 (owner, 2026-11-19: «人物页面的第一个卡片很丑»): one header of three lines (name, who they are,
  // where and how recent), one fixed action column on the right (调查, then the page's translation state), and
  // the facts under one hairline as single-line rows. Nothing else floats in the header.
  return el("header", { class: "r4-head person-head hero" }, [
    // The crumb starts the page's one left edge (#3131), above the face, as on every reading page.
    el("a", { class: "page-crumb", href: categoryHref("people"), text: categoryName("people") }),
    el("div", { class: "hero-top" }, [fusedFace(r, late, "xl"),
      el("div", { class: "hero-who" }, [
        el("div", { class: "hero-marks" }, [updatedMarker(r, true)]),
        el("h1", { class: "r4-name", lang: nameLang(r.title), "aria-label": r.title, text: r.title }), personSub(r), personMeta(r, late), chatPreview(r),
        pageTagRow(r, personSaid(r))]),
      el("div", { class: "hero-acts" }, [recordActs(r)])]),
    profileCard(r)]);
}
// What the person head already names (organisation, its full name, their units): the tag row and the card skip these.
function personSaid(r) {
  const org = personOrg(r);
  return [org?.name, org?.full, org?.org?.path, org?.org?.title, ...(r.units || []).flatMap(edge => [edge.path, byPath(edge.path)?.title])].filter(Boolean);
}
// A link said once: the same profile as a handle and as a link, with or without https://www. and a trailing slash.
function urlKey(text) { return plainLine(text).toLowerCase().replace(/\s*\([^)]*\)\s*$/, "").replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/[?#].*$/, "").replace(/\/+$/, ""); }
// The third header line: where they are, how recent, how much mail, and Today when something waits there.
// These facts are said here, so the card below does not repeat them.
function personMeta(r, late) {
  const parsed = parseFacts(r), have = label => (parsed.has(label) ? parsed.get(label) : legacyFact(r, label)).filter(item => knownValue(item.value));
  const place = have("Location")[0], last = have("Last contact")[0];
  const lastValue = last ? plainLine(oneDate(last).value) : "";
  let lastText = /^\d{4}-\d{2}-\d{2}$/.test(lastValue) ? fmtDate(lastValue) : lastValue || (mappedContact(r) && known(r).last ? fmtDate(known(r).last) : "");
  // WeChat says what the night knows for free (#3346): when you last chatted and how much lately, or that there is
  // nothing to read yet for an address-book friend.
  const chat = chatActivity(r);
  if (chat && calendarDay(chat.last) >= (isoDay(lastValue) || "")) lastText = fmtDate(calendarDay(chat.last));
  // Who wrote last and since when: what the chats say before any model reads them (#3372).
  // The earliest date is one unbroken span: at 390 it must not wrap as "2024 / 年3月5日".
  const wechat = chat ? el("span", {}, [t("WeChat · {n} messages in 90 days", { n: chat.n90 || 0 }),
    chat.first ? " · " : "", chat.first ? el("span", { class: "hero-date", text: t("chatting since {when}", { when: fmtDate(calendarDay(chat.first)) }) }) : null])
    : restingFriends().has(r.path) ? el("span", { text: t("WeChat friend · no chats yet") }) : null;
  // The place keeps its privacy mark, so a [personal] location hides with the others (the facts panel that used to
  // guard it is gone from person pages, #3131).
  const parts = [place ? el("span", { class: "hero-place", html: inline(place.value, r.path) }) : null,
    lastText ? el("span", { text: t("Last contact {when}", { when: lastText }) }) : null,
    r.mail?.mails ? el("span", { title: t("{n} · {received} in, {sent} out", { n: r.mail.mails, received: r.mail.received, sent: r.mail.sent }),
      text: t(r.mail.mails === 1 ? "1 mail" : "{n} mails", { n: r.mail.mails }) }) : null,
    wechat, personTodayLink(r, late)].filter(Boolean);
  return parts.length ? el("p", { class: "hero-meta" }, parts) : null;
}
// The last thing said on WeChat, one line under the header (#3372). It is a chat message, so it is [sensitive]:
// covered at this computer's default level, readable at 全部显示, gone at 只看公开.
function chatPreview(r) {
  const chat = chatActivity(r);
  if (!chat?.preview) return null;
  const who = chat.mine === true ? "You said last:" : chat.mine === false ? "They said last:" : "Last message:";
  // Marked by its level, not by a "[sensitive]" marker in the text, so no chip ever prints beside it.
  return privateFallback(el("p", { class: "hero-preview" }, [el("span", { class: "hero-preview-k", text: t(who) + " " }),
    el("span", { class: "private", "data-level": "sensitive", text: chat.preview })]));
}
// Who they are in one line of words: role, organisation (→ its page) and units (→ theirs). These are said here
// and nowhere else in the header (owner, 2026-11-18: one place per fact); where a value came from stays in its title.
function personSub(r) {
  const role = String(facts(r).role || ""), items = (parseFacts(r).get("Role") || []).filter(item => knownValue(item.value));
  const org = personOrg(r);
  const domain = org?.org ? plainLine(String(facts(org.org).domain || "")).replace(/^https?:\/\/|\/$/g, "") : "";
  const units = (r.units || []).map(edge => ({ edge, unit: byPath(edge.path) })).filter(({ unit }) => unit && !orgHidden(unit));
  const mark = () => el("span", { class: "org-mark", "aria-hidden": "true", text: org.name.trim()[0].toUpperCase() });
  // An English role in a Chinese reader is the page's words, shown as its original (#3410: 「team member」).
  const lede = () => englishProse(labelWord(role)) ? originalQuote(roleLede(items, role, r.path)) : roleLede(items, role, r.path);
  const parts = [knownValue(role) && items.length ? changedValue(el("span", { class: "dek-role" }, [lede()]), r, "Role") : null,
    org ? changedValue(org.org ? el("a", { class: "dek-org", href: href(org.org), title: [org.full, knownValue(domain) ? domain : ""].filter(Boolean).join(" · ") }, [mark(), org.name])
      : el("span", { class: "dek-org" }, [mark(), org.name]), r, "Company") : null,
    ...units.map(({ edge, unit }) => el("a", { class: "dek-unit", href: href(unit), text: orgName(unit) + (edge.role ? " · " + unlabelled(edge.role) : "") }))].filter(Boolean);
  return parts.length ? privateFallback(el("div", { class: "r4-sub dek" }, parts)) : null;
}
// The profile card (owner, 2026-11-18: "shouldn't the profile card be the first thing shown?"): every known fact
// as a label over its value, right under the name, nothing to expand. Role, organisation and units are the line
// above it, so it does not repeat them; unknown facts are one quiet count, never rows of "not found".
const PROFILE_GROUPS = [["Contact", ["Email", "Their agent", "Phone", "Handles", "Links"]], ["Work", ["Signing entity", "Unit", "Role in unit", "Project"]],
  ["Relationship", ["How we know them", "First contact", "Last contact", "Mail"]], ["Identity", ["Also known as", "Language", "Location", "Time zone"]]];
Object.assign(UI.zh, { "Their agent": "对方的 agent", "Name unknown": "未知姓名", "Only the email is known": "只知道邮箱", "Source {n}": "来源 {n}", "Open the original": "打开原文", "Work": "工作", "Relationship": "关系", "Identity": "身份", "Unit": "部门", "Role in unit": "部门职务",
  "1 fact not found": "1 项未找到", "{n} facts not found": "{n} 项未找到", "from the map": "来自映射",
  "Last contact {when}": "最近联系 {when}", "1 mail": "1 封邮件", "{n} mails": "{n} 封邮件", "+{n} more": "还有 {n} 个", "Show less": "收起" });
// A handle or link says its platform in words; its picture is that service's published mark (Simple Icons) or,
// where the set publishes none (LinkedIn, Slack, Teams), an @. [test, picture, name].
const HANDLE_MARKS = [
  [/github/i, "brand-github", "GitHub"],
  [/^(?:x|twitter)$|twitter\.com|\bx\.com\//i, "brand-x", "X"],
  [/wechat|weixin|微信/i, "brand-wechat", "WeChat"],
  [/whatsapp|\bwa\.me\//i, "brand-whatsapp", "WhatsApp"],
  [/telegram|\bt\.me\//i, "brand-telegram", "Telegram"],
  [/discord/i, "brand-discord", "Discord"],
  [/linkedin/i, "at", "LinkedIn"],
  [/slack/i, "at", "Slack"],
  [/\bteams\b/i, "at", "Microsoft Teams"],
];
function handleMark(handle) {
  const found = HANDLE_MARKS.find(([test]) => test.test(handle.qualifier || "") || test.test(handle.value));
  return found ? [found[1], found[2]] : ["at", null];
}
// [the platform's name, its picture] for a profile-card row, or the fallback when no service is named.
function contactPlace(item, fallback) {
  const [picture, name] = handleMark(item);
  return name ? [name, picture] : fallback;
}
function profileCard(r) {
  const parsed = parseFacts(r), from = r.path;
  // A short qualifier ("mobile", "work") stays beside its value; a note on where it came from goes to the tooltip.
  const have = label => (parsed.has(label) ? parsed.get(label) : legacyFact(r, label)).filter(item => knownValue(item.value))
    .map(item => [...item.qualifier].length > 16 ? { ...item, qualifier: "", note: item.qualifier } : item);
  const units = (r.units || []).map(edge => byPath(edge.path)).filter(unit => unit && !orgHidden(unit));
  const mails = have("Email").flatMap(item => plainLine(item.value).toLowerCase().match(/[^\s<>(),;]+@[^\s<>(),;]+/g) || []);
  // #3164: an agent's mailbox is the person's agent, its own row; an address on the owner's page is never theirs.
  const ownerAddresses = new Set(((byPath(REM.owner)?.text || "").toLowerCase().match(/[^\s<>(),;:\[\]]+@[^\s<>(),;\[\]]+/g) || []));
  const agentAddress = item => /^0x[0-9a-f]{6,}@/i.test(plainLine(item.value));
  const notOwners = item => !ownerAddresses.has(plainLine(item.value).toLowerCase()) || r.path === REM.owner;
  const allHandles = have("Handles").filter(item => !mails.includes(plainLine(item.value).toLowerCase()) && notOwners(item));
  const handles = allHandles.filter(item => !agentAddress(item)), agents = allHandles.filter(agentAddress);
  const seen = [...mails, ...handles.map(item => plainLine(item.value).toLowerCase()), r.title.toLowerCase()];
  const rows = {}, add = (group, label, pic, values) => values.length && (rows[group] = rows[group] || []).push({ label, pic, values });
  add("Contact", "Email", "mail", have("Email").filter(notOwners).map(item => ({ item, copy: true })));
  add("Contact", "Their agent", "", agents.map(item => ({ item, copy: true })));
  add("Contact", "Phone", "phone", have("Phone").map(item => ({ item, copy: true })));
  const places = new Map(), linked = new Set();
  const once = item => { const key = urlKey(item.value); if (!/[./]/.test(key) || !linked.has(key)) { linked.add(key); return true; } return false; };
  // A raw WeChat id is not something to read (owner: "一串 wxid_ 开头的乱码"): it lives in ⋯ → 复制微信号 (#3372).
  // On a page the WeChat map made, or one with WeChat chats, a bare handle is a WeChat id too (#3346). One Handles
  // item can hold several ("ash@kiln.example, wxid_…"), so each part is checked, not the item.
  const wechatPart = part => wechatIdPart(r, part);
  const readable = handles.map(item => ({ ...item, value: String(item.value).split(/,\s*/).filter(part => part.trim() && !wechatPart(part)).join(", ") }))
    .filter(item => item.value.trim());
  for (const item of readable.filter(once)) {
    const [label, pic] = contactPlace(item, ["Handle", "at"]);
    places.set(label, { pic, values: [...(places.get(label)?.values || []), { item: label === item.qualifier ? { ...item, qualifier: "" } : item, copy: true }] });
  }
  for (const item of have("Links").filter(once)) {
    // A link names its platform only when it is their profile there, not a pull request or a post on it.
    const profile = /^(?:https?:\/\/)?(?:www\.)?(?:linkedin\.com\/in|github\.com|x\.com|twitter\.com)\/[^/\s]+\/?$/i.test(plainLine(item.value));
    const [label, pic] = profile ? contactPlace(item, ["Links", "globe"]) : ["Links", "globe"];
    places.set(label, { pic, values: [...(places.get(label)?.values || []), { item }] });
  }
  for (const [label, { pic, values }] of places) add("Contact", label, pic, values);
  const said = new Set(personSaid(r).map(word => plainLine(word).toLowerCase()));
  const fresh = item => !said.has(plainLine(item.value).toLowerCase());
  add("Work", "Signing entity", "", have("Signing entity").filter(fresh).map(item => ({ item })));
  if (!units.length) for (const label of ["Unit", "Role in unit"]) add("Work", label, "", have(label).filter(fresh).map(item => ({ item })));
  const project = personProject(r);
  if (project) add("Work", "Project", "", [{ node: el("a", { href: href(project), text: project.title }) }]);
  for (const label of ["How we know them", "First contact"]) add("Relationship", label, "", have(label).map(item => ({ item })));
  // Last contact, mail and location are the header's third line (personMeta); said once.
  const mapped = !have("Last contact").length && mappedContact(r) && known(r).last;
  // Each handle part counts as said, and a raw WeChat id is never an alias to show (#3372); names stay.
  const handleParts = handles.flatMap(item => String(item.value).split(/,\s*/).map(part => plainLine(part).toLowerCase()));
  const aliases = have("Also known as").filter(item => !seen.includes(plainLine(item.value).toLowerCase())
    && !handleParts.includes(plainLine(item.value).toLowerCase()) && !/^wxid_|@openim$/i.test(plainLine(item.value)));
  if (aliases.length) add("Identity", "Also known as", "", [{ node: el("span", { class: "pc-inline" }, aliases.map(item => profileValue(item, r, "Also known as"))) }]);
  const languages = have("Language");
  if (languages.length) add("Identity", "Language", "", [{ node: el("span", { class: "pc-inline" }, languages.map(item => profileValue(item, r, "Language"))) }]);
  if (!have("Location").length) add("Identity", "Time zone", "", have("Time zone").map(item => ({ item })));
  const extra = [...parsed.keys()].filter(label => !FACT_LABELS.people.includes(label) && !PROFILE_GROUPS.some(([, labels]) => labels.includes(label)) && !["Location", "Tags", "Direct send"].includes(label));
  for (const label of extra) add("Identity", label, "", have(label).map(item => ({ item })));
  // What the page has a line for and does not know; a unit or role the line above already says is not missing.
  const missing = [...FACT_LABELS.people, ...extra, ...["Unit", "Role in unit"].filter(label => parsed.has(label) && !units.length)]
    .filter(label => !have(label).length && !(label === "Last contact" && mapped) && !(label === "Company" && personOrg(r)));
  // One list, in the groups' order, each fact one row: its label in a fixed column, its value beside it. The
  // rows flow into two balanced columns, so no column runs long while another stands empty. A list of more
  // than two values shows two and folds the rest behind "+N". What the page does not know is left out; its
  // labels are the card's tooltip, not a line of "not found".
  const flat = PROFILE_GROUPS.flatMap(([name]) => rows[name] || []);
  if (!flat.length) return null;
  const list = el("dl", { class: "pc-list" }, flat.map(row => {
    const values = row.values.map(value => value.node || profileValue(value.item, r, row.label, value.copy));
    const dd = el("dd", { class: "pc-v" }, values.slice(0, 2));
    if (values.length > 2) {
      const more = el("button", { type: "button", class: "pc-more", text: t("+{n} more", { n: values.length - 2 }) });
      more.onclick = () => { more.replaceWith(...values.slice(2)); };
      dd.append(more);
    }
    return el("div", { class: "pc-row" }, [el("dt", { class: "pc-k", text: t(row.label) }), privateFallback(dd)]);
  }));
  const title = missing.length ? t(missing.length === 1 ? "1 fact not found" : "{n} facts not found", { n: missing.length }) + ": " + missing.map(label => t(label)).join(" · ") : null;
  return el("div", { class: "pcard", role: "group", "aria-label": t("Facts"), ...(title ? { title } : {}) }, [list]);
}
// One value: email, phone and handle copy on a click and say so; everything else reads as the fact card does.
// Its sources are small numbers after it; a labelled value hides with the labelled passages.
function profileValue(item, r, label, copy) {
  const noted = node => { if (item.note && !hasPrivacy(item.note)) node.title = plainLine(item.note); return node; };
  if (!copy) return changedValue(noted(factValue(item, r.path, label)), r, label);
  const done = el("span", { class: "pc-done", text: t("Copied") }), value = plainLine(item.value);
  const button = el("button", { type: "button", class: "pc-copy", title: t("Copy {name}", { name: uiLanguage === "zh" ? t(label) : label.toLowerCase() }) }, [
    el("span", { html: inline(item.value, r.path) }), done]);
  const say = words => { done.textContent = t(words); button.classList.add("done"); setTimeout(() => button.classList.remove("done"), 1600); };
  button.onclick = () => navigator.clipboard ? navigator.clipboard.writeText(value).then(() => say("Copied"), () => say("Copy failed")) : say("Select and copy");
  const cites = item.citations.length ? el("span", { class: "pc-cites", html: citeChips(item.citations, r.path) }) : null;
  // The qualifier and sources sit outside the button, so they wrap with each other and not alone under it.
  const after = item.qualifier || cites ? el("span", { class: "pc-after" }, [item.qualifier ? el("span", { class: "qual", text: item.qualifier }) : null, cites]) : null;
  const node = noted(el("span", { class: "pc-item" }, [softBreaks(button), after]));
  return changedValue(hasPrivacy(item.value) ? el("span", { class: "private" }, [node]) : node, r, label);
}
// A person's page is their record; what you owe them is done from Today (owner, 2026-11-08, D-30).
// One quiet link there, red only when it is overdue, and it raises their card.
function personTodayLink(r, late = 0) {
  const n = waitingOn(r).length;
  if (!n) return null;
  const link = el("a", { class: "r4-today" + (late ? " late" : ""), href: "#", text: late ? t("In Today · {n} days overdue", { n: late })
    : t(n === 1 ? "1 item in Today" : "{n} items in Today", { n }) });
  link.onclick = () => { todayLead = r.path; };
  return link;
}
// ---------- 调查 (#3105): one button in the person, organisation and project heads ----------
// Its words follow the page (r.investigation, page_runs.states): 调查 when it was never investigated, 更新 · N
// 封新邮件 when material arrived since, 深挖 · N 条线索 when the last enrich left leads open, 已是最新 greyed. A
// click runs `co rem investigate PAGE --enrich` through the Host (POST /rem/investigate); the ⋯ beside it holds
// the levels for whoever wants them. The run's steps show under the button while it works, then what changed,
// with Undo; a rewrite waits as a draft to replace or discard. In a snapshot the button is off and says why.
Object.assign(UI.zh, { "Investigate": "调查", "Up to date": "已是最新", "Nothing new to read": "没有新材料可读", "Not investigated yet": "还没调查过这页", "last {date}": "上次 {date}",
  "1 new mail not in this page yet": "有 1 封新邮件还没写进这页", "{n} new mails not in this page yet": "有 {n} 封新邮件还没写进这页",
  "1 new session not in this page yet": "有 1 个新会话还没写进这页", "{n} new sessions not in this page yet": "有 {n} 个新会话还没写进这页",
  "1 lead not followed yet (uses the web)": "还有 1 条线索没查（会联网）", "{n} leads not followed yet (uses the web)": "还有 {n} 条线索没查（会联网）",
  "Investigation level": "调查深度",
  "Quick update": "快速更新", "Full investigation": "完整调查", "Rewrite the page": "整页重写", "default": "默认",
  "Reads only the new material, no web": "只读新材料，不联网", "Adds the web follow-up": "含联网补充",
  "Writes a new draft; replaces the page only when you accept it": "生成新稿，确认后替换",
  "Last time about {n} points": "上次约 {n} 点", "Last investigated {date}": "上次调查 {date}", "Never investigated": "还没调查过这页",
  "Investigating…": "正在调查…", "Write": "写", "Append": "追加", "Web follow-up": "联网补充", "Rewrite": "重写",
  "Updated · {n} lines added": "已更新 · 新增 {n} 行", "Updated · 1 line added": "已更新 · 新增 1 行", "Updated": "已更新",
  "Nothing new to add": "没有可补充的内容", "new organisation page": "新建组织页", "linked": "已关联", "What changed": "改了什么", "Undone · the page is back as it was": "已撤销 · 页面已恢复",
  "A rewrite is ready · {before} → {after} characters": "整页重写稿已就绪 · {before} → {after} 字",
  "Replace the page": "替换页面", "Discard": "丢弃", "Rewrite discarded": "已丢弃重写稿",
  "The investigation stopped: {why}": "调查没有完成：{why}", "The investigation stopped": "调查没有完成",
  "The draft did not pass the page check; the page is unchanged": "这次调查的稿子没通过检查，页面保持原样",
  "What the check found": "检查发现了什么",
  "it will try once more tonight": "今晚会再试一次",
  "Tried {n} times and it never passed, so it is paused": "试了 {n} 次都没通过，已暂停",
  "press Investigate to try again": "想再试就点调查",
  "Could not do that: {why}": "没有做成：{why}",
  "This is a snapshot: investigate from the live reader.": "这是快照：请在实时阅读器里调查。" });
const INV_STEPS = { write: "Write", append: "Append", rewrite: "Rewrite", enrich: "Web follow-up" };
// Why a run stopped, by its kind (page_runs.REASONS), in the reader's language; any other reason is shown as written.
const INV_REASONS = { too_long: "the page is too long to add to; the draft is kept and the page is unchanged",
  changed: "the page changed while it was investigated; nothing was written, run it again",
  dropped: "the draft left out lines the page had, so it was not saved; the page is unchanged" };
Object.assign(UI.zh, { "the page is too long to add to; the draft is kept and the page is unchanged": "页面超过长度上限，候选稿已保存，页面没有改动",
  "the page changed while it was investigated; nothing was written, run it again": "调查期间页面被改动，没有写入，请再试一次",
  "the draft left out lines the page had, so it was not saved; the page is unchanged": "候选稿漏掉了页面原有的内容，没有保存，页面没有改动",
  "Earlier history": "更早的经历" });
const INV_LEVELS = [["full", "Full investigation", "Adds the web follow-up"],
  ["quick", "Quick update", "Reads only the new material, no web"], ["rewrite", "Rewrite the page", "Writes a new draft; replaces the page only when you accept it"]];
const INV_RUNS = new Map();  // what this tab has seen of a page's run since the page data was built
// The head's one action slot (rc35 hunt, #3131): the same component in the same place on a person, an organisation
// and a project, 调查 then 查看来源; nothing else in a record's head is an action.
function recordActs(r) {
  const sources = !orgHidden(r) && sourceList(r).length
    ? el("a", { class: "rec-sources", href: href(r) + "&h=sources", text: t("View sources →") }) : null;
  const parts = [investigateControl(r), sources].filter(Boolean);
  return parts.length ? el("div", { class: "rec-acts" }, parts) : null;
}
function investigateControl(r) {
  if (!r.investigation) return null;
  const box = el("div", { class: "inv" });
  const paint = () => {
    const s = { ...r.investigation, ...(INV_RUNS.get(r.path) || {}) };
    box.dataset.label = s.run?.result === "running" ? "running" : s.label;
    box.replaceChildren(...invParts(r, s, paint).filter(Boolean));
  };
  paint();
  return box;
}
function invCount(one, many, n) { return t(n === 1 ? one : many, { n }); }
// One verb on the button, always (owner, 2026-11-18: «更新是什么意思呢？»); the reason is the line under it,
// in words that say what the click will do.
// One look too (rc35 hunt, #3131): "nothing new" is the same button switched off with its reason as the tooltip,
// not a grey "已是最新" on one page and an outlined one on another.
function invLabel(s) { return [t("Investigate")]; }
function invWhy(s) {
  const last = s.last ? " · " + t("last {date}", { date: fmtDate(s.last) }) : "";
  if (s.label === "investigate") return t("Not investigated yet");
  if (s.label === "update" && s.new_pages) return invCount("1 page with this tag is new or changed", "{n} pages with this tag are new or changed", s.new_pages) + last;
  if (s.label === "update") return (s.new_mails ? invCount("1 new mail not in this page yet", "{n} new mails not in this page yet", s.new_mails)
    : invCount("1 new session not in this page yet", "{n} new sessions not in this page yet", s.new_sessions)) + last;
  if (s.label === "deeper") return invCount("1 lead not followed yet (uses the web)", "{n} leads not followed yet (uses the web)", s.leads) + last;
  return s.last ? t("Last investigated {date}", { date: fmtDate(s.last) }) : t("Never investigated");
}
function invParts(r, s, paint) {
  const run = s.run, running = run?.result === "running", live = liveHere();
  const go = el("button", { type: "button", class: "inv-go", ...(live ? {} : { disabled: "disabled", title: t("This is a snapshot: investigate from the live reader.") }) },
    running ? [t("Investigating…")] : invLabel(s));
  if (running || s.label === "current") go.disabled = true;
  if (!running && s.label === "current") go.title = t("Nothing new to read") + (s.last ? " · " + t("Last investigated {date}", { date: fmtDate(s.last) }) : "");
  go.onclick = () => invRun(r, "full", paint);
  const parts = [el("div", { class: "inv-row" }, [go, invMenu(r, s, paint, running || !live)])];
  if (running) parts.push(invSteps(run));
  else if (s.notice) parts.push(el("p", { class: "inv-line", role: "status", text: s.notice }));
  else if (run && invRecent(run)) parts.push(...invResult(r, s, paint));
  if (!running && s.rewrite) parts.push(invDraft(r, s, paint));
  // When there is nothing new the reason is the button's tooltip; the head already says how fresh the page is.
  if (!running && !(run && invRecent(run)) && !s.notice && s.label !== "current") parts.push(el("p", { class: "inv-line", text: invWhy(s) }));
  if (!live) parts.push(liveReaderLine("This is a snapshot: investigate from the live reader."));
  if (running && live) invFollow(r, paint);
  return parts;
}
// ---------- Who REM may reply to without asking (#3121, D-101) ----------
// Each person has a tier on their page: partner (sent with no click, after the hold), close (routine replies
// only), none (a card in Today) or never (drafts only). REM sets it from the relationship; the owner sets it
// here in one click, and his choice wins from then on. The words say what will happen, not the tier's name.
Object.assign(UI.zh, { "Send to them directly from now on": "以后直接发给他", "Show me first from now on": "以后先给我看",
  "REM replies to them without asking; 10 minutes to undo": "REM 直接回复，10 分钟内可撤销",
  "Their replies wait for you in Today": "他的回复先放在今天等你看",
  "Replies to this person": "回复这个人", "Saved: REM sends to them directly": "已改：以后直接发给他",
  "Saved: their replies wait for you": "已改：以后先给我看", "Sending to {name} at {time} · {left} to undo": "{time} 发给 {name} · 还有 {left} 可撤销" });
const DIRECT_TIERS = new Map();  // this tab's changes since the page data was built
function directTier(r) {
  if (DIRECT_TIERS.has(r.path)) return DIRECT_TIERS.get(r.path);
  const line = (parseFacts(r).get("Direct send") || [])[0];
  return (/^(partner|close|none|never)\b/.exec(plainLine(line?.value || "")) || [])[1] || "none";
}
// The one item a menu shows: the opposite of what happens now, with what it will do in words.
function directSendItem(r, close) {
  if (!r || r.category !== "people" || !REM.live) return null;
  const direct = ["partner", "close"].includes(directTier(r));
  const [label, says, tier, done] = direct ? ["Show me first from now on", "Their replies wait for you in Today", "none", "Saved: their replies wait for you"]
    : ["Send to them directly from now on", "REM replies to them without asking; 10 minutes to undo", "partner", "Saved: REM sends to them directly"];
  const item = el("button", { type: "button", role: "menuitem", class: "direct-send", "data-tier": tier }, [t(label), el("small", { text: t(says) })]);
  item.onclick = async () => {
    item.disabled = true;
    const response = await fetch("/rem/direct-send", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page: r.path, tier, reason: "reader" }) }).catch(() => null);
    const result = response ? await response.json().catch(() => ({})) : {};
    if (!response?.ok) { item.disabled = false; item.lastChild.textContent = result.error || t("Could not do that: {why}", { why: t("Try again") }); return; }
    DIRECT_TIERS.set(r.path, tier);
    item.replaceChildren(t(done));
    close?.();
  };
  return item;
}
function invMenu(r, s, paint, off) {
  const menu = el("details", { class: "inv-more" }, [el("summary", { "aria-label": t("Investigation level"), title: t("Investigation level") }, [icon("ellipsis")])]);
  const cost = mode => mode !== "rewrite" && s.cost?.[mode] ? " · " + t("Last time about {n} points", { n: s.cost[mode] }) : "";
  menu.append(el("div", { class: "inv-menu", role: "menu" }, [el("p", { class: "inv-h", text: t("Investigation level") }),
    ...INV_LEVELS.map(([mode, name, says]) => {
      const item = el("button", { type: "button", role: "menuitem", "data-level": mode, ...(off ? { disabled: "disabled" } : {}) },
        [t(name), mode === "full" ? el("span", { class: "inv-default", text: " · " + t("default") }) : null, el("small", { text: t(says) + cost(mode) })]);
      item.onclick = () => { menu.open = false; invRun(r, mode, paint); };
      return item;
    }), ...(r.category === "people" && REM.live ? [el("p", { class: "inv-h", text: t("Replies to this person") }), directSendItem(r)] : []),
    // 不是人 / 是人 lives in the header's ⋯ (#3231 header tidy; #3339): a lone grey word under 查看来源 pushed the page down.
    ...(personMarkItem(r) || wechatIds(r).length ? [el("p", { class: "inv-h", text: t("This person") }), personMarkItem(r, () => { menu.open = false; }),
      wechatCopyItem(r, () => { menu.open = false; })].filter(Boolean) : [])]));
  menu.onkeydown = event => { if (event.key === "Escape" && menu.open) { event.stopPropagation(); menu.open = false; menu.querySelector("summary").focus(); } };
  return menu;
}
function invSteps(run) {
  return el("ol", { class: "inv-steps", "aria-live": "polite" }, (run.progress || run.steps.map(step => ({ step, state: "waiting" }))).map(row =>
    el("li", { class: row.state }, [t(INV_STEPS[row.step] || row.step),
      row.state === "running" && row.stage ? el("span", { class: "inv-stage", text: " · " + invStage(row.stage) }) : null])));
}
// The run record's stage, in the reader's language: the common ones by name, a round with its numbers.
Object.assign(UI.zh, { "gathering sources": "收集材料", "searching project documents": "查找项目文档", "preparing evidence": "整理材料",
  "writing evidence files": "整理材料", "writing investigation": "写作", "reviewing": "审核", "claim audit": "核对引用",
  "following leads": "跟进线索", "recording result": "保存", "reading the organisation's website": "读组织网站",
  "repair round": "修补", "editing round": "编辑", "quote round": "补引语", "insight critic": "复核洞见",
  "processing attributed feedback": "处理反馈" });
function invStage(stage) {
  const round = /^investigation round (\d+) of (\d+)/.exec(stage), repair = /^repair (\d+)/.exec(stage);
  if (round) return uiLanguage === "zh" ? `第 ${round[1]}/${round[2]} 轮` : `round ${round[1]} of ${round[2]}`;
  if (repair) return uiLanguage === "zh" ? `修补 ${repair[1]}` : stage;
  const turn = /^turn (\d+) of (\d+)/.exec(stage), source = /^(gathering|searching|listing) (\S+) (mail|attachments)$/.exec(stage);
  if (turn) return uiLanguage === "zh" ? `第 ${turn[1]}/${turn[2]} 步` : stage;
  if (source && uiLanguage === "zh") return { gathering: "读取", searching: "搜索", listing: "列出" }[source[1]] + " " + source[2]
    + (source[3] === "mail" ? " 邮件" : " 附件");
  const scanned = /^gathering (.+?): [\d,]+ scanned/.exec(stage);
  if (scanned) return uiLanguage === "zh" ? `读取 ${scanned[1]}` : `gathering ${scanned[1]}`;
  return t(stage.replace(/:\s*[\d,]+\b.*$/, ""));
}
// A finished run is said for half a day after it ends, then the head goes back to the page's state.
function invRecent(run) { return run.result !== "running" && Date.now() - Date.parse(run.finished_at || run.started_at) < 12 * 3600 * 1000; }
// A stopped run says why in one sentence. A draft the page check refused (#2235 follow-up) says so in the
// owner's words; what the check found is a detail behind a fold, and never a file name or path.
function invFailed(run) {
  // What happens next comes from the refusal ledger the night retries from (page_runs.next_step), never guessed.
  const next = run.reason_kind === "rejected" ? run.next : null;
  const why = next?.kind === "parked" ? t("Tried {n} times and it never passed, so it is paused", { n: next.tries })
    : run.reason_kind === "rejected" ? t("The draft did not pass the page check; the page is unchanged")
    : run.reason ? t("The investigation stopped: {why}", { why: INV_REASONS[run.reason_kind] ? t(INV_REASONS[run.reason_kind]) : run.reason })
    : t("The investigation stopped");
  const then = next?.kind === "parked" ? t("press Investigate to try again") : next?.kind === "retry" ? t("it will try once more tonight") : "";
  const line = el("p", { class: "inv-line", role: "status" }, [el("span", { class: run.reason_kind === "rejected" ? "inv-kept" : "inv-fail", text: why }),
    then ? el("span", { class: "inv-more inv-kept", text: "\u00a0· " + then }) : null]);
  if (run.reason_kind !== "rejected" || !run.detail) return [line];
  const detail = el("p", { class: "inv-detail", hidden: "", text: refusalReason(String(run.detail)) });
  const open = el("button", { type: "button", "aria-expanded": "false", text: t("What the check found") });
  open.onclick = () => { detail.hidden = !detail.hidden; open.setAttribute("aria-expanded", String(!detail.hidden)); };
  line.append(el("span", { class: "inv-more" }, ["\u00a0· ", open]));  // the dot wraps with its button, never alone
  return [line, detail];
}
function invResult(r, s, paint) {
  const run = s.run;
  if (run.result === "failed") return invFailed(run);
  if (run.mode === "rewrite") return [];
  const added = run.added_lines || [], count = run.added_count ?? added.length;
  const words = !run.changed ? t("Nothing new to add") : count === 1 ? t("Updated · 1 line added")
    : count ? t("Updated · {n} lines added", { n: count }) : t("Updated");
  const line = el("p", { class: "inv-line", role: "status" }, [words]);
  // The organisations the run linked come first, each a link to its page, new pages said so (#3141).
  const orgs = (run.orgs || []).map(org => el("li", { class: "inv-org" }, [el("a", { href: "#r=" + encodeURIComponent(org.record), text: pageName(byPath(org.record)) || org.title }),
    " · " + t(org.created ? "new organisation page" : "linked")]));
  const changes = added.length || orgs.length ? el("div", { class: "inv-changed", hidden: "" }, [el("b", { text: t("What changed") }),
    el("ul", {}, [...orgs, ...added.slice(0, 12).map(text => el("li", { html: inline(text.replace(/^[-*]\s+/, ""), r.path) }))])]) : null;
  if (changes) {
    const open = el("button", { type: "button", "aria-expanded": "false", text: t("What changed") });
    open.onclick = () => { changes.hidden = !changes.hidden; open.setAttribute("aria-expanded", String(!changes.hidden)); };
    line.append(" · ", open);
  }
  if (s.undo && liveHere()) {
    const undo = el("button", { type: "button", text: t("Undo") });
    undo.onclick = () => invAct(r, "undo", paint, t("Undone · the page is back as it was"));
    line.append(" · ", undo);
  }
  return [line, changes];
}
function invDraft(r, s, paint) {
  const [before, after] = s.rewrite.chars || [0, 0];
  const line = el("p", { class: "inv-line", role: "status" }, [t("A rewrite is ready · {before} → {after} characters",
    { before: before.toLocaleString(uiLocale()), after: after.toLocaleString(uiLocale()) })]);
  if (liveHere()) {
    const accept = el("button", { type: "button", text: t("Replace the page") }), discard = el("button", { type: "button", text: t("Discard") });
    accept.onclick = () => invAct(r, "accept", paint, t("Updated"));
    discard.onclick = () => invAct(r, "discard", paint, t("Rewrite discarded"));
    line.append(" · ", accept, " · ", discard);
  }
  return line;
}
async function invRun(r, mode, paint) {
  const reply = await hostPost("/rem/investigate", { action: "run", page: r.path, mode });
  const { ok, code, error, ...run } = reply;
  INV_RUNS.set(r.path, ok ? { run, notice: "" } : { notice: invRefusal(code, error) });
  paint();
}
function invRefusal(code, error) {
  return code === 401 ? t("Your session expired. Reload the page.") : code === 0 ? t(HOST_LOST_WORDS)
    : t("Could not do that: {why}", { why: error || code });
}
async function invAct(r, action, paint, done) {
  const { ok, code, error } = await hostPost("/rem/investigate", { action, page: r.path });
  // Said here at once; the rebuilt page that follows shows the page as it now is.
  INV_RUNS.set(r.path, { notice: ok ? done : invRefusal(code, error), run: null, rewrite: action === "undo" ? r.investigation.rewrite : null,
    undo: false });
  paint();
}
function invFollow(r, paint) {
  if (invFollow.on?.has(r.path)) return;
  (invFollow.on ||= new Set()).add(r.path);
  const tick = async () => {
    const { ok, code, ...run } = await hostPost("/rem/investigate", { page: r.path });
    if (ok) INV_RUNS.set(r.path, { run, notice: "", undo: run.undo, rewrite: run.rewrite });
    if (ok && run.result === "running") { paint(); setTimeout(tick, 4000); return; }
    invFollow.on.delete(r.path);
    paint();
  };
  setTimeout(tick, 4000);
}
// The contact rhythm: one cell per day for the last half year (or since you first spoke), dark where the
// record dates an exchange. Beside it the counts that say how close you are.
function personFuse(r) {
  const d = personFuseData(r);
  if (!d) return null;
  const counts = {};
  for (const day of d.days) counts[day] = (counts[day] || 0) + 1;
  const end = new Date(d.today + "T00:00:00Z"), start = new Date(Math.max(Date.parse(d.first + "T00:00:00Z"), end - 26 * 7 * DAY_MS));
  start.setUTCDate(start.getUTCDate() - start.getUTCDay());
  const cells = [];
  for (let at = start.getTime(); at <= end.getTime(); at += DAY_MS) {
    const day = new Date(at).toISOString().slice(0, 10), n = counts[day] || 0;
    cells.push(el("i", { class: day === d.today ? "today" : n >= 3 ? "l3" : n === 2 ? "l2" : n ? "l1" : "", title: fmtDate(day) + (n ? " · " + n : "") }));
  }
  const mails = facts(r).mails;
  const note = !d.days.length ? t("REM has no dated exchanges in this record yet, only the first contact.")
    : mails > d.days.length ? t("Each tick is a dated exchange in the record ({n}); the other mails have no dates here.", { n: d.days.length })
      : t("Each tick is a dated exchange in the record ({n}).", { n: d.days.length });
  return el("section", { class: "widget span2 r4-fuse" }, [el("div", { class: "wt" }, [icon("clock"), el("span", { text: t("Contact rhythm") })]),
    el("div", { class: "rh-row" }, [el("div", { class: "rh" }, [
      el("div", { class: "rhythm", role: "img", "aria-label": t("{n} dated exchanges from {first} to today", { n: d.days.length, first: fmtDate(d.first) }), title: note }, cells),
      el("div", { class: "fuse-ends" }, [el("span", { text: t("{date} first exchange", { date: fmtDate(d.first) }) }), el("b", { text: t("Today") })])]), personStats(r, d)])]);
}
function personStats(r, d = personFuseData(r)) {
  const f = facts(r), rel = r.index?.relationship;
  const year = rel?.last_mail ? rel.weekly_messages.reduce((a, b) => a + b, 0) : null;
  const last = rel?.last_from_you === true ? t("you wrote last") : rel?.last_from_you === false ? t("{name} wrote last", { name: firstName(r) }) : t("Last contact");
  // The first exchange is under the rhythm; the last one turns red only once their mail has waited past your usual reply time.
  const cells = [year ? [String(year), t("mails this year")] : f.mails ? [String(f.mails), t("mails exchanged")] : null,
    rel?.reply_seconds_owner != null ? [replyDuration(rel.reply_seconds_owner), t("your median reply")] : null,
    f.last ? [fmtDate(f.last), last, d?.wait ? "late" : ""] : null].filter(Boolean);
  return cells.length ? el("div", { class: "r4-stats" }, cells.map(([value, label, cls]) => el("div", { class: cls || "" }, [el("b", { class: "big", text: value }), el("span", { text: label })]))) : null;
}
// What is still open with them leads, right under the header: it is what the owner opens a person for (sprint 15).
// The rest of the record as widgets; the full note with every source stays below them.
function personPage(r) {
  // #3145 (owner, 2026-11-19): no "open topics" here: it disagreed with Today, where those items were already closed,
  // and to-dos live only in Today (D-30). What happened between you, newest first, is the first thing under the header.
  const bentoKids = [personFuse(r), personQuotes(r),
    el("div", { class: "stack2" }, [railUnsure(r), railSources(r)].filter(Boolean)), personSessions(r)]
    .filter(n => n && (!n.classList?.contains("stack2") || n.childElementCount > 0));
  return el("div", { class: "r4 r4-person n3-person" }, [personHead(r), personTimeline(r, { lead: true }),
    bentoKids.length ? el("div", { class: "bento" }, bentoKids) : null].filter(Boolean));
}
// The fuse: a heavy line from the first exchange REM knows to today, one tick per dated
// exchange in the record. Positions are the real dates; nothing is spaced for looks.
function personFuseData(r) {
  const today = calendarDay(REM.as_of || new Date().toISOString()), day = text => /\d{4}-\d{2}-\d{2}/.exec(String(text || ""))?.[0] || "";
  const days = historyItems(section(r, "history")?.text || "").map(item => day(item.day)).filter(d => d && d <= today).sort();
  const first = [day(facts(r).first), days[0]].filter(Boolean).sort()[0];
  return first ? { first, today, days, wait: personWait(r, today) } : null;
}
// Red only from their last mail, and only once it is past your own usual reply time (synced mail).
function personWait(r, today) {
  const rel = r.index?.relationship;
  if (rel?.last_from_you !== false || !rel.last_mail || rel.reply_seconds_owner == null) return "";
  // Today has the last word on what is owed: handled, looks handled or needs no reply means nothing is burning.
  const entries = personEntries(r).filter(entry => entry.t.dir === "mine" && !entry.t.quiet);
  if (entries.length && entries.every(entry => isDone(entry) || looksDone(entry) || threadDraft(entry)?.status === "no_reply")) return "";
  const waited = (Date.parse(REM.as_of || new Date().toISOString()) - Date.parse(rel.last_mail)) / 1000;
  return waited > rel.reply_seconds_owner && calendarDay(rel.last_mail) <= today ? calendarDay(rel.last_mail) : "";
}
// The archive keeps From, To, Cc and the subject, not Auto-Submitted, List-Id or Bcc: these are what it can judge by.
function isAutoReply(text) {
  return /^\s*(?:automatic reply|auto(?:matic)?[- ]?reply|auto:|out of (?:the )?office|自动回复)|\bthank(?:s| you) for your (?:e-?mail|message)\b[\s\S]{0,200}?\b(?:away from|out of (?:the )?office|on (?:annual )?leave|will (?:respond|reply|get back))|\b(?:I am|I'm) (?:currently )?(?:out of (?:the )?office|away from (?:my desk|the office)|on (?:annual )?leave)\b/i.test(String(text || ""));
}
// The owner's own addresses: the map's and the mail archive's (snapshot owner_addresses), then the owner page's.
function ownerAddresses() {
  const owner = REM.owner && byPath(REM.owner);
  const found = [...(REM.owner_addresses || []), ...(owner ? String(facts(owner).email || "").match(/[^\s<>(),;]+@[^\s<>(),;]+/g) || [] : []), ...(owner?.index?.emails || [])];
  return [...new Set(found.map(a => a.toLowerCase()))];
}
// Said to you, personally: you are on To or Cc (not Bcc, not a list), at most eight people are, and it is not an auto-reply.
function saidToYou(c, owner) {
  if (!Array.isArray(c.participants?.to)) return false;
  const addresses = list => [].concat(list || []).join(" ").toLowerCase().match(/[^\s<>(),;"']+@[^\s<>(),;"']+/g) || [];
  const all = [...addresses(c.participants.to), ...addresses(c.participants.cc)];
  // Without the owner's addresses nothing can show it was said to him, so nothing is quoted.
  if (!owner.length || !all.length || all.length > 8 || !all.some(a => owner.includes(a))) return false;
  return !isAutoReply(c.subject) && !isAutoReply(c.excerpt);
}
// What they wrote to you, in their own words: archived mail cited by the record, newest first, each with its source.
// Their words, not the envelope: quoted lines, greetings (on their own line or before the first sentence)
// and the signature block (a sign-off, or a phone number and everything after it) are dropped.
function saidWords(text) {
  const lines = [];
  for (const raw of String(text || "").split(/\n+/)) {
    const line = raw.trim();
    // A sign-off, "--" or a phone line on its own ends the mail, but only once there is a body above it.
    const signature = /^--\s*$/.test(line) || /^(?:kind|best|warm|many)?\s*(?:regards|thanks|cheers|sincerely)[,!.]?$/i.test(line)
      || /^(?:(?:T|M|P|Tel|Ph|Phone|Mobile)\s*[:.]?\s*)?\+?\d[\d ().-]{7,}\d$/i.test(line);
    if (signature && lines.length) break;
    if (line && !/^>/.test(line) && !/^(?:hi|hello|hey|dear)\b[^.!?。]{0,40}[,，!！]?$/i.test(line)) lines.push(line);
  }
  const words = lines.join(" ").replace(/\s+/g, " ").replace(/^(?:hi|hello|hey|dear)\s+[\p{L}'’-]+(?:\s+[\p{L}'’-]+)?\s*[,，!！]\s*/iu, "");
  // A sign-off inside a line ("…card.Kind Regards, Tamara …") cuts there, and the cut says so.
  const cut = words.search(/\s*\b(?:kind|best|warm)\s+regards\b/i);
  return cut > 0 ? words.slice(0, cut).trim() + "…" : words.trim();
}
// Sources a public passage cites and no private passage does: a mail cited by a [personal] passage
// stays as private as the passage, even when a public sentence cites it too.
function publicOnlyCites(r) {
  const body = r.text.split(/\n## Sources\b/)[0], cite = /[\[［](W?\d{1,3})[\]］]/g, hidden = new Set();
  const visible = privatePassages(body, passage => { for (const m of passage.matchAll(cite)) hidden.add(m[1]); return ""; });
  return new Set([...visible.matchAll(cite)].map(m => m[1]).filter(n => !hidden.has(n)));
}
function personQuotes(r) {
  const mails = (String(facts(r).email || "").match(/[^\s<>(),;]+@[^\s<>(),;]+/g) || []).map(a => a.toLowerCase());
  const names = [r.title.toLowerCase(), firstName(r).toLowerCase()];
  const theirs = sender => { const s = String(sender || "").toLowerCase(); return mails.some(a => s.includes(a)) || names.some(n => n && (s === n || s.startsWith(n + " "))); };
  const seen = new Set(), owner = ownerAddresses(), cited = publicOnlyCites(r), key = words => words.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
  const rows = sourceList(r).filter(s => cited.has(s.n)).map(s => ({ s, c: REM.source_context?.[sourceId(s.text, s.plain)] }))
    .filter(({ c }) => c?.excerpt && !c.body_empty && !hasPrivacy(c.excerpt) && theirs(c.sender) && saidToYou(c, owner)).map(row => ({ ...row, words: saidWords(row.c.excerpt) }))
    .filter(({ words }) => [...words].length >= 12 && !/\breacted to your message\b/i.test(words) && !seen.has(key(words)) && seen.add(key(words)))
    .sort((a, b) => String(b.c.time).localeCompare(String(a.c.time)));
  if (!rows.length) return null;
  const kind = s => ({ gmail: "Gmail", outlook: "Outlook", imap: "Mail" })[sourceId(s.text).split(":")[0]] || "";
  const list = el("ol", {}, rows.slice(0, 6).map(({ s, words }) => el("li", {}, [
      el("span", { class: "said-src" }, [el("span", { text: kind(s) }), el("span", { html: inline("[" + s.n + "]", r.path) })]),
      el("q", { class: "said-q", text: [...words].length > 280 ? [...words].slice(0, 279).join("") + "…" : words })])));
  return el("section", { class: "widget r4-said" }, [widgetHead("quote", t("In their words"), rows.length > 1 ? expandChip(list, t("{n} entries", { n: Math.min(6, rows.length) })) : null), list]);
}
// A widget's title line: its icon, its name, and on the right a count or the one control that shows more.
function widgetHead(iconName, title, end = null) {
  return el("div", { class: "wt" }, [icon(iconName), el("h2", { text: title }), end ? el("span", { class: "end" }, [end]) : null]);
}
function expandChip(list, words) {
  const button = el("button", { type: "button", class: "chip ghost", "aria-expanded": "false", text: words });
  button.onclick = () => { const all = list.classList.toggle("all"); button.setAttribute("aria-expanded", String(all)); };
  return button;
}
// Month and day; an exchange from another year carries its year under them, where the narrow column has room.
function timelineDay(day) {
  if (day.length !== 10) return [];
  const say = parts => new Date(day + "T00:00:00Z").toLocaleDateString(uiLocale(), { timeZone: "UTC", ...parts });
  const thisYear = day.slice(0, 4) === calendarDay(REM.as_of || new Date().toISOString()).slice(0, 4);
  // "9月3日" / "Sep 3", never "9/3": one date form on every page (rc35 hunt).
  return [say({ month: "short", day: "numeric" }), thisYear ? null : el("span", { class: "y", text: say({ year: "numeric" }) })];
}
function timelineRow(r, item) {
  const text = withoutDateClutter(youify(item.text));
  const content = historyRowContent(text, r.path);
  if (!content) return null;
  const yours = /^\s*(?:\*\*)?(?:the user|you|你)\b/i.test(unlabelled(item.text));
  const li = el("li", { class: "tl-e" + (content.classList.contains("privacy-only") ? " private-entry" : "") }, [el("span", { class: "d" }, timelineDay(item.day)),
    el("span", { class: "w" }, [el("i", { class: yours ? "me" : "", title: t(yours ? "You" : "Them") })]), el("span", { class: "x" }, [content])]);
  // One click on the row shows the whole original beside it, in the source card (#3145, owner: «每点击一个，旁边就可以
  // 显示完整的对话记录或者邮件»); the row stays marked while it is open. A row with no source stays a plain line.
  // The row's sources are read from its written line: the timeline draws the words without their [n] marks.
  const number = (/\[(W?\d+)\]/.exec(unlabelled(item.text)) || [])[1] || li.querySelector("a.cite")?.dataset.sources?.split(" ")[0];
  if (number) {
    Object.assign(li, { tabIndex: 0, title: t("Open the original") });
    li.classList.add("tl-open");
    li.setAttribute("role", "button");
    const open = () => { document.querySelectorAll(".tl-e.on").forEach(row => row.classList.remove("on")); li.classList.add("on"); openEvidence(r, number, li, { fromList: true }); };
    li.addEventListener("click", event => { if (!event.target.closest("a, button")) open(); });
    li.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } });
  }
  return li;
}
function personTimeline(r, { lead = false } = {}) {
  const items = historyItems(section(r, "history")?.text || "").filter(item => item.day).sort((a, b) => b.day.localeCompare(a.day));
  const rows = items.map(item => timelineRow(r, item)).filter(Boolean);
  if (!rows.length) return null;
  const first = lead ? 5 : 3;
  rows.slice(first).forEach(row => row.classList.add("later"));
  const list = el("ol", { class: "tl" + (rows.length > first ? "" : " all") }, rows);
  const more = rows.length > first ? el("button", { type: "button", class: "chip ghost tl-more", text: t("Show all {n} entries", { n: rows.length }) }) : null;
  if (more) more.onclick = () => { list.classList.add("all"); more.remove(); };
  return el("section", { class: "widget r4-sec" + (lead ? " tl-lead" : ""), id: "history-timeline" }, [widgetHead("layers", t("Exchanges"), el("span", { text: t("{n} entries", { n: rows.length }) })),
    list, privateHistoryNotice(rows), more]);
}
// REM's open questions about this person: its inference, so a dashed card; the questions open in a sheet.
function railUnsure(r) {
  // Only the bullets: a summary paragraph under them is not an open question.
  const items = (section(r, "uncertainties")?.text || "").split("\n").filter(line => /^\s*[-*]\s/.test(line)).map(line => plainLine(line)).filter(Boolean);
  if (!items.length) return null;
  const button = el("button", { type: "button", class: "widget row2 dashed unsure-open" }, [el("b", { class: "big muted", text: String(items.length) }), el("span", { text: t("REM is not sure") }), icon("right")]);
  button.onclick = () => openListSheet(t("REM is not sure"), el("ul", { class: "r4-unsure" }, items.map(item => el("li", { text: item }))));
  return button;
}
function openListSheet(title, body) {
  const close = el("button", { type: "button", class: "ibtn", "aria-label": t("Close") }, [icon("x")]);
  const dialog = el("dialog", { class: "n3-sheet list-sheet", "aria-label": title }, [el("div", { class: "sheet-head" }, [el("h2", { text: title }), close]), body]);
  close.onclick = () => dialog.close();
  dialog.addEventListener("close", () => dialog.remove());
  document.body.appendChild(dialog);
  dialog.showModal();
}
// The sources: the count, and a click opens the full note where every one is listed.
function railSources(r) {
  const n = sourceList(r).length;
  if (!n) return null;
  const button = el("button", { type: "button", class: "widget row2 r4-src" }, [el("b", { class: "big", text: String(n) }), el("span", { text: t(n === 1 ? "source" : "sources") }), icon("right")]);
  button.onclick = () => {
    const deep = document.querySelector(".deep-note");
    // Straight to the source band (#3104), not the top of a long memory.
    if (deep) { deep.open = true; (document.getElementById("sources") || deep).scrollIntoView({ block: "start" }); }
  };
  return button;
}
// Sessions that name this person: five rows under the timeline, the rest one link away.
function personSessions(r) {
  const sessions = (r.session_mentions || []).map(byPath).filter(Boolean);
  if (!sessions.length) return null;
  const all = el("a", { href: sessionHash({ person: r.path }), text: t("All {n} sessions", { n: sessions.length }) });
  return el("section", { class: "widget person-sessions" }, [widgetHead("terminal", t("Mentioned in sessions"), all),
    el("ul", { class: "session-context-rows" }, sessions.slice(0, 3).map(s => sessionContextRow(s, r.title)))]);
}
// What is still open between you, as facts of the record (D-30: no to-do UI here; D-36: not folded).
// The words and the date only; marking, replying and closing happen in Today. The top three show; 全部 N 条 opens the rest.
function personTopics(r) {
  const items = threads(r).items.filter(item => item.dir !== "third");
  const rows = items.map(item => {
    const content = historyRowContent(withoutDateClutter(youify(item.text), item), r.path);
    return content ? el("li", { class: content.classList.contains("privacy-only") ? "private-entry" : "" }, [
      el("span", { class: "d", text: item.since ? fmtDate(item.since) : "" }), el("span", { class: "x" }, [content])]) : null;
  }).filter(Boolean);
  if (!rows.length) return null;
  // With labelled passages hidden, the top three and the count are of the rows shown: the card neither leads
  // the page empty nor tells how many hidden rows there are, and it leaves when none is shown.
  const section = el("section", { class: "widget r4-sec r4-topics" });
  section.refreshTopics = () => {
    const hidden = document.documentElement.classList.contains("hide-private");
    const shown = rows.filter(row => !hidden || !row.classList.contains("private-entry"));
    shown.forEach((row, i) => row.classList.toggle("later", i >= 3));
    const list = el("ul", { class: shown.length > 3 ? "" : "all" }, shown);
    section.hidden = !shown.length;
    section.replaceChildren(widgetHead("activity", t("Open topics"), shown.length > 3 ? expandChip(list, t("All {n} entries", { n: shown.length })) : el("span", { text: String(shown.length) })), list);
  };
  section.refreshTopics();
  return section;
}
// What is still owed between you and a person: Today's rows (D-30), counted here, never listed.
function waitingOn(r) {
  // Today's own rule (waitingOnYou: answered, quiet and stale rows are not waiting) and its own marks (isDone), so the
  // header's "N in Today" can never count what was closed there (#3145).
  return personEntries(r).filter(entry => waitingOnYou(entry) && !isDone(entry) && !looksDone(entry)).sort(byUrgency);
}
// Entity lists are records; what you owe lives in Today, reached by this one quiet line.
function listTodayLink(text) {
  return text ? el("a", { class: "list-today", href: "#", text }) : null;
}
// ---------- People: the page's name, then the table (owner, 2026-11-13, #2991, #2841) ----------
// «上来直接就是表格»: People is what has settled, so no count of who is waiting and no Today link.
// The title row holds the page's name, a filter and Columns; one grey line under the table says who
// is left out of it. The columns compare people; the phone shows the same rows as cards.
function relation(r) { return r.index?.relationship || null; }
// Ties fall to the last time both sides had written (relationship_stats.py), then any mail, then the page's own date.
function byTwoWay(a, b) {
  const x = relation(a), y = relation(b);
  return (y?.last_two_way || "").localeCompare(x?.last_two_way || "") || (y?.last_mail || "").localeCompare(x?.last_mail || "") || byActivity(a, b);
}
// The same liveness as Today's rows (todayGroups): not done, not quiet, not stale, not already answered.
function openItems(r, f = facts(r)) {
  return personEntries(r, f.open).filter(entry => !isDone(entry) && !looksDone(entry) && !entry.t.quiet
    && (entry.t.dir === "mine" ? waitingOnYou(entry) : !answered(entry) && !staleEntry(entry))).length;
}
// One row's values, worked out once per draw: sorting and cells read these, never recompute them.
function peopleRow(r) {
  const base = facts(r), chat = chatActivity(r);
  let f = base, rel = relation(r);
  if (chat) {
    // The later of mail and WeChat is the last contact; the 90-day count is both together (#3346).
    const day = calendarDay(chat.last), mail = isoDay(base.last);
    const later = !mail || day >= mail;
    f = later ? { ...base, last: day } : base;
    rel = { ...(rel || {}), messages_90d: (rel?.messages_90d || 0) + (chat.n90 || 0),
      last_from_you: later ? chat.mine : rel?.last_from_you };
  }
  return { r, f, open: openItems(r, base), org: personOrg(r), rel, status: known(r).status, src: personSources(r) };
}
// Mark only the rarer source (#3368): with most rows from WeChat, "微信" on every row says nothing, so the few
// mail people carry the mark instead (and the reverse). One source alone, or a tie, marks nothing.
let minorityMemo = null;
function minoritySource() {
  const people = inCategory("people"), key = people.length + ":" + (people[0]?.path || "");
  if (minorityMemo?.key === key) return minorityMemo.src;
  const n = { wechat: 0, mail: 0 };
  for (const r of people) for (const src of personSources(r)) if (src in n) n[src] += 1;
  const src = n.wechat && n.mail && n.wechat !== n.mail ? (n.wechat < n.mail ? "wechat" : "mail") : null;
  minorityMemo = { key, src };
  return src;
}
// #3157: a page titled by an address is a person whose name REM does not know; it never reads as a name.
function addressTitle(r) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(r.title || "").trim()); }
function personNameCell(d) {
  const name = addressTitle(d.r)
    ? el("a", { href: href(d.r), class: "nm-unknown", title: d.r.title }, [el("span", { text: t("Name unknown") }), el("span", { class: "nm-address", text: d.r.title })])
    : el("a", { href: href(d.r), title: d.r.title, text: d.r.title });
  const rare = minoritySource();
  const marks = (d.src || []).filter(src => src === rare).map(src => el("span", { class: "src-mark", text: t(src === "wechat" ? "WeChat" : "Mail") }));
  return el("span", { class: "nm" }, [name, ...marks, updatedMarker(d.r), notPersonButton(d.r, true)]);
}
// The organisation's name only; where it came from ("(their signature)") is its tooltip (#3157).
function personOrgCell(org) {
  const note = /\s*[（(]([^()（）]*)[)）]\s*$/.exec(org.name);
  const name = note ? org.name.slice(0, note.index) : org.name;
  return el("span", { class: "clamp", title: [org.full, note?.[1]].filter(Boolean).join(" · "), text: name });
}
function depthCell(status) {
  const mark = moon(status);
  mark.setAttribute("aria-hidden", "true");
  return el("span", { class: "depth" }, [mark, t(status)]);
}
const DEPTH_RANK = { "Investigated": 0, "Partly investigated": 1, "Mapped": 2 };
const blank = value => value === "" || value == null ? null : value;
// A sort key of null is a blank: it goes last whichever way the column is sorted.
const PEOPLE_COLUMNS = [
  { key: "name", label: "Name", sort: d => addressTitle(d.r) ? "\uffff" + d.r.title : d.r.title, cell: d => personNameCell(d) },
  // A nameless mailbox shows its address once, muted, in the name cell; the organisation cell stays empty (#3157).
  { key: "org", label: "Organisation", sort: d => addressTitle(d.r) ? null : blank(d.org?.name),
    cell: d => d.org && !addressTitle(d.r) ? personOrgCell(d.org) : textCell("") },
  { key: "last", label: "Last contact", num: true, desc: true, sort: d => blank(d.f.last), cell: d => dateCell(d.f.last, mappedContact(d.r)) },
  { key: "m90", label: "Messages · 90 days", num: true, desc: true, sort: d => blank(d.rel?.messages_90d),
    cell: d => d.rel?.messages_90d == null ? textCell("") : el("span", { class: "mono", text: String(d.rel.messages_90d) }) },
  { key: "lastby", label: "Who wrote last", sort: d => d.rel?.last_from_you == null ? null : d.rel.last_from_you ? 1 : 0,
    cell: d => d.rel?.last_from_you == null ? textCell("") : el("span", { text: t(d.rel.last_from_you ? "You" : "Them") }) },
  { key: "open", label: "Open items", num: true, desc: true, sort: d => d.open, cell: d => el("span", { class: d.open ? "mono" : "mono unk", text: String(d.open) }) },
  { key: "depth", label: "Page depth", sort: d => DEPTH_RANK[d.status] ?? 2, cell: d => depthCell(d.status) },
  // Chosen from Columns; off by default.
  { key: "role", label: "Role", extra: true, sort: d => blank(plainValue(d.f.role)), cell: d => textCell(d.f.role) },
  { key: "email", label: "Email", extra: true, sort: d => blank(d.f.email), cell: d => d.f.email ? peopleEmails(d.f.email) : textCell("") },
  { key: "phone", label: "Phone", extra: true, sort: d => blank(d.f.phone), cell: d => d.f.phone ? peoplePhones(d.f.phone) : textCell("") },
  ...[["contact", "Contact · 52 weeks"], ["trend", "Warming / cooling"], ["starts", "Who writes first"], ["replies", "Reply times"]].map(([key, label]) => ({
    key, label, extra: true, desc: key !== "replies", cell: d => relationshipCell(d.r, key), sort: d => {
      const x = d.rel;
      return blank(key === "contact" ? x?.weekly_messages.reduce((a, b) => a + b, 0) : key === "trend" ? x?.change_percent : key === "starts" ? x?.started_by_them_percent : x?.reply_seconds_them);
    } })),
  { key: "mails", label: "Mails", extra: true, num: true, desc: true, sort: d => blank(d.f.mails),
    cell: d => d.f.mails == null ? textCell("") : el("span", { class: "mono", title: d.f.sent != null ? t("{n} from them, {m} from you", { n: d.f.received, m: d.f.sent }) : "", text: String(d.f.mails) }) }];
// co-rem-people-columns holds the chosen keys; its older "more" / "less" read as all columns / the default ones.
function peopleColumnKeys(saved, columns = PEOPLE_COLUMNS) {
  if (saved === "more") return columns.map(col => col.key);
  const keys = (saved && saved !== "less" ? saved.split(",") : []).filter(key => columns.some(col => col.key === key));
  return keys.length ? ["name", ...keys.filter(key => key !== "name")] : columns.filter(col => !col.extra).map(col => col.key);
}
// The default is the visible Last contact column, newest first (review of #2991).
// The filter's words live here too, so a render (marking done, switching language) keeps them.
const PEOPLE_SORT = { sort: "last", desc: true, text: "" };
// Names sort as the reader reads them: pinyin order in Chinese, numbers by value.
function peopleOrder(col, desc, tie = (a, b) => byTwoWay(a.r, b.r)) {
  const collator = new Intl.Collator(uiLanguage === "zh" ? "zh-u-co-pinyin" : "en", { numeric: true, sensitivity: "base" });
  const sign = desc ? -1 : 1;
  return (a, b) => {
    const x = a.keys[col.key], y = b.keys[col.key];
    if (x === null || y === null) return x === y ? tie(a, b) : x === null ? 1 : -1;
    const order = typeof x === "string" ? collator.compare(x, y) : x - y;
    return order ? order * sign : tie(a, b);
  };
}
function peopleChooser(draw, config = {}) {
  const columns = config.columns || PEOPLE_COLUMNS, translate = config.translate || t;
  const chosen = () => config.chosen ? config.chosen() : peopleColumns;
  const button = el("button", { type: "button", class: "r4-btn sm ghost people-columns-open", "aria-expanded": "false", text: t("Columns") });
  const panel = el("div", { class: "people-columns", hidden: "" }, columns.filter(col => col.key !== "name").map(col => {
    const box = el("input", { type: "checkbox", value: col.key });
    box.checked = chosen().includes(col.key);
    box.onchange = () => {
      const keys = columns.map(c => c.key).filter(key => key === "name" || (key === col.key ? box.checked : chosen().includes(key)));
      if (config.choose) config.choose(keys); else peopleColumns = keys;
      readerStorage(config.storage || "co-rem-people-columns", keys.join(","));
      draw();
    };
    return el("label", {}, [box, translate(col.label)]);
  }));
  button.onclick = () => { panel.hidden = !panel.hidden; button.setAttribute("aria-expanded", String(!panel.hidden)); };
  return el("div", { class: "people-chooser" }, [button, panel]);
}
// Who is not in the table, in one grey line under it: never a count of who is waiting.
function peopleFoot() {
  const { held, service } = peopleExclusions(), missing = REM.people_coverage?.missing;
  const notes = [missing ? t("{n} people you write to have no page yet", { n: missing }) : "",
    held ? t("{n} possible contacts are held for review, outside this list.", { n: held }) : "",
    service ? t("{n} service or institutional senders are excluded from People.", { n: service }) : ""].filter(Boolean);
  return el("div", { class: "r4-foot" }, [notes.length ? el("p", { class: "held-note", text: notes.join(" · ") }) : null, contactDirectory(), friendFold("resting"), friendFold("quiet"), machineDirectory()]);
}
// WeChat friends under the table, collapsed (#3347, #3346): "resting" have nothing to read yet, "quiet" have chats but
// none in 90 days. One line per person, the name and, for quiet ones, when they last talked; each opens its page.
function friendFold(which) {
  const people = listRows("people").filter(r => which === "resting" ? restingFriends().has(r.path) : quietFriend(r))
    .sort(which === "quiet" ? (a, b) => (chatActivity(b).last || "").localeCompare(chatActivity(a).last || "") : (a, b) => a.title.localeCompare(b.title));
  if (!people.length) return null;
  const summary = which === "resting" ? "WeChat friends · no chats · {n}" : "WeChat friends · not in 90 days · {n}";
  const details = el("details", { class: "contact-directory friend-directory" });
  details.appendChild(el("summary", { text: t(summary, { n: people.length }) }));
  const find = el("input", { type: "search", class: "directory-find", "aria-label": t("Find a friend…"), placeholder: t("Find a friend…") });
  const list = el("ul", { class: "friend-list", "aria-label": t("WeChat friends table") });
  const more = el("button", { type: "button", class: "directory-more", text: t("Show more contacts") });
  let limit = 100;
  const draw = () => {
    const needle = find.value.trim().toLowerCase();
    const matched = people.filter(r => !needle || r.title.toLowerCase().includes(needle));
    list.replaceChildren(...matched.slice(0, limit).map(r => el("li", {}, [el("a", { href: href(r), text: r.title }),
      which === "quiet" ? el("span", { class: "when", text: shortDate(chatActivity(r).last) }) : null])));
    more.hidden = matched.length <= limit;
  };
  find.oninput = () => { limit = 100; draw(); };
  more.onclick = () => { limit += 100; draw(); };
  draw();
  details.appendChild(el("div", { class: "directory-body" }, [
    el("p", { class: "directory-note", text: t(which === "resting"
      ? "In your WeChat address book, with no chats on this Mac yet. REM investigates each one once a chat or a mail arrives."
      : "WeChat friends you have chatted with, but not in the last 90 days. Each keeps its page.") }),
    find, list, more]));
  return details;
}
function peopleView(items, config = {}) {
  const columns = config.columns || PEOPLE_COLUMNS, state = config.state || PEOPLE_SORT;
  const chosen = () => config.chosen ? config.chosen() : peopleColumns;
  const category = config.category || "people", translate = config.translate || t;
  const main = document.getElementById("main");
  const thead = el("thead"), tbody = el("tbody");
  const scroller = el("div", { class: "sheet-scroll people-scroll", tabindex: "0", role: "region", "aria-label": t("{name} table", { name: label(category) }) }, [el("table", { class: "sheet people-table " + (config.tableClass || "") }, [thead, tbody])]);
  const sortSelect = el("select", { class: "people-sort", "aria-label": t("Sort by") });
  const find = el("input", { type: "search", class: "people-find " + (config.findClass || ""), placeholder: translate(config.placeholder || "Filter name, company, role"), "aria-label": t("Filter {category}", { category: label(category).toLowerCase() }) });
  const empty = el("div", { class: "people-empty" });
  const moreWrap = el("div", { class: "people-more-wrap", style: "margin-top:12px" });
  let pageLimit = 100;
  const rows = config.rows || items.map(peopleRow);
  const urlFiltered = !!(route().tag || route().src);
  for (const d of rows) if (!d.text) d.text = [d.r.title, d.org?.name || "", plainValue(d.f.company), plainValue(d.f.role), d.f.email].join(" ").toLowerCase();
  const draw = () => {
    const cols = columns.filter(col => chosen().includes(col.key));
    if (!cols.some(x => x.key === state.sort)) Object.assign(state, { sort: cols[0].key, desc: !!cols[0].desc });
    const col = cols.find(x => x.key === state.sort);
    const needle = state.text.trim().toLowerCase();
    let shown = rows.filter(d => config.matches ? config.matches(d, needle) : !needle || d.text.includes(needle));
    if (col) for (const d of shown) (d.keys = d.keys || {})[col.key] ??= col.sort(d);
    shown.sort(col ? peopleOrder(col, state.desc, config.tie) : (a, b) => byTwoWay(a.r, b.r));
    if (config.visible) shown = config.visible(shown, col, state);
    const slice = category === "people" && shown.length > pageLimit ? shown.slice(0, pageLimit) : shown;
    const groupRow = d => el("tr", { class: "sheet-group" }, [el("th", { scope: "colgroup", colspan: String(cols.length) }, d.heading)]);
    thead.replaceChildren(el("tr", {}, cols.map(c => {
      const sorted = col === c;
      const button = el("button", { type: "button" }, [translate(c.label), el("span", { class: "arrow", "aria-hidden": "true", text: sorted ? (state.desc ? "↓" : "↑") : "↕" })]);
      button.onclick = () => { state.desc = sorted ? !state.desc : !!c.desc; state.sort = c.key; draw(); };
      return el("th", { scope: "col", class: "c-" + c.key + (c.key === "name" ? " name" : "") + (c.num ? " num" : ""), "aria-sort": sorted ? (state.desc ? "descending" : "ascending") : "none",
        ...(config.widths ? {style: `width:${(config.widths[c.key] || 10) / cols.reduce((sum, x) => sum + (config.widths[x.key] || 10), 0) * 100}%`} : {}) }, [button]);
    })));
    tbody.replaceChildren(...slice.map(d => d.heading ? groupRow(d) : el("tr", { "data-href": href(d.r), class: config.rowClass || "" }, cols.map(c => {
      const cell = c.cell(d, draw);
      return el("td", { class: "c-" + c.key + (c.key === "name" ? " name" : "") + (c.num ? " num" : ""), "data-label": translate(c.label), "data-empty": String(!!cell.classList?.contains("unk") && c.key !== "open") }, [cell]);
    }))));
    moreWrap.replaceChildren();
    if (slice.length < shown.length) {
      const moreBtn = el("button", { type: "button", class: "chip ghost people-more", text: uiLanguage === "zh" ? `显示更多（已显示 ${slice.length} / ${shown.length}）` : `Show more (${slice.length} of ${shown.length})` });
      moreBtn.onclick = () => { pageLimit += 200; draw(); };
      moreWrap.appendChild(moreBtn);
    }
    scroller.hidden = !shown.length;
    const clearAll = config.clear || (() => { find.value = state.text = ""; if (urlFiltered) location.hash = "#c=" + category; else { draw(); find.focus(); } });
    empty.replaceChildren(...(shown.length ? [] : (rows.length || (urlFiltered && inCategory(category).length)) ? [emptyState("No matching pages", "Clear filters →", "#c=" + category, clearAll)]
      : [emptyState(category === "orgs" ? "No pages yet" : "No contacts yet")]));
    sortSelect.replaceChildren(...cols.map(c => el("option", { value: c.key, text: translate(c.label) })));
    sortSelect.value = col ? col.key : "";
  };
  sortSelect.onchange = () => { state.sort = sortSelect.value; state.desc = !!columns.find(c => c.key === state.sort)?.desc; draw(); };
  find.value = state.text;
  find.oninput = () => { state.text = find.value; draw(); };
  // Enter opens the first match: type a name, press Enter, you are on the page.
  find.onkeydown = event => { const first = tbody.querySelector("tr[data-href]"); if (event.key === "Enter" && first) location.hash = first.dataset.href; };
  tbody.addEventListener("click", event => {
    const row = event.target.closest("tr[data-href]");
    if (row && !event.target.closest("a, button, input") && !String(window.getSelection())) location.hash = row.dataset.href;
  });
  draw();
  main.appendChild(el("div", { class: "r4 r4-people wide " + (config.className || "") }, [
    el("div", { class: "people-head" }, [el("h1", { text: config.title || label(category) }), config.views || null, find, sortSelect, peopleChooser(draw, config)]), config.filters ? config.filters(draw) : null, scroller, moreWrap, empty, config.foot ? config.foot() : category === "people" ? peopleFoot() : null]));
}

function categoryCount(c, counts, total) {
  if (c === "people" && REM.people_coverage) {
    const { covered, total } = REM.people_coverage;
    return t("{n} of {m} qualifying correspondents have a page", { n: covered, m: total })
      + (total ? " · " + Math.round(100 * covered / total) + "%" : "");
  }
  if (c === "skills") return t(total === 1 ? "{n} skill" : "{n} skills", { n: total });
  const unit = uiLanguage === "zh" ? ({ people: " 人", orgs: " 个组织", projects: " 个项目", skills: " 项", decisions: " 项", principles: " 条" })[c] || " 页" : " pages";
  return counts ? t("{n} written of {m}", { n: counts.written, m: counts.mapped, unit }) : t("{n}{unit}", { n: total, unit });
}
// Every list but Sessions (which has its own tag filter) takes the tag chips under its head (#3093 point 3).
function tagBarInto(c) {
  if (!TAG_LISTS.includes(c)) return;
  const main = document.getElementById("main"), bar = tagBar(c, inCategory(c));
  const title = main.querySelector(".category-head") || main.querySelector("h1");
  const head = title && title.parentElement !== main && !title.classList.contains("category-head") ? title.parentElement : title;
  // 来源 sits right under the heading on People (#3346), the tag chips under it.
  const sources = c === "people" && !main.querySelector(".source-bar") ? sourceBar() : null;
  if (sources) head ? head.after(sources) : main.prepend(sources);
  if (!bar || main.querySelector(".tag-bar")) return;
  // Right under the heading row (the title and its finder), above the rows it filters.
  const after = sources || head;
  after ? after.after(bar) : main.prepend(bar);
}
// 来源: People from mail or from WeChat (#3346); shown once both are there. One tap filters, a second clears.
function sourceBar() {
  const people = inCategory("people"), active = route().src;
  const counts = { wechat: people.filter(r => personSources(r).includes("wechat")).length,
    mail: people.filter(r => personSources(r).includes("mail")).length };
  if (!counts.wechat || !counts.mail) return null;
  const link = (src, words) => el("a", { class: "chip" + (src === active ? " on" : ""), href: src && src !== active ? "#c=people&src=" + src : "#c=people",
    "aria-current": src === active ? "true" : null }, [words, ...(src ? [" ", el("span", { class: "chip-n", text: String(counts[src]) })] : [])]);
  return el("nav", { class: "open-chips source-bar", "aria-label": t("Source") }, [
    el("span", { class: "bar-label", text: t("Source") }),
    link("", t("All")), link("wechat", t("WeChat")), link("mail", t("Mail"))]);
}
function category(c) {
  if (c === "keys") { keysView(); return; }
  if (c === "sessions") { sessionsView(); return; }
  if (c === "projects" && inCategory("projects").length) { projectsView(); return; }
  if (c === "orgs") { orgsView(); return; }
  if (c === "skills" && inCategory("skills").length) { skillsView(); return; }
  if (c === "knowledge") { topicList(); return; }
  if (c === "agenda") { agendaView(); return; }
  const main = document.getElementById("main");
  main.textContent = "";
  const items = listRows(c);
  if (c === "people") {
    // The table keeps people in recent contact; WeChat friends with nothing to read yet (#3347) and those not talked
    // with in 90 days (#3346) fold under it instead of filling it with dashes.
    peopleView(items.filter(r => !restingFriends().has(r.path) && !quietFriend(r)));
    return;
  }
  // The page names itself and nothing more (#2994): the order and the cards say what a sentence used to. The
  // count stays as a number beside the name; Skills puts it in its finder instead.
  const counts = (REM.counts || {})[c];
  const other = c === "people" ? (REM.contact_candidates || []).length : 0;
  const hasCoverage = c === "people" && REM.people_coverage?.total;
  const head = el("div", { class: "category-head" }, [el("h1", { text: label(c) }),
    c !== "skills" && (items.length || other || hasCoverage) ? el("span", { class: "mono", text: categoryCount(c, counts, items.length)
      + (other ? " · " + t("{n} other contacts", { n: other }) : "") }) : null]);
  main.appendChild(head);
  if (c === "people" && REM.people_coverage?.missing) main.appendChild(el("p", { class: "directory-note",
    text: t("{n} people you write to have no page yet", { n: REM.people_coverage.missing }) }));
  const { held, service } = c === "people" ? peopleExclusions() : { held: 0, service: 0 };
  if (held || service) {
    const note = el("p", { class: "held-note" }, [el("span", { text:
      (held ? t("{n} possible contacts are held for review, outside this list.", { n: held }) : "") +
      (service ? (held ? " " : "") + t("{n} service or institutional senders are excluded from People.", { n: service }) : "") })]);
    main.appendChild(note);
  }
  if (!items.length && !other && !(c === "people" && (REM.contact_coverage || {}).incomplete)) {
    main.appendChild(emptyState(c === "people" ? "No contacts yet" : "No pages yet"));
    return;
  }
  if (c === "people") {
    const directory = contactDirectory();
    if (directory) main.appendChild(directory);
  }
  if (COLUMNS[c] && items.length) main.appendChild(sheet(c, items));
  else if (items.length) main.appendChild(el("ul", { class: "hits" + (c === "skills" ? " skills" : "") }, items.sort(byActivity).map(r => row(r))));
}

// ---------- 钥匙 / Keys (#3137, owner 2026-11-19: «类似于 LastPass 或者 1Password 那种») ----------
// A key's page is what the secret is; its value is in this Mac's Keychain (rem/vault.py), never in the notebook.
// Copy and Show reach the Keychain through the Host, on this computer only (its own prompt: Touch ID or the login
// password); a copy leaves the clipboard after 30 s. A snapshot, the phone included, shows the rows and says
// where the value is, never the value.
Object.assign(UI.zh, { "Service": "服务", "Account": "账号", "Purpose": "用途", "Used in": "用在", "Rotated": "最近更换", "Expires": "到期",
  "Who else has it": "还有谁知道", "Created": "建立", "Link": "链接", "Vault": "保存在",
  "Add a key": "添加钥匙", "Import a password export (CSV)": "导入密码导出文件（CSV）", "Import a CSV export": "导入 CSV 文件", "Password or key": "密码或密钥", "Importing from {name} — approve the Keychain prompt…": "正在从 {name} 导入——请在钥匙串弹窗里点允许…", "Filed {n} keys from {name}; {m} had no password.": "从 {name} 导入了 {n} 条，{m} 条没有密码。", "One-click import. Values go to the Keychain; the notebook keeps only what each key is.": "一键导入。密码存进钥匙串，笔记本只记每条是什么。", "Import from a browser in one click — no typing.": "从浏览器一键导入，不用手打。",
  "Save to the Keychain": "存进钥匙串", "Copy": "复制", "Show": "显示", "Hide": "隐藏",
  "Copied · cleared from the clipboard in 30 s": "已复制 · 30 秒后从剪贴板清除",
  "The value is in this Mac's Keychain. Copy it from the reader on this Mac.": "密码在这台电脑的钥匙串里，只能在这台电脑上的阅读器里复制。",
  "Filed {n} keys; {m} rows had no password. Delete the export file now: it holds every password in plain text.":
    "已存入 {n} 个钥匙，{m} 行没有密码。现在请删除那个导出文件：里面是明文的全部密码。",
  "No keys yet. Add one, or import a password manager's export.": "还没有钥匙。添加一个，或导入密码管理器的导出文件。",
  "Saved · the value is in the Keychain": "已存好 · 密码在钥匙串里" });
function keyFact(r, label) { return plainLine(((parseFacts(r).get(label) || [])[0] || {}).value || "").replace(/^Unknown$/, ""); }
// The site a key belongs to, for grouping (#3326): an import of 335 browser logins is mostly one page per origin, so
// the list groups by registrable domain (accounts.google.com and mail.google.com are both google.com).
// The page title, not the Service fact: plainLine reads a leading "10." as a list number, so an IP like 10.0.0.1
// came back as "0.0.1" (#3327). The title is the imported origin as written.
function keyHost(r) { return r.title || keyFact(r, "Service"); }
function keySite(r) {
  const raw = (keyHost(r) || "").toLowerCase().replace(/^[a-z]+:\/\//, "").split(/[\/?#\s]/)[0].replace(/:\d+$/, "");
  if (!raw.includes(".") || /^[\d.]+$/.test(raw)) return raw || r.title;
  const parts = raw.split(".").filter(Boolean);
  const country = parts.length > 2 && parts.at(-1).length === 2 && /^(co|com|org|net|gov|edu|ac)$/.test(parts.at(-2));
  return parts.slice(country ? -3 : -2).join(".");
}
// Groups larger than KEY_GROUP_OPEN start folded; above KEY_MANY keys in all, every group starts folded (#3326).
const KEY_GROUP_OPEN = 5, KEY_MANY = 30;
function keysView() {
  const main = document.getElementById("main"), items = inCategory("keys").sort((a, b) => keySite(a).localeCompare(keySite(b)) || a.title.localeCompare(b.title));
  main.textContent = "";
  const head = el("div", { class: "category-head" }, [el("h1", { text: label("keys") }), items.length ? el("span", { class: "mono", text: String(items.length) }) : null]);
  // What is on the page, in one line: the vault and co's own keys, so "none" and "29" never sit together (#3326).
  const summary = el("p", { class: "key-summary", text: items.length ? t("{n} in the Keychain", { n: items.length }) : "" });
  // With no keys yet, open the adder so the one-click import buttons are the first thing seen, not hidden
  // inside a collapsed "Add a key" disclosure. Once there are keys, keep it collapsed so it doesn't nag.
  main.append(head, summary, liveHere() ? keyAdder(!items.length) : el("p", { class: "quiet-line", text: t("The value is in this Mac's Keychain. Copy it from the reader on this Mac.") }));
  if (items.length) main.appendChild(keysTable(items));
  // The empty line shows only when nothing at all is here: no vault keys and none of co's own (keys.env).
  if (!liveHere()) {
    if (!items.length) main.appendChild(emptyState("No keys yet. Add one, or import a password manager's export."));
    return;
  }
  const empty = el("div", { hidden: "" }, [emptyState("No keys yet. Add one, or import a password manager's export.")]);
  if (!items.length) main.appendChild(empty);
  main.appendChild(keysEnvSection(own => {
    if (!items.length && !own) empty.hidden = false;
    if (own) summary.textContent = items.length ? t("{n} in the Keychain · co's own {m}", { n: items.length, m: own })
      : t("Nothing imported into the Keychain yet · co's own {m}, below", { m: own });
  }));
}
// Every key grouped by site (#3326). Above KEY_MANY keys every group starts as one row, "<site> · N 条", so hundreds of
// imported sites read as a scannable list; below it a group opens when small. A single-entry site is a group like the
// rest, sorted with them. Inside a group the host shows only where it differs from the group's name, and a column whose
// every value is the same (all "sign in") is dropped. A phone gets a list, not a five-column table: the account on line
// one, host and purpose muted on line two. A search box opens the groups it matches. Values are never in the page.
function keysTable(items) {
  const groups = new Map();
  for (const r of items) groups.set(keySite(r), [...(groups.get(keySite(r)) || []), r]);
  const sites = [...groups.keys()].sort((a, b) => a.localeCompare(b));
  const many = items.length > KEY_MANY, phone = matchMedia("(max-width: 719px)").matches;
  const entry = r => ({ r, site: keySite(r), account: keyFact(r, "Account") || r.title, host: keyHost(r),
    purpose: keyFact(r, "Purpose"), used: keyFact(r, "Used in"), rotated: keyFact(r, "Rotated") });
  const all = items.map(entry);
  const varies = field => new Set(all.map(e => e[field])).size > 1;
  const showHost = all.some(e => e.host !== e.site);
  const cols = [["Account", "account"], ...(showHost ? [["Service", "host"]] : []),
    ...[["Purpose", "purpose"], ["Used in", "used"], ["Rotated", "rotated"]].filter(([, field]) => varies(field))];
  const blocks = sites.map(site => {
    const members = groups.get(site).map(entry);
    const open = !many && members.length <= KEY_GROUP_OPEN;
    const toggle = el("button", { type: "button", class: "key-group-toggle", "aria-expanded": String(open) }, [
      el("span", { class: "key-group-site", text: site }),
      el("span", { class: "key-group-count", text: "· " + (members.length === 1 ? t("1 key") : t("{n} keys", { n: members.length })) })]);
    const find = e => [e.account, e.host, e.r.title].join(" ").toLowerCase();
    const link = e => el("a", { href: href(e.r), text: e.account });
    const host = e => (e.host !== site ? e.host : "");
    const rows = members.map(e => phone
      ? el("li", { class: "key-row key-entry", "data-site": site, "data-find": find(e) }, [link(e),
        el("span", { class: "key-entry-meta", text: [host(e), varies("purpose") ? e.purpose : ""].filter(Boolean).join(" · ") })])
      : el("tr", { class: "key-row", "data-site": site, "data-find": find(e) }, cols.map(([, field]) =>
        field === "account" ? el("td", { class: "name" }, [link(e)]) : el("td", {}, [textCell(field === "host" ? host(e) : e[field])]))));
    for (const row of rows) row.hidden = !open;
    const head = phone ? el("li", { class: "key-group", "data-site": site }, [toggle])
      : el("tr", { class: "key-group", "data-site": site }, [el("td", { colspan: String(cols.length) }, [toggle])]);
    const setOpen = value => { toggle.setAttribute("aria-expanded", String(value)); for (const row of rows) row.hidden = !value; };
    toggle.onclick = () => setOpen(toggle.getAttribute("aria-expanded") !== "true");
    return { site, head, rows, toggle, setOpen };
  });
  const body = blocks.flatMap(b => [b.head, ...b.rows]);
  const list = phone ? el("ul", { class: "key-list" }, body)
    : el("table", { class: "sheet" }, [el("thead", {}, [el("tr", {}, cols.map(([name]) => el("th", { text: t(name) })))]), el("tbody", {}, body)]);
  const find = el("input", { type: "search", class: "key-search", placeholder: t("Find a site or account"), "aria-label": t("Find a site or account") });
  const remembered = new Map(blocks.map(b => [b.site, b.toggle.getAttribute("aria-expanded") === "true"]));
  find.oninput = () => {
    const q = find.value.trim().toLowerCase();
    for (const b of blocks) {
      if (!q) { b.head.hidden = false; b.setOpen(remembered.get(b.site)); continue; }
      const siteHit = b.site.includes(q), hits = b.rows.map(row => siteHit || row.dataset.find.includes(q));
      b.head.hidden = !hits.some(Boolean);
      b.toggle.setAttribute("aria-expanded", String(hits.some(Boolean)));
      b.rows.forEach((row, i) => { row.hidden = !hits[i]; });
    }
  };
  for (const b of blocks) b.toggle.addEventListener("click", () => { if (!find.value.trim()) remembered.set(b.site, b.toggle.getAttribute("aria-expanded") === "true"); });
  return el("div", { class: "keys-list" }, [find, el("div", { class: "sheet-scroll keys-sheet" + (phone ? " keys-phone" : ""), tabindex: "0", role: "region",
    "aria-label": t("{name} table", { name: label("keys") }) }, [list])]);
}
// co's own credentials (#3305, owner 2026-11-22: «我们自己的密钥是在 keys.env 里面»), grouped by service (#3326):
// one row per service with "connected" and a count; settings that aren't secrets (scopes, expiry times, flags, the
// browser engine, the agent address) fold under 设置项. The Host sends names only; a value never reaches it.
function keysEnvSection(onLoad = () => {}) {
  const loading = el("p", { class: "key-import-note keys-env-loading", role: "status", text: t("Reading co's own keys…") });
  const box = el("section", { class: "keys-env" }, [loading]);
  hostPost("/rem/keys/env", {}).then(reply => {
    loading.remove();
    const services = reply.ok ? reply.services || [] : [], settings = reply.ok ? reply.settings || [] : [];
    const own = services.reduce((n, s) => n + s.count, 0);
    onLoad(own);
    if (!reply.ok || (!services.length && !settings.length && !reply.error)) { box.hidden = true; return; }
    box.append(...[el("h2", { class: "keys-env-h", text: t("co's own keys") }),
      el("p", { class: "key-import-note", text: t("They live in {where}. Values stay hidden.", { where: reply.where }) }),
      reply.error ? el("p", { class: "key-import-note", text: reply.error }) : null,
      services.length ? el("ul", { class: "keys-env-list" }, services.map(s => el("li", {}, [el("span", { class: "keys-env-service", text: s.service }),
        el("span", { class: "keys-env-state", text: t("Connected") }), el("span", { class: "keys-env-mask", text: s.count === 1 ? t("1 key") : t("{n} keys", { n: s.count }) })]))) : null,
      settings.length ? el("details", { class: "keys-env-settings" }, [el("summary", { text: t("Settings ({n})", { n: settings.length }) }),
        el("ul", { class: "keys-env-list" }, settings.map(name => el("li", {}, [el("code", { class: "keys-env-name", text: name })])))]) : null]
      .filter(Boolean));
    box.hidden = false;
  });
  return box;
}
function keyAdder(open = false) {
  const field = (name, type = "text") => el("input", { type, name, placeholder: t(name), "aria-label": t(name), autocomplete: type === "password" ? "new-password" : "off" });
  const service = field("Service"), account = field("Account"), secret = field("Password or key", "password"), purpose = field("Purpose");
  const status = el("p", { class: "key-status", role: "status" });
  const save = el("button", { type: "submit", class: "btn-act", text: t("Save to the Keychain") });
  const form = el("form", { class: "key-add" }, [service, account, secret, purpose, save]);
  form.onsubmit = async event => {
    event.preventDefault();
    save.disabled = true;
    const reply = await hostPost("/rem/keys/add", { service: service.value, account: account.value, secret: secret.value, purpose: purpose.value });
    if (reply.ok) secret.value = "";
    save.disabled = false;
    status.setAttribute("role", reply.ok ? "status" : "alert");
    status.textContent = reply.ok ? t("Saved · the value is in the Keychain") : reply.error || t("Could not do that. Try again.");
  };
  const summary = el("summary", { text: t("Add a key") });
  // The heading above already says 一键导入; this line only says where the values go (#3316 review).
  const safety = () => el("p", { class: "key-import-lead", text: t("Values go to the Keychain; the notebook keeps only what each key is.") });
  const importer = keyImporter();
  if (open) {
    // No keys yet: the import is the page's one action (he wants to click, not type). Typing one in by hand is the
    // folded fallback, and its save is an outline button so nothing competes with the sources (#3305 review).
    save.className = "btn-action";
    const manual = el("details", { class: "key-manual" }, [el("summary", { text: t("Add one by hand") }), form, status]);
    return el("details", { class: "key-adder", open: "" }, [summary, importer, safety(), manual]);
  }
  return el("details", { class: "key-adder" }, [summary, form, status, safety(), importer]);
}
// One-click import (#3305, owner 2026-11-22: «那个按钮应该就是直接一键导入吧。里面可以选择 Chrome，还有 macOS
// 本身、Apple 本身都可以导入»). One button opens the sources. A browser or the macOS Keychain waits on the
// system's 允许 prompt in a visible step with a cancel; the outcome is a block, never a one-line status he misses
// («点击了导入之后，并没有给我弹出一个框»). Apple Passwords cannot be read by another program, so it says how to
// export a CSV and offers that file — the honest path, not a button that pretends.
const KEY_IMPORT_ERRORS = {
  no_gui: "REM is running in a background session (a background process restarted it), so macOS cannot show the Keychain prompt here. Run this in this Mac's Terminal, then import again:",
  denied: "The Keychain prompt was declined, so nothing was imported. Import again and choose Allow.",
  timeout: "No one clicked Allow in the Keychain prompt within two minutes. Import again.",
  not_found: "{name} has no saved-password key on this Mac. Is it installed and signed in?",
  no_data: "{name} has no saved passwords on this Mac.",
};
Object.assign(UI.zh, {
  "One-click import": "一键导入", "Import from": "从哪里导入", "macOS Keychain": "macOS 钥匙串", "asks once per password": "每条都会问一次",
  "Apple Passwords": "Apple 密码", "via a CSV export": "先导出 CSV", "A CSV export": "CSV 导出文件", "Cancel": "取消",
  "Waiting for you to click Allow in the Keychain prompt…": "等你在钥匙串弹窗里点「允许」…",
  "macOS asks once for each password.": "每条密码 macOS 都会问一次。",
  "macOS asks once for {name}'s saved passwords.": "macOS 会问一次能不能读 {name} 保存的密码。",
  "Imported {n} keys from {name}.": "从 {name} 导入了 {n} 条。", "and {n} more": "等另外 {n} 个",
  "{n} had no password and were skipped.": "{n} 条没有密码，跳过了。", "Stopped early: {why}": "中途停了：{why}",
  "the Keychain stopped answering": "钥匙串没有再回应", "the CSV export": "CSV 导出文件",
  "REM is running in a background session (a background process restarted it), so macOS cannot show the Keychain prompt here. Run this in this Mac's Terminal, then import again:":
    "REM 现在运行在后台会话里（是被后台程序重启的），macOS 没法在这里弹出钥匙串授权窗。在这台 Mac 的「终端」里运行下面这行，然后回来再导入一次：",
  "The Keychain prompt was declined, so nothing was imported. Import again and choose Allow.": "钥匙串弹窗里点了「拒绝」，所以没有导入。再导入一次，选「允许」。",
  "No one clicked Allow in the Keychain prompt within two minutes. Import again.": "两分钟内没等到你在钥匙串弹窗里点「允许」。再导入一次。",
  "{name} has no saved-password key on this Mac. Is it installed and signed in?": "这台 Mac 上的 {name} 没有保存密码用的钥匙。装过并登录过吗？",
  "{name} has no saved passwords on this Mac.": "{name} 在这台 Mac 上没有保存的密码。",
  "Delete the export file now: it holds every password in plain text.": "现在就把导出文件删掉：里面每个密码都是明文。",
  "Apple's Passwords app doesn't let other programs read it. In Passwords, choose File → Export All Passwords…, save the CSV, then pick it here:":
    "Apple 的「密码」App 不让其他程序直接读取。在「密码」App 里选 文件 → 导出所有密码…，存成 CSV，再在这里选这个文件：",
  "Pick a password export from 1Password, LastPass, Bitwarden, Chrome or Safari:": "选一个从 1Password、LastPass、Bitwarden、Chrome 或 Safari 导出的密码文件：",
  "Add one by hand": "手动添加一条", "Values go to the Keychain; the notebook keeps only what each key is.": "密码存进钥匙串，笔记本只记每条是什么。", "co's own keys": "co 自己用的密钥", "They live in {where}. Values stay hidden.": "存在 {where} 里，数值不显示。", "hidden": "已隐藏",
  "{n} in the Keychain": "钥匙串里 {n} 条", "{n} in the Keychain · co's own {m}": "钥匙串里 {n} 条 · co 自己用的 {m} 项",
  "Nothing imported into the Keychain yet · co's own {m}, below": "钥匙串里还没有导入的密码 · co 自己用的 {m} 项在下面",
  "{n} keys": "{n} 条", "1 key": "1 条", "Find a site or account": "找网站或账号", "Connected": "已连接", "Settings ({n})": "设置项（{n}）" });
function keyImporter() {
  const result = el("div", { class: "key-import-result", hidden: "" });
  const file = el("input", { type: "file", accept: ".csv,text/csv", "aria-label": t("Import a password export (CSV)") });
  const waiting = el("div", { class: "key-import-wait", role: "status", hidden: "" });
  // 一键导入 is the heading and the sources ARE its buttons, always in view: a button that opened them did nothing
  // visible once they were shown (#3305 review). A wait disables them so one prompt is asked at a time.
  const chooser = el("div", { class: "key-import-chooser", role: "group", "aria-label": t("Import from") });
  const show = node => {
    waiting.hidden = node !== waiting;
    result.hidden = node !== result;
    for (const button of chooser.querySelectorAll("button")) button.disabled = node === waiting;
  };
  const outcome = (reply, name) => {
    result.textContent = "";
    if (reply.ok) {
      result.className = "key-import-result ok";
      const sites = reply.sites || [];
      result.append(...[el("p", { class: "key-import-head", text: t("Imported {n} keys from {name}.", { n: reply.filed, name }) }),
        sites.length ? el("p", { class: "key-import-sites", text: sites.slice(0, 12).join(" · ") + (sites.length > 12 ? " · " + t("and {n} more", { n: sites.length - 12 }) : "") }) : null,
        reply.skipped ? el("p", { class: "key-import-note", text: t("{n} had no password and were skipped.", { n: reply.skipped }) }) : null,
        reply.stopped ? el("p", { class: "key-import-note", text: t("Stopped early: {why}", { why: t(KEY_IMPORT_ERRORS[reply.stopped] || "the Keychain stopped answering", { name }) }) }) : null]
        .filter(Boolean));  // append() would print a null as the word "null"
    } else {
      result.className = "key-import-result error";
      result.setAttribute("role", "alert");
      const words = KEY_IMPORT_ERRORS[reply.reason];
      result.append(el("p", { class: "key-import-head", text: reply.code === 0 ? t(HOST_LOST_WORDS)
        : words ? t(words, { name }) : reply.error || t("Could not do that. Try again.") }));
      if (reply.reason === "no_gui") result.append(el("code", { class: "key-import-fix", text: "co rem open" }));
    }
    show(result);
  };
  const run = async (body, name, hint) => {
    let cancelled = false;
    const cancel = el("button", { type: "button", class: "btn-quiet", text: t("Cancel") });
    cancel.onclick = () => { cancelled = true; show(null); };
    waiting.textContent = "";
    waiting.append(el("span", { class: "key-spin", "aria-hidden": "true" }),
      el("div", {}, [el("p", { class: "key-import-head", text: t("Waiting for you to click Allow in the Keychain prompt…") }),
        el("p", { class: "key-import-note", text: hint })]), cancel);
    show(waiting);
    const reply = await hostPost("/rem/keys/import", body);
    if (!cancelled) outcome(reply, name);
  };
  const csvPanel = lead => el("div", { class: "key-import-csv" }, [el("p", { class: "key-import-note", text: lead }), file]);
  file.onchange = async () => {
    if (!file.files[0]) return;
    const reply = await hostPost("/rem/keys/import", { csv: await file.files[0].text() });
    file.value = "";
    outcome(reply.ok ? { ...reply, sites: reply.sites || [] } : reply, t("the CSV export"));
    if (reply.ok) result.append(el("p", { class: "key-import-note", text: t("Delete the export file now: it holds every password in plain text.") }));
  };
  const source = (id, name, note) => {
    const button = el("button", { type: "button", class: "key-source", "data-source": id }, [el("span", { text: name }), note ? el("small", { text: note }) : null]);
    button.onclick = () => {
      if (id === "apple") { result.textContent = ""; result.className = "key-import-result"; result.removeAttribute("role");
        result.append(csvPanel(t("Apple's Passwords app doesn't let other programs read it. In Passwords, choose File → Export All Passwords…, save the CSV, then pick it here:"))); show(result); return; }
      if (id === "csv") { result.textContent = ""; result.className = "key-import-result"; result.removeAttribute("role");
        result.append(csvPanel(t("Pick a password export from 1Password, LastPass, Bitwarden, Chrome or Safari:"))); show(result); return; }
      run({ source: id }, name, id === "keychain" ? t("macOS asks once for each password.") : t("macOS asks once for {name}'s saved passwords.", { name }));
    };
    return button;
  };
  chooser.append(source("chrome", "Chrome"), source("edge", "Edge"), source("brave", "Brave"),
    source("keychain", t("macOS Keychain"), t("asks once per password")), source("apple", t("Apple Passwords"), t("via a CSV export")),
    source("csv", t("A CSV export")));
  return el("div", { class: "key-importers" }, [el("h2", { class: "key-import-title", text: t("One-click import") }),
    el("p", { class: "key-import-note", text: t("Import from a browser in one click — no typing.") }), chooser, waiting, result]);
}
function keyPage(r) {
  const rows = ["Service", "Account", "Purpose", "Who else has it", "Used in", "Created", "Rotated", "Expires", "Link", "Vault"]
    .map(name => [name, keyFact(r, name)]).filter(([, value]) => value);
  const value = el("code", { class: "key-value", hidden: "" }), status = el("span", { class: "key-status", role: "status" });
  const reveal = async () => { const reply = await hostPost("/rem/keys/reveal", { page: r.path }); if (!reply.ok) status.textContent = reply.error || t("Could not do that. Try again."); return reply.ok ? reply.secret : null; };
  const copy = el("button", { type: "button", class: "btn-act", text: t("Copy") }), show = el("button", { type: "button", class: "btn-quiet", text: t("Show") });
  copy.onclick = async () => {
    const secret = await reveal();
    if (secret == null) return;
    await navigator.clipboard.writeText(secret);
    status.textContent = t("Copied · cleared from the clipboard in 30 s");
    setTimeout(() => navigator.clipboard.writeText("").catch(() => {}), 30000);
  };
  show.onclick = async () => {
    if (!value.hidden) { value.hidden = true; value.textContent = ""; show.textContent = t("Show"); return; }
    const secret = await reveal();
    if (secret == null) return;
    Object.assign(value, { hidden: false, textContent: secret });
    show.textContent = t("Hide");
    setTimeout(() => { value.hidden = true; value.textContent = ""; show.textContent = t("Show"); }, 15000);
  };
  const notesSec = section(r, "notes");
  const notesText = notesSec ? notesSec.text.trim() : "";
  const showNotes = notesText && !/^The secret is in this Mac's Keychain/i.test(notesText);
  const actions = liveHere() ? el("div", { class: "key-actions" }, [copy, show, status, value])
    : el("p", { class: "quiet-line", text: t("The value is in this Mac's Keychain. Copy it from the reader on this Mac.") });
  return el("div", { class: "r4 key-page" }, [
    el("header", { class: "page-head" }, [el("h1", { text: r.title }), actions]),
    el("dl", { class: "pc-list key-facts" }, rows.map(([name, text]) => el("div", { class: "pc-row" }, [el("dt", { class: "pc-k", text: t(name) }),
      el("dd", { class: "pc-v" }, [/^https?:\/\//.test(text) ? el("a", { href: text, target: "_blank", rel: "noopener", text: text.replace(/^https?:\/\//, "") }) : el("span", { text })])]))),
    showNotes ? el("section", { class: "key-notes", style: "margin-top:20px" }, [el("h2", { class: "section", text: t("Notes") }), el("div", { class: "note", html: markdown(notesText, r.path) })]) : null]);
}

