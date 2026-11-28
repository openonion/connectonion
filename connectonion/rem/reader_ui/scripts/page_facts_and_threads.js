// ---------- reading a page's parts ----------
// Open threads name who owes whom (rem-page-person): the reader shows the direction.
// Pages name the owner as "the user", "you" or by first name ("Ellis promised…").
// The earliest phrase that says who must act decides the thread's direction.
let OWING = null;
function owing() {
  if (OWING) return OWING;
  const owner = REM.owner && byPath(REM.owner);
  const first = owner ? owner.title.trim().split(/\s+/)[0].replace(/[.*+?^${}()|[\]\\]/g, "\\$&") : "";
  // "User owes pickup of the card" (1.9.2b1) names the owner without "the".
  const me = "(?:the user|user|you" + (first ? "|" + first : "") + ")";
  // The owner asking or waiting on someone is their debt: "Ellis asked Anselm to arrange a call" (1.9.2b3).
  const chasing = "\\b" + me + "\\s+(?:asked|asks|requested|requests|reminded|chased|is awaiting|awaits|awaited|is waiting (?:on|for)|was waiting (?:on|for))\\s+(?!" + me + "\\b)";
  OWING = {
    // An offer of something ("offered Mara a trial") is optional; an offer to do something is owed.
    mine: new RegExp("\\b" + me + "(?:['’]s)?\\s+(?:has |have |had |still )?(?:owes?|owed|promised|offered to|agreed|needs? to|must|should|said (?:he|she|they) would|to (?:send|reply|sign|confirm|pay|review|decide)|has not|have not|hasn't|haven't)\\b" +
      "|^\\s*" + me + "\\s*:|\\b(?:asks?|asked|requests?|requested|wants|invited)\\s+" + me + "\\s+to\\b|\\b(?:requested|asked for|awaits?|awaiting|waiting (?:on|for))\\s+(?:" + me + "(?:['’]s)?|your)\\b|\\brequested (?:confirmation|approval|a reply|an answer)\\b|\\byou owe\\b", "i"),
    theirs: new RegExp(chasing + "|\\b(?:owes?|owed) (?:the user|you)\\b|\\bwaiting (?:on|for) (?:them|him|her|their)\\b|\\bunanswered\\b|\\b(?:he|she|they) (?:has|have) not (?:replied|answered|sent|confirmed)\\b|\\bno reply\\b|\\b[A-Z][\\w-]+(?:['’]s)? (?:promised|is expected to|agreed to|owes|said (?:he|she|they) would)\\b|\\bpromised\\b")
  };
  return OWING;
}
function direction(text) {
  // Keep structured prefixes in step with census.py direction() (UI audit #4).
  const owner = REM.owner && byPath(REM.owner);
  const first = owner ? owner.title.trim().split(/\s+/)[0].replace(/[.*+?^${}()|[\]\\]/g, "\\$&") : "";
  const me = "(?:the user|user|you" + (first ? "|" + first : "") + ")";
  const prefix = text.replace(/^\s*(?:[-*+]\s+)?/, "").replaceAll("**", "");
  const own = new RegExp("^" + me + "\\s+(owes?|asked)\\b", "i").exec(prefix);
  if (own) return own[1].toLowerCase() === "asked" ? "theirs" : "mine";
  const debt = /^([^:;!?：；！？]+?)\s+owes?\s+(.+)/i.exec(prefix);
  if (debt && /^[A-Z]/.test(debt[1]) && debt[1].split(/\s+/).length <= 6 && !/[，,]|\b(?:said|would|that|what)\b/i.test(debt[1]))
    return new RegExp("^" + me + "\\b", "i").test(debt[2]) ? "theirs" : "third";
  const { mine, theirs } = owing();
  const a = text.search(mine), b = text.search(theirs);
  return a < 0 && b < 0 ? "plain" : a < 0 ? "theirs" : b < 0 ? "mine" : a <= b ? "mine" : "theirs";
}
// Project requests can be about work to revisit, without naming a debtor.
function projectDirection(text) {
  const dir = direction(text);
  const first = (REM.owner && byPath(REM.owner)?.title.split(/\s+/)[0] || "").toLowerCase();
  const ownerNamed = first && text.toLowerCase().split(/\W+/).includes(first);
  if (dir === "mine" && (ownerNamed || /\b(?:you|your|user)\b/i.test(text))) return dir;
  if (dir === "third") return dir;
  const explicit = /\bowes? (?:you|the user)\b|\b(?:he|she|they) (?:promised|agreed|owe|has not|have not)\b|\b[A-Z][\w-]+ (?:promised|agreed to|owes)\b|\b[Ww]aiting (?:on|for) [A-Z][\w-]+\b/;
  return dir === "theirs" && explicit.test(text) ? dir : "plain";
}
const DIRECTION_LABEL = { mine: "You owe", theirs: "They owe", plain: "Open", third: "Between others" };
function listItems(text) {
  const items = [];
  for (const line of String(text).split("\n")) {
    if (/^\s*(?:[-*+]|\d+[.)])\s+/.test(line) && !/^\s{2,}/.test(line)) items.push(line.replace(/^\s*(?:[-*+]|\d+[.)])\s+/, ""));
    else if (line.trim() && items.length) items[items.length - 1] += " " + line.trim();
    else if (line.trim()) items.push(line.trim());
  }
  return items;
}
// A line saying nothing is open, in the words pages use for it (1.9.2b1 showed
// "None identified" and "No explicit open request" as OPEN for 30 days).
function isCalm(t) {
  return /^(?:nothing (?:open|owed|outstanding|pending)|none(?:\s+(?:identified|open|outstanding|known|as of))?\b(?![-\w])|no (?:explicit |known |confirmed |current )?(?:open|outstanding|pending)\b|no work is (?:confirmed )?pending\b)/i
    .test(t.replace(/\*/g, "").trim());
}
function writtenDatePattern() {
  const month = "January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec";
  return "\\b(?:(\\d{1,2})\\s+(" + month + ")|(" + month + ")\\s+(\\d{1,2}))(?:,?\\s+(\\d{4}))?\\b";
}
function writtenDates(text) {
  const months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
  const snapshot = calendarDay(REM.as_of), year = Number(snapshot.slice(0, 4));
  return [...text.matchAll(new RegExp(writtenDatePattern(), "gi"))].map(m => {
    const month = months.indexOf((m[2] || m[3]).slice(0, 3).toLowerCase()) + 1;
    const day = String(m[1] || m[4]).padStart(2, "0"), mm = String(month).padStart(2, "0");
    let date = (m[5] || year) + "-" + mm + "-" + day;
    if (!m[5] && new Date(date) - new Date(snapshot) > 30 * DAY_MS) date = (year - 1) + "-" + mm + "-" + day;
    return date;
  });
}
function threads(r) {
  const sourceText = r.shown ? r.original ?? r.text : r.text;
  const cache = r?.path ? (threads._cache ??= new Map()) : null;
  const retCount = typeof REM !== "undefined" && REM.threads ? Object.keys(REM.threads).length : 0;
  const cacheKey = cache ? [r.path, r.shown || "", uiLanguage, REM.as_of || "", retCount, sourceText.length].join("\0") : "";
  if (cache?.has(cacheKey)) return cache.get(cacheKey);
  const original = rawSection({ ...r, text: sourceText }, "Open threads");
  if (!original) {
    const empty = { items: [], calm: "" };
    if (cache) cache.set(cacheKey, empty);
    return empty;
  }
  const all = listItems(original);
  // The lines as the reader's language has them (#3072): a cached translation keeps the page's headings and its
  // list, so line n of its Open threads is line n of the original. Today never switches a page's shown version, so
  // without this its rows stayed English on a 中文 reader whose pages were already translated. A translation whose
  // list is not the same length is not trusted line by line: the originals show, marked 原文, never a guess.
  const language = uiLanguage === "en" || r.shown ? "" : Object.keys(r.translations || {}).find(tag => tag === uiLanguage || tag.split("-")[0] === uiLanguage);
  const translated = language ? listItems(rawSection({ ...r, text: r.translations[language] }, "Open threads")) : [];
  const displayed = translated.length === all.length ? translated : listItems(rawSection(r, "Open threads"));
  const calmAt = all.findIndex(isCalm);
  const calm = calmAt < 0 ? "" : displayed[calmAt] || all[calmAt];
  const today = calendarDay(REM.as_of);
  const items = all.map((text, i) => ({ text, displayed: displayed[i] || text })).filter(({ text: t }) => !isCalm(t) && !/^(?:unknown\b|no (?:confirmed|known) pending work\b)/i.test(t)).map(({ text, displayed }) => {
    const dated = text.replace(/(?:open as of|last moved(?: on)?)\s+\d{4}-\d{2}-\d{2}/gi, "");
    const days = [...(dated.match(/\d{4}-\d{2}-\d{2}/g) || []), ...writtenDates(dated)];
    const after = words => {
      const date = new RegExp("\\b(?:" + words + ")\\s*[:：]?\\s*(\\d{4}-\\d{2}-\\d{2}|" + writtenDatePattern() + ")", "i").exec(text)?.[1] || "";
      return /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : writtenDates(date)[0] || "";
    };
    // Only a date immediately after a deadline word establishes a deadline.
    const due = after("due(?:\\s+(?:on|is))?|deadline(?:\\s+(?:on|is))?|by");
    const requested = after("since|requested(?:\\s+on)?|asked(?:\\s+on)?");
    const moved = after("last moved(?:\\s+on)?");
    const returnedAt = REM.threads?.[doneKey({ r, t: { text } })]?.returned_at;
    const sources = new Map([...rawSection({ ...r, text: sourceText }, "Sources").matchAll(/^\s*- \[(W?\d+)\]\s+(\S+)/gm)].map(m => [m[1], m[2]]));
    const messages = [...text.matchAll(/\[(W?\d+)\]/g)].map(m => REM.source_context?.[sources.get(m[1])]?.time)
      .filter(Boolean).map(calendarDay).filter(day => day && (!today || day <= today)).sort();
    const since = returnedAt ? calendarDay(returnedAt) : messages.at(-1) || moved || requested || days.filter(d => d !== due && (!today || d <= today)).sort().at(-1) || "";
    const quiet = !returnedAt && !!since && !due && daysSince(since) > 60;
    return { text: displayed, originalText: text, returnedAt, dir: r.category === "projects" ? projectDirection(text) : direction(text), since, due, quiet };
  });
  const built = { items, calm };
  if (cache) cache.set(cacheKey, built);
  return built;
}
// One merged row set for home, Open threads and the rail.
function threadEntries() {
  const hide = typeof document !== "undefined" && !!document.documentElement?.classList?.contains("hide-private");
  const cacheKey = [REM.records?.length || 0, typeof detailReady !== "undefined" ? detailReady : false, uiLanguage, hide, Object.keys(REM.ignored_senders || {}).join(",")].join("|");
  if (threadEntries.cached && threadEntries.cachedKey === cacheKey) return threadEntries.cached;
  if (REM.today_queue) {
    const records = new Map(listedRecords().map(r => [r.path, r]));
    const entries = new Map([...records.values()].flatMap(r => threads(r).items.map(t => [doneKey({r, t}), {r, t}])));
    const rows = REM.today_queue.map(row => {
      const chosen = entries.get(row.key);
      // A sender ignored since this page was built leaves at once; the next build leaves it out (today.py).
      if (!chosen || row.sender && REM.ignored_senders?.[row.sender]) return null;
      const members = row.keys.map(key => entries.get(key)).filter(Boolean);
      const also = [...new Map(members.filter(entry => entry.r.path !== chosen.r.path).map(entry => [entry.r.path, entry.r])).values()];
      return {...chosen, t: {...chosen.t, since: row.since, due: row.due, quiet: row.quiet, dir: row.dir}, also, members};
    }).filter(Boolean);
    if (threadEntries.cacheEnabled) { threadEntries.cached = rows; threadEntries.cachedKey = cacheKey; }
    return rows;
  }
  // Older snapshots lack the Python projection; only their page ledger uses this parser.
  const order = (a, b) => (a.t.due || "9999").localeCompare(b.t.due || "9999")
    || (b.t.since || "").localeCompare(a.t.since || "");
  const entries = listedRecords().filter(r => ["people", "orgs", "projects"].includes(r.category))
    .flatMap(r => threads(r).items.filter(t => t.dir !== "third" && /[\p{L}\p{N}]/u.test(plainLine(threadWords(t.text, r)))).map(t => ({ r, t })))
    .sort(order);
  const rows = threadGroups(entries).map(group => {
    const chosen = [...group].sort((a, b) => Number(a.t.dir === "plain") - Number(b.t.dir === "plain") || (b.t.since || b.t.due || "").localeCompare(a.t.since || a.t.due || "")
      || (b.t.originalText || b.t.text).length - (a.t.originalText || a.t.text).length)[0];
    const also = [...new Map(group.filter(entry => entry.r.path !== chosen.r.path && obligationWords(entry.r.title) !== obligationWords(chosen.r.title)).map(entry => [entry.r.path, entry.r])).values()];
    return { ...chosen, also, members: group };
  }).sort(order);
  if (threadEntries.cacheEnabled) { threadEntries.cached = rows; threadEntries.cachedKey = cacheKey; }
  return rows;
}
// Source numbers belong to their page; copied promises share the resolved id.
function obligationWords(text) {
  return text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}
function obligationEvidence({ r, t }) {
  const text = t.originalText || t.text;
  const sources = new Map([...rawSection({ ...r, text: r.shown ? r.original ?? r.text : r.text }, "Sources").matchAll(/^\s*- \[(W?\d+)\]\s+(\S+)/gm)].map(m => [m[1], m[2]]));
  const ids = new Set([...text.matchAll(/\[(W?\d+)\]/g)].map(m => sources.get(m[1])).filter(Boolean));
  for (const id of [...ids]) {
    const context = REM.source_context?.[id];
    if (context?.thread) ids.add("thread:" + context.source + ":" + context.thread);
  }
  const quotes = [...text.matchAll(/“([^”\n]{6,})”|"([^"\n]{6,})"|「([^」\n]{6,})」/g)];
  const content = obligationWords(text.replace(/\d{4}-\d{2}-\d{2}|\[W?\d+\]/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")).replace(/\bmeet\b/g, "meeting");
  const stop = (obligationEvidence._stop ??= new Set("a an the and or to of in on for with from by as at is are was were be been you your user owes owe asks asked request requests requested sent send confirm confirmed since due has have had still please this that it said before after whether required supplied through team should would could about their there which stated unknown outcome evidence established also then they them will january february march april june july august september october november december sept".split(" ")));
  const recs = REM?.records || [];
  if (obligationEvidence._names?.recs !== recs || obligationEvidence._names.len !== recs.length) {
    obligationEvidence._names = { recs, len: recs.length, words: new Set(recs.filter(page => ["people", "orgs"].includes(page.category)).flatMap(page => obligationWords(page.title || "").split(/\s+/))) };
  }
  const entityNames = obligationEvidence._names.words;
  const rNames = new Set(obligationWords(r.title || "").split(/\s+/));
  const words = new Set(content.split(/\s+/).filter(word => word.length > 3 && !/^\d+$/.test(word) && !stop.has(word) && !entityNames.has(word) && !rNames.has(word)));
  return { ids, quotes: quotes.map(m => obligationWords(m[1] || m[2] || m[3])), words,
    text: content, dir: t.dir, day: t.since || t.due || "", due: t.due || "" };
}
function sameObligation(a, b) {
  const shared = [...a.ids].some(id => b.ids.has(id));
  const overlap = [...a.words].filter(word => b.words.has(word)).length;
  const sharedSource = [...a.ids].some(id => !id.startsWith("thread:") && b.ids.has(id));
  // Two requests in one email share their source; only one that mostly repeats the other is the same.
  const covers = overlap >= 2 && overlap / Math.min(a.words.size, b.words.size) >= 0.5;
  const directional = a.dir === b.dir || ([a.dir, b.dir].includes("plain") && [a.dir, b.dir].some(dir => dir === "mine" || dir === "theirs"));
  if (!directional || a.dir !== b.dir && (!sharedSource || !covers)) return false;
  if (a.day && b.day && Math.abs(new Date(a.day) - new Date(b.day)) > 7 * DAY_MS) return false;
  // Dated copies can be more loosely worded, but still need two distinctive words.
  const threshold = a.day && b.day && a.dir === b.dir ? 0.3 : 0.5;
  if (shared) return overlap >= 2 && overlap / Math.min(a.words.size, b.words.size) >= threshold;
  if (a.dir !== b.dir) return false;
  if (!a.day || !b.day) return false;
  const union = new Set([...a.words, ...b.words]).size;
  return union > 0 && overlap / union >= (a.due && a.due === b.due ? 0.4 : 0.6);
}
function threadGroups(entries) {
  const groups = [], evidence = entries.map(obligationEvidence);
  entries.forEach((entry, i) => {
    const matches = [];
    for (const group of groups) {
      const combined = [i, ...matches.flat(), ...group].map(j => evidence[j].day).filter(Boolean).sort();
      const withinWeek = !combined.length || new Date(combined.at(-1)) - new Date(combined[0]) <= 7 * DAY_MS;
      const directions = new Set([i, ...matches.flat(), ...group].map(j => evidence[j].dir).filter(dir => dir !== "plain"));
      if (withinWeek && directions.size <= 1 && group.some(j => sameObligation(evidence[i], evidence[j]))) matches.push(group);
    }
    if (!matches.length) groups.push([i]);
    else {
      matches[0].push(i, ...matches.slice(1).flat());
      for (const group of matches.slice(1)) groups.splice(groups.indexOf(group), 1);
    }
  });
  return groups.map(group => group.sort((a, b) => a - b).map(i => entries[i]));
}
let threadStates = {}, pendingThreads = {};
// What the notebook itself last said it holds. threadStates is this plus the marks the page has not saved yet,
// so a refused mark goes back to this and never to another unsaved mark.
let notebookThreads = {};
let threadWrite = Promise.resolve();
function doneKey(entry) {
  return shortHash(entry.r.path + "\n" + (entry.t.originalText || entry.t.text));
}
function doneStorageKey() {
  return "co-rem-done:" + shortHash(REM.root || "");
}
function threadStorageKey() {
  return "co-rem-threads:" + shortHash(REM.root || "");
}
function isDone(entry) {
  return closedMark(threadStates[doneKey(entry)]);
}
// The reader's clock, in one place: a put-off's choices, when it is over, and what "today" a finished item belongs to.
function clockNow() { return Date.now(); }
function localDay(at) { return new Date(at).toLocaleDateString("en-CA"); }
// Not now carries the moment the owner chose (#3072: «暂不处理，我不知道下次怎么给我»). Once it has passed the mark no
// longer closes the item, on a page left open as much as in the next night's list (threads.listing says the same).
function putOffOver(value) { return value?.state === "skipped" && !!value.until && Date.parse(value.until) <= clockNow(); }
function closedMark(value) {
  return ["done", "skipped", "ignored"].includes(value?.state) && !value.returned_at && !putOffOver(value);
}
// What the owner did, in his words: 忽略 is its own state (ignored), so an ignored ad never reads 已完成.
function stateWord(state) {
  return t(state === "skipped" ? "Not now" : state === "ignored" ? "Ignored" : "Marked done");
}
// A closed list's summary says what is inside it: "Marked done · Ignored (3)", only the states it holds.
function closedSummary(values) {
  const states = ["done", "skipped", "ignored"].filter(state => values.some(value => (value?.state || "done") === state));
  return t("{states} ({n})", { states: states.map(stateWord).join(" · "), n: values.length });
}
// A mark names only the mail it cites, at the versions this page showed. It never carries the whole
// table: past 64 KB the Host refused every Done, Undo and Skip (#2936).
function citedVersions(entries, shown) {
  const threads = entries.flatMap(entry => [...obligationEvidence(entry).ids]).map(id => REM.source_context?.[id]?.thread);
  return Object.fromEntries(threads.filter(thread => shown[thread]).map(thread => [thread, shown[thread]]));
}
// A mark's key is its page's path and the thread's words: enough to read again what it cites.
function keyEntry(key) {
  const cut = key.indexOf("\n");
  return { r: byPath(key.slice(0, cut)), t: { text: key.slice(cut + 1) } };
}
async function reconcileThreads() {
  if (!REM.live) return;
  const response = await fetch("/rem/thread").catch(() => null);
  if (!response?.ok) return;
  notebookThreads = await response.json();
  threadStates = { ...notebookThreads, ...pendingThreads };
  REM.threads = threadStates;
  for (const [key, value] of Object.entries(pendingThreads)) {
    // A mark kept from before #2936 holds the whole table, too much to send: it is cut to the mail this page can
    // place. A mark that fits goes as it is, placed or not: its versions are what its reader saw, and a Skip
    // returns on anything newer. 32768 is half of what the Host reads for one mark.
    const cited = (value.keys || [key]).map(keyEntry).filter(entry => entry.r);
    if (JSON.stringify(value.versions || {}).length > 32768) value.versions = citedVersions(cited, value.versions);
    await saveThreadState(key, value);
  }
  await readerStorage(threadStorageKey(), JSON.stringify({ states: threadStates, pending: pendingThreads }));
}
// The page shows what the notebook holds for these threads, except where a mark of its own is still unsaved.
function showNotebookThreads(keys) {
  for (const item of keys) {
    if (pendingThreads[item]) continue;
    if (notebookThreads[item]) threadStates[item] = notebookThreads[item];
    else delete threadStates[item];
  }
}
// The notebook took the mark: what it answered is what it holds, for every thread it names.
function notebookTook(key, value, { keys = [key], ...decision }) {
  for (const item of keys) {
    if (value.state === "open") delete notebookThreads[item];
    else notebookThreads[item] = { ...decision, keys, draft_statuses: decision.draft_statuses || value.draft_statuses };
  }
  return keys;
}
// One mark's turn at the notebook. No answer, a busy notebook (409) and a failing Host (5xx) leave the mark waiting
// to be sent again. Any other refusal is final: the same mark sent again is refused again, so it stops waiting.
async function sendThreadState(key, value) {
  if (pendingThreads[key] !== value) return true;
  const response = await fetch("/rem/thread", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, state: value.state, versions: value.versions, keys: value.keys, until: value.until, device: navigator.platform || "browser" }) }).catch(() => null);
  if (!response || response.status === 409 || response.status >= 500) return false;
  const keys = response.ok ? notebookTook(key, value, await response.json()) : value.keys || [key];
  if (pendingThreads[key] !== value) return true;
  delete pendingThreads[key];
  showNotebookThreads(keys);
  await readerStorage(threadStorageKey(), JSON.stringify({ states: threadStates, pending: pendingThreads }));
  return response.ok || "refused";
}
// Resolves true once the notebook holds the mark, false while it waits on this device, "refused" when the notebook said no.
async function saveThreadState(key, value) {
  pendingThreads[key] = value;
  if (value.state === "open") delete threadStates[key];
  else threadStates[key] = value;
  REM.threads = threadStates;
  await readerStorage(threadStorageKey(), JSON.stringify({ states: threadStates, pending: pendingThreads }));
  if (!REM.live) return false;
  threadWrite = threadWrite.then(() => sendThreadState(key, value));
  return threadWrite;
}
// The mark one click makes: every key of the thread, the mail it cites as this page showed it, and what its drafts were.
function threadMark(key, members, done, state, until = null) {
  const value = { state: done ? state : "open", at: new Date(clockNow()).toISOString(), device: navigator.platform || "browser" };
  if (done && state === "skipped" && until) value.until = until;
  value.keys = [...new Set([...members.map(doneKey), ...(threadStates[key]?.keys || [])])];
  value.versions = citedVersions(members, REM.mail_versions || {});
  value.draft_statuses = Object.assign({}, ...value.keys.map(item => threadStates[item]?.draft_statuses || {}));
  return value;
}
// The drafts that answer a marked thread follow it: a Skip sets them aside, an Undo gives each its status back.
function markDrafts(related, value, done, state) {
  for (const draft of related) {
    if (draft.status === "sent") continue;
    if (done) {
      value.draft_statuses[draft.id] ??= { status: draft.status, version: draft.version };
      if (state === "skipped") draft.status = "skipped";
    } else if (value.draft_statuses[draft.id]?.version === draft.version) draft.status = value.draft_statuses[draft.id].status;
  }
}
// extra: one more choice the notice offers after Undo (忽略's "stop showing this sender"; see stripDone).
// One mark, without drawing: the thread's state here and on its way to the notebook. restore() gives the drafts it
// set aside their statuses back when the notebook refuses it.
// A snapshot keeps no mark: a file:// page's storage is not the live reader's and nothing carries a mark from one
// to the other, so a "saved on this device" there was a promise nobody kept (#2990 review). null: nothing marked.
function markThread(entry, done, state = "done", entries = [entry], until = null) {
  if (!liveHere()) return null;
  const key = doneKey(entry), members = entries.flatMap(item => item.members || [item]);
  const value = threadMark(key, members, done, state, until);
  const related = (REM.drafts || []).filter(d => d.thread && members.some(item => obligationEvidence(item).ids.has("thread:" + d.provider + ":" + d.thread)));
  const statuses = related.map(draft => draft.status);
  markDrafts(related, value, done, state);
  const saved = saveThreadState(key, value);
  for (const memberKey of value.keys) {
    if (done) threadStates[memberKey] = value;
    else delete threadStates[memberKey];
  }
  return { saved, restore: () => related.forEach((draft, i) => { draft.status = statuses[i]; }) };
}
// until: when a Not now comes back (laterChoices); a mark without one waits for new mail, as before.
function setDone(entry, done, state = "done", entries = [entry], extra = null, until = null) {
  const mark = markThread(entry, done, state, entries, until);
  if (!mark) return Promise.resolve(false);
  const { saved, restore } = mark;
  const scroll = window.scrollY;
  render();
  window.scrollTo(0, scroll);
  document.getElementById("done-notice")?.remove();
  const notice = done ? doneNotice(entry, state, entries, extra, until) : null;
  return saved.then(synced => {
    if (synced === "refused") {
      restore();
      notSavedNotice(() => setDone(entry, done, state, entries, extra, until), notice);
    }
    // The save's own redraw keeps the page where it was: it used to draw from the top, so on a phone the answer to
    // Mark done was the page jumping back to its first screen (#3072).
    if (synced) {
      const at = window.scrollY;
      render();
      window.scrollTo(0, at);
    }
    // A refusal has its own words, and the "Saved" still showing belongs to a later mark.
    const status = synced !== "refused" && document.getElementById("thread-save-status");
    if (status) status.textContent = t(synced ? "Saved in notebook" : "Saved on this device — sync pending");
    return synced;
  });
}
// A refused mark is not saved: the notice says so in place of its "Saved" and offers another try. The thread is back
// on the page by then. The notice of a later mark stays, with its Undo and its own "Saved", and gains these words.
function notSavedNotice(retry, own) {
  const showing = document.getElementById("done-notice");
  const again = el("button", { type: "button", text: t("Try again") });
  again.onclick = retry;
  if (showing && showing !== own) return showing.appendChild(el("div", { role: "alert" }, [t("Not saved"), " · ", again]));
  const held = showing?.contains(document.activeElement);
  showing?.remove();
  const notice = el("div", { id: "done-notice", class: "done-notice", role: "alert" }, [t("Not saved"), " · ", again]);
  document.body.appendChild(notice);
  if (held) again.focus({ preventScroll: true });
  noticeLeaves(notice);
}
// The keyboard's place on Today is the raised card: E, R and Enter act from there.
function focusRaisedCard() {
  document.querySelector("#main .qcard.focal")?.focus({ preventScroll: true });
}
// The notice holds the focus while it shows: Enter undoes, E closes the next card. When Undo is used or the
// notice goes, the focus returns to the raised card, so the keys go on working.
// extra: one more worded choice after Undo (忽略's "stop showing this sender"); it gets time to be read and tapped.
// The notice says what happened and where the item went (#3072: «我想把它标成没完成怎么办»): its last words name the
// list on Today that now holds it, Finished today or Put off, with that list's count, and open it.
function doneNotice(entry, state, entries, extra, until = null) {
  const undo = el("button", { type: "button", text: t("Undo") });
  // What comes back goes in front again, so Undo shows the card it was pressed for.
  undo.onclick = () => { todayLead = (entry.who || entry.r).path; setDone(entry, false, "done", entries); focusRaisedCard(); };
  const status = el("span", { id: "thread-save-status", text: t("Saving…") });
  const words = state === "skipped" ? (until ? t("Put off · {back}", { back: backWords(until) }) : t("Not now · returns with new mail"))
    : t(state === "ignored" ? "Ignored · this one will not come back" : "Marked done");
  const where = closedLink(state === "skipped" ? "put-off" : "finished-today");
  const notice = el("div", { id: "done-notice", class: "done-notice", role: "status" }, [words, " · ", undo, ...(extra ? [" · ", extra()] : []), " · ", status, ...(where ? [" · ", where] : [])]);
  document.body.appendChild(notice);
  undo.focus({ preventScroll: true });
  noticeLeaves(notice, extra ? 12000 : 5000);
  return notice;
}
function noticeLeaves(notice, wait = 5000) {
  setTimeout(() => {
    const held = notice.contains(document.activeElement);
    notice.remove();
    if (held) focusRaisedCard();
  }, wait);
}

// The one thing to do next: write to the person the thread is with. The address and
// subject come from the cited message, never guessed; without them the page opens.
function threadContact(entry) {
  const { r, t: thread } = entry;
  const owner = byPath(REM.owner);
  for (const [, n] of thread.text.matchAll(/\[(W?\d{1,3})\]/g)) {
    const context = (REM.source_context || {})[citationId(r, n)];
    if (!context) continue;
    const from = context.participants?.from, to = context.participants?.to || [];
    const candidates = [...(Array.isArray(from) ? from : [from]), ...(Array.isArray(to) ? to : [to])].filter(Boolean);
    for (const raw of candidates) {
      const who = mailbox(raw);
      if (!who.address || personByAddress(who.address) === owner) continue;
      const subject = context.subject || REM.conversations?.[context.thread]?.subject || "";
      return { address: who.address, subject, name: personByAddress(who.address)?.title.split(/\s+/)[0] || who.name };
    }
  }
  // No archived message: the address the page itself records for this person.
  if (r.category !== "people") return null;
  const listed = (parseFacts(r).get("Email") || []).flatMap(item => item.value.toLowerCase().match(/[\w.+-]+@[\w-]+\.[\w.-]+/g) || []);
  const address = listed.find(candidate => personByAddress(candidate) !== owner);
  return address ? { address, subject: "", name: r.title.split(/\s+/)[0] } : null;
}
// What kind of thing this card is, read from the message it cites.
function threadKind(entry) {
  const { r, t: thread } = entry;
  const draft = threadDraft(entry);
  if (draft && ["gmail", "outlook"].includes(draft.provider)) return {kind: draft.provider, channel: sourceChannel(draft.provider), thread: draft.thread, mail: true};
  for (const [, n] of thread.text.matchAll(/\[(W?\d{1,3})\]/g)) {
    const id = citationId(r, n), context = (REM.source_context || {})[id];
    const kind = context?.source || (id || "").split(":")[0];
    if (kind) return { kind, channel: sourceChannel(kind), thread: context?.thread || "", mail: ["gmail", "outlook"].includes(kind) };
  }
  const reply = (REM.today_queue || []).find(row => (row.keys || [row.key]).includes(doneKey(entry)))?.reply;
  return reply?.provider ? {kind: reply.provider, channel: sourceChannel(reply.provider), thread: reply.thread || "", mail: ["gmail", "outlook"].includes(reply.provider)} : null;
}
function outlookMark() {
  const label = t("{channel} reply", {channel: "Outlook"});
  return el("span", {class: "outlook-mark", role: "img", "aria-label": label, title: label});
}
function kindBadge(entry) {
  const kind = threadKind(entry), chat = threadDraft(entry)?.channel;
  // A reply rewritten for a chat says that chat, the same word as its draft and its footer (#3312 C).
  if (chat && chat !== "mail") return el("span", { class: "kind-badge", text: t("{channel} reply", { channel: { lark: "Lark", whatsapp: "WhatsApp" }[chat] || chat }) });
  if (kind?.kind === "outlook") return outlookMark();
  if (!kind) return el("span", {class: "kind-badge", text: t("Task")});
  return el("span", { class: "kind-badge" + (kind.mail ? " mail" : ""), text: kind.mail ? t("{channel} reply", { channel: kind.channel }) : kind.channel });
}
// A new message only.  A mailto with "Re: <subject>" is not a reply: the mail
// app sends it without In-Reply-To, so it lands outside the thread.
function mailtoLink(contact, cls, label, reply = false) {
  return el("a", { class: cls, href: "mailto:" + contact.address, text: label, ...(reply ? { "data-reply": "" } : {}) });
}
function draftNowButton(entry, kind, contact, cls = "btn-act") {
  const button = el("button", { type: "button", class: cls, text: t("Draft now"), "data-reply": "" });
  const status = el("span", { class: "quiet-line draft-status", role: "status" });
  const thread = kind.thread.split(":").slice(2).join(":") || kind.thread;
  button.onclick = async () => {
    button.disabled = true;
    status.textContent = t("Drafting the reply… about a minute");
    const response = await fetch("/rem/draft", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "prepare", provider: kind.kind, thread }) }).catch(() => null);
    const result = response ? await response.json() : { error: t("Could not update draft. Check the connection and try again.") };
    if (!response || !response.ok) { button.disabled = false; status.textContent = result.error || t("Could not update draft"); return; }
    REM.drafts = [...(REM.drafts || []).filter(d => d.id !== result.id), result];
    render();
  };
  return el("span", { class: "draft-now" }, [button, status]);
}
function primaryAction(entry, completion = true) {
  const { r } = entry, kind = threadKind(entry);
  const reply = (REM.today_queue || []).find(row => (row.keys || [row.key]).includes(doneKey(entry)))?.reply;
  if (completion && reply?.state === "replied") {
    const done = el("button", {type: "button", class: "btn-act", text: t("Mark done"), ...snapshotWhy("This is an offline snapshot; open REM to mark it.")});
    done.onclick = () => setDone(entry, true);
    return done;
  }
  if (REM.live && reply?.state === "queued") {
    return draftNowButton(entry, {kind: reply.provider, thread: reply.thread}, null);
  }
  if (reply?.state === "unarchived" && !reply.thread) {
    const number = /\[(W?\d+)\]/.exec(entry.t.originalText || entry.t.text)?.[1];
    return el("a", {class: "btn-act", href: href(r) + (number ? "&h=src-" + number : "&h=open-threads"), text: t("Open the recorded source")});
  }
  const url = threadUrl(reply, kind);
  if (url) return el("a", {class: "btn-quiet", href: url.href, target: "_blank", rel: "noopener", text: t("Open the {channel} thread", {channel: url.channel})});
  return el("a", { class: "btn-act", href: href(r) + "&h=open-threads", text: t("Open the page") });
}
// One primary per screen (#3158): the first filled action in the lists keeps its fill; every later one reads as a
// quiet worded action, the same click.
function quietLaterPrimaries(root) {
  [...root.querySelectorAll("ul.threads .btn-act")].slice(1).forEach(node => node.classList.add("act-quiet"));
}
function threadUrl(reply, kind) {
  if (!reply?.provider && !kind?.mail) return null;
  const provider = reply?.provider || kind.kind, channel = provider === "outlook" ? "Outlook" : "Gmail";
  const raw = reply?.thread || kind?.thread || "", thread = (raw.split(":").slice(2).join(":") || raw).trim();
  const source = (reply?.source?.replace(/^(gmail|outlook):/, "") || "").trim();
  const id = provider === "gmail" ? (thread || source) : (source || thread);
  if (reply && !id) return null;
  return { channel, href: provider === "gmail" ? "https://mail.google.com/mail/u/0/#all/" + encodeURIComponent(id)
    : "https://outlook.live.com/mail/0/id/" + encodeURIComponent(id) };
}

// On the record's own page the actions stay quiet: no green, no link back to the page itself.
function quietOnly(node) {
  return node && !node.matches(".btn-act") && !node.querySelector(".btn-act") ? node : null;
}
// strip: the row also carries the hand-off strip, which holds its one Mark done (owner, 2026-11-11), so
// nothing here marks it done: not the quiet button, and not the green one a replied row would lead with.
function threadActions(entry, onPage = false, strip = false) {
  const undo = isDone(entry);
  const done = el("button", { type: "button", class: "btn-quiet", text: t(undo ? "Undo" : "Mark done"), ...snapshotWhy("This is an offline snapshot; open REM to mark it.") });
  done.onclick = () => setDone(entry, !undo);
  const draft = threadDraft(entry);
  const replied = (REM.today_queue || []).find(row => (row.keys || [row.key]).includes(doneKey(entry)))?.reply?.state === "replied";
  if (!undo && replied && draft?.status !== "prepared" && draft?.status !== "no_reply") {
    const open = primaryAction(entry, false);
    return el("div", {class: "thread-actions"}, onPage ? [quietOnly(open), done] : strip ? [open] : [primaryAction(entry), open]);
  }
  const primary = undo || draft?.status === "no_reply" ? null : primaryAction(entry, !strip);
  return el("div", { class: "thread-actions" }, [
    undo ? el("span", { class: "done-tag", text: stateWord(threadStates[doneKey(entry)]?.state)
      + " · " + fmtDate(calendarDay(threadStates[doneKey(entry)]?.at || REM.as_of)) }) : onPage ? quietOnly(primary) : primary,
    ...(entry.t.returnedAt ? [el("span", { class: "done-tag", text: t("New mail · {date}", { date: fmtDate(calendarDay(entry.t.returnedAt)) }) })] : []), strip && !undo ? null : done]);
}
// Full-screen writing: the letter on the left, editable; on the right what the
// owner needs to remember, the Chinese reading, and the cited messages.
// The full-screen writer (#3303). It reads as a dialog over a dimmed page, closes where every dialog does
// (× top right, Esc, a click outside, each asking once if the letter changed), keeps REM's open questions on
// the right where the owner answers them, and answers Send on its own button: 发送中… → 已发送, or the reason
// and 重试. It used to close at once and leave a grey caption, and it refused any bracket in the letter while
// REM's 【需要你：…】 sat in the text with nowhere to answer it, so Send looked dead (owner, 2026-11-22).
const SLOT_SPLIT = /(\[[^\]]*(?:\]|$)|［[^］]*(?:］|$)|【[^】]*(?:】|$))/g;
// Where a reply goes and whether it can honestly go there: the card and full screen read this one answer (#3348).
// A draft written for a chat the person is not on is a defect (never sent); one REM already rewrote says so.
function replyChannel(draft, name) {
  const channel = draft.channel || "mail";
  const chat = value => ({ lark: "Lark", whatsapp: "WhatsApp" }[value] || value);
  const provider = draft.provider === "gmail" ? "Gmail" : "Outlook";
  return { channel, defect: !!draft.channel_defect,
    defectWords: t("This reply was written for {channel}, but {name} can't be reached there.", { channel: chat(channel), name }),
    // While the channel can't send, the fix is the primary action and the footer says where it will go (#3348).
    footer: t("{channel} can't reach {name} · rewritten as an email it sends from {provider}", { channel: chat(channel), name, provider }),
    held: t("Rewrite it before sending"),
    note: draft.redrafted_from && !draft.channel_defect
      ? t("REM rewrote this as an email: the earlier draft was written for {channel}, but {name} isn't on {channel}.", { channel: chat(draft.redrafted_from), name }) : "" };
}
// Evidence comes from the local archive projection for this exact draft version.
function writerMail(draft) {
  const mail = draft.writer_mail;
  if (REM.shared || !mail?.original || privacyLevel === "public") return { examples: [] };
  return { original: mail.original, examples: mail.examples || [] };
}
function writerMessage(message) {
  const level = message.level === "sensitive" ? "sensitive" : message.level === "personal" ? "personal" : "";
  return el("article", { class: "writer-msg" + (level ? " private" : ""), ...(level ? { "data-level": level } : {}) }, [
    el("div", { class: "writer-msg-head", text: [sourceSender(message), message.time && fmtTime(message.time), message.subject].filter(Boolean).join(" · ") }),
    el("div", { class: "writer-msg-text", text: message.excerpt ? message.excerpt + (message.truncated ? "…" : "") : t("Message text unavailable") })]);
}
function openWriter(draft, who, onSend, onFix, answers = {}) {
  const to = mailbox(draft.to);
  // The letter is editable text with REM's open questions as chips in it, as on the card (#3312 F): a chip reads
  // the question in its own words until it is answered on the right, then the answer. Bracket text never shows.
  const body = el("div", { class: "writer-body", contenteditable: "true", role: "textbox", "aria-multiline": "true", "aria-label": t("Reply body") });
  const parts = draft.body.split(SLOT_SPLIT), fills = {}, chips = {};
  const isSlot = part => /^(?:\[|［|【)/.test(part);
  for (const [i, part] of parts.entries()) {
    if (!isSlot(part)) { if (part) body.append(document.createTextNode(part)); continue; }
    const chip = chips[i] = el("span", { class: "slot-chip", contenteditable: "false", role: "button", tabindex: "0", "data-slot": String(i), text: slotWhat(part) });
    chip.onclick = () => rows[slots.findIndex(([, k]) => k === i)]?.querySelector("button, input")?.focus();
    chip.onkeydown = event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        event.stopPropagation();
        chip.onclick();
      }
    };
    body.append(chip);
  }
  // What the letter says now: its text, an answered chip as its answer, an open one as REM's slot (so Send waits).
  const slotOf = node => node.dataset ? node.dataset.slot : node["data-slot"];
  const letterText = () => [...body.childNodes].map(node => node.nodeType === 3 ? node.nodeValue
    : slotOf(node) !== undefined ? fills[slotOf(node)] ?? parts[slotOf(node)]
    : node.tagName === "BR" ? "\n" : node.innerText ?? node.textContent ?? "").join("");
  // Enter and paste stay plain text, so the letter holds only text and chips.
  body.addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); document.execCommand("insertText", false, "\n"); } });
  body.addEventListener("paste", event => { event.preventDefault(); document.execCommand("insertText", false, event.clipboardData.getData("text/plain")); });
  const send = el("button", { type: "button", class: "btn-act", text: t("Send") });
  const close = el("button", { type: "button", class: "writer-close", "aria-label": t("Close"), title: t("Close") + " (Esc)" }, [icon("x")]);
  const notice = el("p", { class: "mail-status writer-notice", role: "status" });
  const { original, examples } = writerMail(draft);
  // REM's open questions, answered on the right: the chip in the letter shows the answer.
  const slots = parts.map((part, i) => [part, i]).filter(([part]) => isSlot(part));
  const rows = slots.map(([part, i]) => slotChoices(part, fills, i, () => {
    chips[i].textContent = fills[i] ?? slotWhat(part);
    chips[i].classList?.toggle("filled", !!fills[i]);
    notice.textContent = "";
  }));
  // Keep the original template and restore each control independently, including a
  // meeting time whose required location is still blank. Answers are plain text.
  slots.forEach(([, i], n) => { if (answers[i]) rows[n].setAnswerState(answers[i]); });
  const fieldState = () => JSON.stringify(rows.map(row => row.getAnswerState()));
  const initial = letterText(), initialFields = fieldState();
  const dirty = () => letterText() !== initial || fieldState() !== initialFields;
  // A chip deleted from the letter is a question the owner took out; one still there and unanswered holds Send.
  const unanswered = () => slots.filter(([, i]) => !fills[i] && chips[i].isConnected !== false);
  const did = el("p", { class: "writer-did", text: remDid(draft) });
  const reach = replyChannel(draft, who?.title || mailbox(draft.to).name);
  const fix = el("button", { type: "button", class: reach.defect ? "btn-act" : "btn-line", text: t("Rewrite it as an email") });
  fix.onclick = () => { dialog.close(); onFix?.(); };
  const band = reach.defect ? el("p", { class: "mail-defect writer-defect", role: "alert" }, [reach.defectWords, " ", fix])
    : reach.note ? el("p", { class: "mail-redrafted writer-defect", role: "status", text: reach.note }) : null;
  const channel = draft.channel || "mail";
  const channelWord = channel === "mail" ? (draft.provider === "gmail" ? "Gmail" : "Outlook") : t({ lark: "Lark", whatsapp: "WhatsApp" }[channel] || channel);
  // The title bar: who it goes to and on what, × at the top right; on a phone 取消 top left and 发送 top right.
  const cancel = el("button", { type: "button", class: "btn-quiet writer-cancel", text: t("Cancel") });
  const sendTop = el("button", { type: "button", class: "btn-act writer-send-top", text: t("Send") });
  const title = el("header", { class: "writer-title" }, [cancel,
    el("h2", { text: t("Reply to {name}", { name: who?.title || to.name }) + " · " + channelWord }), sendTop, close]);
  const dialog = el("dialog", { class: "writer " + (channel === "mail" ? "provider-" + (draft.provider || "mail") : "chat"), "aria-label": t("Reply draft") }, [
    title,
    el("div", { class: "writer-letter" }, [band,
      el("details", { class: "writer-original", ...(innerWidth >= 720 ? { open: "" } : {}) }, [
        el("summary", { text: t("Original message") }),
        original ? writerMessage(original) : el("p", { text: t("No archived message available") })]),
      el("h3", { class: "writer-reply-title", text: t("Your reply") }),
      el("div", { class: "mail-head" }, [
        el("div", { class: "mail-row" }, [el("span", { class: "k", text: t("To") }), el("span", { class: "v", text: (who?.title || to.name) + (channel === "mail" ? " <" + to.address + ">" : " · " + t({ lark: "Lark", whatsapp: "WhatsApp" }[channel] || "")) })]),
        channel === "mail" && draft.cc ? el("div", { class: "mail-row" }, [el("span", { class: "k", text: t("CC") }), el("span", { class: "v", text: draft.cc })]) : null,
        channel === "mail" ? el("div", { class: "mail-row" }, [el("span", { class: "k", text: t("Subject") }), el("span", { class: "v subject", text: draft.subject })]) : null]),
      body,
      el("div", { class: "writer-actions" }, [send, ...(reach.defect ? [el("span", { class: "choose-hint", text: reach.held })] : []),
        el("span", { class: "mail-note", text: reach.defect ? reach.footer : channel === "mail"
        ? t("Sends from {mailbox} via {provider}", { mailbox: draft.from, provider: draft.provider === "gmail" ? "Gmail" : "Outlook" })
        // A Lark or WhatsApp reply leaves through that chat, as the card says, never through the mailbox it answers.
        : t("Sends as you via {tool}", { tool: channel === "lark" ? "lark-cli" : "co whatsapp" }) })]),
      notice]),
    el("aside", { class: "writer-side" }, [
      el("h3", { text: t("Reply assistance") }),
      rows.length ? el("section", { class: "writer-choices", "aria-label": t("Your call") }, rows) : null,
      el("section", { class: "writer-examples" }, [el("h4", { text: t("Your earlier replies") }),
        ...(examples.length ? examples.map(writerMessage) : [el("p", { text: t("No archived reply to this recipient") })])]),
      el("details", { class: "writer-context" }, [el("summary", { text: t("Reply context") }),
        who ? el("h4", {}, [el("a", { href: href(who), text: who.title })]) : null,
        who ? el("p", { class: "writer-brief", text: summaryLine(known(who).summary) }) : null,
        draft.ask ? el("section", {}, [el("h4", { text: t("What they asked") }), el("p", { text: draft.ask })]) : null,
        el("section", {}, [el("h4", { text: t("What REM did") }), did]),
        draft.why ? el("section", {}, [el("h4", { text: t("Why this reply") }), el("p", { text: draft.why })]) : null,
        draft.gist ? el("section", {}, [el("h4", { text: gistTitle(draft.gist) }), el("p", { text: draft.gist })]) : null])])]);
  const mayLeave = () => !dirty() || confirm(t("Discard your changes to this reply?"));
  const leave = () => { if (mayLeave()) dialog.close(); };
  send.onclick = async () => {
    // The same rule as the card: a reply written for a chat this person is not on never leaves (#3348).
    if (reach.defect) { notice.textContent = reach.defectWords; fix.focus(); return; }
    const left = unanswered();
    if (left.length) {
      notice.textContent = t("Answer REM's question on the right first: {what}", { what: slotWhat(left[0][0]) });
      const row = rows[slots.indexOf(left[0])];
      (row.querySelector("input:invalid") || row.querySelector("button, input"))?.focus();
      return;
    }
    const text = letterText();
    if (!text.trim()) { notice.textContent = t("Write a reply before sending"); body.focus(); return; }
    send.disabled = close.disabled = sendTop.disabled = true;
    send.textContent = sendTop.textContent = t("Sending…");
    notice.textContent = "";
    const error = await onSend(text.trim() === draft.body.trim() ? undefined : text);
    if (!error) {
      send.textContent = sendTop.textContent = t("Reply sent");
      setTimeout(() => dialog.close(), motionStilled() ? 0 : 700);
      return;
    }
    send.disabled = close.disabled = sendTop.disabled = false;
    send.textContent = sendTop.textContent = t("Retry");
    notice.textContent = error;
  };
  close.onclick = cancel.onclick = leave;
  sendTop.onclick = () => send.onclick();
  // Paused while the channel can't send: quiet, not the boldest thing on the sheet (#3348).
  if (reach.defect) for (const button of [send, sendTop]) button.className = button.className.replace("btn-act", "btn-quiet");
  // Esc is the dialog's own cancel; a changed letter asks once before it goes.
  dialog.addEventListener("cancel", event => { if (!mayLeave()) event.preventDefault(); });
  // A click on the dimmed page outside the letter lands on the dialog element itself.
  dialog.addEventListener("click", event => { if (event.target === dialog) leave(); });
  dialog.addEventListener("close", () => dialog.remove());
  document.body.appendChild(dialog);
  dialog.showModal();
  // On a phone the keyboard would cover the letter's opening; the owner taps where he wants to write.
  if (innerWidth >= 720) body.focus();
}
function threadDraft(entry) {
  // No drafts, no answer: skip working out the evidence (People asks this for every person's items).
  if (!REM.drafts?.length) return undefined;
  if (entry.t && entry.t._draftRef === REM.drafts && "_draft" in entry.t) return entry.t._draft;
  const ids = obligationEvidence(entry).ids;
  const drafts = (REM.drafts || []).filter(d => ids.has("thread:" + d.provider + ":" + d.thread));
  const chosen = drafts.find(d => d.status === "prepared" || d.status === "no_reply") || drafts[0];
  if (entry.t) { entry.t._draftRef = REM.drafts; entry.t._draft = chosen; }
  return chosen;
}
function draftNote(draft, entry) {
  const reply = entry && (REM.today_queue || []).find(row => (row.keys || [row.key]).includes(doneKey(entry)))?.reply;
  if (draft?.status === "prepared") return null;
  if (draft?.status === "no_reply") return el("p", { class: "quiet-line", text: t("No reply needed: ") + (draft.gist || draft.why || "") });
  if (reply?.last_word_yours) {
    const values = {promise: unlabelled(reply.promise || t("message text unavailable")), since: fmtDate(reply.since)};
    // A reply after the promise fell due does not settle it; do not invite "mark done".
    const late = entry.t?.due && entry.t.due < calendarDay(REM.as_of);
    return el("p", {class: "quiet-line draft-reason", text: t(reply.state === "task"
      ? "You promised: “{promise}” ({since}) — this is a task, not a reply."
      : late ? "You replied on {since}: “{promise}” — the promise is still open."
      : "You replied on {since}: “{promise}” — if this is handled, mark it done.", values)});
  }
  if ((!draft || draft.status === "pending") && reply) {
    const channel = reply.provider === "outlook" ? "Outlook" : "Gmail";
    const state = REM.status?.mailboxes?.[reply.provider] || "";
    const text = reply.state === "task" ? t("Task: {promise} · since {since}",
      {promise: unlabelled(reply.promise || entry.t.text), since: reply.since || entry.t.since || t("date not agreed")})
      : reply.state === "unarchived" ? t(/last read failed|read failed/i.test(state)
        ? "The original is not archived from {channel}; its last read failed."
        : "The original is not archived from {channel}.", {channel})
      : reply.state === "waiting" ? t("Waiting for their reply; open the thread to follow up.")
      : reply.state === "queued" && REM.live ? null
      : t(REM.status?.worker?.enabled ? "Reply draft queued for tonight" : "Reply draft pending — background updates off");
    if (!text) return null;
    return el("p", {class: "quiet-line draft-reason", text});
  }
  if (!draft) return null;
  return el("p", { class: "quiet-line", text: t(draft.status === "sent" ? "Sent" : draft.status === "discarded" ? "Draft discarded" : draft.status === "skipped" ? "Not now"
    : REM.status?.worker?.enabled ? "Reply draft queued for tonight" : "Reply draft pending — background updates off") });
}
// A reply is shown as the mail it will become: who it goes to, the subject, the
// words, and beside them the owner's-language reading. One button sends it.
// REM's owner slot, 【需要你：<what> — <by when>】, becomes a row to choose from. The options are
// the slot's own words, split only where REM wrote alternatives ("邮件附件 / 共享文件夹", "A 还是 B");
// the part after the dash is a date and is never split. One option means a field to type into.
function slotWhat(part) {
  return part.replace(/^[\[［【]|[\]］】]$/g, "").replace(/^需要你[:：]\s*/, "").split(/\s+—\s+/)[0];
}
function schedulingQuestion(what) {
  if (/\btime\s?zone\b|时区/i.test(what)) return false;
  return /^(?:时间|时段|时间段|time|meeting time|(?:your |my )?availability|time slots?)$/i.test(what.trim())
    || /(?:方便|可用|可选|空闲|有空|会面|开会|会议|通话|见面|约谈|面试|演示).{0,8}(?:时间|时段)|(?:时间|时段).{0,6}(?:方便|有空)/.test(what)
    || /\b(?:available times?|time slots?|(?:your|my|meeting) availability|availability for (?:a |the )?(?:meeting|call)|times? that work for you|time (?:for|to) (?:a |the )?(?:meet(?:ing)?|call|chat|interview|demo)|(?:meeting|call|interview|demo) times?)\b/i.test(what);
}
function calendarSlotChoices(calendar, now = Date.now()) {
  const window = calendar?.window;
  const instant = text => typeof text === "string" && /T.*(?:Z|[+-]\d\d:\d\d)$/.test(text) ? Date.parse(text) : NaN;
  const saved = instant(calendar?.saved_at), start = instant(window?.start), end = instant(window?.end);
  const day = 86400000, halfHour = 1800000;
  if (!(saved <= now && now - saved <= day && start <= now && now < end) || !window.timezone
      || !Array.isArray(calendar.events) || calendar.errors?.length !== 0 || !Array.isArray(calendar.read)
      || !calendar.read.some(r => r?.calendars > 0)
      || !calendar.read.every(r => Number.isInteger(r?.calendars) && r.calendars >= 0 && !r.capped && !r.left_out?.unticked && instant(r.at) === saved)) return [];
  let clock;
  try {
    clock = new Intl.DateTimeFormat("en-GB", {timeZone: window.timezone, weekday: "short", year: "numeric",
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23"});
  } catch (error) { if (error instanceof RangeError) return []; throw error; }
  const busy = [], allDay = [];
  for (const event of calendar.events) {
    if (event?.all_day === true) {
      const date = text => /^\d{4}-\d\d-\d\d$/.test(text) && Number.isFinite(Date.parse(text))
        && new Date(text).toISOString().slice(0, 10) === text;
      if (!date(event.start) || !date(event.end) || event.end <= event.start) return [];
      allDay.push([event.start, event.end]);
    } else {
      const from = instant(event?.start), to = instant(event?.end);
      if (!(from < to)) return [];
      busy.push([from, to]);
    }
  }
  // Start on the grid of the queried local midnight, including zones with a fractional UTC offset.
  const first = start + (Math.floor((now - start) / halfHour) + 1) * halfHour;
  const choices = [];
  const displayDate = new Intl.DateTimeFormat(uiLanguage === "zh" ? "zh-CN" : "en-AU",
    { timeZone: window.timezone, year: "numeric", month: "long", day: "numeric" });
  let lastDay;
  for (let at = first; at + halfHour <= Math.min(end, now + 21 * day) && choices.length < 3; at += halfHour) {
    const local = Object.fromEntries(clock.formatToParts(at).map(({type, value}) => [type, value]));
    const date = [local.year, local.month, local.day].join("-");
    if (date === lastDay || ["Sat", "Sun"].includes(local.weekday) || +local.hour < 9 || +local.hour >= 17
        || allDay.some(([from, to]) => from <= date && date < to)
        || busy.some(([from, to]) => from < at + halfHour && at < to)) continue;
    const until = new Date(at + halfHour);
    const finish = Object.fromEntries(clock.formatToParts(until).map(({type, value}) => [type, value]));
    choices.push(displayDate.format(at) + " · " + local.hour + ":" + local.minute + "–" + finish.hour + ":" + finish.minute + " (" + window.timezone + ")");
    lastDay = date;
  }
  return choices;
}
function schedulingInputs(row, needsPlace, fills, i, onChange, keep) {
  const suggestions = REM.shared ? [] : calendarSlotChoices(REM.calendar);
  const field = (label, suffix) => el("input", { type: "text", "aria-label": t(label), placeholder: t(label),
    ...(keep ? { "data-keep": keep + ":" + i + suffix } : {}) });
  const time = field("Meeting time or alternatives", "");
  const place = needsPlace ? field("Meeting location (required)", ":location") : null;
  if (place) time.required = place.required = true;
  const buttons = new Map();
  const times = () => (time.value || "").split(" / ").map(value => value.trim()).filter(Boolean);
  const update = () => {
    const answer = time.value.trim(), location = place?.value.trim();
    fills[i] = answer && (!place || location) ? [answer, location].filter(Boolean).join(" · ") : undefined;
    const offered = times();
    for (const [choice, button] of buttons) button.setAttribute("aria-pressed", String(offered.includes(choice)));
    onChange();
  };
  row.appendChild(el("span", { text: t(suggestions.length ? "Choose one or more times, or enter your own."
    : "No verified calendar times. Enter a time manually.") }));
  for (const choice of suggestions) {
    const button = el("button", { type: "button", "aria-pressed": "false", text: choice });
    buttons.set(choice, button);
    button.onclick = () => {
      const offered = times();
      if (offered.includes(choice)) time.value = offered.filter(value => value !== choice).join(" / ");
      else if (calendarSlotChoices(REM.calendar).includes(choice)) time.value = [...offered, choice].join(" / ");
      else { button.disabled = true; time.focus(); return; }
      time.dispatchEvent(new Event("input", { bubbles: true }));
    };
    row.appendChild(button);
  }
  time.oninput = update;
  row.appendChild(time);
  if (place) { place.oninput = update; row.appendChild(place); }
}
function slotChoices(part, fills, i, onChange, keep) {
  const what = slotWhat(part);
  const choices = what.split(/\s+\/\s+|\s*／\s*|\s*｜\s*|\s+\|\s+|\s*还是\s*|\s*或者\s*/).filter(Boolean);
  const needsPlace = /地点|地址|场地|\b(?:place|location|venue|address|where to meet)\b/i.test(what);
  const schedule = schedulingQuestion(what) && (choices.length === 1 || needsPlace);
  const label = choices.length > 1 && !schedule ? t("Your call") : what;
  const row = el("span", { class: "owner-slot choose", role: "group", "aria-label": label }, [el("span", { class: "k", text: label + (uiLanguage === "zh" ? "：" : ": ") })]);
  if (schedule) {
    schedulingInputs(row, needsPlace, fills, i, onChange, keep);
  } else if (choices.length > 1) for (const choice of choices) {
    const button = el("button", { type: "button", "aria-pressed": "false", text: choice });
    button.onclick = () => {
      fills[i] = choice;
      for (const other of row.querySelectorAll("button")) other.setAttribute("aria-pressed", String(other === button));
      onChange();
    };
    row.appendChild(button);
  } else {
    const input = el("input", { type: "text", "aria-label": what, placeholder: t("Type your answer"), ...(keep ? { "data-keep": keep + ":" + i } : {}) });
    input.oninput = () => { fills[i] = input.value.trim() || undefined; onChange(); };
    row.appendChild(input);
  }
  row.getAnswerState = () => {
    const inputs = [...row.querySelectorAll("input")];
    return inputs.length ? inputs.map(field => field.value) : [fills[i] || ""];
  };
  row.setAnswerState = state => {
    const inputs = [...row.querySelectorAll("input")];
    if (inputs.length) {
      inputs.forEach((field, index) => { field.value = state[index] || ""; });
      inputs[0].dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      fills[i] = choices.includes(state[0]) ? state[0] : undefined;
      for (const button of row.querySelectorAll("button")) button.setAttribute("aria-pressed", String(button.textContent === fills[i]));
      onChange();
    }
  };
  return row;
}
// What a slot is called beside Send: the label the letter gives it ("Format: 【…】"), else REM's own words, short.
function slotName(parts, i) {
  const label = /(?:^|\n)[ \t]*([^\n:：]{1,24}?)[ \t]*[:：][ \t]*$/.exec(parts[i - 1] || "")?.[1];
  const what = slotWhat(parts[i]).trim();
  return label || (what.length > 24 ? what.slice(0, 22).replace(/\s+\S*$/, "") + "…" : what);
}
// "Choose above" did not say what: the hint names each choice still open, and a tap on a name takes you to it.
function chooseHint(hint, open) {
  const zh = uiLanguage === "zh";
  hint.replaceChildren(t(open.length === 1 ? "1 choice left: " : "{n} choices left: ", { n: open.length }), ...open.flatMap(([name, row], k) => {
    const jump = el("a", { href: "#", class: "slot-jump", text: name });
    jump.onclick = event => {
      event.preventDefault();
      row.scrollIntoView({ block: "center", behavior: motionStilled() ? "auto" : "smooth" });
      row.querySelector("button, input")?.focus({ preventScroll: true });
    };
    return [k ? (zh ? "、" : ", ") : "", jump];
  }));
}
// What REM did, in one line: the message it read and what it wrote, on the card and in full screen alike.
function remDid(draft) {
  const read = (draft.sources || []).map(id => (REM.source_context || {})[id]).filter(Boolean).at(-1);
  const subject = (read?.subject || draft.subject || "").replace(/^\s*(?:re|fw|fwd|回复|答复|转发)\s*[:：]\s*/i, "").trim();
  return read?.time && subject ? t("REM read the {date} message “{subject}” and drafted this reply.", { date: fmtDate(calendarDay(read.time)), subject })
    : subject ? t("REM read the thread “{subject}” and drafted this reply.", { subject })
    : t("REM drafted this reply from the thread.");
}
function replyDraftCard(draft, onSent, person, extra = {}) {
  const parts = draft.body.split(/(\[[^\]]*(?:\]|$)|［[^］]*(?:］|$)|【[^】]*(?:】|$))/g);
  const fills = {}, filled = () => parts.every((part, i) => !/^(?:\[|［|【)/.test(part) || fills[i])
    ? parts.map((part, i) => fills[i] ?? part).join("") : null;
  // REM's questions sit above Send, outside the letter's scroll window, so the choice is never out of sight;
  // the letter keeps a marker in their place that shows the answer once it is chosen.
  const isSlot = part => /^(?:\[|［|【)/.test(part), markers = {};
  const syncChoices = () => {
    for (const [i, marker] of Object.entries(markers)) marker.textContent = fills[i] || slotWhat(parts[i]);
    status.textContent = "";
    // An open part leaves Send clickable and only looking unready (aria-disabled): a disabled button swallowed the
    // owner's click without a word (2026-11-18, a Lark reply to the Jane card); the click now says what is missing.
    // Send never looks disabled (#3312 E): a click with a question open goes to it and says which one.
    hint.hidden = filled() !== null;
    const open = parts.map((part, i) => i).filter(i => isSlot(parts[i]) && !fills[i]);
    if (open.length) chooseHint(hint, open.map(i => [slotName(parts, i), rowAt[i]]));
  };
  const rowAt = {};
  const choiceRows = parts.map((part, i) => isSlot(part) ? (rowAt[i] = slotChoices(part, fills, i, () => syncChoices(), draft.id && "slot:" + draft.id)) : null).filter(Boolean);
  const hint = el("span", { class: "choose-hint" });
  const provider = draft.provider === "gmail" ? "Gmail" : "Outlook";
  const status = el("p", { class: "quiet-line mail-status", role: "status" });
  const send = el("button", { type: "button", class: "btn-act", text: t("Send") });
  const edit = el("button", { type: "button", class: "btn-quiet edit-provider", text: t("Edit in {provider}", { provider }) });
  const skip = el("button", { type: "button", class: "btn-quiet", text: t("Skip"), ...snapshotWhy("This is an offline snapshot; open REM to mark it.") });
  const writeLabel = t("Write full screen");
  const write = el("button", { type: "button", class: "ibtn mail-write mail-write-labeled", "aria-label": writeLabel, title: writeLabel + " · R", "data-key": "r" }, [
    icon("expand"), el("span", { class: "mail-write-label", text: writeLabel })]);
  const to = mailbox(draft.to), who = personByAddress(to.address), channel = draft.channel || "mail";
  const reach = replyChannel(draft, who?.title || to.name);
  // Only channels this person can be reached on (#3302): the Host lists them from the person's page. A switch
  // says what it does, and while REM rewrites, the pill itself says so.
  const offered = (draft.channels?.length ? draft.channels : [channel]).filter(name => ["mail", "lark", "whatsapp"].includes(name));
  if (!offered.includes(channel)) offered.unshift(channel);
  const channelName = name => t({ mail: "Mail", lark: "Lark", whatsapp: "WhatsApp" }[name]);
  const channels = el("div", { class: "mail-channels", role: "group", "aria-label": t("Reply channel"), ...(offered.length > 1 ? {} : { hidden: "" }) }, offered.map(name => {
    const pill = el("button", { type: "button", class: "channel" + (name === channel ? " active" : ""), "aria-pressed": String(name === channel),
      text: name === channel ? channelName(name) : t("Switch to {channel}", { channel: channelName(name) }),
      ...(name === channel ? {} : { title: t(name === "mail" ? "REM rewrites it as an email." : "REM rewrites it as a chat message.") }) });
    if (name !== channel) pill.onclick = () => { pill.textContent = t("Rewriting for {channel}…", { channel: channelName(name) }); run("redraft", undefined, name); };
    return pill;
  }));
  // Send is the one green action. Writing full screen stays in sight beside it: behind 更多 the owner could not find
  // it (sprint 22); editing in the mail app and Skip wait behind 更多 (D-120).
  // Provider tools stay in More. A single Today item has its own visible triage footer.
  const more = el("details", { class: "more-menu" }, [el("summary", { "aria-label": t("More"), title: t("More") }, [icon("more")]),
    el("div", { class: "menu" }, [...(channel === "mail" ? [edit] : []), extra.triage ? null : skip, directSendItem(who || person)].filter(Boolean))]);
  const actions = el("div", { class: "mail-actions" }, [hint, ...(reach.defect ? [el("span", { class: "choose-hint", text: reach.held })] : []),
      el("span", { class: "mail-note", text: reach.defect ? reach.footer : channel === "mail" ? t("Sends from {mailbox} via {provider}", { mailbox: draft.from, provider })
        : t("Sends as you via {tool}", { tool: channel === "lark" ? "lark-cli" : "co whatsapp" }) }), write, more, send]);
  const why = draft.why ? el("p", { class: "mail-why" }, [el("span", { class: "k", text: t("Why this reply") }), " ", draft.why]) : null;
  let letter;
  // Rewritten for a chat this person is not on: said so, never sent, and mail offered (#3312 C).
  const defectWords = reach.defectWords;
  const backToMail = el("button", { type: "button", class: "btn-line", text: t("Rewrite it as an email") });
  if (reach.defect) { backToMail.className = "btn-act"; send.className = "btn-quiet"; }
  const defect = reach.defect ? el("p", { class: "mail-defect", role: "alert" }, [defectWords, " ", backToMail])
    : reach.note ? el("p", { class: "mail-redrafted", role: "status", text: reach.note }) : null;
  const card = el("section", { class: "mailcard" + (channel === "mail" ? "" : " chat"), "aria-label": t("Reply draft") }, [
    el("div", { class: "mail-head" }, [channels, ...(channel === "mail" ? [
      el("div", { class: "mail-row" }, [el("span", { class: "k", text: t("To") }), el("span", { class: "v" }, [
        draft.provider === "outlook" ? outlookMark() : null, who ? el("a", { href: href(who), text: who.title }) : el("span", { text: to.name }), el("span", { class: "addr", text: " <" + to.address + ">" })])]),
      el("div", { class: "mail-row" }, [el("span", { class: "k", text: t("CC") }), el("span", { class: "v" + (draft.cc ? "" : " addr"), text: draft.cc || t("No one") })]),
      el("div", { class: "mail-row" }, [el("span", { class: "k", text: t("Subject") }), el("span", { class: "v subject", text: draft.subject })])]
      : [el("div", { class: "mail-row" }, [el("span", { class: "k", text: t("To") }), el("span", { class: "v" }, [who ? el("a", { href: href(who), text: who.title }) : el("span", { text: to.name }),
          el("span", { class: "addr", text: " · " + t({ lark: "Lark", whatsapp: "WhatsApp" }[channel]) })])])])]),
    letter = el("div", { class: "mail-body" + (draft.gist ? " bilingual" : "") }, [
      el("div", { class: "mail-text", ...(parts.length > 1 ? {} : {text: draft.body}) },
        // The choice row is a block of its own, so the blank lines around it would only add height.
        parts.length > 1 ? parts.map((part, i) => isSlot(part) ? (markers[i] = el("span", { class: "slot-ref", text: slotWhat(part) })) : part) : []),
      // Why this reply sits under the owner's-language reading, beside the letter, not under it.
      draft.gist ? el("div", { class: "mail-gist" }, [el("span", { class: "k", text: gistTitle(draft.gist) }), el("p", { text: draft.gist }), why]) : null]),
    // The dock: REM's choices, a defect if any, and Send. On a phone it is pinned above the tab bar together, so
    // the owner reads, picks and sends with the thumb and nothing he must tap ever sits under it (#3312 H).
    draft.gist ? null : why, el("div", { class: "mail-dock" }, [choiceRows.length ? el("div", { class: "mail-choices" }, choiceRows) : null, defect, actions, extra.triage ? el("div", {class: "draft-triage"}, [extra.triage]) : null]), status,
    el("p", { class: "mail-did" }, [remDid(draft)])]);
  // The letter is shown whole; past about fourteen lines it fades and 展开全文 opens the rest (#3312 B4).
  // Measured when the letter gets its size (a card raised later is laid out later), not once at the first frame.
  const measure = () => {
    if (!letter.isConnected || letter.classList.contains("long") || letter.classList.contains("whole")
      || letter.scrollHeight <= letter.clientHeight + 4) return;
    letter.classList.add("long");
    // The fold falls between two lines, never through one (the owner's letters were cut mid-sentence).
    const text = letter.querySelector(".mail-text");
    if (text) {
      const style = getComputedStyle(text), line = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.6;
      letter.style.maxHeight = parseFloat(style.paddingTop) + (innerWidth < 720 ? 8 : 14) * line + "px";
    }
    const unfold = el("button", { type: "button", class: "btn-quiet mail-unfold", text: t("Show the whole letter") });
    unfold.onclick = () => { letter.classList.remove("long"); letter.classList.add("whole"); letter.style.maxHeight = ""; unfold.remove(); };
    letter.after(unfold);
  };
  if (globalThis.ResizeObserver) new ResizeObserver(measure).observe(letter);
  if (!REM.live) {
    // A snapshot cannot send (D-60): Send is shown disabled, and the page says why once, never with a command.
    actions.replaceChildren(el("button", {type: "button", class: "btn-act", disabled: "", text: t("Send")}));
    channels.replaceChildren(el("span", {text: t({mail: "Mail", lark: "Lark", whatsapp: "WhatsApp"}[channel])}));
    return draft.private ? privateFallback(el("div", {}, [el("div", {class: "private"}, [card])])) : card;
  }
  const busy = (on, sending) => {
    send.disabled = edit.disabled = skip.disabled = write.disabled = on;
    send.textContent = t(on && sending ? "Sending…" : "Send");
    if (!on) syncChoices();
  };
  syncChoices();
  const act = async (action, body, channel) => {
    busy(true, action === "send");
    status.textContent = t(action === "redraft" ? "Rewriting for {channel}…" : "Working…", { channel: t({ mail: "Mail", lark: "Lark", whatsapp: "WhatsApp" }[channel] || "") });
    const response = await fetch("/rem/draft", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: draft.id, action, ...(body ? { body } : {}), ...(channel ? { channel } : {}) }) });
    const result = await response.json();
    busy(false);
    if (!response.ok) return status.textContent = result.error || t("Could not update draft");
    if (action === "open") {
      status.replaceChildren(el("a", { href: result.url, target: "_blank", rel: "noopener", text: t("Continue in {provider} drafts", { provider }) }));
      window.open(result.url, "_blank", "noopener");
      return "";
    }
    if (action === "redraft") {
      REM.drafts = REM.drafts.map(d => d.id === draft.id ? result : d);
      card.replaceWith(replyDraftCard(result, onSent, person, extra));
      return "";
    }
    const next = action === "send" ? "sent" : "discarded";
    REM.drafts = REM.drafts.map(d => d.id === draft.id ? { ...d, status: next } : d);
    card.replaceChildren(el("p", { class: "mail-done", text: t(next === "sent" ? "Sent to {name}" : "Skipped", { name: who?.title || to.name }) }));
    if (next === "sent") onSent?.();
    return "";
  };
  // Every path answers with the reason it failed, or "" when it worked, so the full-screen writer can say it too.
  const run = (action, body, channel) => act(action, body, channel).catch(() => { busy(false); return status.textContent = t("Could not update draft. Check the connection and try again."); });
  // Send is the approval: the reply waits 10 minutes with Undo (D-101). Without an approval
  // outcome for this draft the Host sends at once, and the note after it says it cannot be undone.
  const deliver = async body => {
    const item = (REM.approval_outcomes || []).find(item => item.kind === "reply" && item.draft_id === draft.id);
    if (!item) return run("send", body);
    busy(true, true);
    status.textContent = t("Working…");
    const reply = await approvalRequest({ ids: [item.id], bodies: body ? { [item.id]: body } : {} }).catch(error => ({ error: error.message }));
    const value = (reply.results || []).find(value => value.id === item.id);
    busy(false);
    if (reply.error || !value || value.status === "error") return status.textContent = reply.error || (value ? approvalStatus(value) : t("Could not update draft"));
    REM.approval_outcomes = (REM.approval_outcomes || []).filter(other => other.id !== item.id);
    REM.approval_pending = [...(REM.approval_pending || []).filter(other => other.id !== item.id), { ...item, ...value }];
    REM.drafts = REM.drafts.map(d => d.id === draft.id ? { ...d, status: value.status } : d);
    const release = value.release_at || reply.release_at;
    card.replaceChildren(el("p", { class: "mail-done", role: "status", text: value.status === "held" && release
      ? t("Sending to {name} at {time}.", { name: who?.title || to.name, time: fmtTime(release) }) : t("Sent to {name}", { name: who?.title || to.name }) }));
    onSent?.(value.status === "held" ? { ids: [item.id], release_at: value.release_at || reply.release_at } : null);
    return "";
  };
  backToMail.onclick = () => run("redraft", undefined, "mail");
  send.onclick = () => {
    if (reach.defect) { status.textContent = defectWords; backToMail.focus(); return; }
    const body = filled();
    if (body === null) {
      const open = parts.findIndex((part, i) => isSlot(part) && !fills[i]), first = rowAt[open];
      status.textContent = t("Answer REM's question first: {what}", { what: slotName(parts, open) });
      first?.scrollIntoView({ block: "center", behavior: motionStilled() ? "auto" : "smooth" });
      (first?.querySelector("input:invalid") || first?.querySelector("input, button"))?.focus({ preventScroll: true });
      first?.classList.remove("attention"); void first?.offsetWidth; first?.classList.add("attention");
      return;
    }
    deliver(body === draft.body ? undefined : body);
  };
  write.onclick = () => {
    const answers = Object.fromEntries(Object.entries(rowAt).map(([i, row]) => [i, row.getAnswerState()]));
    openWriter({ ...draft, ask: extra.ask }, who, deliver, () => backToMail.click(), answers);
  };
  edit.onclick = () => run("open");
  skip.onclick = () => {
    const entries = threadEntries().filter(entry => obligationEvidence(entry).ids.has("thread:" + draft.provider + ":" + draft.thread));
    if (entries.length) setDone(entries[0], true, "skipped", entries);
  };
  return draft.private ? privateFallback(el("div", {}, [el("div", { class: "private" }, [card])])) : card;
}
function threadDecisionHistory(r) {
  const current = new Set(threads(r).items.map(t => doneKey({ r, t })));
  const saved = Object.entries(threadStates).filter(([key]) => key.startsWith(r.path + "\n") && !current.has(key));
  if (!saved.length) return null;
  return el("details", { id: "done-history", class: "done-details thread-history" }, [el("summary", { text: closedSummary(saved.map(([, value]) => value)) }),
    el("ul", { class: "threads" }, saved.map(([key, value]) => {
      const entry = { r, t: { text: key.slice(r.path.length + 1) } };
      const undo = el("button", { type: "button", class: "btn-quiet", text: t("Undo"), ...snapshotWhy("This is an offline snapshot; open REM to mark it.") });
      undo.onclick = () => setDone(entry, false);
      return el("li", {}, [privateFallback(el("span", { text: entry.t.text })), " · ",
        el("span", { class: "done-tag", text: stateWord(value.state)
          + " · " + fmtDate(calendarDay(value.at || REM.as_of)) }), undo]);
    }))]);
}
function markedDone(entries) {
  const done = entries.filter(isDone);
  if (!done.length) return null;
  return el("details", { id: "done-today", class: "done-details" }, [el("summary", { text: closedSummary(done.map(entry => threadStates[doneKey(entry)])) }),
    el("p", { class: "quiet-line", text: t(Object.keys(pendingThreads).length
      ? "Saved on this device — sync pending" : "Saved in your notebook. Undo here or on the record page at any time.") }),
    el("ul", { class: "threads" }, done.map(({ r, t, also }) => threadRow(r, t, true, also, true)))]);
}
function threadCounterpart({ r, t }, person) {
  if (person.path === REM.owner) return false;
  const first = REM.owner ? byPath(REM.owner)?.title.trim().split(/\s+/)[0] : "";
  const me = "(?:the user|user|you" + (first ? "|" + first.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") : "") + ")";
  const text = t.text.replaceAll("**", "");
  const named = new RegExp("^" + me + "\\s+(?:owes?|asked)\\s+(.+)", "i").exec(text)?.[1]
    || new RegExp("^(.+?)\\s+owes?\\s+" + me + "\\b", "i").exec(text)?.[1] || "";
  const link = /^\s*\[[^\]]+\]\(([^)]+\.md)\)/.exec(named);
  if (link && resolve(r.path, link[1]) === person.path) return true;
  const words = obligationWords(named.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")), title = obligationWords(person.title);
  return !!title && (words === title || words.startsWith(title + " "));
}
// A reply sent, or held for its 10 minutes, answers the item until Undo.
function answered(entry) { return ["held", "sent"].includes(threadDraft(entry)?.status); }
// The one "waiting on you": an item you owe, not quiet, not a stale promise (asked about apart), not answered.
// Today's header, the rail badge and the rows of Waiting on you all read it, so they never disagree (sprint 14).
function waitingOnYou(entry) {
  return entry.t.dir === "mine" && !entry.t.quiet && !staleEntry(entry) && !answered(entry);
}
function threadCounts() {
  const counts = { mine: 0, theirs: 0, other: 0, quiet: 0, open: 0 };
  for (const entry of threadEntries().filter(entry => !isDone(entry))) {
    const t = entry.t;
    // A stale promise is counted with the quiet ones, never as waiting (staleEntry).
    if (t.quiet || staleEntry(entry)) counts.quiet++;
    else if (t.dir === "mine") { if (waitingOnYou(entry)) { counts.mine++; counts.open++; } }
    else { counts[t.dir === "plain" ? "other" : t.dir]++; counts.open++; }
  }
  return counts;
}
function historyItems(text) {
  return listItems(text).map(t => {
    // A range is one entry dated by its start: "2026-07-05–17", "2026-07-29–08-04" (#2059),
    // "2026-08-26–2026-08-28" and "2026-09-23 to 2026-10-09" (1.9.2b1).
    const m = /^(?:\*\*)?(\d{4}-\d{2}(?:-\d{2})?)(?:\s*(?:[–-]|to)\s*((?:\d{4}-)?(?:\d{2}-)?\d{2})(?!\d))?(?:\*\*)?\s*(?:[:：]|[—–]|\s-\s)\s*(?:\*\*)?\s*(.*)$/.exec(t);
    if (!m) return { day: "", end: "", text: t };
    return { day: m[1], end: m[2] ? m[1].slice(0, m[1].length - m[2].length) + m[2] : "", text: m[3] };
  });
}
// A range on two lines so it fits the date column: "Aug 26" over "– 28", or
// "Jul 29" over "– Aug 4". A month alone is "Oct 2025", not the 1st of it.
function dayLabel(item) {
  const one = d => d.length === 7 ? new Date(d + "-01T00:00:00Z").toLocaleDateString(uiLocale(), { timeZone: "UTC", month: "short", year: "numeric" }) : shortDate(d);
  if (!item.end || item.end === item.day) return one(item.day);
  const sameMonth = item.end.length === 10 && item.end.slice(0, 7) === item.day.slice(0, 7);
  return one(item.day) + "\n– " + (sameMonth ? String(Number(item.end.slice(8))) : one(item.end));
}
// "- [n] id — what it shows; confidence; observed date" -> {n: "id — what it shows ..."}
function rawSection(r, name) {
  const text = r.text.replace(COMMENT, "");
  const m = new RegExp("^## " + name + "[^\\n]*\\n([\\s\\S]*?)(?=^## |^Investigation:|(?![\\s\\S]))", "mi").exec(text);
  return m ? m[1].trim() : "";
}
function sourceList(r) {
  const cache = r?.path ? (sourceList._cache ??= new Map()) : null;
  const cacheKey = cache ? r.path + "\0" + (r.shown || "") + "\0" + (r.text?.length || 0) : "";
  if (cache?.has(cacheKey)) return cache.get(cacheKey);
  // An entry's Sources blocks are gathered into one list, numbered as its page shows them (#3097).
  if (["knowledge", "decisions", "principles"].includes(r.category)) {
    const res = entryOf(r).sources;
    if (cache) cache.set(cacheKey, res);
    return res;
  }
  const out = [];
  const sections = rawSection(r, "Sources");
  const sources = sections.replace(/^([ \t]*)(\d{1,3})\.[ \t]+/gm, "$1- $2. ");
  for (const item of listItems(sources)) {
    const m = /^(?:[\[［](W?\d{1,3})[\]］]|(\d{1,3})\.)\s*(.*)$/.exec(item);
    if (m && !UNKNOWN_TEXT.test(m[3])) out.push({ n: m[1] || m[2],
      text: m[2] ? m[3] : m[3].replace(/[*`]/g, ""), ...(m[2] ? { plain: true } : {}) });
    else if (r.category === "sessions" && /^(?:codex:[^\s:]+:\d+(?:-[0-9a-f]{8})?|claude-code:[^\s:]+:\d+)$/.test(item)) out.push({ n: String(out.length + 1), text: item });
  }
  if (cache) cache.set(cacheKey, out);
  return out;
}
function sourceId(text, plain = false) {
  return plain ? "" : /^([a-z][\w-]*:[^\n]+?)(?=\s+[—–]\s+|\s*$)/i.exec(text)?.[1] || "";
}
// #3104: a source row says what the thing is — a mail's subject, a session's title, a file's name — never
// its hash. The raw id stays in the row's tooltip. {n, id, kind, title, who, channel, day}
const SOURCE_KINDS = ["mail", "session", "file", "other"];
function sourceKind(id, context) {
  const scheme = (context?.source || id.split(":")[0] || "").toLowerCase();
  if (/^(gmail|outlook|imap|mail|attachment|email)$/.test(scheme)) return "mail";
  if (/^(codex|claude|claude-code)$/.test(scheme)) return "session";
  if (/^(file|project-source)$/.test(scheme)) return "file";
  return "other";
}
function sessionForSource(id) {
  const key = /^(?:codex|claude-code|claude):([^\s:]+)/.exec(id)?.[1];
  return key ? (REM.records || []).find(r => r.category === "sessions" && r.session_id && (r.session_id === key || key.endsWith(r.session_id))) : null;
}
function sourceSummary(r, src) {
  // An attachment's id is its mail's id plus the file name; the mail carries the subject and sender.
  const id = sourceId(src.text, src.plain), all = REM.source_context || {};
  const context = id ? all[id] || (/^(gmail|outlook|imap):[^:]+:./.test(id) ? all[id.split(":").slice(0, 2).join(":")] : null) : null;
  const rest = (id ? src.text.slice(src.text.indexOf(id) + id.length) : src.text).replace(/^\s*[—–-]\s*/, "");
  const written = /\b(\d{4}-\d{2}-\d{2})\b/.exec(rest)?.[1] || "";
  // The note is a source's own words: its date is the row's date, not "observed ." left behind (rc34 hunt), and a
  // [personal]/[sensitive] mark on the line is never printed as text.
  const note = rest.replace(/[\[［](?:personal|sensitive)[\]］]/gi, "").replace(/\b(?:observed|seen|written)\s+\d{4}-\d{2}-\d{2}\b/gi, "")
    .replace(/\b\d{4}-\d{2}-\d{2}\b/g, "").replace(/\s*([;·,])(?:\s*[;·,])+/g, "$1").replace(/^[\s;·,.—–-]+|[\s;·,.—–-]+$/g, "");
  const kind = id ? sourceKind(id, context) : "other", parts = id.split(":"), scheme = parts[0].toLowerCase();
  let title = "", who = context ? sourceIdentity(context) : "", day = context?.time ? calendarDay(context.time) : written;
  // A file's name, without its content hash ("CLAUDE.md@be1c3a…") or the folders above it.
  const fileName = path => path.replace(/@[0-9a-f]{12,}$/i, "").split(/[\\/]/).filter(Boolean).at(-1) || path;
  const bare = !id && /^(\/[^\s]+)(?:\s+[—–-]\s+(.*))?$/.exec(src.text);
  if (bare) return { n: src.n, id: bare[1], kind: "file", title: fileName(bare[1]), who: "", channel: t("File"),
    day: written };
  if (!id) title = note || src.text;
  else if (kind === "mail") {
    const file = parts.length > 2 ? parts.slice(2).join(":") : "", subject = context?.subject || REM.conversations?.[context?.thread]?.subject || "";
    // No subject: the first words of the mail itself, not the word "Mail".
    const opening = (context?.excerpt || "").split("\n").map(line => line.trim()).find(line => line && !/^(hi|hello|dear|hey)\b[^.!?]{0,30}[,，]?$/i.test(line) && !/^>/.test(line)) || "";
    title = [file, subject].filter(Boolean).join(" — ") || note || (opening.length > 80 ? opening.slice(0, 79) + "…" : opening)
      || t(context ? "Mail" : "Mail — original not in this snapshot");
  } else if (kind === "session") {
    const session = sessionForSource(id);
    title = session?.session_title || session?.title || note || t(scheme === "codex" ? "Codex session" : "Claude Code session");
    day = day || session?.session_date || "";
  } else if (scheme === "project-source") {
    // Named by the file it captured (context, or the snapshot's small label list when the excerpt had no room), never its hash.
    const origin = context?.origin || REM.source_labels?.[id]?.origin || "";
    title = origin ? fileName(origin.replace(/^(git|file):/, "").replace(/:[0-9a-f]{7,}$/, "").replace(/@[0-9a-f]{64}$/, "")) : t("Repository file");
  } else if (scheme === "file") title = fileName(id.slice(scheme.length + 1).replace(/@[0-9a-f]{64}$/, ""));
  else if (isWebSource(id)) title = webSource(id, context).title;
  else if (scheme === "investigation") title = t("REM investigation") + (note ? " — " + note : "");
  else title = note || sourceLabel(id);
  const channel = !id ? "" : kind === "mail" ? sourceChannel(context?.source && context.source !== "attachment" ? context.source : scheme)
    : kind === "session" ? (scheme === "codex" ? "Codex" : "Claude Code") : kind === "file" ? t("File") : isWebSource(id) ? webSource(id).site : "";
  return { n: src.n, id, kind, title, who, channel, day, ...(id && !context && kind === "mail" ? { missing: true } : {}) };
}
// Most cited first, then newest, then the page's own number.
function sortSources(rows, counts) {
  return rows.slice().sort((a, b) => (counts[b.n] || 0) - (counts[a.n] || 0) || String(b.day).localeCompare(String(a.day))
    || String(a.n).localeCompare(String(b.n), undefined, { numeric: true }));
}
const SOURCE_FIRST = 10, SOURCE_FILTER_AT = 20;
function sourceRow(r, s) {
  const chip = el("span", { html: citeChip(s.n, r.path) }).firstChild;
  chip.classList.add("n", "source-open");
  chip.textContent = s.n;
  const meta = [s.channel, s.who, s.day ? fmtDate(s.day) : ""].filter(Boolean).join(" · ");
  const cited = el("button", { type: "button", class: "src-cited", hidden: "" });
  // The title opens the source itself in the side card (#3134: before the band every source did).
  const title = el("button", { type: "button", class: "src-title" + (s.missing ? " src-missing" : ""), text: s.title, title: t("Open the original") });
  title.onclick = () => openEvidence(r, s.n, title, { fromList: true });
  const li = el("li", { id: "src-" + s.n.toLowerCase(), class: "src-row", "data-kind": s.kind, title: s.id || "" }, [chip,
    title, el("span", { class: "src-meta", text: meta }), cited]);
  li.search = [s.title, s.who, s.channel, s.id, meta].join(" ").toLowerCase();
  return li;
}
// The page's sources as a full-width band: kind chips, a filter above 20, the first 10 and "Show all N".
function sourcesBlock(r) {
  const summaries = sourceList(r).map(src => sourceSummary(r, src));
  if (!summaries.length) return null;
  const state = { kind: "all", query: "", all: false };
  const rows = new Map(summaries.map(s => [s.n, sourceRow(r, s)]));
  const list = el("ol", {}, [...rows.values()]);
  const counts = Object.fromEntries(SOURCE_KINDS.map(kind => [kind, summaries.filter(s => s.kind === kind).length]));
  const kinds = SOURCE_KINDS.filter(kind => counts[kind]);
  const chips = kinds.length > 1 ? el("div", { class: "src-kinds", role: "group", "aria-label": t("Source kinds") },
    ["all", ...kinds].map(kind => {
      const b = el("button", { type: "button", class: "chip ghost", "aria-pressed": String(kind === "all"), "data-kind": kind }, [
        el("span", { text: t({ all: "All", mail: "Mail", session: "Sessions", file: "Files", other: "Other" }[kind]) }),
        el("span", { class: "mono", text: " " + (kind === "all" ? summaries.length : counts[kind]) })]);
      b.onclick = () => { state.kind = kind; apply(); };
      return b;
    })) : null;
  const filter = summaries.length > SOURCE_FILTER_AT ? el("input", { type: "search", class: "src-filter", placeholder: t("Filter sources…"), "aria-label": t("Filter sources") }) : null;
  if (filter) filter.oninput = () => { state.query = filter.value.trim().toLowerCase(); apply(); };
  const more = el("button", { type: "button", class: "chip ghost src-more" });
  more.onclick = () => { state.all = true; apply(); };
  const empty = el("p", { class: "src-empty", text: t("No source matches."), hidden: "" });
  const box = el("section", { class: "deep-sources block-sources", "aria-labelledby": "sources" }, [
    el("h2", { id: "sources", text: t("Sources") }), chips || filter ? el("div", { class: "src-tools" }, [chips, filter]) : null, list, empty, more]);
  function apply() {
    const matching = [...list.children].filter(li => (state.kind === "all" || li.dataset.kind === state.kind) && (!state.query || li.search.includes(state.query)));
    const cap = state.all || state.query ? Infinity : SOURCE_FIRST;
    const shown = new Set(matching.slice(0, cap));
    for (const li of list.children) li.hidden = !shown.has(li);
    chips?.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.kind === state.kind)));
    more.hidden = matching.length <= cap;
    more.textContent = t("Show all {n}", { n: matching.length });
    empty.hidden = matching.length > 0;
  }
  // Counted once the page is built: how many marks on it cite each row, then rows ordered by that.
  box.finish = page => {
    const marks = [...page.querySelectorAll("a.cite[data-sources]")].filter(a => !a.closest(".deep-sources"));
    const citing = n => marks.filter(a => a.dataset.sources.split(" ").includes(n));
    const tally = Object.fromEntries(summaries.map(s => [s.n, citing(s.n).length]));
    for (const s of sortSources(summaries, tally)) {
      const li = rows.get(s.n), button = li.querySelector(".src-cited");
      list.appendChild(li);
      if (!tally[s.n]) continue;
      button.hidden = false;
      button.textContent = t("Cited {n}×", { n: tally[s.n] });
      button.title = t("Jump to the lines that cite it");
      let next = 0;
      button.onclick = () => {
        const all = citing(s.n).filter(a => a.getClientRects().length);
        const mark = all[next++ % Math.max(1, all.length)];
        if (!mark) return;
        for (let p = mark.parentElement; p; p = p.parentElement) if (p.tagName === "DETAILS") p.open = true;
        mark.scrollIntoView({ block: "center" });
        flashNode(mark.closest("li, p, dd") || mark);
      };
    }
    apply();
  };
  // A citation asks for its rows: they show whatever the filter was, lit, the first scrolled to.
  box.reveal = (numbers, scroll = true) => {
    state.kind = "all"; state.query = ""; state.all = true;
    if (filter) filter.value = "";
    apply();
    const targets = numbers.map(n => rows.get(String(n)) || rows.get(String(n).toUpperCase())).filter(Boolean);
    targets.forEach(flashNode);
    if (scroll && targets[0]) targets[0].scrollIntoView({ block: "center" });
    return targets;
  };
  apply();
  return box;
}
function flashNode(node) {
  node.classList.remove("flash");
  void node.offsetWidth;
  node.classList.add("flash");
  setTimeout(() => node.classList.remove("flash"), 2400);
}
const CONTACT_FIELDS = ["Email", "Phone", "Company", "Role", "Signing entity", "Handles", "Language", "Also known as"];
// A page's fact lines (#2068): `## Facts`, or `## Contact` on a page written before it.
// Mirrors facts.parse(): {label: [{value, qualifier, citations}]}, [] when Unknown.
// Values split on "; ", a trailing "(work)" is a qualifier, trailing [n] / [W1] are citations.
const PARSED_FACTS = new Map();
// "A (x; y); B" -> ["A (x; y)", "B"]: a semicolon inside brackets is part of its role, never a cut.
function topLevelParts(value) {
  const parts = [""];
  let depth = 0;
  for (const ch of String(value)) {
    depth += "([{（【".includes(ch) ? 1 : ")]}）】".includes(ch) && depth ? -1 : 0;
    if (ch === ";" && !depth) parts.push(""); else parts[parts.length - 1] += ch;
  }
  return parts.map(part => part.trim()).filter(Boolean);
}
function parseFacts(r) {
  const language = r.readLanguage ?? (uiLanguage === "en" ? (r.shown || "") : uiLanguage);
  const text = r.translations?.[language] ?? (r.shown ? r.original ?? r.text : r.text);
  const key = JSON.stringify([r.path, language]), cached = PARSED_FACTS.get(key);
  if (cached?.text === text) return cached.facts;
  const out = new Map();
  const page = { ...r, text }, raw = rawSection(page, "Facts") || rawSection(page, "Contact");
  for (const line of raw.split("\n")) {
    const m = /^\s*[-*]\s+([^:：\n]{1,40})[:：]\s*(.*)$/.exec(line);
    if (!m) continue;
    const value = m[2].trim();
    const items = [];
    if (value && !/^(unknown|not known)\b/i.test(value)) {
      // Split and qualify as facts.py values() does: ";" outside brackets, a trailing "(qualifier)".
      for (const part of topLevelParts(value.replace(/；\s*/g, "; "))) {
        const cites = /((?:\s*[\[［]W?\d{1,3}[\]］])+)\s*$/.exec(part);
        let v = cites ? part.slice(0, cites.index) : part;
        // "(mobile)" is a qualifier; "[UNSW](../orgs/unsw.md)" is a link, not one.
        const q = /(?:(?<!\])\s*\(([^()]+)\)|（([^（）]+)）)\s*$/.exec(v);
        if (q) v = v.slice(0, q.index);
        if (v.trim()) items.push({ value: v.trim(), qualifier: q ? q[1] || q[2] : "", citations: cites ? cites[1].match(/W?\d{1,3}/g) : [] });
      }
    }
    out.set(m[1].trim(), items);
  }
  PARSED_FACTS.set(key, { text, facts: out });
  return out;
}
function contactFields(r) {
  return [...parseFacts(r)].map(([label, items]) => ({ label, value: items.map(i => i.value + (i.citations.length ? " [" + i.citations.join("][") + "]" : "")).join("; ") }));
}
// A skill's Usage history line (skill_usage.py usage_line).
function skillUsage(r) {
  const m = /Invoked (once|(\d+) times)[^\n]*?last (\d+) days[^\n]*?last on (\d{4}-\d{2}-\d{2})(?: \(([^)]*)\))?/.exec(r.original ?? r.text);
  if (m) return { count: m[2] ? Number(m[2]) : 1, days: Number(m[3]), last: m[4],
    tools: (m[5] || "").replace(/\b(Claude Code|Codex|co ai) (\d+)\b/g, (_, tool, n) => n + " matches in " + tool) };
  const none = /No invocation found[^\n]*?last (\d+) days/.exec(r.original ?? r.text);
  return none ? { count: 0, days: Number(none[1]), last: "", tools: "" } : null;
}
function usageCaption(u) {
  return u.count ? t(u.count === 1 ? "{n} skill-name match · last {last} · version unverified" : "{n} skill-name matches · last {last} · version unverified", { n: u.count, last: fmtDate(u.last) })
    : t("0 skill-name matches in {n} days · version unverified", { n: u.days });
}
let MAX_USAGE = null;
function maxUsage() {
  if (MAX_USAGE === null) MAX_USAGE = Math.max(1, ...inCategory("skills").map(r => (skillUsage(r) || { count: 0 }).count));
  return MAX_USAGE;
}
function usageBar(u) {
  const pct = Math.round(100 * u.count / maxUsage());
  return el("span", { class: "bar", title: t("{n} of the most-used skill's {m}", { n: u.count, m: maxUsage() }) }, [el("i", { style: "width:" + Math.max(u.count ? 3 : 0, pct) + "%" })]);
}
function company(r) {
  const c = contactFields(r).find(f => f.label === "Company");
  return c && c.value ? plainLine(c.value) : "";
}

// ---------- facts: a page as fields (#2064, #2068) ----------
// One adapter turns a page into the facts the tables and fact cards show. Today
// it reads the page's own fields (Contact, Paths, Domains) and the map's mail
// counts (reader.py mail_facts); when the notebook keeps facts in an index
// (#2067) only this function changes.
const FACTS = new Map();
function facts(r) {
  const uiLang = typeof uiLanguage !== "undefined" ? uiLanguage : "en";
  const variant = (r.shown || "") + "\0" + (r.readLanguage ?? (uiLang === "en" ? (r.shown || "") : uiLang));
  let bucket = FACTS.get(r.path);
  const cached = bucket?.[variant];
  if (cached && cached.text === r.text && cached.index === r.index && cached.mail === r.mail && cached.last_activity === r.last_activity) return cached.value;
  const parsed = parseFacts(r);
  const k = known(r), contact = {};
  // Preserve qualifications, especially historical roles and affiliations.
  for (const [label, items] of parsed) contact[label.toLowerCase()] = items.map(i => i.value + (i.qualifier ? " (" + i.qualifier + ")" : "")).join("; ");
  const text = r.text.replace(COMMENT, "");
  const lineOf = name => { const s = section(r, name); return s ? plainLine(s.text, true) : ""; };
  const history = historyItems((section(r, "history") || { text: "" }).text).filter(i => i.day).map(i => i.end || i.day).sort();
  const observed = /Observed mail count[:：]\s*(\d+);\s*first[:：]\s*(\d{4}-\d{2}-\d{2})/.exec(text);
  const paths = listItems(rawSection(r, "Paths"));
  const field = re => (paths.map(p => re.exec(p)).find(Boolean) || [])[1] || "";
  const t = threads(r);
  const f = {
    email: contact.email || ((text.match(/[\w.+-]+@[\w-]+\.[\w.-]+/) || [])[0] || ""),
    company: contact.company || "", role: contact.role || "", phone: contact.phone || "",
    location: contact.location || contact["time zone"] || contact.timezone || "",
    links: contact.links || [...new Set((rawSection(r, "Contact").match(/https?:\/\/[^\s)\]]+/g) || []))].join(", "),
    language: contact.language || "",
    how: lineOf("why they are here") || lineOf("our relationship"),
    first: (r.mail && r.mail.first) || (observed && observed[2]) || history[0] || field(/^First seen[:：]\s*(\S+)/),
    last: k.last || (r.mail && r.mail.last) || "", mails: r.mail ? r.mail.mails : observed ? Number(observed[1]) : null,
    sent: r.mail ? r.mail.sent : null, received: r.mail ? r.mail.received : null,
    open: t.items, calm: t.calm,
    what: contact["what they do"] || lineOf("what it is") || lineOf("who they are") || lineOf("what it does"),
    domain: contact.website || r.domain || plainLine(rawSection(r, "Domains")).replace(/\s*\[\d+\]/g, ""),
    people: listItems((section(r, "people here") || section(r, "people and ownership") || { text: "" }).text)
      .filter(item => /\]\((?:\.\.\/|\.\/)?people\/[^)]+\.md\)/.test(item)).length,
    sessions: Number(field(/^Sessions[:：]\s*(\d+)/)) || null
  };
  // The index (#2067) supplies derived columns; explicit page Company/Role fields
  // remain authoritative, including Unknown and historical qualifications.
  const x = r.index;
  if (x) {
    const take = (key, value) => { if (value != null && value !== "" && !(Array.isArray(value) && !value.length)) f[key] = value; };
    if (!parsed.has("Email")) take("email", Array.isArray(x.emails) ? x.emails.join("; ") : x.emails);
    if (!parsed.has("Phone")) take("phone", x.phone);
    if (!parsed.has("Language")) take("language", x.language);
    // Reviewed page fields, including explicit Unknown, supersede derived index values.
    if (!parsed.has("Company")) take("company", x.company);
    if (!parsed.has("Role")) take("role", x.role);
    if (!["Location", "Time zone", "Timezone"].some(label => parsed.has(label))) take("location", [x.location, x.timezone].filter(Boolean).join(" · "));
    if (!parsed.has("Links")) take("links", [x.linkedin, x.website].filter(Boolean).join(", "));
    if (!r.shown || !f.how) take("how", x.how_known);
    take("first", x.first_contact);
    // The page census owns activity dates; an older index must not contradict it.
    take("last", r.last_activity === undefined ? x.last_contact : k.last);
    if (x.relationship?.last_mail) f.last = x.relationship.last_mail.slice(0, 10);
    take("mails", x.mails); take("sent", x.sent); take("received", x.received);
  }
  if (!bucket) FACTS.set(r.path, bucket = Object.create(null));
  bucket[variant] = { parsed, text: r.text, index: r.index, mail: r.mail, last_activity: r.last_activity, value: f };
  return f;
}
function plainValue(v) { return plainLine(v || ""); }

// Relationship counts use synced mail metadata, never prose or a model (#2843).
function relationshipCell(r, key) {
  const stats = r.index?.relationship;
  if (!stats) return textCell("");
  if (!stats.last_mail) return key === "trend" ? textCell(t("No indexed mail")) : textCell("");
  if (key === "contact") {
    const counts = stats.weekly_messages, peak = Math.max(1, ...counts);
    const bars = counts.map((n, i) => `<rect x="${i * 2}" y="${24 - n / peak * 23}" width="1.5" height="${Math.max(0.5, n / peak * 23)}"/>`).join("");
    const title = t("{n} messages · 52 weeks, oldest first", { n: counts.reduce((a, b) => a + b, 0) });
    return el("span", { class: "contact-spark", title, html: `<svg viewBox="0 0 104 24" role="img" aria-label="${esc(title)}"><title>${esc(title)}</title>${bars}</svg>` });
  }
  if (key === "starts") {
    const them = Math.round(stats.started_by_them_percent);
    return el("span", { class: "mono", title: t("Threads started in the last 90 days; first indexed message") + ` · ${stats.started_by_them}/${stats.threads_90d}`,
    text: stats.started_by_them_percent == null ? "—" : t("{n}% them · {m}% you", { n: them, m: 100 - them }) });
  }
  if (key === "replies") {
    const duration = seconds => seconds == null ? "—" : seconds < 3600 ? Math.round(seconds / 60) + "m" : seconds < 86400 ? (seconds / 3600).toFixed(1) + "h" : (seconds / 86400).toFixed(1) + "d";
    return el("span", { class: "mono", title: t("Median reply time · all indexed history; consecutive turns in the same thread"),
      text: t("{n} them · {m} you", { n: duration(stats.reply_seconds_them), m: duration(stats.reply_seconds_owner) }) });
  }
  const change = stats.change_percent;
  return el("span", { class: "mono", title: t("Daily message rate: last 30 days vs prior 90 days") + ` · ${stats.messages_30d} / ${stats.messages_prior_90d}`,
    text: change == null ? t(stats.trend === "new" ? "↑ New contact" : "No recent mail") : (change > 0 ? "↑ " : change < 0 ? "↓ " : "→ ") + Math.abs(change) + "%" });
}

// ---------- the sheet: People, Organisations, Projects as a table (#2064) ----------
const OPEN_RANK = { mine: 0, theirs: 1, plain: 2 };
function openCell(f) {
  if (!f.open.length) return f.calm ? el("span", { class: "unk", text: t("nothing open") }) : el("span", { class: "unk", text: "—" });
  const thread = f.open[0];
  return el("span", { class: "open-cell " + thread.dir, title: withoutDateClutter(displayLine(thread.text)) }, [el("span", { class: "dir", text: t(DIRECTION_LABEL[thread.dir]) }),
    el("span", { class: "txt", text: withoutDateClutter(displayLine(thread.text)) }), f.open.length > 1 ? el("span", { class: "more", text: "+" + (f.open.length - 1) }) : null]);
}
function dateCell(day, fromMap=false) { return day ? el("span", { class: "mono", title: fromMap ? t("Last contact in map") : "",
  text: shortDate(day) }) : el("span", { class: "unk", text: "—" }); }
function privateFallback(node) {
  const visible = node.cloneNode(true);
  visible.querySelectorAll(".private, .cite, .privacy-tag").forEach(span => span.remove());
  if (node.querySelector(".private") && !/[\p{L}\p{N}]/u.test(visible.textContent)) {
    const content = el("span", { class: "privacy-content" });
    while (node.firstChild) content.appendChild(node.firstChild);
    node.append(content, el("span", { class: "private-hidden-notice", text: t("Hidden labelled passage") }));
    node.classList.add("privacy-only");
  }
  return node;
}
function textCell(v) { return v ? privateFallback(el("span", { class: "clamp",
  title: hasPrivacy(v) ? "" : plainLine(v),
  html: inline(v.replace(/\s*\[W?\d{1,3}\]/g, ""), "") })) : el("span", { class: "unk", text: "—" }); }
function roleSummary(value, from) {
  // Labelled passages retain their full privacy boundary.
  const roles = hasPrivacy(value) ? [value] : topLevelParts(value);
  return privateFallback(el("span", { title: hasPrivacy(value) ? "" : plainLine(value) }, [
    el("span", { html: inline(labelWord(roles[0].replace(/\s*\[W?\d{1,3}\]/g, "")), from) }),
    roles.length > 1 ? el("span", { class: "role-more", text: " +" + (roles.length - 1) }) : null]));
}
function peopleEmails(value) {
  const addresses = plainValue(value).match(/[^\s<>(),;]+@[^\s<>(),;]+/g) || [];
  return peopleContact(addresses, "email");
}
function peoplePhones(value) {
  return peopleContact(plainValue(value).split(/\s*[;,]\s*/).filter(Boolean), "phone");
}
function peopleContact(values, kind) {
  if (!values.length) return textCell("");
  return el("span", { class: "people-" + kind + "s", title: values.join("; ") }, [
    el(kind === "email" ? "a" : "span", { class: "contact-first " + kind + "-first", text: values[0],
      ...(kind === "email" ? { href: "mailto:" + values[0] } : {}) }),
    values.length > 1 ? el("span", { class: "contact-more " + kind + "-more", text: "+" + (values.length - 1) }) : null]);
}
function nameCell(r, f, withSummary) {
  const k = known(r);
  return el("div", { class: "name-cell" }, [el("span", { class: "nm" }, [el("span", { class: "st", role: "img", title: t(k.status), "aria-label": t(k.status) }, [moon(k.status)]), el("a", { href: href(r), text: r.title }), updatedMarker(r)]),
    withSummary && k.summary ? el("span", { class: "sum", text: withoutDateClutter(summaryLine(k.summary)) }) : null]);
}
const COLUMNS = {
  orgs: [
    { key: "name", label: "Name", cls: "name", sort: r => r.title.toLowerCase(), cell: (r, f) => nameCell(r, f, false) },
    { key: "domain", label: "Domain", cls: "mono-col", sort: (r, f) => f.domain || "￿", cell: (r, f) => f.domain ? el("span", { class: "mono", text: f.domain }) : textCell("") },
    { key: "what", label: "What they do", cls: "wide", sort: (r, f) => f.what || "￿", cell: (r, f) => textCell(f.what) },
    { key: "people", label: "People", num: true, sort: (r, f) => f.people, cell: (r, f) => el("span", { class: "mono", text: f.people ? String(f.people) : "—" }), desc: true },
    { key: "last", label: "Last contact", num: true, sort: (r, f) => f.last || "", cell: (r, f) => dateCell(f.last), desc: true },
    { key: "open", label: "What's open", cls: "open-col", sort: (r, f) => f.open.length ? OPEN_RANK[f.open[0].dir] : 9, cell: (r, f) => openCell(f) },
    { key: "status", label: "Status", sort: r => ({ "Investigated": 0, "Partly investigated": 1 })[known(r).status] ?? 2, cell: r => statusPill(r) }]
};
const FILTERS = [
  ["all", "All", () => true], ["open", "Something open", (r, f) => f.open.length > 0],
  ["mine", "Yours to answer", (r, f) => f.open.some(t => t.dir === "mine")],
  ["written", "Written", r => known(r).status !== "Mapped"], ["mapped", "Mapped only", r => known(r).status === "Mapped"]];
const SHEET = {};
function sheet(c, items) {
  const cols = COLUMNS[c].filter(col => col.key !== "status" || items.some(r => known(r).status !== "Investigated"));
  const state = SHEET[c] = SHEET[c] || { sort: null, desc: false, filter: "all", text: "" };
  const wrap = el("div", { class: "sheet-box" });
  const bar = el("div", { class: "sheet-bar" });
  const find = el("input", { type: "search", class: "sheet-find", placeholder: t("Filter {category}", { category: label(c).toLowerCase() }) + "…", "aria-label": t("Filter {category}", { category: label(c).toLowerCase() }), value: state.text });
  const chips = el("div", { class: "seg", role: "group", "aria-label": t("Show") });
  const count = el("span", { class: "sheet-count mono" });
  bar.append(find, chips, count);
  const table = el("table", { class: "sheet" });
  const thead = el("thead"), tbody = el("tbody");
  table.append(thead, tbody);
  const scroller = el("div", { class: "sheet-scroll", tabindex: "0", role: "region", "aria-label": t("{name} table", { name: label(c) }) }, [table]);
  wrap.append(bar, scroller);
  const draw = () => {
    chips.textContent = "";
    for (const [key, name, test] of FILTERS) {
      const n = items.filter(r => test(r, facts(r))).length;
      if (key !== "all" && !n) continue;
      const b = el("button", { type: "button", class: state.filter === key ? "on" : "", "aria-pressed": String(state.filter === key) }, [t(name), el("span", { class: "n", text: String(n) })]);
      b.onclick = () => { state.filter = key; draw(); };
      chips.appendChild(b);
    }
    const test = (FILTERS.find(f => f[0] === state.filter) || FILTERS[0])[2];
    const needle = state.text.trim().toLowerCase();
    let rows = items.filter(r => test(r, facts(r)) && (!needle || (r.title + " " + Object.values(facts(r)).filter(v => typeof v === "string").join(" ")).toLowerCase().includes(needle)));
    const col = cols.find(x => x.key === state.sort);
    rows = col ? rows.sort((a, b) => { const x = col.sort(a, facts(a)), y = col.sort(b, facts(b)); return (x < y ? -1 : x > y ? 1 : byActivity(a, b)) * (state.desc ? -1 : 1); }) : rows.sort(byActivity);
    thead.textContent = "";
    const tr = el("tr");
    for (const col of cols) {
      const sorted = state.sort === col.key;
      const th = el("th", { class: "c-" + col.key + " " + (col.cls || "") + (col.num ? " num" : ""), scope: "col", "aria-sort": sorted ? (state.desc ? "descending" : "ascending") : "none" });
      const btn = el("button", { type: "button" }, [t(col.label), el("span", { class: "arrow", "aria-hidden": "true", text: sorted ? (state.desc ? "↓" : "↑") : "↕" })]);
      btn.onclick = () => { if (state.sort === col.key) state.desc = !state.desc; else { state.sort = col.key; state.desc = !!col.desc; } draw(); };
      th.appendChild(btn); tr.appendChild(th);
    }
    thead.appendChild(tr);
    tbody.textContent = "";
    for (const r of rows) {
      const row = el("tr", { "data-href": href(r) });
      for (const c2 of cols) row.appendChild(el("td", { "data-empty": String(!knownValue(c2.cell(r, facts(r))?.textContent)), "data-label": t(c2.label), class: "c-" + c2.key + " " + (c2.cls || "") + (c2.num ? " num" : "") }, [c2.cell(r, facts(r))]));
      tbody.appendChild(row);
    }
    wrap.querySelector(".empty")?.remove();
    scroller.hidden = !rows.length;
    if (!rows.length) wrap.appendChild(emptyState("No matching pages", "Clear filters →", categoryHref(c), () => {
      state.text = ""; state.filter = "all"; find.value = ""; draw(); find.focus();
    }));
    count.textContent = rows.length === items.length ? t("{n} pages", { n: items.length }) : t("{n} of {m}", { n: rows.length, m: items.length });
  };
  find.addEventListener("input", () => { state.text = find.value; draw(); });
  tbody.addEventListener("click", e => {
    if (e.target.closest("a")) return;
    const tr = e.target.closest("tr[data-href]");
    if (tr && !String(window.getSelection())) location.hash = tr.dataset.href;
  });
  draw();
  // The fade shows only while columns are hidden to the right.
  const edge = () => {
    wrap.classList.toggle("clip-right", scroller.scrollLeft + scroller.clientWidth < scroller.scrollWidth - 2);
    wrap.style.setProperty("--sheet-top", scroller.offsetTop + "px");
  };
  scroller.addEventListener("scroll", edge, { passive: true });
  if (window.ResizeObserver) { const watch = new ResizeObserver(edge); watch.observe(scroller); watch.observe(table); }
  requestAnimationFrame(edge);
  return wrap;
}

// ---------- the night: what the last pass did ----------
const HOUR = 3600e3, DAY_MS = 24 * HOUR;
const FAILED = /^(failed|abandoned|error|refused|timeout)/i;
// A task the night set aside after it could not finish (rc18, #3377): "parked" spans every turn it was retried, so
// on the curve it is the time the night was stuck awake, never part of a dream (#3379: a 108-minute loop drew as REM).
const STUCK = /^(parked|discarded)/i;
const STUCK_MINUTES = 15;
function stuckMinutes(run) {
  if (!STUCK.test(String(run.outcome || ""))) return 0;
  const minutes = Math.round((runEnd(run) - runTime(run)) / 60e3);
  return minutes >= STUCK_MINUTES ? minutes : 0;
}
function runTime(run) { return new Date(run.started_at).getTime(); }
function runEnd(run) {
  const end = run.finished_at ? new Date(run.finished_at).getTime() : runTime(run) + 1000 * (run.seconds || 0);
  return Math.max(runTime(run), isNaN(end) ? runTime(run) : end);
}
function sourceName(s) { return typeof s === "string" ? s : (s && (s.id || s.kind)) || ""; }
// Historical run claims need the same rewording rule as claim_changes.py _same().
function sameClaim(before, after) {
  const words = value => value.toLocaleLowerCase().trim().replace(/(?:\s*\([^()]*\)[\s.,;]*)+$/, "")
    .replace(/\s+\b(?:in the supplied|per the|according to)\b.*$/, "").match(/[\p{L}\p{N}_]+/gu) || [];
  const old = words(before), current = words(after);
  if (!old.length) return !current.length;
  let at = 0;
  for (const word of current) if (word === old[at]) at++;
  return at === old.length;
}
// The page's detailed logs are only the latest 21 runs; night_runs is the whole pass in brief (#3391). Detailed rows win,
// the brief ones fill in the start of the night, so the curve begins with the night and not 90 minutes before dawn.
function passRuns() {
  const detailed = REM.logs?.length ? REM.logs : (REM.brief_logs || []);
  if (!detailed.length) return [];
  const key = run => run.started_at + "|" + (run.phase || "");
  const seen = new Set(detailed.map(key));
  return [...detailed, ...(REM.night_runs || []).filter(run => !seen.has(key(run)))];
}
function lastPass() {
  const logs = passRuns().filter(run => !isNaN(runTime(run)));
  if (!logs.length) return null;
  const latest = Math.max(...logs.map(runTime));
  // One pass is every run in the evening-to-morning stretch before the latest one.
  const runs = logs.filter(run => runTime(run) >= latest - 18 * HOUR);
  const changed = new Set();
  for (const run of runs) for (const path of run.changed || []) if (byPath(path) && path !== "skills/catalog/index.md") changed.add(path);
  // Investigations write the page's stamp; count those of the pass's day as changed too.
  const day = new Date(latest - 18 * HOUR).toISOString().slice(0, 10);
  for (const r of listedRecords()) {
    const m = /\b(?:investigated|updated)\s+(\d{4}-\d{2}-\d{2})/.exec((STAMP.exec(r.text) || [""])[0]);
    if (m && m[1] >= day) changed.add(r.path);
  }
  const sources = [...new Set(runs.flatMap(run => Array.isArray(run.sources) ? run.sources.map(sourceName) : []).filter(Boolean))];
  // A failed translation is not a failed investigation; the translation notice reports it.
  const failed = runs.filter(run => FAILED.test(String(run.outcome || "")) && !/translat/.test(run.phase || ""));
  const items = runs.reduce((n, run) => n + (Number(run.items) || 0), 0);
  const claims = runs.flatMap(run => Array.isArray(run.claim_changes) ? run.claim_changes : [])
    .filter(claim => byPath(claim.record) && (claim.sources || []).length && !sameClaim(claim.before || "", claim.after || ""));
  return { latest, runs, changed: [...changed].map(byPath).sort(byActivity), sources, failed, items, claims };
}
function firstBuild(pass = lastPass()) {
  if (!pass) return false;
  const started = Math.min(...pass.runs.map(runTime));
  // The page carries only the latest runs; the notebook's first run says whether it is new.
  const earlier = [...(REM.logs || REM.brief_logs || []), ...(REM.first_run_at ? [{ started_at: REM.first_run_at }] : [])];
  return !earlier.some(run => runTime(run) < started);
}
let memoryPass = null;
function updatedMarker(r, withLabel = false) {
  if (firstBuild(memoryPass)) return null;
  if (!memoryPass?.changed.some(page => page.path === r.path)) return null;
  if (!withLabel) return el("span", { class: "fresh-label", text: t("last night"), title: t("Updated in last night's pass") });
  const dot = el("span", { class: "fresh-dot", role: "img", text: "●", title: t("updated last night"), "aria-label": t("updated last night") });
  return el("span", { class: "updated-label" }, [dot, t("updated last night")]);
}
function factText(r, label) {
  const items = [...parseFacts(r)].find(([key]) => key.toLowerCase() === label.toLowerCase())?.[1] || [];
  return items.map(item => item.value + (item.qualifier ? " (" + item.qualifier + ")" : "")).join("; ");
}
function changedValue(node, r, label) {
  const current = factText({ ...r, readLanguage: "" }, label);
  const change = memoryPass?.claims.find(claim => claim.record === r.path
    && (claim.field || "").toLowerCase() === label.toLowerCase()
    && plainLine(current) === plainLine(claim.after));
  if (change && !firstBuild(memoryPass)) {
    node.classList.add("changed-value");
    node.title = t("Changed last night: {before} → {now}", { before: change.before, now: change.after });
  }
  return node;
}
function weekChanges() {
  const asOf = new Date(REM.as_of).getTime() || Date.now(), since = asOf - 7 * DAY_MS, seen = new Map();
  for (const run of REM.logs || REM.brief_logs || []) {
    if (!(runTime(run) >= since)) continue;
    const day = new Date(runTime(run)).toISOString().slice(0, 10);
    for (const path of run.changed || []) { const r = byPath(path); if (r && (!seen.has(path) || seen.get(path).day < day)) seen.set(path, { r, day }); }
  }
  for (const r of listedRecords()) {
    const m = /\b(?:investigated|updated|written)\s+(\d{4}-\d{2}-\d{2})/.exec((STAMP.exec(r.text) || [""])[0]);
    if (m && new Date(m[1] + "T00:00:00").getTime() >= since && (!seen.has(r.path) || seen.get(r.path).day < m[1])) seen.set(r.path, { r, day: m[1] });
  }
  return [...seen.values()].filter(x => !x.r.catalog_parent && x.r.path !== "skills/catalog/index.md").sort((a, b) => b.day.localeCompare(a.day) || byActivity(a.r, b.r));
}
function listWords(words) {
  if (uiLanguage === "zh") return words.join("、");
  return words.length <= 1 ? words.join("") : words.slice(0, -1).join(", ") + " and " + words[words.length - 1];
}
function runSegments(runs, span) {
  const segments = [], gap = Math.max(span * .02, 5 * 60e3);
  for (const run of runs) {
    const start = runTime(run), end = runEnd(run);
    let segment = segments[segments.length - 1];
    // A stuck run of 15 minutes or more is a stretch of its own, whatever the gap (#3382): folded into the work just
    // after it, its caption read "00:52–05:57 stuck 93 min · …", stuck for five hours (art director, #3394).
    const stuck = stuckMinutes(run) > 0;
    if (!segment || start >= segment.end + gap || stuck || segment.stuck) {
      segment = { start, end, items: 0, changed: 0, runs: 0, failed: 0, stuck: 0, list: [] };
      segments.push(segment);
    }
    segment.list.push(run);
    segment.end = Math.max(segment.end, end);
    segment.items += Number(run.items) || 0;
    segment.changed += (run.changed || []).length;
    segment.runs++;
    segment.failed += Number(FAILED.test(String(run.outcome || "")));
    segment.stuck += stuckMinutes(run);
  }
  return segments;
}
function runMarkers(markers) {
  const last = new Map(), dots = [];
  for (const marker of markers.sort((a, b) => a.left - b.left)) {
    if (marker.left - (last.get(marker.kind) ?? -Infinity) < 1.6) continue;
    last.set(marker.kind, marker.left);
    dots.push('<span class="dot ' + marker.kind + '" style="left:' + marker.left.toFixed(2) + '%;top:' + marker.top + 'px" title="' + esc(marker.title) + '"></span>');
  }
  return dots.join("");
}
// The trace groups nearby runs; dots mark changed pages and stopped runs.
// One time axis for the curve and for the night's work drawn under it (#3311): both read this, so a stretch's
// words sit under the dip they describe.
// 昨夜 is the night: a run the owner started by day, hours after the night ended, is not part of it (#3413: phone
// Today listed 「11:42–11:48 改写了 1 页」 under 昨夜 while the desktop happened to have no row for it). Runs split at
// gaps of three hours; a later stretch that begins between 09:00 and 18:00 local is dropped when a night precedes it.
const NIGHT_GAP = 3 * HOUR;
function localHour(t) {
  return Number(new Date(t).toLocaleString("en-GB", { hour: "2-digit", hour12: false, timeZone: REM.status?.timezone || "UTC" })) % 24;
}
function nightOnly(runs) {
  const parts = [];
  for (const run of runs) {
    const last = parts.at(-1);
    if (last && runTime(run) - Math.max(...last.map(runEnd)) < NIGHT_GAP) last.push(run); else parts.push([run]);
  }
  while (parts.length > 1) {
    const hour = localHour(runTime(parts.at(-1)[0]));
    if (hour >= 9 && hour < 18) parts.pop(); else break;
  }
  return parts.flat();
}
function hypnoScale(asOf) {
  const runs = nightOnly((lastPass()?.runs || []).filter(run => runTime(run) <= asOf).sort((a, b) => runTime(a) - runTime(b)));
  const W = 1000, finished = runs.length ? Math.min(asOf, Math.max(...runs.map(runEnd))) : asOf;
  const start = Math.floor((runs.length ? runTime(runs[0]) : asOf - 4 * HOUR) / HOUR) * HOUR - HOUR / 2;
  // The axis ends just after the last run, never an hour past it: rounding up to the hour plus half an hour drew an
  // empty hour after "now" (#3391). A run still going ends the axis at now.
  const end = Math.max(start + HOUR, Math.min(asOf, finished) + 10 * 60e3);
  return { runs, W, finished, start, end, segments: runSegments(runs, end - start), x: t => 4 + (W - 8) * (t - start) / (end - start) };
}
function hypnoTime(t) {
  return new Date(t).toLocaleTimeString(uiLanguage === "zh" ? "zh-CN" : "en-GB", { hour: "2-digit", minute: "2-digit", timeZone: REM.status?.timezone || "UTC" });
}
// A sleep chart, not a timeline (art director on #3371: «快速眼动期 and 深睡期 must be visible»). Each run is a step
// to its stage: a run that changed pages is REM (dreaming: the night rewrote what it knew, drawn heavier), a run that
// only read is light sleep, a run that stopped early woke him; between runs of one stretch the night dozes in light
// sleep, and between stretches it sinks to deep sleep. The levels are named at the left when the chart is Today's.
// size "mid" is Today's desktop chart, "short" a phone's: two-thirds and half the height, so the first card's Send
// stays in reach (D-10; owner, 2026-11-22: «手机上压缩时间轴»).
const SLEEP_STAGES = ["Awake", "REM sleep", "Light sleep", "Deep sleep"];
const STAGE_RANK = [1, 3, 2];  // which stage a merged cluster of runs shows: REM over light sleep over a stopped run
function runStage(run) {
  if (FAILED.test(String(run.outcome || "")) || STUCK.test(String(run.outcome || ""))) return 0;
  return (run.changed || []).length ? 1 : 2;
}
function hypnogram(asOf, size = "") {
  const short = size === "short", mid = size === "mid";
  const { runs, W, finished, start, end, segments, x } = hypnoScale(asOf);
  const H = short ? 32 : mid ? 56 : 84, LEVEL = short ? [4, 12, 20, 28] : mid ? [6, 20, 34, 50] : [10, 28, 48, 72], DEEP = LEVEL[3], markers = [];
  const pct = v => (100 * v / W).toFixed(2) + "%";
  const time = hypnoTime;
  const svg = ['<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none" aria-hidden="true">'];
  const over = [], step = Math.max(HOUR, Math.ceil((end - start) / (6 * HOUR)) * HOUR);
  for (let t = Math.ceil(start / HOUR) * HOUR; t < end; t += step) {
    svg.push('<line class="grid" x1="' + x(t).toFixed(1) + '" y1="2" x2="' + x(t).toFixed(1) + '" y2="' + (H - 2) + '"/>');
    over.push('<span class="day" style="left:' + pct(x(t)) + '">' + esc(time(t)) + "</span>");
  }
  // Each stage is a faint band line, so even a quiet night reads as levels of sleep and not a flat timeline.
  if (size) LEVEL.forEach(y => svg.push('<line class="lv" x1="4" y1="' + y + '" x2="' + (W - 4) + '" y2="' + y + '"/>'));
  let path = "M4," + DEEP, at = 4, level = DEEP;
  const rem = [];
  const num = v => String(+v.toFixed(1));  // 996, not 996.0
  const go = (toX, y) => {
    toX = Math.max(at, Math.min(W - 4, toX));
    if (y !== level) {
      const span = Math.max(0, toX - at), ramp = Math.min(18, Math.max(4, span * 0.42));
      const endX = Math.min(toX, at + ramp);
      path += " C" + num(at + (endX - at) * 0.48) + "," + level + " " + num(at + (endX - at) * 0.52) + "," + y + " " + num(endX) + "," + y;
      if (toX > endX) path += " L" + num(toX) + "," + y;
    } else if (toX > at) {
      path += " L" + num(toX) + "," + y;
    }
    at = toX; level = y;
  };
  for (const segment of segments) {
    go(x(segment.start), DEEP);
    // Runs closer than a few units apart are one step at the highest stage among them (REM over light over awake's
    // absence), so a dense stretch reads as one block, not a comb.
    const steps = [];
    for (const run of [...segment.list].sort((a, b) => runTime(a) - runTime(b))) {
      const x0 = x(runTime(run)), x1 = Math.max(x0 + 6, x(Math.min(asOf, runEnd(run)))), stage = runStage(run), last = steps[steps.length - 1];
      const stuck = stuckMinutes(run) > 0;
      // A stuck loop never merges with a run beside it: the run after it may change a page, and the loop must still
      // read as awake (#3379). A brief stopped run inside a dense stretch still folds into the block (no comb).
      if (last && x0 - last.x1 < 8 && !stuck && !last.stuck) { last.x1 = Math.max(last.x1, x1); if (STAGE_RANK[stage] > STAGE_RANK[last.stage]) last.stage = stage; }
      else steps.push({ x0, x1, stage, stuck });
    }
    steps.forEach(({ x0, x1, stage }, i) => {
      if (i && x0 > at) go(x0, LEVEL[2]);  // dozing between two runs of the same stretch
      go(x1, LEVEL[stage]);
      if (stage === 1) rem.push("M" + Math.max(4, x0).toFixed(1) + "," + LEVEL[1] + " L" + Math.min(W - 4, x1).toFixed(1) + "," + LEVEL[1]);
    });
    const x0 = x(segment.start), x1 = Math.min(W - 4, Math.max(x0 + 6, x(Math.min(asOf, segment.end))));
    const range = time(segment.start) + "–" + time(segment.end);
    if (segment.failed) markers.push({ kind: "woke", left: 100 * x0 / W, top: LEVEL[0], title: range + " · " + t("{n} runs stopped early", { n: segment.failed }) });
    if (segment.stuck) markers.push({ kind: "woke", left: 100 * x0 / W, top: LEVEL[0], title: range + " · " + t("stuck {n} min · skipped automatically", { n: segment.stuck }) });
    // The dot sits over the runs that changed pages, not the stretch's middle: after a loop the middle is the loop (#3379).
    const wrote = segment.list.filter(run => (run.changed || []).length);
    const wroteAt = wrote.length ? (x(runTime(wrote[0])) + x(Math.min(asOf, runEnd(wrote[wrote.length - 1])))) / 2 : (x0 + x1) / 2;
    if (segment.changed) markers.push({ kind: "changed", left: 100 * Math.min(W - 4, wroteAt) / W, top: LEVEL[1], title: range + " · " + t("{n} runs · {m} pages changed", { n: segment.runs, m: segment.changed }) });
  }
  go(W - 4, DEEP);
  svg.push('<path class="area" d="' + path + " L" + num(W - 4) + "," + DEEP + " L4," + DEEP + ' Z"/>', '<path class="trace" pathLength="1" d="' + path + '"/>');
  if (rem.length) svg.push('<path class="rem" d="' + rem.join(" ") + '"/>');
  svg.push("</svg>");
  // The stage names at the left. A phone's levels stand 8px apart, too close for four words, so it names two: the
  // highest level tonight's curve reached and 深睡 (art director on #3382: an unnamed top level read as REM, so a
  // stuck night says 清醒 there; a calm night says 快速眼动, as before).
  const top = Math.min(...(path.match(/,(\d+(?:\.\d+)?)/g) || [",0"]).map(v => Number(v.slice(1))).filter(y => LEVEL.includes(y)), DEEP);
  if (size) LEVEL.forEach((y, i) => { if (!short || y === top || y === DEEP) over.push('<span class="lvl" style="top:' + y + 'px">' + esc(t(SLEEP_STAGES[i])) + "</span>"); });
  if (runs.length) over.push('<span class="dot dawn" style="left:' + pct(x(finished)) + ';top:' + DEEP + 'px" title="' + esc(t("Last run ended {time}", { time: fmtTime(new Date(finished).toISOString()) })) + '"></span>');
  return '<div class="hypno' + (size ? " " + size : "") + '" role="img" aria-label="' + t("{n} runs in {m} stretches in the last pass; white dots mark pages changed; grey marks stopped runs; amber marks the last run ending", { n: runs.length, m: segments.length }) + '">' + svg.join("") + over.join("") + runMarkers(markers) + "</div>";
}
// The night under its curve (#3311, owner 2026-11-22: «那个线的下面，就是晚上做事情的时候»): each stretch's work sits
// under the dip it made, on the curve's own time axis (hypnoScale), and opens to the pages it changed. Up to three
// rows; a phone keeps the three biggest stretches in time order. 全部 → opens the whole night in Activity.
// What one stretch did, in numbers. Each Today line about the night adds these up (nightTotals), so the 昨夜
// heading and the captions under the curve are the same count, never three (#3396).
function stretchCounts(segment) {
  let read = 0, rewrote = 0, translated = 0;
  for (const run of segment.list) {
    const changed = (run.changed || []).filter(path => byPath(path)).length;
    if (/translat/.test(run.phase || "")) translated += changed; else rewrote += changed;
    if ((run.phase || "sync") === "sync" || !changed) read += Number(run.items) || 0;
  }
  return { read, rewrote, translated };
}
function stretchWords(segment) {
  const { read, rewrote, translated } = stretchCounts(segment);
  return [segment.stuck ? t("stuck {n} min · skipped automatically", { n: segment.stuck }) : null,
    read ? t(read === 1 ? "read {n} item" : "read {n} items", { n: num(read) }) : null,
    rewrote ? t(rewrote === 1 ? "rewrote {n} page" : "rewrote {n} pages", { n: rewrote }) : null,
    translated ? t(translated === 1 ? "translated {n} page" : "translated {n} pages", { n: translated }) : null,
    segment.failed ? t("{n} runs stopped early", { n: segment.failed }) : null].filter(Boolean);
}
function stretchItem(stretch) {
  const { segment, words, pages } = stretch;
  const range = hypnoTime(segment.start) + (segment.end - segment.start >= 5 * 60e3 ? "–" + hypnoTime(segment.end) : "");
  // Each clause keeps together and carries its own 「·」, so a narrow line breaks only between clauses, never inside
  // one (art director on #3408: 「提前停止」 left a lone 「止」), and never starts with a dot (#3398).
  const clauses = words.flatMap((word, i) => [el("span", { class: "clause", text: word + (i < words.length - 1 ? " ·" : "") }), i < words.length - 1 ? " " : ""]);
  const item = el("details", { class: "stretch" }, [el("summary", {}, [el("span", { class: "stretch-time", text: range }),
    el("span", { class: "stretch-what" }, clauses.filter(Boolean))])]);
  if (pages.length) item.appendChild(el("ul", { class: "stretch-pages", "aria-label": t("Pages this stretch changed") }, [
    ...pages.slice(0, 10).map(r => el("li", {}, [el("a", { href: href(r), text: r.title })])),
    pages.length > 10 ? el("li", { class: "stretch-more", text: t("+{n} more", { n: pages.length - 10 }) }) : null].filter(Boolean)));
  // One open at a time, and Escape folds it back: a stretch's pages float over the rows under it.
  item.addEventListener("toggle", () => {
    if (item.open) for (const other of item.parentElement?.querySelectorAll(".stretch[open]") || []) if (other !== item) other.open = false;
  });
  item.addEventListener("keydown", event => { if (event.key === "Escape" && item.open) { item.open = false; item.querySelector("summary").focus(); } });
  return item;
}
function nightStretches(asOf) {
  const scale = hypnoScale(asOf);
  if (!scale.runs.length) return null;
  const narrow = typeof window !== "undefined" && window.innerWidth <= 640;
  const stretches = scale.segments.map(segment => ({ segment, words: stretchWords(segment), weight: segment.items + 4 * segment.changed,
    pages: [...new Set(segment.list.flatMap(run => run.changed || []))].map(byPath).filter(r => r && r.path !== "skills/catalog/index.md") }))
    .filter(stretch => stretch.words.length);
  if (!stretches.length) return null;
  const lane = el("div", { class: "stretches stacked" });
  const chosen = narrow ? [...stretches].sort((a, b) => b.weight - a.weight).slice(0, 3).sort((a, b) => a.segment.start - b.segment.start) : stretches;
  for (const stretch of chosen) {
    const item = stretchItem(stretch);
    item.dataset.from = (100 * scale.x(stretch.segment.start) / scale.W).toFixed(2);
    item.dataset.to = (100 * scale.x(Math.min(asOf, stretch.segment.end)) / scale.W).toFixed(2);
    lane.appendChild(item);
  }
  if (chosen.length < stretches.length) lane.appendChild(el("a", { class: "stretch-all", href: "#view=activity", text: t("All →") }));
  return lane;
}
function nightTimeline(asOf) {
  const scale = hypnoScale(asOf);
  if (!scale.runs.length) return null;
  const wrap = el("div", { class: "night-line" });
  const narrow = typeof window !== "undefined" && window.innerWidth <= 640;
  wrap.insertAdjacentHTML("beforeend", hypnogram(asOf, narrow ? "short" : "mid"));
  return wrap;
}
function nightBand(showActivityLink = true) {
  const pass = lastPass(), band = el("section", { class: "night", "aria-label": t("The last pass") });
  if (!pass) {
    band.appendChild(el("h2", { class: "night-title", text: t("No pass yet") }));
    band.appendChild(el("p", {}, [t("Each night co rem reads new material and works through queued pages.")]));
    return band;
  }
  const asOf = new Date(REM.as_of).getTime() || Date.now();
  const ago = Math.max(0, Math.round((asOf - pass.latest) / HOUR));
  band.appendChild(el("div", { class: "night-head" }, [
    el("h2", { class: "night-title", text: t(firstBuild(pass) ? "First build" : ago < 24 ? "Last night" : "The last pass") }),
    el("span", { class: "when", text: fmtTime(new Date(pass.latest).toISOString()) }),
    showActivityLink ? el("a", { href: "#view=activity", text: t("See all activity") }) : null]));
  band.insertAdjacentHTML("beforeend", hypnogram(asOf));
  const stages = el("div", { class: "stages stats" });
  const stage = (heading, detail) => stages.appendChild(el("div", { class: "stat" }, [el("b", { class: "v", text: heading }), el("span", { class: "k", text: detail })]));
  stage(t(pass.items === 1 ? "Read {n} item" : "Read {n} items", { n: num(pass.items) }), pass.sources.length ? listWords(pass.sources) : t("items from your sources"));
  stage(t(firstBuild(pass) ? "Wrote {n} pages" : pass.changed.length === 1 ? "Rewrote {n} page" : "Rewrote {n} pages", { n: pass.changed.length }), t(firstBuild(pass) ? "Pages in your new notebook" : "Page rewrites; see memory changes for findings"));
  stage(t(pass.runs.length === 1 ? "{n} run" : "{n} runs", { n: pass.runs.length }), t("Dips show how much each run read"));
  stage(pass.failed.length ? t("{n} stopped early", { n: pass.failed.length }) : t("Nothing stopped early"), t("White: changed · grey: stopped · amber: run ended"));
  band.appendChild(stages);
  if (pass.changed.length) {
    const changes = el("div", { class: "changes" }, [el("span", { class: "k", text: t(firstBuild(pass) ? "Pages written" : "Pages rewritten") })]);
    changes.appendChild(el("span", { class: "page-names" }, pass.changed.slice(0, 14).flatMap((r, i) =>
      [i ? (uiLanguage === "zh" ? "、" : ", ") : "", el("a", { href: href(r), title: label(r.category), text: r.title })])));
    if (pass.changed.length > 14) changes.appendChild(el("span", { class: "k", text: t("+{n} more", { n: pass.changed.length - 14 }) }));
    band.appendChild(changes);
  }
  return band;
}

