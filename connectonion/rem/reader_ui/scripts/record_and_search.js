// ---------- a page ----------
// Which sections lead: what is open first on a relationship, the state of play on a project.
const LEADING = {
  people: ["insight", "open threads"], orgs: ["open threads"],
  projects: ["insight", "what it is", "where it stands", "overview", "open threads"],
  skills: ["insight", "what it does", "when to use", "how to use"]
};
// Shown as the fact card, not as a section of prose (#2068; legacy pages have Contact).
const CARD_SECTIONS = new Set(["facts", "contact"]);
function ordered(r, sections) {
  const lead = LEADING[r.category] || [];
  const first = lead.map(t => sections.find(s => s.title.toLowerCase() === t)).filter(Boolean);
  return [...first, ...sections.filter(s => !first.includes(s))];
}
function sectionBody(r, s) {
  const name = s.title.toLowerCase();
  // Session quotes are the owner's words, including Markdown and citation-looking text.
  if (r.category === "sessions" && ["what you typed", "final reply"].includes(name)) {
    const out = el("div", { class: "block" });
    let quoted = [], level = "";
    const flush = () => {
      if (quoted.length) out.appendChild(sessionQuote(quoted.join("\n"), level));
      quoted = [];
    };
    for (const line of s.text.split("\n")) {
      if (line.startsWith("> ")) quoted.push(line.slice(2));
      else if (line.startsWith("### ")) { flush(); const heading = markedText(line.slice(4)); level = heading.level; out.appendChild(el("h3", { text: heading.text })); }
    }
    flush();
    return out;
  }
  // Insight (#2068): each line starts Now / Changed / At stake / Pattern; the label becomes a badge.
  if (name === "insight") {
    const items = listItems(s.text).map(t => /^(Now|Changed|At stake|Pattern|现在|变化|利害|模式)[:：]\s*(.*)$/i.exec(t.replace(/^\*\*([^*]+)\*\*/, "$1")));
    if (items.length && items.every(Boolean)) {
      return el("div", { class: "block-insight" }, [el("ul", { class: "insight" }, items.map(m => el("li", { class: "ins-" + m[1].toLowerCase().replace(/\s+/g, "-") }, [
        el("span", { class: "badge", text: t(m[1]) }), privateFallback(el("span", { class: "txt", html: inline(m[2], r.path) }))])))]);
    }
  }
  if (name === "open threads") {
    // A person's and a project's record keep their threads as written: what to do about them is Today's (D-30, #3096).
    if (r.category === "people" || r.category === "projects") return el("div", { class: "person-threads", html: markdown(s.text, r.path) });
    const state = threads(r);
    const box = el("div", { class: "block-threads" });
    if (state.calm) box.appendChild(el("div", { class: "calm" }, [el("span", { class: "dir", text: t("Clear") }), el("span", { html: inline(state.calm, r.path) })]));
    if (state.items.length) box.appendChild(el("ul", { class: "threads" }, state.items.map(item => threadRow(r, item, false))));
    return box.childNodes.length ? box : el("div", { html: markdown(s.text, r.path) });
  }
  // History as a dated spine. Conversations shown as chat history (#2066) will hook in here.
  if (name === "history") {
    const items = historyItems(s.text);
    if (items.some(i => i.day)) {
      const rows = items.map(i => {
        const content = historyRowContent(i.text, r.path);
        return content ? el("li", { class: (i.day ? "" : "undated ") + (content.classList.contains("privacy-only") ? "private-entry" : "") }, [
          el("span", { class: "d", text: i.day ? dayLabel(i) : "·" }), el("div", { class: "e" }, [content])]) : null;
      }).filter(Boolean);
      return el("div", { class: "block-history" }, [el("ol", { class: "timeline" }, rows), privateHistoryNotice(rows)]);
    }
  }
  if (name === "sources") {
    const list = sourceList(r);
    if (list.length) {
      return el("div", { class: "block-sources" }, [el("ol", {}, list.map(src => {
        const id = sourceId(src.text, src.plain);
        const rest = id ? src.text.replace(id, "").replace(/^\s*[—–-]\s*/, "") : src.text;
        const chip = el("span", { html: citeChip(src.n, r.path) }).firstChild;
        chip.classList.add("n", "source-open");
        return el("li", { id: "src-" + src.n.toLowerCase() }, [chip,
          el("span", {}, [id ? el("span", { class: "id", text: sourceLabel(id), title: id }) : null, id ? " " : "", rest])]);
      }))]);
    }
  }
  const html = markdown(s.text, r.path);
  return el("div", { class: /^(where it stands|current status)$/.test(name) ? "block-standing" : "block", html });
}
// The labels of `## Facts`, in the page's order (#2068 docs/cli/rem.md).
const FACT_LABELS = {
  people: ["Email", "Phone", "Company", "Role", "Location", "Time zone", "Links", "How we know them", "First contact", "Last contact",
    "Signing entity", "Handles", "Language", "Also known as"],
  devices: ["Kind", "Host", "Location", "Role", "Status", "Last activity"],
  projects: ["Repository", "Stack", "Status", "People", "Organisation", "Started", "Last activity"],
  orgs: ["What they do", "Website", "Location", "Legal entity", "Your contacts", "First contact", "Last contact"]
};
const COPYABLE = new Set(["Email", "Phone", "Links", "Website", "Repository", "Host"]);
// What a page written before `## Facts` still says, for the labels it has no line for.
function legacyFact(r, label) {
  const f = facts(r), k = known(r);
  const v = {
    "How we know them": f.how, "First contact": f.first, "Last contact": r.category !== "projects" ? f.last : "", "Email": f.email,
    "Last activity": r.category === "projects" ? k.last : "",
    "What they do": r.category === "orgs" ? f.what : "", "Website": r.category === "orgs" ? f.domain : "",
    "Your contacts": f.people ? t(f.people === 1 ? "{n} person" : "{n} people", { n: f.people }) : "", "Links": f.links
  }[label];
  return v ? [{ value: v, qualifier: "", citations: [], derived: true }] : [];
}
// A value that states one date twice ("2026-10-29 (10月29日)", "2015-11-18 2015年11月18日") keeps the ISO date only;
// the reader prints it once in its own words (hunt on rc31).
function oneDate(item) {
  const m = /^(\d{4})-(\d{2})-(\d{2})\s*[（(]?\s*(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*[)）]?$/.exec(String(item.value).trim());
  if (!m || Number(m[5]) !== Number(m[2]) || Number(m[6]) !== Number(m[3]) || (m[4] && m[4] !== m[1])) {
    const q = /^(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日$/.exec(String(item.qualifier || "").replace(/[（()）]/g, "").trim());
    const d = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(item.value).trim());
    return q && d && Number(q[2]) === Number(d[2]) && Number(q[3]) === Number(d[3]) ? { ...item, qualifier: "" } : item;
  }
  return { ...item, value: m[1] + "-" + m[2] + "-" + m[3] };
}
// English a page skill wrote, in a Chinese reader (#3410): a role "team member", how you met, an open question. The
// reader never translates it itself; it shows the words as the original, behind the same quiet 原文 mark a page
// header uses, so 「如何认识：Met through…」 reads as a quotation and not as a Chinese label's broken second half.
// Names, codes, addresses and single words are not prose: "Example University", "Swift", "wren@example.edu".
function englishProse(text) {
  const plain = String(text || "").replace(/\[[^\]]*\]\([^)]*\)|\[\[[^\]]*\]\]|\[W?\d{1,3}\]|[\[［](?:personal|sensitive)[\]］]/gi, " ").trim();
  if (uiLanguage !== "zh" || !plain || /[\p{Script=Han}]/u.test(plain) || /@|:\/\/|^[\w.-]+\.[a-z]{2,}$/i.test(plain)) return false;
  const words = plain.match(/[A-Za-z][A-Za-z'’-]*/g) || [];
  return words.length >= 2 && words.some(w => /^[a-z]{2,}$/.test(w));
}
function originalQuote(node) {
  return el("span", { class: "orig-quote", lang: "en" }, [originalMark(), " ", node]);
}
function factValue(item, from, label = "") {
  // A kind word is the reader's own vocabulary ("course" → 课程); any other English value is the page's words.
  if (["Kind", "Role", "Role in unit", "You are"].includes(label)) item = { ...item, value: labelWord(item.value) };
  item = oneDate(item);
  const day = /^\d{4}-\d{2}-\d{2}$/.test(item.value);
  const email = /^[\w.+-]+@[\w-]+\.[\w.-]+$/.test(item.value);
  const url = /^https?:\/\/\S+$/.test(item.value);
  const html = day ? esc(fmtDate(item.value)) : email ? '<a href="mailto:' + esc(item.value) + '">' + esc(item.value) + "</a>"
    : url ? '<a href="' + esc(item.value) + '" target="_blank" rel="noopener noreferrer">' + esc(item.value.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")) + "</a>"
    : inline(item.value, from);
  const words = el("span", { html });
  const value = el("span", { class: "val" + (day || email || url ? " mono" : "") + (item.derived ? " derived" : ""), title: item.derived ? t("read from the page's prose, not its Facts") : "" }, [
    !day && !email && !url && englishProse(item.value) ? originalQuote(words) : words,
    item.qualifier ? el("span", { class: "qual", text: item.qualifier }) : null]);
  if (!item.citations.length) return value;
  const cites = el("span", { html: citeChips(item.citations, from) });
  softBreaks(value);
  const walker = document.createTreeWalker(value.firstChild, NodeFilter.SHOW_TEXT);
  let last;
  while (walker.nextNode()) if (walker.currentNode.data.trim() && !walker.currentNode.parentElement.closest(".privacy-tag, .cite")) last = walker.currentNode;
  if (!last) { value.appendChild(cites); return value; }
  // The marks stay with the end of the last word; a long word keeps only its last 12 characters with them, so the
  // rest can wrap (#2942: a whole long word held on one line ran past the screen).
  // A Chinese tail is the last two characters, so no character is left alone on a line (#3405: 「团」 over 「队」).
  const tail = /(?:[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}][^\p{L}\p{N}\s]*){1,2}\s*$/u.exec(last.data) || /\S{1,12}\s*$/.exec(last.data);
  const range = document.createRange();
  // A short value goes whole (about four Chinese characters wide), and a link moves as one: cutting 「课程 1234」
  // made two links (#3405, rc20 hunt).
  const link = last.parentElement.closest("a");
  const wide = [...last.data.trim()].reduce((w, c) => w + (/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]/u.test(c) ? 1 : 0.55), 0);
  if (link && value.contains && value.contains(link) && link.textContent.trim().length <= 24) range.setStartBefore(link);
  else range.setStart(last, wide <= 4 ? 0 : tail.index);
  range.setEnd(value, value.childNodes.length);
  value.appendChild(el("span", { class: "fact-tail" }, [range.extractContents(), cites]));
  return value;
}
// A long URL wraps before '/', never mid-domain ("…edu / .au", #3231); an email address wraps only after '@' (#3104).
function softBreaks(node) {
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT), texts = [];
  while (walker.nextNode()) texts.push(walker.currentNode);
  for (const text of texts.filter(t => /[^\s]{16,}/.test(t.data))) {
    const mail = !!text.parentElement?.closest('a[href^="mailto:"]');
    const webUrl = !!text.parentElement?.closest('a[href^="http://"], a[href^="https://"]');
    const parts = text.data.split(/(\s+)/).flatMap(token => token.length < 16 ? [token]
      : token.split(mail || /^[^\s/]+@[^\s/]+$/.test(token) ? /(?<=@)/ : webUrl || token.includes("/") ? /(?=\/)/ : /(?<=@)|(?=\.\w)/)
        .flatMap((part, i) => i ? [document.createElement("wbr"), part] : [part]));
    text.replaceWith(...parts);
  }
  return node;
}
// The facts a reader came for: labels in small caps, values cited, a missing one visibly empty.
function factList(r) {
  const labels = FACT_LABELS[r.category];
  if (!labels) return null;
  const parsed = parseFacts(r);
  const order = [...labels, ...[...parsed.keys()].filter(l => !labels.includes(l))];
  const dl = el("dl", { class: "factlist" });
  let filled = 0, idOnly = 0;
  const notFound = [];
  for (const label of order) {
    let items = (parsed.has(label) ? parsed.get(label) : legacyFact(r, label)).filter(item => knownValue(item.value));
    if (r.category === "people" && (label === "Handles" || label === "Also known as") && items.length) {
      items = items.map(item => withoutWechatIds(r, item, label)).filter(Boolean);
      // Known, but only as the WeChat id ⋯ copies: neither a fact to count nor one "not found".
      if (!items.length) { idOnly++; continue; }
    }
    // A WeChat friend's last chat is when you were last in touch: the header says it, so the card does not call it
    // "not found" (#3372).
    const chatDay = label === "Last contact" && !items.length && r.category === "people" && calendarDay(chatActivity(r)?.last || "");
    if (chatDay) items = [{ value: chatDay, qualifier: t("WeChat"), citations: [], derived: true }];
    if (items.length) filled++;
    const missing = label === "Last contact" && mappedContact(r) && known(r).last
      ? "— map date shown above" : "— not found";
    // Empty fields are one quiet line under the card, not a row each (#3104).
    if (!items.length && missing === "— not found") { notFound.push(t(label)); continue; }
    const dd = el("dd", { class: items.length ? "" : "none" }, items.length ? items.map(i => changedValue(factValue(i, r.path, label), r, label)) : [el("span", { text: t(missing) })]);
    if (items.length && COPYABLE.has(label)) {
      const btn = el("button", { type: "button", class: "copy", "aria-label": t("Copy {name}", { name: uiLanguage === "zh" ? t(label) : label.toLowerCase() }), text: t("Copy") });
      btn.onclick = () => copyToClipboard(items.map(i => i.value).join("; "), btn, t("Copied"));
      dd.appendChild(btn);
    }
    dl.append(el("dt", { text: t(label) }), softBreaks(dd));
  }
  if (r.category === "people" && r.mail) {
    dl.append(el("dt", { text: t("Mail") }), el("dd", {}, [el("span", { class: "val mono", text: t("{n} · {received} in, {sent} out", { n: r.mail.mails, received: r.mail.received, sent: r.mail.sent }) })]));
  }
  if (!filled && !(r.category === "people" && r.mail)) return null;
  // "Not found" means REM looked. On a page not investigated yet nobody has (art director on #3381): the rest is
  // what investigation fills in, its list folded; known(r).status is the page's own investigated-or-not signal.
  const pending = known(r).status === "Mapped";
  const none = !notFound.length ? null : pending
    ? el("details", { class: "fact-missing fact-pending" }, [el("summary", { text: t("{n} more once investigated", { n: notFound.length }) }),
      el("p", { text: notFound.join(" · ") })])
    : el("p", { class: "fact-missing", title: notFound.join(" · "), text: t("{n} not found", { n: notFound.length }) + ": " + notFound.join(" · ") });
  return panel("Facts", [el("p", { class: "fill mono", text: t("{n} of {m} known", { n: filled, m: order.length - idOnly }) }), dl, none]);
}
function daysSince(day) {
  const today = calendarDay(REM.as_of || new Date().toISOString());
  const ms = new Date(today + "T00:00:00Z").getTime() - new Date(day + "T00:00:00Z").getTime();
  return isNaN(ms) ? null : Math.max(0, Math.floor(ms / DAY_MS));
}
function age(day) {
  const n = daysSince(day);
  return n == null ? "" : n === 0 ? t("today") : n === 1 ? t("1 day") : t("{n} days", { n });
}
// Tag only explicit blocking language; age alone does not imply urgency.
function blocksWork(thread) { return /\b(?:blocks|blocked|blocking)\b|\bbefore\b[^.!?\n]*\bcan\b/i.test(thread.text); }
function blockerTag(thread) {
  return blocksWork(thread) ? el("small", { class: "blocker-tag", text: t("blocker") }) : null;
}
// Show an explicit deadline first, without inferring whether it was met. Something happening today or tomorrow says
// when first and how old second (#3406: a card about a demo at 14:00 today read 「2 天」).
function threadAge(thread, r) {
  const soon = upcomingWhen(thread, r);
  // Beside a time the age needs its word, or 「今天 11:41 · 15 天」 reads as two dates (art director on #3408).
  return soon ? [soon, thread.since ? t("waiting {age}", { age: age(thread.since) }) : ""].filter(Boolean).join(" · ")
    : [age(thread.since), thread.due ? dueLabel(thread) : ""].filter(Boolean).join(" · ");
}
// The days a thread's words name: 2026-11-23, 11月23日, Nov 23 or 23 November, in this year (the year of `today`).
const MONTH_WORDS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
function statedDays(text, today) {
  const year = today.slice(0, 4), iso = (m, d) => year + "-" + String(m).padStart(2, "0") + "-" + String(d).padStart(2, "0");
  const month = word => MONTH_WORDS.indexOf(word.slice(0, 3).toLowerCase()) + 1;
  return [...(text.match(/\b\d{4}-\d{2}-\d{2}\b/g) || []),
    ...[...text.matchAll(/(\d{1,2})月(\d{1,2})[日号]/g)].map(m => iso(m[1], m[2])),
    ...[...text.matchAll(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})\b/gi)].map(m => iso(month(m[1]), m[2])),
    ...[...text.matchAll(/\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b/gi)].map(m => iso(month(m[2]), m[1]))];
}
// When a thread's thing happens, if that is today or tomorrow: the person's next calendar event on those days, else a
// due date or an ISO date in the thread's words, with its time when the words give one. Never guessed from 今天/today
// in old words: those meant the day they were written.
function upcomingWhen(thread, r) { return upcomingMoment(thread, r).label; }
// The clock a card is read against: the render's moment, moved on by the real clock while the page stays open, so
// 「今天 14:00」 turns into 「今天 14:00 · 已过」 after two (13:25 hunt: a card still said 14:00 at 14:40).
// Within the hour before it, a card's time gets the quiet "today" mark; once it has gone by, it greys (13:25 hunt).
function momentClass(thread, r) { const s = upcomingMoment(thread, r).state; return s === "soon" || s === "started" ? " soon" : ""; }
// The card's age: overdue days, or its time and age; only a passed time carries the muted 「已过」 as its own node.
function qageNode(late, thread, r) {
  const attrs = { class: "qage" + (late ? " late" : momentClass(thread, r)), ...momentData(late ? null : thread, r) };
  if (late) return el("span", { ...attrs, text: t(late === 1 ? "1 day overdue" : "{n} days overdue", { n: late }) });
  const nodes = ageNodes(threadAge(thread, r));
  return nodes.length === 1 ? el("span", { ...attrs, text: nodes[0] }) : el("span", attrs, nodes);
}
// A card whose time has gone by keeps its weight and its place: the debt is still owed. Only 「已过」 is muted.
function ageNodes(text) {
  const mark = " · " + t("passed"), i = text.indexOf(mark);
  return i < 0 ? [text] : [text.slice(0, i) + " · ", el("span", { class: "age-passed", text: t("passed") }), text.slice(i + mark.length)];
}
function momentBucket(at, now) { return at <= now ? "past" : at - now <= 3600e3 ? "soon" : "later"; }
function momentData(thread, r) {
  const at = thread ? upcomingMoment(thread, r).at : null;
  return at == null ? {} : { "data-at": String(at), "data-bucket": momentBucket(at, readNow()) };
}
// The page is read for hours: once a minute, a card counting down, or one whose time crossed into the hour before it or
// past it, is drawn again. Only in a real browser document: node harnesses that run this script must still exit.
if (typeof window !== "undefined" && window.document) setInterval(() => {
  const now = readNow();
  const cards = [...document.querySelectorAll("#main .qage[data-at]")];
  if (cards.some(node => node.dataset.bucket === "soon" || momentBucket(Number(node.dataset.at), now) !== node.dataset.bucket)) redraw();
}, 60e3);
function readNow() { return Math.max(Date.parse(REM.as_of || "") || 0, clockNow()); }
// When a thread's thing happens, if that is today or tomorrow: the person's next calendar event on those days, else a
// due date or a date in the thread's words, with its time when the words give one. Never guessed from 今天/today in old
// words: those meant the day they were written. {label, at, state}: state is "later", "soon" (within the hour before),
// "started" (an event under way) or "passed" (a time in the words that has gone by). A day without a time never turns.
function upcomingMoment(thread, r) {
  const today = agToday(), tomorrow = agDay(today, 1), soon = day => day === today || day === tomorrow;
  const word = day => agT(day === today ? "Today" : "Tomorrow");
  const now = readNow(), HOUR = 3600e3;
  const turn = at => at == null ? "later" : at <= now ? "passed" : at - now <= HOUR ? "soon" : "later";
  // In the hour before it the card counts down in words (「40 分钟后」), redrawn each minute; after it, 「· 已过」 (art director on #3423).
  const marked = (label, s, at) => s === "soon" ? t("in {n} min", { n: Math.max(1, Math.ceil((at - now) / 60e3)) })
    : label + (s === "passed" ? " · " + t("passed") : s === "started" ? " · " + t("started") : "");
  // An event still running keeps its card's time ("started"); one that ended falls back to the thread's own words.
  const event = r && !REM.shared ? timedEvents(now).find(e => soon(e.first) && e.people.some(p => p.path === r.path)) : null;
  if (event) {
    const at = Date.parse(event.start), s = at <= now ? "started" : turn(at);
    return { label: marked(word(event.first) + " " + agTime(event.start), s, at), at, state: s };
  }
  const text = thread.text || "", day = soon(thread.due) ? thread.due : statedDays(text, today).find(soon);
  if (!day) return { label: "", at: null, state: "later" };
  const clock = text.match(/\b([01]?\d|2[0-3])[:：]([0-5]\d)\b/), meridiem = text.match(/\b(1[0-2]|[1-9])\s?([ap])\.?m\b/i);
  const time = clock ? clock[1].padStart(2, "0") + ":" + clock[2]
    : meridiem ? String((Number(meridiem[1]) % 12) + (meridiem[2].toLowerCase() === "p" ? 12 : 0)).padStart(2, "0") + ":00" : "";
  const at = time ? zonedMoment(day, time) : null, s = turn(at);
  return { label: marked(word(day) + (time ? " " + time : ""), s, at), at, state: s };
}
// A day and HH:MM on the notebook's clock as epoch ms: read the UTC guess back through agTime and remove the offset.
function zonedMoment(day, time) {
  const guess = Date.parse(day + "T" + time + ":00Z");
  if (isNaN(guess)) return null;
  const iso = new Date(guess).toISOString(), minutes = hm => hm.split(":").reduce((h, m) => Number(h) * 60 + Number(m));
  const shownDay = Date.parse(calendarDay(iso) + "T00:00:00Z"), wantDay = Date.parse(day + "T00:00:00Z");
  return guess - (shownDay - wantDay) - (minutes(agTime(iso)) - minutes(time)) * 60e3;
}
function threadPreview(text) {
  const summary = withoutDateClutter(plainLine(text));
  return summary.length > 100 ? summary.slice(0, 97).replace(/\s+\S*$/, "") + "…" : summary;
}
// Under the title: what is open and how long, when you last spoke, how sure the page is.
function leadRow(r) {
  const k = known(r), thread = threads(r), row = el("div", { class: "leadrow" });
  if (thread.items.length && !["projects", "orgs", "skills", "agenda", "notes"].includes(r.category)) {
    const first = thread.items[0];
    row.appendChild(el("a", { class: "lead-open " + first.dir, href: "#r=" + encodeURIComponent(r.path) + "&h=open-threads" }, [
      el("span", { class: "dir", text: t(DIRECTION_LABEL[first.dir]) }), el("span", { class: "txt", text: threadPreview(first.text) }),
      threadAge(first) ? el("span", { class: "age mono" + ((!first.due && daysSince(first.since) === 0) ? " today" : ""), text: threadAge(first) }) : null,
      thread.items.length > 1 ? el("span", { class: "more mono", text: t("+{n} more", { n: thread.items.length - 1 }) }) : null]));
  }
  const hasProjectFinding = r.category === "projects" && !/^\s*-?\s*Unknown\b/i.test(section(r, "insight")?.text.trim() || "Unknown");
  const purpose = r.category === "projects" && k.status !== "Mapped" && hasProjectFinding ? section(r, "what it is") : null;
  const projectLead = purpose ? listItems(purpose.text)[0] || purpose.text : "";
  if (projectLead && !/^\s*-?\s*Unknown\b/i.test(projectLead)) {
    const preview = projectLead.replace(/(?:\s*\[W?\d{1,3}\])+\s*([.!?。！？])?\s*$/, "$1").trim();
    const statement = privateFallback(el("span", { id: "what-it-is", class: "lead-meta project-purpose-preview clamped", html: inline(preview, r.path) }));
    row.append(statement, expansionButton(statement, "Read full purpose"));
    const purposeSources = [...new Set(projectLead.match(/(?<=\[)W?\d{1,3}(?=\])/g) || [])];
    if (purposeSources.length) row.appendChild(el("span", { class: "project-purpose-cites", role: "group", "aria-label": t("Purpose sources") },
      [el("span", { text: t("Purpose sources") }), ...purposeSources.map(n => el("span", { html: citeChip(n, r.path, false, true) }))]));
  } else if (k.last && r.category !== "skills" && r.category !== "projects") row.appendChild(el("span", { class: "lead-meta" }, [el("span", { class: "k", text: t(r.category === "people" && r.path !== REM.owner ? (mappedContact(r) ? "Last contact in map" : "Last contact") : "Last active") + " " }), el("span", { class: "mono", text: fmtDate(k.last) })]));
  const u = r.category === "skills" ? skillUsage(r) : null;
  if (u) row.append(el("span", { class: "lead-meta usage" }, [usageBar(u), el("span", { class: "mono", text: usageCaption(u) })]),
    el("span", { class: "lead-meta usage-scope", text: t("Matched by skill name in coding sessions and co ai runs; retained eval attempts are counted separately. Neither confirms this installed version or task outcome.") }));
  if (section(r, "uncertainties")) row.appendChild(el("a", { class: "unsure", href: "#r=" + encodeURIComponent(r.path) + "&h=uncertainties", title: t("Not confirmed by the sources") }, [el("span", { class: "unsure-icon", "aria-hidden": "true", text: "◌" }), el("span", { text: t("Uncertain points") })]));
  return row;
}
function tocPanel(children) { const p = panel("On this page", children); p.classList.add("toc-panel"); return p; }
function panel(title, children) { title = t(title); return el("section", { class: "panel" }, [el("h3", { text: title }), ...children]); }
function sidePanels(r, k) {
  const panels = [];
  const glance = el("dl", {});
  const add = (dt, dd) => glance.append(el("dt", { text: t(dt) }), el("dd", {}, [dd]));
  const status = statusPill(r);
  if (status) add("Status", status);
  if (k.last && r.category !== "skills") add(r.category === "people" ? (mappedContact(r) ? "Last contact in map" : "Last contact") : r.category === "projects" ? "Last mapped session" : "Last active", el("span", { class: "mono", text: fmtDate(k.last) }));
  const mail = /Observed mail count[:：]\s*(\d+);\s*first[:：]\s*(\d{4}-\d{2}-\d{2});\s*last[:：]\s*(\d{4}-\d{2}-\d{2})/.exec(r.text);
  if (mail) add("Mail", el("span", { class: "mono", text: mail[1] + " · " + shortDate(mail[2]) + "–" + shortDate(mail[3]) }));
  const sessions = /^- Sessions[:：]\s*(\d+)/m.exec(r.text), first = /^- First seen[:：]\s*(\S+)/m.exec(r.text);
  if (sessions) add(r.category === "projects" ? "Mapped sessions" : "Sessions", el("span", { class: "mono", title: t("Sessions in the mapping window; archived input coverage can differ."), text: sessions[1] + (first ? t(" since ") + shortDate(first[1]) : "") }));
  if (r.category === "skills") {
    if (r.installation) {
      // Where it lives, named as the owner knows it ("Claude Code"), not "claude-user" and a path tail.
      const also = [...(r.original ?? r.text).matchAll(/^- Also installed at[:：]\s*(\S+)/gm)].map(m => skillHome(m[1]));
      const homes = [...new Set([skillHome(r.installation), ...also])];
      const file = el("dl", {});
      file.append(el("dt", { text: t("Lives in") }), el("dd", { text: homes.join(" · ") }),
        el("dt", { text: t("File") }), el("dd", {}, [location.protocol === "file:" ? el("a", { href: "file://" + encodeURI(r.installation), title: r.installation, text: t("Open SKILL.md") }) : el("code", { class: "local-path", text: r.installation })]));
      panels.push(panel("Source", [file]));
    }
  }
  // A person's facts, last contact and mail are the profile card and its header line (#3103): said there once, never
  // again in Full memory (#3131, hunt on rc31: '资料 · 已知 15/17 项' repeated the card). Organisations and projects
  // open on their fact card here, and so does a person whose page knows no fact yet (no profile card to say them).
  if (r.category === "people" && (r.path === REM.owner || profileCard(r))) return panels;
  const factsPanel = factList(r);
  if (factsPanel) panels.unshift(factsPanel); else if (glance.children.length || r.category !== "skills") panels.unshift(panel("At a glance", [glance]));
  return panels;
}

function refreshFocusExpansion() {
  document.querySelectorAll(".focus-more").forEach(more => {
    const statement = document.getElementById(more.getAttribute("aria-controls"));
    more.hidden = statement.classList.contains("clamped") && statement.scrollHeight <= statement.clientHeight + 1;
  });
}
function expansionButton(statement, label) {
  const more = el("button", { type: "button", class: "focus-more", "aria-controls": statement.id,
    "aria-expanded": "false", text: t(label), hidden: "" });
  more.onclick = () => {
    const clamped = statement.classList.toggle("clamped");
    more.setAttribute("aria-expanded", String(!clamped));
    more.textContent = t(clamped ? label : "Show less");
    refreshFocusExpansion();
  };
  return more;
}
// Match the origin's first explicit link, as reader_model._forward_relations does.
function translatedRelationBasis(origin, target) {
  const text = uiLanguage !== "en" && origin?.translations?.[uiLanguage];
  if (!text) return "";
  const line = text.split(/^## Sources\b/im)[0].split("\n").find(line =>
    [...line.matchAll(/\[([^\]]+)\]\(([^)]+)\)/g)].some(match => resolve(origin.path, match[2]) === target));
  if (!line) return "";
  const basis = closeStripped(line.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").replace(/\[W?\d{1,3}\]/g, "")).replace(/^[- ]+/, "").trim();
  return basis.length <= 220 ? basis : basis.slice(0, 220).replace(/\s+\S*$/, "").replace(/[ ,;:]+$/, "") + "…";
}
function localizedRelation(link, currentPath) {
  if (uiLanguage === "en" || !link.basis) return { ...link, original: false };
  const origin = byPath(link.via);
  const field = /^([^:：\n]{1,40})[:：]/.exec(link.basis)?.[1];
  const items = origin?.translations?.[uiLanguage] && field
    ? parseFacts({ ...origin, readLanguage: uiLanguage }).get(field) : null;
  const translated = items?.length ? t(field) + ": " + plainLine(items.map(i => i.value + (i.qualifier ? " (" + i.qualifier + ")" : "")).join("; "), true)
    : translatedRelationBasis(origin, origin?.path === link.path ? currentPath : link.path);
  return { ...link, basis: translated || link.basis, original: !translated };
}
// A citation or a label taken out of a line leaves no space before the punctuation that followed it
// ("Wren runs the venue at Fernhill ." on a related-page card, rc36 dates fixer).
function closeStripped(text) { return String(text).replace(/[ \t]+(?=[.,;:!?。，；：！？])/g, "").replace(/[ \t]{2,}/g, " "); }
// Why two pages belong together, from the line that links them. A basis taken from an Insight line keeps its
// writer's prefix ("Pattern: …"), so the card shows the sentence. A "Changed:" line is the page's history
// (a version moved, a date slipped), never a reason the two are related (#3397: 「ConnectOnion — Changed:
// 所提供的 Oct6 快照为 1.9.0a41…」 on a client's page), so it gives no reason at all.
// A line that only names the two pages ("Related: Willowmere Fund", "Organisation: Fernhill Labs") says nothing about why.
const RELATION_HISTORY = /^[-*\s]*(?:Changed|变化|变更)[:：]/i;
function relationReason(basis, ...pages) {
  if (!basis || RELATION_HISTORY.test(basis)) return "";
  const cleaned = String(basis).replace(/<\/?artifact-content-authored-by-others\s*\/?>/gi, "").replace(/\*\*([^*]+)\*\*/g, "$1");
  const reason = closeStripped(cleaned).replace(/^[-*\s]*(?:Now|Pattern|At stake|现在|规律|关键所在|利害|模式)[:：]\s*/i, "").trim();
  // Longest name first: taking "9900" out before 「课程 9900」 left 「课程」 behind, so 「上级组织: 课程 9900」 read as a
  // reason (13:25 hunt). A kind word a coded name carries (课程, 团队, course, team) left on its own says nothing either.
  const names = [...new Set(pages.filter(Boolean).flatMap(page => [page.title, pageName(page)]).filter(Boolean))].sort((a, b) => b.length - a.length);
  // The basis still carries its links and citations ("Parent: [[orgs/1234-….md]] [2]", the org page's own line):
  // a link's path or a citation number is not a reason either, so they go before the names do.
  const bare = reason.replace(/\[\[[^\]]*\]\]/g, "").replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/\[W?\d{1,3}\]/g, "");
  const left = names.reduce((text, name) => text.split(name).join(""), bare).replace(/^[^:：\n]{1,40}[:：]/, "")
    .replace(/(?:课程|团队|小组|course|team|unit|group)/gi, "");
  return /[\p{L}\p{N}]/u.test(left) ? reason : "";
}
// A line drawn as text, outside inline(): its [personal]/[sensitive] marks leave the words, and the strongest one
// becomes the element's data-level, so applyPrivacy curtains or removes it like any passage (#3425). A relation
// reason was drawn as plain text: the raw mark printed, and its .private carried no level, so 遮敏感 passed it by.
function markedText(text) {
  const value = String(text || "");
  const level = /[\[［]sensitive[\]］]/i.test(value) ? "sensitive" : /[\[［]personal[\]］]/i.test(value) ? "personal" : "";
  return { text: value.replace(/[ \t]*[\[［](?:personal|sensitive)[\]］]/gi, "").trim(), level };
}
// The chip a labelled passage carries, built the way inline() builds it, so it reads and hides the same everywhere.
function privacyChip(level) {
  return el("span", { class: "privacy-tag " + level, text: t(level === "sensitive" ? "Sensitive" : "Personal passage") });
}
function relationCard(link, currentPath = "") {
  const other = byPath(link.path), origin = byPath(link.via);
  const marked = markedText(relationReason(link.basis, other, origin, byPath(currentPath)));
  const basis = marked.text;
  // The mark's own level first; a line on a private topic, or one clipped before its mark, is at least personal.
  const level = marked.level || link.level || (link.private ? "personal" : "");
  const labelled = !!level;
  const labels = { linked: "Mentioned on this page", "linked from": "Its page mentions this one",
    "cited mention": "Mentions it", mentioned: "Mentions it", "mentioned by": "Mentioned elsewhere" };
  const entry = el("div", { class: "relation-entry" + (other.private || origin?.private ? " private" : "") }, [
    el("a", { class: "relation-card", href: href(other) }, [
      el("span", { class: "relation-kind", text: singular(other.category) + " · " + t(labels[link.kind] || link.kind) }),
      el("strong", { text: pageName(other) }),
      // The same chip the line carries in the body and the 关联 list, from the same level (#3425 follow-up).
      basis && level ? el("span", { class: "relation-basis private", "data-level": level }, [youify(pageWords(factWords(basis))), privacyChip(level)])
        : basis ? el("span", { class: "relation-basis", text: youify(pageWords(factWords(basis))) }) : null,
      // 原文 only while the line still reads as English: a Facts line now says its label in Chinese (#3416).
      // A curtained reason has no words on show, so nothing to call original either.
      basis && level !== "sensitive" && link.original && englishProse(factWords(basis)) ? originalMark() : null])]);
  if (origin) entry.appendChild(el("div", { class: "relation-provenance" + (labelled ? " private" : "") }, [
    origin.path !== currentPath ? el("span", {}, [t("On "), el("a", { href: href(origin), text: origin.title })]) : null,
    el("span", { html: inline((link.sources || []).map(n => "[" + n + "]").join(""), origin.path) })]));
  return entry;
}
function relationDisclosure(links, label, className = "", currentPath = "") {
  return links.length ? el("details", { class: "more-relations " + className }, [
    el("summary", { text: label }), el("div", { class: "relation-list" }, links.map(link => relationCard(link, currentPath)))]) : null;
}
function dedupeRelationSnippets(links) {
  const seen = new Set();
  return links.map(link => {
    const basis = String(link.basis || "").replace(/\s+/g, " ").trim();
    // A repeated excerpt may be hidden, never replaced by another page's claim.
    // Different origins, citations, privacy and translation states remain visible.
    const privateBasis = !!link.private || hasPrivacy(link.basis || "");
    const key = JSON.stringify([link.via, link.sources || [], privateBasis, !!link.original, basis]);
    const duplicate = basis && seen.has(key);
    if (basis) seen.add(key);
    return { ...link, private: privateBasis, basis: duplicate ? "" : link.basis };
  });
}

function connectedContext(r) {
  const related = (r.relations || []).filter(link => byPath(link.path) && !byPath(link.path).service
    && !privateTopicHidden(byPath(link.path)) && !privateTopicHidden(byPath(link.via) || {})
    && !(r.category === "projects" && byPath(link.path).category === "sessions")).map(link => localizedRelation(link, r.path));
  if (!related.length) return null;
  const explicit = link => link.kind === "linked" || link.kind === "linked from";
  const page = link => ["people", "orgs", "projects"].includes(byPath(link.path).category)
    || link.path.startsWith("skills/catalog/") && !link.path.endsWith("/index.md");
  const ordered = dedupeRelationSnippets([
    ...related.filter(link => explicit(link) && page(link)),
    ...related.filter(link => explicit(link) && !page(link)), ...related.filter(link => !explicit(link))]);
  const links = ordered.filter(link => explicit(link) && page(link));
  const notes = ordered.filter(link => explicit(link) && !page(link));
  const mentions = ordered.filter(link => !explicit(link));
  return el("div", { class: "focus-section related-records" }, [
    el("h2", { text: t("Related pages") }),
    el("p", { class: "relation-description", text: t("Pages linked from or mentioning this one.") }),
    links.length ? el("div", { class: "relation-list" }, links.slice(0, 6).map(link => relationCard(link, r.path))) : null,
    relationDisclosure(links.slice(6), t("Show {n} more related pages", { n: links.length - 6 }), "", r.path),
    relationDisclosure(notes, t("Other linked pages") + " · " + notes.length, "notebook-links", r.path),
    mentions.length ? el("details", { class: "more-relations mention-hints" }, [
      el("summary", { text: t("Pages that mention it") + " · " + mentions.length }),
      el("p", { class: "relation-description", text: t("Name matches help navigate the notebook. A mention alone does not establish a relationship.") }),
      el("div", { class: "relation-list" }, mentions.map(link => relationCard(link, r.path)))]) : null]);
}
// Who they are and how to reach them, first on a person (#2104): the owner
// asked to see email, phone, what to call them and the company at a glance.
function knownValue(value) {
  const text = plainLine(String(value ?? ""), true).trim();
  return !/^(?:unknown[.!]?|—|\s*)$/i.test(text) && !UNFILLED_LINE.test(text);
}
function contactStrip(r) {
  const parsed = parseFacts(r);
  // The parts of one field, put back together: "OpenOnion (internship; 2026)" is one value.
  const value = label => (parsed.get(label) || []).map(i => i.value + (i.qualifier ? " (" + i.qualifier + ")" : "")).join("; ");
  // Role and Company through facts(): a reviewed "Unknown" outranks an older index value.
  const f = facts(r), company = f.company ? String(f.company) : "";
  const org = /\]\((\.\.\/orgs\/[^)]+\.md)\)/.exec(company);
  const orgRecord = org && byPath(org[1].replace(/^\.\.\//, ""));
  const what = orgRecord && (parseFacts(orgRecord).get("What they do") || [])[0];
  const aka = (parsed.get("Also known as") || []).map(i => withoutWechatIds(r, i, "Also known as")).filter(Boolean)
    .map(i => i.value).filter(v => !v.includes("@")).join("; ");   // never a WeChat id (#3372)
  const rows = [["Email", value("Email")], ["Phone", value("Phone")], ["Also known as", aka],
    ["Company", company], ["Role", f.role ? String(f.role) : ""]].filter(([, v]) => knownValue(v));
  if (!rows.length) return null;
  return el("dl", { class: "focus-facts contact-strip" }, rows.map(([label, v]) => {
    const dd = el("dd", {}, [changedValue(el("span", { html: inline(v, r.path) }), r, label)]);
    if (label === "Company" && what) dd.appendChild(el("span", { class: "contact-what", html: inline(what.value, orgRecord.path) }));
    return el("div", { class: "focus-fact" }, [el("dt", { text: t(label) }), softBreaks(dd)]);
  }));
}
// A mapped project's hero says it waits and how much there is to read, not its
// folder: "WHERE THE WORK STANDS /Users/…/LayeredVisions" on the busiest project (#2349).
function mappedProjectLine(r) {
  const paths = section(r, "paths")?.text || "";
  const sessions = (/^-\s*Sessions[:：]\s*(\d+)/m.exec(paths) || [])[1];
  const last = (/^-\s*Last seen[:：]\s*([0-9-]+)/m.exec(paths) || [])[1];
  return t("Not written yet") + (sessions ? t(sessions === "1" ? ": {n} session" : ": {n} sessions", { n: sessions }) +
    (last ? t(", last on {day}", { day: fmtDate(last) }) : "") : "") + (uiLanguage === "zh" ? "。" : ".");
}
// Remove a structured label for display; direction still comes from threads().
function threadWords(text, r) {
  const names = [r, ...inCategory("people")].filter(Boolean)
    .flatMap(person => [person.title.trim(), person.title.trim().split(/\s+/)[0]]).sort((a, b) => b.length - a.length);
  const name = names.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const words = text.replaceAll("**", "").replace(/^[^:;!?：；！？]+?\s+owes?\s+(?:the user|user|you)\b\s*:?\s*/i, "");
  return name ? words.replace(new RegExp("^(?:the user|user|you)\\s+(?:owes?|asked)\\s+(?:" + name + ")\\b\\s*:?\\s*", "i"), "") : words;
}
function projectLimit(r) {
  if (r.category !== "projects" || known(r).status === "Mapped" || newestStanding(r)) return null;
  const insight = section(r, "insight");
  if (insight && !/^-?\s*Unknown\b/i.test(insight.text.trim())) return null;
  const days = r.project_coverage?.days;
  const text = r.project_coverage?.inputs_read === 0
    ? t(days ? "No coding-session input was assigned to this project in this {n}-day investigation." : "No coding-session input was assigned to this project in this investigation.", { n: days })
    : t(days ? "The {n}-day session sample did not confirm current project work." : "The supplied session sample did not confirm current project work.", { n: days });
  return el("p", { class: "deep-note-limit", text });
}
// Projects reuse the supported context inside Full memory; the first screen keeps only steps and activity.
function recordFocus(r, contextOnly = false) {
  if (r.category === "sessions") return el("div");
  const k = known(r), out = el("section", { class: "record-focus " + r.category,
    "aria-label": t("At a glance") });
  const privateMapped = r.private_project && k.status === "Mapped";
  const projectMapped = r.category === "projects" && k.status === "Mapped" && !privateMapped;
  const purpose = section(r, r.category === "orgs" ? "our relationship" : r.category === "skills" ? "when to use" : r.category === "knowledge" ? "where you stand" : "");
  const projectPurpose = r.category === "projects" ? section(r, "what it is") : null;
  const projectInsight = r.category === "projects" ? section(r, "insight") : null;
  const projectPurposeLine = projectPurpose ? listItems(projectPurpose.text)[0] || projectPurpose.text : "";
  const projectDescription = plainLine(projectPurposeLine, true);
  const projectNeedsContext = r.category === "projects" && k.status !== "Mapped" && !newestStanding(r) &&
    (!projectInsight || /^-?\s*Unknown\b/i.test(projectInsight.text.trim()));
  const findingLine = r.category === "skills" ? (section(r, "insight")?.text || "").split("\n").find(line => plainLine(line, true)) || "" : "";
  const finding = plainLine(findingLine, true);
  const statement = privateMapped ? t("Automatic investigations skip this private project. Ask for one on this page.")
    : projectMapped ? mappedProjectLine(r)
    : projectNeedsContext ? projectDescription || t("Current project work is unconfirmed in the supplied evidence.")
    : finding || plainLine(purpose?.text || "", true) || memoryStatement(r) || facts(r).what || ((k.intro || !threads(r).items.length) ? k.summary : "");
  const question = privateMapped ? "Needs your explicit request" : projectMapped ? "Mapped from your sessions" : projectNeedsContext ?
    (projectDescription ? "What this project does" : "Current work") : ({ people: "Where we stand", projects: "Where the work stands", orgs: "The relationship now",
    skills: finding ? "Useful finding" : "When this helps" })[r.category] || "What matters now";
  const focusHead = el("div", { class: "focus-head" + (projectNeedsContext ? " purpose-lead" : ""), ...(projectNeedsContext ? { id: "what-it-is" } : {}) }, [el("span", { class: "focus-kicker", text: t(question) })]);
  const statementNode = privateFallback(el("p", { id: "focus-statement", class: "focus-statement" + (privateMapped || r.category === "projects" && !projectNeedsContext ? "" : " clamped"), html: inline(statement || (k.status === "Mapped"
    ? t("Mapped from source metadata. REM has not investigated this record yet.") : t("No supported summary yet.")), r.path) }));
  focusHead.appendChild(statementNode);
  if (statement && !privateMapped && (r.category !== "projects" || projectNeedsContext)) {
    const label = projectNeedsContext ? "Read full purpose" : r.category === "skills" ? "Read complete finding" :
      r.category === "orgs" ? "Read complete relationship" : "Read full context";
    focusHead.appendChild(expansionButton(statementNode, label));
  }
  if (finding) {
    const findingSources = [...new Set(findingLine.match(/(?<=\[)W?\d{1,3}(?=\])/g) || [])];
    if (findingSources.length) focusHead.appendChild(el("span", { class: "skill-finding-cites" + (hasPrivacy(findingLine) ? " private" : ""),
      role: "group", "aria-label": t("Finding sources") },
      [el("span", { text: t(findingSources.length === 1 ? "Finding source" : "Finding sources") }),
        ...findingSources.map(n => el("span", { html: citeChip(n, r.path, false, true) }))]));
  }
  if (projectNeedsContext) {
    const purposeSources = [...new Set(projectPurposeLine.match(/(?<=\[)W?\d{1,3}(?=\])/g) || [])];
    if (purposeSources.length) focusHead.appendChild(el("span", { class: "project-purpose-cites", role: "group", "aria-label": t("Purpose sources") },
      [el("span", { text: t("Purpose sources") }), ...purposeSources.map(n => el("span", { html: citeChip(n, r.path, false, true) }))]));

  }
  if (sourceList(r).length && r.category !== "projects") focusHead.appendChild(el("a", { class: "focus-source", href: href(r) + "&h=sources", text: t("View sources →") }));
  if (r.path === REM.owner) {
    const insight = section(r, "insight");
    const items = insight ? listItems(insight.text) : [];
    const changed = items.some(item => /^(?:Changed|变化)[:：]/i.test(item));
    const next = changed && items.find(item => /^(?:Now|现在)[:：]/i.test(item));
    if (next) {
      const step = next.replace(/^(?:Now|现在)[:：]\s*/i, "");
      focusHead.appendChild(el("div", { class: "focus-next" }, [
        el("span", { class: "k", text: t("Next step") }),
        el("p", { html: inline(capFirst(step), r.path) })]));
    }
  }
  if (contextOnly) return focusHead;
  if (r.category !== "projects" || k.status === "Mapped") out.appendChild(focusHead);
  // A project's record is what is known about it (#3096); its facts, links, conversations and history fold
  // into the full memory with everything else.
  if (r.category === "projects") {
    out.append(...projectLead(r));
    return out;
  }
  const thread = threads(r), open = thread.items;
  if (open.length || ["people", "orgs"].includes(r.category)) out.appendChild(el("div", { class: "focus-section next-exchanges" }, [
    el("h2", { text: t("Open threads") }), !open.length ? emptyLine(thread) : el("ul", { class: "threads", "aria-label": t("Open threads on this record") },
      open.slice(0, 3).map(t => threadRow(r, t, false)))]));
  const strip = recordFacts(r);
  if (strip) out.appendChild(strip);
  out.append(...recordContext(r).childNodes);
  const activity = activityPanel(r);
  if (activity) out.appendChild(activity);
  return out;
}
function recordFacts(r) {
  const f = facts(r);
  const labels = r.path === REM.owner ? [["Role", f.role], ["Location", f.location], ["Company", f.company]]
    : r.category === "people" ? [["Role", f.role], ["Company", f.company], ...(mappedContact(r) ? [] : [["Last contact", f.last]])]
    // A project's folder path is the machine's, not something the owner reads (D-60): it stays in the full memory.
    : r.category === "projects" ? [["Mapped sessions", f.sessions]]
      : r.category === "orgs" ? (r.domain ? [] : [["Domain", f.domain]])
      : [];
  const shown = labels.filter(([, value]) => knownValue(value)).slice(0, 3);
  return shown.length ? el("dl", { class: "focus-facts" }, shown.map(([key, value]) => {
    const text = /^\d{4}-\d{2}-\d{2}$/.test(String(value)) ? fmtDate(value) : String(value);
    return el("div", { class: "focus-fact" }, [el("dt", { text: t(key) }),
      changedValue(el("dd", { html: inline(text, r.path), title: plainLine(text) }), r, key)]);
  })) : null;
}
function recordContext(r) {
  const out = el("div", { class: "record-focus deep-context " + r.category });
  if (r.category === "projects") {
    const sessions = projectSessions(r);
    if (sessions) out.appendChild(sessions);
  }
  // Enrich (#2315): the documents this page cites, each one click from its file.
  const documents = sourceList(r).map(source => [source, (REM.source_context || {})[sourceId(source.text, source.plain)]])
    .filter(([, c]) => c?.source === "attachment");
  if (documents.length) out.appendChild(el("div", { class: "focus-section documents private" }, [
    el("h2", { text: t("Documents") }),
    el("ul", { class: "document-list" }, documents.map(([source, c]) => el("li", {}, [
      (() => {
        const url = c.url || c.file;
        if (url) return el("a", { href: url, target: "_blank", rel: "noopener", text: c.filename });
        const button = el("button", { type: "button", class: "evidence-open-file", text: c.filename });
        button.onclick = () => openEvidence(r, source.n, button, { fromList: true });
        return button;
      })(),
      el("span", { html: " " + citeChip(source.n, r.path, false, true) })])))]));
  const conversations = [...new Set(sourceList(r).map(source => {
    const id = sourceId(source.text, source.plain);
    return id && (REM.source_context || {})[id]?.thread;
  }).filter(Boolean))].map(id => [id, conversationFor(r, id)]).filter(([, value]) => value);
  if (conversations.length) out.appendChild(el("div", { class: "focus-section conversation-view" }, [
    el("h2", { text: t("Cited conversations") }),
    el("div", { class: "conversation-list" }, conversations.slice(0, 3).map(([id, value]) => {
      const button = el("button", { type: "button", class: "conversation-open" }, [
        el("strong", { text: pageName(byPath(value.subject)) || value.subject }),
        el("span", { text: value.total + (uiLanguage === "zh" ? "" : " ") + t("archived messages") + " · " + (value.messages.at(-1)?.time ? fmtDate(value.messages.at(-1).time) : t("date unknown")) })]);
      button.onclick = () => openConversation(r, id, button);
      return button;
    })), conversations.length > 3 ? el("details", { class: "more-relations" }, [
      el("summary", { text: t("Show {n} more cited conversations", { n: conversations.length - 3 }) }),
      el("div", { class: "conversation-list" }, conversations.slice(3).map(([id, value]) => {
        const button = el("button", { type: "button", class: "conversation-open" }, [
          el("strong", { text: pageName(byPath(value.subject)) || value.subject }),
          el("span", { text: value.total + (uiLanguage === "zh" ? "" : " ") + t("archived messages") + " · " + (value.messages.at(-1)?.time ? fmtDate(value.messages.at(-1).time) : t("date unknown")) })]);
        button.onclick = () => openConversation(r, id, button);
        return button;
      }))]) : null]));
  const related = connectedContext(r);
  if (related) out.appendChild(related);
  return out;
}

function inputScopeText(scope) {
  if (/^Historical citation recovery/.test(scope)) return t("Recovered later. Original retrieval time unknown; Archived marks retention, not original investigation coverage. Initial window unchanged; provider thread unknown.");
  if (/voice transcription/i.test(scope)) return t("Voice transcript. Only your input is shown; other conversation context is omitted. Transcription may contain errors.");
  if (/Older native Codex Desktop turn/.test(scope)) return t("Older Desktop input. The app did not record how this input was supplied.");
  if (/^Skill instructions;/.test(scope)) return t("Instructions describe intended behavior, not a verified result.") + (/Recovered from/.test(scope) ? t(" This excerpt was recovered from matching file content.") : "");
  return scope;
}
function conversationFor(r, id) {
  const conversation = REM.conversations?.[id];
  if (!conversation) return null;
  const sources = sourceList(r).map(source => sourceId(source.text, source.plain))
    .filter(source => REM.source_context?.[source]?.thread === id);
  const ids = new Set(sources.flatMap(source => conversation.windows?.[source] || []));
  const messages = conversation.messages.filter(message => ids.has(message.id));
  return messages.length ? { ...conversation, messages, cited_ids: [...new Set(sources.map(source => conversation.anchors[source]).filter(id => ids.has(id)))] } : null;
}
function openConversation(r, id, trigger) {
  const conversation = conversationFor(r, id);
  if (!conversation) return;
  let dialog = document.getElementById("conversation-dialog");
  if (!dialog) { dialog = el("dialog", { id: "conversation-dialog", class: "evidence-dialog", "aria-label": t("Conversation") }); document.body.appendChild(dialog); }
  dialog.textContent = "";
  const close = el("button", { type: "button", class: "evidence-close", text: t("Close ×"), "aria-label": t("Close conversation") });
  close.onclick = () => dialog.close();
  dialog.append(el("div", { class: "evidence-top" }, [el("span", { class: "focus-kicker", text: t("Archived conversation") }), close]),
    el("h2", { text: pageName(byPath(conversation.subject)) || conversation.subject }),
    el("p", { class: "evidence-summary", text: t("{n} archived messages around this page’s citations. Up to two before and after each cited message.", { n: conversation.messages.length }) }));
  const commonScope = conversation.messages.find(message => /^Your input only\./.test(message.input_scope || ""))?.input_scope || "";
  if (commonScope) dialog.appendChild(el("p", { class: "evidence-input-scope private", text: inputScopeText(commonScope) }));
  dialog.appendChild(el("p", { class: "private-hidden-notice", text: t("Archived messages are hidden because their private content has not been classified. Use Show labelled passages in the menu to read them.") }));
  for (const message of conversation.messages) dialog.appendChild(el("div", { class: "conversation-message private" + (conversation.cited_ids.includes(message.id) ? " cited" : "") }, [
    el("span", { class: "evidence-meta", text: [message.sender === "You" ? t("You") : message.sender === "Agent" ? t("Agent") : sourceSender(message), message.time ? fmtTime(message.time) : "", conversation.cited_ids.includes(message.id) ? t("Cited message") : ""].filter(Boolean).join(" · ") }),
    ...(message.input_scope && message.input_scope !== commonScope ? [el("p", { class: "evidence-input-scope", text: inputScopeText(message.input_scope) })] : []),
    el("p", { text: message.excerpt + (message.truncated ? "…" : "") })]));
  dialog.addEventListener("close", () => trigger.focus(), { once: true });
  if (dialog.showModal) dialog.showModal(); else dialog.setAttribute("open", "");
  dialog.scrollTop = 0;
  dialog.querySelector(".conversation-message.cited")?.scrollIntoView({ block: "center" });
  close.focus({ preventScroll: true });
}
// Dates and citation labels alone are not history. Keep private rows reversible.
function historyRowContent(text, from) {
  const content = privateFallback(el("span", { html: inline(text, from) }));
  const prose = content.cloneNode(true);
  prose.querySelectorAll(".cite, .privacy-tag").forEach(node => node.remove());
  return /[\p{L}\p{N}]/u.test(prose.textContent) ? content : null;
}
function privateHistoryNotice(rows) {
  const count = rows.filter(row => row.classList.contains("private-entry")).length;
  return count ? el("p", { class: "private-history-notice", text: t(count === 1 ? "{n} private entry hidden" : "{n} private entries hidden", { n: count }) }) : null;
}
function activityType(text) {
  if (/\b(decid|agreed|chose|approved|rejected)\w*/i.test(text)) return "Decision";
  if (/\b(promis|owe|waiting|due)\w*/i.test(text)) return "Commitment";
  return "Conversation";
}
function activityDisclosure(list, rows, recent) {
  let selected = "All", expanded = false;
  const more = el("button", { class: "btn-action activity-more", type: "button", "aria-expanded": "false" });
  const update = () => {
    const privateHidden = document.documentElement.classList.contains("hide-private");
    const matching = rows.filter(row => (selected === "All" || row.dataset.type === selected)
      && !(privateHidden && row.classList.contains("private-entry")));
    const visible = new Set(expanded ? matching : matching.slice(0, 5));
    for (const row of rows) row.hidden = !visible.has(row);
    more.hidden = recent || matching.length <= 5;
    more.textContent = expanded ? t("Show less") : t("Show all {n}", { n: matching.length });
    more.setAttribute("aria-expanded", String(expanded));
  };
  more.onclick = () => { expanded = !expanded; update(); };
  list.filterActivity = name => { selected = name; expanded = false; update(); };
  list.refreshActivity = update;
  update();
  return more;
}
function activityPanel(r, recent = false, limit = 5) {
  const history = section(r, "history");
  if (!history) return null;
  const items = historyItems(history.text).filter(item => item.day);
  if (!items.length) return null;
  const box = el("section", { class: "focus-section activity-view" + (recent ? " recent-activity" : ""), "aria-label": t(recent ? "Recently" : "Activity") });
  box.appendChild(el("div", { class: "activity-head" }, [el("h2", { text: t(recent ? "Recently" : "Activity") }),
    recent ? el("a", { href: href(r) + "&h=history", text: t("All history →") }) : el("span", { class: "activity-note", text: t("From this page's dated history") })]));
  const filters = el("div", { class: "activity-filters", role: "group", "aria-label": t("Filter activity") });
  const list = el("ol", { class: "activity-list" });
  const sorted = items.map(item => ({ ...item, content: historyRowContent(item.text, r.path) }))
    .filter(item => item.content).sort((a, b) => b.day.localeCompare(a.day));
  if (!sorted.length) return null;
  const rows = (recent ? sorted.slice(0, limit) : sorted).map(item => {
    const type = activityType(item.text);
    const row = el("li", { "data-type": type, class: item.content.classList.contains("privacy-only") ? "private-entry" : "" }, [el("span", { class: "activity-day", text: item.day.length === 7 ? dayLabel(item) : threadDate(item.day) }),
      el("span", { class: "activity-type", text: t(type) }),
      el("span", { class: "activity-text" }, [item.content])]);
    list.appendChild(row);
    return row;
  });
  const more = activityDisclosure(list, rows, recent);
  for (const name of ["All", "Conversation", "Commitment", "Decision"]) {
    const count = name === "All" ? rows.length : rows.filter(row => row.dataset.type === name).length;
    if (!count) continue;
    const button = el("button", { type: "button", class: name === "All" ? "active" : "",
      "aria-pressed": String(name === "All"), text: t(name) + " " + count });
    button.onclick = () => {
      for (const b of filters.querySelectorAll("button")) { b.classList.toggle("active", b === button); b.setAttribute("aria-pressed", String(b === button)); }
      list.filterActivity(name);
    };
    filters.appendChild(button);
  }
  if (!recent) box.appendChild(filters);
  box.appendChild(list);
  const notice = privateHistoryNotice(rows);
  if (notice) box.appendChild(notice);
  box.appendChild(more);
  return rows.length ? box : null;
}

function recordEyebrow(r, person) {
  const k = known(r), children = [el("a", { href: categoryHref(r.category), text: categoryName(r.category) }),
    updatedMarker(r, true)];
  const status = !person && statusPill(r);
  if (status) children.push(el("span", { class: "sep", text: "/" }), status);
  if (!person && !["projects", "orgs"].includes(r.category)) children.push(el("span", { class: "when", text:
    (k.last && !mappedContact(r) && r.category !== "skills" ? t("last activity") + " " + fmtDate(k.last) + " · " : "") + t("file updated") + " " + fmtDate(r.updated) }));
  return el("div", { class: "eyebrow" }, children);
}

// A skill is called by what it does when that is a short phrase ("AI 语言特征修复"), with its slug (what is typed)
// under it; otherwise by the slug alone. A long sentence or a placeholder is not a name.
function skillDisplayName(r) {
  // Only a slug ("ai-language-fix") gives way; a skill already named in words ("Demo") keeps its name.
  if (r.category !== "skills" || !/^[a-z0-9]+(?:[-_.][a-z0-9]+)+$/.test(r.title.trim())) return "";
  const line = plainLine((section(r, "what it does")?.text || "").split("\n").find(l => l.trim()) || "").replace(/\s*\((?:user|project|plugin)\)\s*$/i, "").trim();
  return line && line.length <= 40 && !UNKNOWN_TEXT.test(line) && !/^unknown\b|^未知/i.test(line) && line.toLowerCase() !== r.title.toLowerCase() ? line : "";
}
function memoryHint(r, disclosed, sections, sources) {
  if (r.category === "orgs") return r.updated ? t("File updated") + " " + calendarDate(calendarDay(r.updated)) : "";
  return (disclosed ? (sources ? t("{n} sections · {m} sources", { n: sections, m: sources }) : t(sections === 1 ? "1 section" : "{n} sections", { n: sections })) : t("Original note · all fields · citations"))
    + (r.category === "projects" ? " · " + t("File updated") + " " + fmtDate(r.updated) : "");
}

function record(path, heading) {
  const r = byPath(path);
  const main = document.getElementById("main");
  main.textContent = "";
  if (!r) {
    main.appendChild(el("h1", { text: liveHere() ? (uiLanguage === "zh" ? "找不到该页面" : "Page not found") : t("Not in this snapshot") }));
    main.appendChild(emptyState(liveHere() ? "No matching pages" : "Not in this snapshot"));
    return;
  }
  if (privateTopicHidden(r)) {
    main.appendChild(el("p", { role: "status", text: t("Hidden labelled passage") }));
    return;
  }
  if (r.category === "sessions") { sessionRecord(r, heading); return; }
  translationQueued(r);  // asks for the translation; the line under the header says it is under way
  const parts = splitTrailers(r.text);
  const k = known(r);
  const person = r.category === "people" && r.path !== REM.owner;
  const disclosed = person || ["projects", "orgs", "skills", "decisions"].includes(r.category);
  CITES = { from: r.path, sources: Object.fromEntries(sourceList(r).map(s => [s.n, s.text])) };
  // A knowledge entry, a decision and a principle are one reading with their notes last (#3097): no focus block, no Full memory.
  if (ENTRY_KINDS.has(r.category)) {
    main.appendChild(entryPage(r));
    const gxRail = entryRail(r);
    attachPageNav(main, r, gxRail ? [gxRail] : []);
    entryReveal(heading);
    return;
  }
  if (r.category === "keys") { main.appendChild(keyPage(r)); return; }
  // Keep the original prose in the full note. The first screen uses the
  // structured status, actions, facts and connections above that note.
  let intro = k.intro;
  const head = el("header", { class: "page-head" }, [el("h1", { text: skillDisplayName(r) || r.title }),
    skillDisplayName(r) ? el("p", { class: "skill-slug mono", text: "/" + r.title }) : null].filter(Boolean));
  if (person) { main.appendChild(personPage(r)); fitNames(); }
  else if (r.category === "orgs") {
    main.appendChild(orgPage(r));
    fitNames();
    if (orgHidden(r)) return;
  } else {
    main.appendChild(el("div", { class: "mobile-back" }, [el("a", { href: categoryHref(r.category) }, ["← " + categoryName(r.category)])]));
    main.appendChild(recordEyebrow(r, person));
    if (r.category === "projects") head.append(projectStateLine(r), recordActs(r) || "");
    if (r.category !== "projects" && !(["agenda", "notes"].includes(r.category) && !intro && (facts(r).open?.length || threads(r).items.length))) head.appendChild(leadRow(r));
    head.append(pageTagRow(r) || "");
    main.appendChild(head);
    // A page's translation state is the top bar's language control, not a line in the body (#3143).
    main.appendChild(recordFocus(r));
  }
  const decisions = threadDecisionHistory(r);
  if (decisions) main.appendChild(decisions);

  const catalog = r.catalog_parent ? byPath(r.catalog_parent) : r;
  if (catalog && catalog.installations && catalog.installations.length > 1) {
    const copies = el("details", { class: "copies" }, [el("summary", { text: t("{n} installed copies (may differ)", { n: catalog.installations.length }) })]);
    for (const copy of catalog.installations) copies.appendChild(el("p", {}, [el("a", { href: "#r=" + encodeURIComponent(copy.path), text: copy.source })]));
    main.appendChild(copies);
  }

  const projectContext = r.category === "projects" ? el("div", { class: "project-context" },
    [leadRow(r), k.status === "Mapped" ? null : recordFocus(r, true)]) : null;
  const note = el("div", { class: "note" });
  if (intro) note.insertAdjacentHTML("beforeend", markdown(intro, r.path));
  for (const s of ordered(r, k.kept)) {
    if (FACT_LABELS[r.category] && CARD_SECTIONS.has(s.title.toLowerCase())) continue;
    // The sources get a band of their own under the grid (#3104).
    if (s.title.toLowerCase() === "sources" && sourceList(r).length) continue;
    if (["people", "projects", "orgs", "agenda", "notes"].includes(r.category) && ["open", "open threads"].includes(s.title.toLowerCase()) && (facts(r).open?.length || threads(r).items.length || listItems(s.text).every(isCalm))) continue;
    if (["key decisions", "people here", "people and ownership", "history"].includes(s.title.toLowerCase()) && listItems(s.text).every(isCalm)) continue;
    if (r.category === "projects" && s.title.toLowerCase() === "what it is" &&
      (main.querySelector(".purpose-lead") || projectContext?.querySelector(".project-purpose-preview, .purpose-lead"))) continue;
    // The anchor keeps the written (English) title, so "&h=uncertainties" works in 中文 too (#3104). A project's
    // open threads are not shown here at all: its open work lives in Today (#3096).
    const headingText = r.category === "devices" && s.title === "What it is" ? t("Device overview") : t(s.title);
    note.appendChild(el("h2", { html: inline(headingText, r.path), "data-anchor": s.title }));
    const body = sectionBody(r, s);
    // Plain Markdown joins the note flat, so lists and code stay direct children.
    if (body.className === "block") note.append(...body.childNodes); else note.appendChild(body);
  }

  note.querySelectorAll("li").forEach(li => {
    const rest = li.cloneNode(true);
    rest.querySelectorAll(".private").forEach(span => span.remove());
    if (li.querySelector(".private") && !rest.textContent.trim()) li.classList.add("private-item");
  });

  foldUnfilled(note);
  const headings = [...note.querySelectorAll("h2, h3, h4, h5, h6")];
  const ids = new Set(), toc = [];
  for (const h of headings) {
    const base = (h.dataset.anchor || h.textContent).trim().toLowerCase().replace(/[^\p{L}\p{N}_\s-]/gu, "").replace(/\s+/g, "-") || "section";
    let id = base, n = 1;
    while (ids.has(id)) id = base + "-" + n++;
    ids.add(id); h.id = id;
    if (h.tagName === "H2") toc.push({ title: h.textContent.trim(), id });
    h.appendChild(el("a", { class: "heading-anchor", href: "#r=" + encodeURIComponent(r.path) + "&h=" + encodeURIComponent(id), "aria-label": t("Direct link to section"), text: "#" }));
  }
  for (const block of note.querySelectorAll(".code-block")) {
    const btn = block.querySelector(".code-copy");
    btn.onclick = () => copyToClipboard(block.querySelector("code").textContent, btn, t("Copied"));
  }

  const sourceBand = sourcesBlock(r);
  if (sourceBand) toc.push({ title: t("Sources"), id: "sources" });
  const panels = sidePanels(r, k);
  const grid = el("div", { class: "page-grid" }, [el("div", { class: "body" }, r.category === "projects"
    ? [projectContext, recordFacts(r), note, recordContext(r), activityPanel(r)] : [note, person || r.category === "orgs" ? recordContext(r) : null])]);
  const sections = toc.length + (note.firstElementChild && note.firstElementChild.tagName !== "H2" ? 1 : 0)
    + grid.querySelectorAll(".deep-context .focus-section").length + panels.length
    + Number(!!parts.related) + Number(!!parts.sources);
  const sources = sourceList(r).length;
  const limit = projectLimit(r);
  const hasMemory = !!limit || note.childElementCount > 0 || !!grid.querySelector(".factlist, .deep-context h2") || panels.some(p => p.querySelector(".factlist, a"))
    || !!parts.related || !!parts.sources || sources > 0;
  // Opens by itself (owner, #3104): the page lands with its memory showing; the summary still folds it.
  const deep = el(disclosed ? "details" : "section", { class: "deep-note", "aria-labelledby": "full-memory-heading", ...(disclosed ? { open: "" } : {}) }, [
    el(disclosed ? "summary" : "div", { class: "deep-head" }, [el("span", { class: "deep-label" }, [el("h2", { id: "full-memory-heading", text: t("Full memory and sources") }),
      el("span", { class: "deep-hint", text: memoryHint(r, disclosed, sections, sources) })]),
      disclosed ? el("span", { class: "deep-toggle", "aria-hidden": "true" }) : null]), limit, grid, sourceBand]);
  if (hasMemory) main.appendChild(deep);
  if (sourceBand) sourceBand.finish(main);
  const column = grid.firstChild;
  if (projectContext) {
    const cites = projectContext.querySelector(".project-purpose-cites"), unsure = projectContext.querySelector(".unsure");
    if (cites && unsure) cites.appendChild(unsure);
  }

  if (parts.related || parts.sources) {
    const aside = el("div", { class: "aside" });
    if (parts.related) {
      aside.appendChild(el("div", { class: "k", text: t("Related") }));
      const links = [...parts.related.matchAll(/\[([^\]]+)\]\(([^)\s]+)\)/g)];
      const box = el("div", { class: "related" });
      if (links.length) {
        for (const [, lbl, url] of links) {
          const link = safeHref(r.path, url);
          box.appendChild(link ? el("a", { href: link.href, text: lbl }) : el("span", { text: lbl }));
        }
      } else box.innerHTML = inline(parts.related, r.path);
      aside.appendChild(box);
    }
    if (parts.sources) {
      aside.appendChild(el("div", { class: "k", text: t("Sources") }));
      const chips = sourceChips(parts.sources);
      aside.appendChild(chips.length ? el("div", { class: "chips" }, chips) : el("div", { text: parts.sources }));
    }
    column.appendChild(aside);
  }

  if (k.missing.length) {
    const mapped = k.status === "Mapped";
    const box = el("div", { class: "missing" + (mapped ? " primary" : "") }, [
      el("span", { class: "lead", text: r.private_project ? t("Private project — waiting for your request") : !REM.status?.worker?.enabled ? t("Page pending — background updates off") : mapped ? queuedLine(r) : t("Unresolved sections queued for a future pass") }),
      r.private_project ? el("p", { text: t("This private project waits for your request.") }) : null,
      r.private_project ? investigateRequest(r) : null,
      el("div", { class: "names", text: mapped ? t("{n} sections will be written when it is investigated.", { n: k.missing.length }) : t("Still unknown: ") + youify(k.missing.map(name => t(name)).join(uiLanguage === "zh" ? "、" : ", ")) + (uiLanguage === "zh" ? "。" : ".") })]);
    if (mapped) main.insertBefore(box, deep.parentNode ? deep : null); else column.appendChild(box);
  }

  const foot = el("div", { class: "page-foot" });
  // The raw path is for the owner's terminal, not for reading: the button says what it does; the path is its tooltip.
  const pathBtn = el("button", { class: "btn-action copy-path", type: "button", text: t("Copy the file path"), title: r.path });
  pathBtn.onclick = () => copyToClipboard(REM.root + "/" + r.path, pathBtn, t("Path copied"));
  const copyMd = el("button", { class: "btn-action", type: "button", text: t("Copy Markdown"), title: t("Copy the page as written, unknowns included") });
  copyMd.onclick = () => copyToClipboard(r.text, copyMd, t("Markdown copied"));
  foot.append(pathBtn, copyMd);
  const languages = languageBar(r);
  if (languages) foot.appendChild(languages);
  if (!hasMemory || !["projects", "orgs"].includes(r.category)) foot.append(el("span", { class: "when", text: t("File updated") + " " + fmtDate(r.updated) }));
  (deep.parentNode ? (sourceBand ? deep : column) : main).appendChild(foot);

  if (heading) {
    const target = document.getElementById(heading) || document.getElementById(heading.toLowerCase()) || headings.find(h => h.id === heading.toLowerCase());
    // Reveal a deep link before asking the browser to scroll to it.
    for (let parent = target?.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === "DETAILS") parent.open = true;
    }
    if (target?.closest(".deep-sources")) target.closest(".deep-sources").reveal([target.id.replace(/^src-/, "")], false);
    if (target && target.tagName === "LI") {
      // A citation's source: centred and briefly lit, so the eye finds the line (#2054).
      target.scrollIntoView({ block: "center" });
      target.classList.add("flash");
    } else if (target) target.scrollIntoView();
  }
  const graphBlock = r.category !== "orgs" ? graphRailBlock(r) : null;
  attachPageNav(main, r, [...panels, graphBlock].filter(Boolean));
  shortenPaths(main);
}
// ---- One text pass over what the reader shows (#3165, rc34 hunt): every ISO date in the reader's own form, a date
// never printed twice in a row, and a raw source id as a short named chip that opens it. The page text and the
// Markdown keep what was written; only what is drawn changes.
Object.assign(UI.zh, { "Record": "记录", "Commit": "提交", "Its original isn't in this snapshot.": "这条来源的原文不在这份快照里。" });
const ISO_RANGE = /\b(\d{4}-\d{2}-\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?(?:\s*(?:–|—|-|to|至|到)\s*((?:\d{4}-)?(?:\d{2}-)?\d{2})(?![\d-]))?\b/g;
const RAW_ID = /\b(?:(?:codex|claude-code|gmail|outlook|github|mail|session):[A-Za-z0-9][\w.:@/+=-]{5,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{24,})\b/gi;
// A short hash (a commit, a hex record id): 7–23 hex characters with both a digit and a letter, so a plain number or
// a word like "facade" never matches. Longer runs and prefixed ids are RAW_ID's.
const SHORT_HEX = /\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,23}\b/gi;
// Dates are put in the reader's form everywhere a person reads them, links and buttons included (a person's company
// line and the sources' titles are links and buttons; rc35 hunt). What was written to be copied stays as written.
const TIDY_SKIP = "pre, code, textarea, input, select, script, style, .local-path, .src-id, .cite, .evidence-meta, [contenteditable]";
// Inside a link or a button a raw id cannot become a chip of its own (a control inside a control); it is named in place.
// Only an id standing alone is (standaloneId): a link whose text is a URL or a page slug keeps it whole.
const NO_CHIP = "a, button";
function readerDate(day, locale = uiLocale()) {
  return calendarDate(day, locale);
}
// One language per sentence: a date in page text takes its own sentence's language, so the page's words read the same
// whichever interface language is on. Per sentence, not per block: an org summary's English sentence beside a Chinese
// one kept getting a Chinese date ("hosted the pilot (8月10日)", rc36 dates fixer).
// The reader's own chips inside a sentence (citations, source ids, privacy labels) speak the interface's language
// and say nothing about the sentence's.
const LOCALE_CHIPS = ".cite, .src-id, .privacy-tag, .uncertain-marker, .sr-only";
const HAN_WORDS = text => /\p{Script=Han}/u.test(text.replace(/(?:\d{4}年)?\d{1,2}月\d{1,2}日/g, ""));
const LATIN_WORDS = text => /\p{Script=Latin}{2,}/u.test(text);
// The block's text with chips blanked out, and where this node starts in it.
function blockText(node) {
  const block = node.parentElement.closest("p, li, td, th, dd, dt, h1, h2, h3, h4, blockquote, .tl-e, .row") || node.parentElement;
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  let text = "", at = 0;
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (n === node) at = text.length;
    text += n !== node && n.parentElement.closest(LOCALE_CHIPS) ? " ".repeat(n.nodeValue.length) : n.nodeValue;
  }
  return { text, at };
}
// The locale for a date at [index, index + length) of this node: its sentence's script; a sentence with no words of
// its own (a bare date in a list item) takes the block's.
function sentenceLocale(node) {
  const { text, at } = blockText(node), block = HAN_WORDS(text) ? "zh-CN" : "en-US";
  // An English full stop ends a sentence before a space; Chinese ones end it where they stand.
  const ends = [...text.matchAll(/[.!?;](?=\s)|[。！？；\n]/g)].map(m => m.index + 1);
  return (index, length) => {
    const from = at + index, to = from + length;
    const start = Math.max(0, ...ends.filter(end => end <= from)), stop = Math.min(text.length, ...ends.filter(end => end > to));
    const words = text.slice(start, from) + " " + text.slice(to, stop);
    return HAN_WORDS(words) ? "zh-CN" : LATIN_WORDS(words) ? "en-US" : block;
  };
}
// "2026-07-05–17" → "7月5日–17日"; "2026-07-29–08-04" → "7月29日–8月4日"; "2026-08-26–2026-08-28" likewise.
function readerRange(start, end, locale) {
  if (!end) return readerDate(start, locale);
  const full = end.length === 10 ? end : end.length === 5 ? start.slice(0, 5) + end : start.slice(0, 8) + end;
  if (isNaN(new Date(full + "T00:00:00Z"))) return readerDate(start, locale) + "–" + end;
  if (full.slice(0, 7) === start.slice(0, 7))
    return readerDate(start, locale) + "–" + (locale.startsWith("zh") ? Number(full.slice(8)) + "日" : String(Number(full.slice(8))));
  return readerDate(start, locale) + "–" + readerDate(full, locale);
}
// locale: one locale, or a function of where the date stands (sentenceLocale) giving each date its own.
function localiseDates(text, locale = uiLocale()) {
  ISO_RANGE.lastIndex = 0;
  const at = typeof locale === "function" ? locale : () => locale;
  // "8 月 10 日", "2026 年 8 月 10 日": the spaced form a model sometimes writes reads as the reader's own "8月10日".
  return text.replace(ISO_RANGE, (m, start, end, index) => readerRange(start, end, at(index, m.length)))
    .replace(/(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日/g, (m, y, month, day) => (y ? y + "年" : "") + month + "月" + day + "日");
}
// "10月29日 (10月29日)", "10月29日 10月29日", "Oct 29 (Oct 29)": once. Prose only: a fact's value is made single by
// oneDate before it is drawn (#3192), and every pass here skips text that holds no ISO date, so nothing is formatted twice.
function onceDates(text) {
  const date = "(?:(?:\\d{4}年)?\\d{1,2}月\\d{1,2}日|[A-Z][a-z]{2,8} \\d{1,2}(?:, \\d{4})?|\\d{1,2} [A-Z][a-z]{2,8}(?: \\d{4})?)";
  return text.replace(new RegExp("(" + date + ")\\s*[（(]\\s*(" + date + ")\\s*[)）]", "g"), (m, one, two) => sameDay(one, two) ? one : m)
    .replace(new RegExp("(" + date + ")(\\s+\\1)+(?![\\d日])", "g"), "$1");
}
// "10月29日" and "Oct 29" name the same day: month and day compared, whatever the language.
function monthDay(text) {
  const zh = /(\d{1,2})月(\d{1,2})日/.exec(text);
  if (zh) return Number(zh[1]) + "-" + Number(zh[2]);
  const d = new Date(text.replace(/,? \d{4}$/, "") + " 2000");
  return isNaN(d) ? text : d.getMonth() + 1 + "-" + d.getDate();
}
function sameDay(one, two) {
  return monthDay(one) === monthDay(two);
}
function rawIdLabel(id) {
  const kind = /^(codex|claude-code|session):/i.test(id) ? "Session" : /^(gmail|outlook|mail):/i.test(id) ? "Mail" : /^github:/i.test(id) ? "GitHub"
    : /^[0-9a-f]{7,12}$/i.test(id) ? "Commit" : "Record";
  const when = REM.source_context?.[id]?.time;
  return t(kind) + (when ? " · " + readerDate(calendarDay(when)) : "");
}
function rawIdChip(id) {
  // An inline link like a citation chip, not a <button>: the phone's 44px touch box would break the line it sits in.
  const chip = el("a", { href: "#", role: "button", class: "src-id", title: id, text: rawIdLabel(id) });
  chip.onclick = event => { event.preventDefault(); openRawId(id, chip); };
  return chip;
}
// The page's own numbered source when it lists this id; else the archived excerpt; else a card saying so.
function openRawId(id, trigger) {
  const path = new URLSearchParams(location.hash.slice(1)).get("r"), r = path && byPath(path);
  const listed = r && sourceList(r).find(source => sourceId(source.text, source.plain) === id);
  if (listed) return openEvidence(r, listed.n, trigger, { fromList: true });
  const panel = evidencePanel(), close = el("button", { type: "button", class: "evidence-close", text: t("Close ×"), "aria-label": t("Close source context") });
  close.onclick = closeEvidence;
  const context = REM.source_context?.[id];
  panel.replaceChildren(el("div", { class: "evidence-handle", "aria-hidden": "true" }),
    el("div", { class: "evidence-top" }, [el("span", { text: rawIdLabel(id) }), close]),
    context?.excerpt ? el("blockquote", { text: context.excerpt }) : el("p", { class: "evidence-unavailable", text: t("Its original isn't in this snapshot.") }),
    el("p", { class: "evidence-meta", text: id }));
  evidenceTrigger = trigger;
  panel.parentElement.hidden = false;
  document.body.classList.add("evidence-open");
  evidenceLayout();
  close.focus({ preventScroll: true });
  return true;
}
// A row's own date label (timeline, activity) already says the day: the text after it does not repeat it.
function rowDateLabel(node) {
  const row = node.parentElement.closest("li, tr, .tl-e, .row");
  const label = row && [...row.querySelectorAll(".d, .when, .date, .day, time")].find(n => !n.contains(node));
  return label ? label.textContent.replace(/\s+/g, " ").trim() : "";
}
// An id is a word of its own: "Fixed in e5f48af0." or "(gmail:…)". A hex run inside a longer token is part of that
// token: a URL's last segment, a page slug's hash suffix, a file name, an email's local part (rc36 hunt: a profile
// link followed by a stray 提交 on 18 of 21 pages). The token is the run of non-space text around the match, less the
// punctuation that ends a sentence or wraps a word.
function standaloneId(text, m) {
  let start = m.index, end = m.index + m[0].length;
  while (start > 0 && !/[\s（(\[「『"'“‘<，。；：、]/.test(text[start - 1])) start--;
  while (end < text.length && !/[\s）)\]」』"'”’>，。；：、]/.test(text[end])) end++;
  return text.slice(start, end).replace(/[.,;:!?…]+$/, "") === m[0];
}
// Every raw id in a text: a long or prefixed id (RAW_ID) or a short hash (SHORT_HEX), in order, never overlapping,
// each standing alone.
function rawIds(text) {
  RAW_ID.lastIndex = 0; SHORT_HEX.lastIndex = 0;
  const found = [...text.matchAll(RAW_ID)];
  for (const m of text.matchAll(SHORT_HEX))
    if (!found.some(f => m.index < f.index + f[0].length && f.index < m.index + m[0].length)) found.push(m);
  return found.filter(m => standaloneId(text, m)).sort((a, b) => a.index - b.index);
}
// The text right before a citation chip, even when the chip is tethered to the word before it.
function textBefore(node) {
  for (let at = node; at && !/^(P|LI|TD|DD|BLOCKQUOTE|H\d)$/.test(at.tagName || ""); at = at.parentElement) {
    let prev = at.previousSibling;
    while (prev && prev.nodeType === 1 && prev.lastChild) prev = prev.lastChild;
    if (prev) return prev.nodeType === 3 ? prev : null;
  }
  return null;
}
// "venue (8月10日) [chip: 8月10日]": the chip already says the day, so the prose copy goes (46 on the rc35 hunt).
function dropDatesBeforeChips(root) {
  const date = "(?:\\d{4}年)?\\d{1,2}月\\d{1,2}日|[A-Z][a-z]{2,8} \\d{1,2}(?:, \\d{4})?|\\d{1,2} [A-Z][a-z]{2,8}(?: \\d{4})?";
  const tail = new RegExp("\\s*[（(]\\s*(" + date + ")\\s*[)）]\\s*$");
  for (const chip of root.querySelectorAll(".cite")) {
    const node = textBefore(chip), said = chip.querySelector(".cite-short")?.textContent || "";
    const m = node && tail.exec(node.nodeValue);
    if (m && said && sameDay(m[1], said)) node.nodeValue = node.nodeValue.slice(0, m.index) + " ";
  }
}
function tidyText(root) {
  if (!root || typeof document === "undefined" || !document.createTreeWalker) return root;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: node =>
    /\d/.test(node.nodeValue) && !node.parentElement.closest(TIDY_SKIP) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    let text = onceDates(localiseDates(node.nodeValue, sentenceLocale(node)));
    const label = rowDateLabel(node);
    if (label && text.trimStart().startsWith(label)) text = text.trimStart().slice(label.length).replace(/^\s*[—–:：-]\s*/, "");
    const ids = rawIds(text);
    if (!ids.length) { if (text !== node.nodeValue) node.nodeValue = text; continue; }
    const control = node.parentElement.closest(NO_CHIP);
    if (control) {
      // Named in place; the whole id stays one hover away on the control itself.
      if (!control.title) control.title = ids.map(m => m[0]).join(" ");
      node.nodeValue = ids.reduceRight((out, m) => out.slice(0, m.index) + rawIdLabel(m[0]) + out.slice(m.index + m[0].length), text);
      continue;
    }
    const parts = [];
    let last = 0;
    for (const m of ids) {
      parts.push(document.createTextNode(text.slice(last, m.index)), rawIdChip(m[0]));
      last = m.index + m[0].length;
    }
    parts.push(document.createTextNode(text.slice(last)));
    node.replaceWith(...parts);
  }
  dropDatesBeforeChips(root);
  shortenPaths(root);
  return root;
}

// A local path in page text reads as its file name; the whole path is one hover away (auto-scan, #3165).
const LOCAL_PATH = /(?:\/Users|\/home|\/private|\/var\/folders|~)\/[^\s<>"'`，。、；）)\]]+/g;
function shortenPaths(root) {
  const hasPath = text => { LOCAL_PATH.lastIndex = 0; return LOCAL_PATH.test(text); };
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: node =>
    hasPath(node.nodeValue) && !node.parentElement.closest("a, pre, textarea, input, .local-path") ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const parts = [], text = node.nodeValue;
    let last = 0;
    for (const m of text.matchAll(LOCAL_PATH)) {
      parts.push(document.createTextNode(text.slice(last, m.index)));
      parts.push(el("span", { class: "local-path", title: m[0], text: m[0].replace(/\/+$/, "").split("/").pop() }));
      last = m.index + m[0].length;
    }
    parts.push(document.createTextNode(text.slice(last)));
    node.replaceWith(...parts);
  }
}

function highlight(line, needle) {
  if (!needle) return esc(line);
  const lower = line.toLowerCase();
  const out = [];
  let i = 0, at;
  while ((at = lower.indexOf(needle, i)) !== -1) {
    out.push(esc(line.slice(i, at)), "<mark>", esc(line.slice(at, at + needle.length)), "</mark>");
    i = at + needle.length;
  }
  out.push(esc(line.slice(i)));
  return out.join("");
}

function recordedNames(r) {
  const src = r.original ?? r.text ?? "";
  if (r._namesSrc === src && r._namesTitle === r.title && r._names) return r._names;
  const aliases = src.split("\n", 40).flatMap(line => {
    const match = /^\s*-?\s*(?:also known as|aka|别名)[:：]\s*(.*)$/i.exec(line);
    return match ? match[1].replace(/\s*\[W?\d+\]/g, "").split(/[,;、]/) : [];
  });
  const alternate = [...r.title.matchAll(/\(([^()]*)\)/g)].map(match => match[1]);
  r._namesSrc = src; r._namesTitle = r.title;
  return (r._names = [r.title, ...alternate, ...aliases].map(name => name.trim().replace(/^`|`$/g, "").replace(/\s*\([^()]*\)$/, "").trim().toLowerCase()).filter(Boolean));
}
function nameMatches(records, query) {
  const needle = query.trim().toLowerCase();
  return records.filter(r => recordedNames(r).some(name => name === needle
    || (!/\s/.test(needle) && name.split(/\s+/)[0] === needle)));
}
// Identity choices use original visible facts, never cached translated identity or file order.
function identityDetails(r) {
  const original = r.original ?? r.text;
  const text = document.documentElement.classList.contains("hide-private") ? unlabelled(original) : original;
  const parsed = parseFacts({ ...r, text, original: text, translations: {}, readLanguage: "" });
  return ["Company", "Role", "Email", "What they do", "Repository", "Status"]
    .map(name => [name, (parsed.get(name) || []).map(item => plainValue(item.value + (item.qualifier ? " (" + item.qualifier + ")" : ""))).filter(knownValue).join("; ")])
    .filter(([, value]) => value);
}
function identityChoices(records, query, related = false) {
  const section = el("section", { class: "search-group" }, [
    el("h2", { class: "section", text: t("Choose a page") }),
    el("p", { class: "lede", text: t("Several pages match this name. Choose one to keep their facts and connections separate.") })]);
  const list = el("ul", { class: "hits" });
  for (const [index, r] of records.entries()) {
    const detailId = "identity-choice-" + index;
    const destination = related ? "#q=" + encodeURIComponent(query) + "&related=" + encodeURIComponent(r.path) : href(r);
    const details = identityDetails(r);
    list.appendChild(el("li", {}, [el("div", { class: "t" }, [el("a", { href: destination, text: pageName(r), "aria-describedby": detailId }),
      el("span", { class: "when", text: label(r.category) })]),
      el("dl", { class: "best-facts", id: details.length ? detailId : detailId + "-facts" }, details.flatMap(([name, value]) => [el("dt", { text: t(name) }), el("dd", { text: value })])),
      !details.length ? el("p", { class: "hit", id: detailId, text: t("No visible identifying details. Open the page to check its sources.") }) : null,
      related ? el("a", { href: href(r), text: t("Open page →") }) : null]));
  }
  section.appendChild(list);
  return section;
}
function search(q, relatedPath = "") {
  const main = document.getElementById("main");
  main.textContent = "";
  if (/^\s*tag:/i.test(q)) { tagPage(tagResolve(q)); return; }
  if (/\b(who\s+(?:do\s+i\s+)?owe|what\s+do\s+i\s+owe|waiting\s+on\s+me|open\s+threads)\b/i.test(q)) { taskView("open"); return; }
  if (/\b(what\s+changed|memory\s+changes|learned\s+(?:last\s+night|overnight))\b/i.test(q)) { taskView("changes"); return; }
  const connected = /\b(?:connected|related)\s+to\s+(.+)/i.exec(q) || (relatedPath ? [q, q.replace(/^(?:相关|关联)\s*/, "")] : null);
  if (connected) {
    const candidates = nameMatches(listedRecords(), connected[1]);
    const target = relatedPath ? candidates.find(r => r.path === relatedPath) : candidates.length === 1 ? candidates[0] : null;
    if (!target && (candidates.length > 1 || relatedPath)) {
      main.appendChild(el("h1", { text: t("Connected to {name}", { name: connected[1].trim() }) }));
      if (relatedPath) main.appendChild(emptyState("This page is unavailable in this snapshot."));
      if (candidates.length) main.appendChild(identityChoices(candidates, q, true));
      return;
    }
    if (target) {
      main.appendChild(el("div", { class: "eyebrow", text: t("Search / related pages") }));
      main.appendChild(el("h1", { text: t("Connected to {name}", { name: target.title }) }));
      const card = connectedContext(target);
      main.appendChild(card || emptyState("No supported links in this snapshot."));
      return;
    }
  }
  const needle = q.toLowerCase();
  const hits = [];
  const grouped = new Map();
  const plain = l => (document.documentElement.classList.contains("hide-private") ? unlabelled(l) : privacyLevel === "cover" ? l.replace(/[^.!?。！？\n]*\[sensitive\]/gi, "") : l).replace(/\[W?\d{1,3}\]/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/[*`>]/g, "");
  const hidePriv = document.documentElement.classList.contains("hide-private");
  for (const r of REM.records) {
    if (privateTopicHidden(r) || r.path === "skills/catalog/index.md" || skillReport(r)) continue;
    if (r.category === "sessions") {
      if (sessionText(r).lower.includes(needle)) hits.push({ r, lines: null, sessionLazy: true });
      continue;
    }
    if (r._searchSrc !== r.text) {
      r._searchSrc = r.text;
      r._searchBody = splitTrailers(r.text).body.replace(COMMENT, "");
      r._searchLower = r._searchBody.toLowerCase();
      r._searchLines = r._searchBody.split("\n");
    }
    const titleAllowed = !r.private || privacyLevel === "all";
    const titleHit = titleAllowed && r.title.toLowerCase().includes(needle);
    const extractLines = () => {
      const out = [];
      for (const rawLine of r._searchLines) {
        if (!rawLine || !rawLine.toLowerCase().includes(needle[0])) continue;
        const cleaned = plain(rawLine);
        if (cleaned.replace(/[\[［](?:personal|sensitive)[\]］]/gi, "").toLowerCase().includes(needle)) {
          out.push(cleaned);
          if (out.length === 3) break;
        }
      }
      return out;
    };
    const rawBodyHit = r._searchLower.includes(needle);
    const hasPrivTag = rawBodyHit && /[\[［](?:personal|sensitive)[\]］]/i.test(r._searchBody);
    const bodyMatched = rawBodyHit && (!hasPrivTag || extractLines().length > 0);
    if (bodyMatched || titleHit) {
      const lines = hasPrivTag ? extractLines() : null;
      const primary = r.catalog_parent ? byPath(r.catalog_parent) : r;
      if (!grouped.has(primary.path)) { const hit = { r: primary, lines: [] }; grouped.set(primary.path, hit); hits.push(hit); }
      const hit = grouped.get(primary.path);
      if (lines) { hit.lines = [...new Set([...(hit.lines || []), ...lines])].slice(0, 3); }
      else { (hit.sources = hit.sources || []).push(r); }
    }
  }
  // Names first: a page whose title matches is what was looked for.
  hits.sort((a, b) => (((!b.r.private || privacyLevel === "all") && b.r.title.toLowerCase().includes(needle)) ? 1 : 0)
    - (((!a.r.private || privacyLevel === "all") && a.r.title.toLowerCase().includes(needle)) ? 1 : 0));
  main.appendChild(el("div", { class: "eyebrow" }, [el("span", { text: t("Search") })]));
  main.appendChild(el("h1", { text: "“" + q + "”" }));
  const asTag = tagResolve(q);
  if (asTag) main.appendChild(el("p", { class: "tag-hit" }, [el("a", { class: "chip", href: tagHref(asTag) },
    [t("Tag {label}", { label: tagLabel(asTag) }), " ", el("span", { class: "chip-n", text: String(REM.tags[asTag].count || 0) })])]));
  main.appendChild(el("p", { class: "lede", text: t(hits.length === 1 ? "{n} page matches — literal, case-insensitive" : "{n} pages match — literal, case-insensitive", { n: hits.length }) }));
  if (!hits.length) {
    main.appendChild(emptyState("No match"));
    return;
  }
  // The best match answers: a person's or organisation's name gets its facts right here.
  const eligible = new Set(listedRecords().map(r => r.path));
  const named = nameMatches(hits.map(h => h.r).filter(r => eligible.has(r.path) && FACT_LABELS[r.category]), q);
  // A handful of same-named pages is a choice; more than five is what the groups below are for.
  if (named.length > 1 && named.length <= 5) main.appendChild(identityChoices(named, q));
  else if (named.length === 1) main.appendChild(bestMatch(named[0]));
  // Grouped by kind, people first; one snippet a page, never a local path. Each group shows its first five and
  // "显示全部 N 个"; chips above filter to one kind (#3169: 232 hits used to be one 22-screen list).
  const ORDER = ["people", "orgs", "projects", "knowledge", "skills", "decisions", "principles", "sessions"];
  const rank = c => ORDER.includes(c) ? ORDER.indexOf(c) : ORDER.length;
  const groups = new Map();
  for (const hit of hits.sort((a, b) => rank(a.r.category) - rank(b.r.category))) {
    if (!groups.has(hit.r.category)) groups.set(hit.r.category, []);
    groups.get(hit.r.category).push(hit);
  }
  const isPath = l => /^(?:\/|~\/|[A-Z]:\\)\S+/.test(l) || /^(?:File|Path)[:：]\s*[/~]/.test(l);
  if (groups.size > 1) {
    const chips = el("div", { class: "search-kinds", role: "group", "aria-label": t("Kinds") });
    const choose = kind => { chips.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.kind === kind)));
      main.querySelectorAll(".search-group").forEach(g => { g.hidden = kind !== "all" && g.dataset.kind !== kind; }); };
    for (const [kind, words, n] of [["all", t("All"), hits.length], ...[...groups].map(([c, list]) => [c, label(c), list.length])]) {
      const b = el("button", { type: "button", class: "chip ghost", "data-kind": kind, "aria-pressed": String(kind === "all") }, [el("span", { text: words }), el("span", { class: "mono", text: " " + n })]);
      b.onclick = () => choose(kind);
      chips.appendChild(b);
    }
    main.appendChild(chips);
  }
  const FIRST = 5;
  for (const [c, list] of groups) {
    const group = el("section", { class: "search-group", "data-kind": c });
    main.appendChild(group);
    group.appendChild(el("h2", { class: "section group" }, [el("span", { text: label(c) }), el("span", { class: "n", text: String(list.length) })]));
    const buildHitRow = (hit) => {
      const { r } = hit;
      let lines = hit.lines;
      if (hit.sessionLazy) lines = [sessionExcerpt(r, [needle]).text.slice(0, 240)];
      else if (!lines && hit.sources) {
        lines = [];
        for (const sr of hit.sources) {
          for (const rawLine of (sr._searchLines || [])) {
            if (!rawLine || !rawLine.toLowerCase().includes(needle[0])) continue;
            const cleaned = plain(rawLine);
            if (cleaned.replace(/[\[［](?:personal|sensitive)[\]］]/gi, "").toLowerCase().includes(needle)) {
              if (!lines.includes(cleaned)) lines.push(cleaned);
              if (lines.length === 3) break;
            }
          }
          if (lines.length === 3) break;
        }
      }
      lines = lines || [];
      const shownTitle = typeof pageName === "function" ? pageName(r) : r.title;
      const li = el("li", {}, [
        el("div", { class: "t" }, [el("span", {}, [el("a", { href: href(r) + (c === "sessions" ? "&find=" + encodeURIComponent(q) : ""), html: highlight(shownTitle, needle) }), statusPill(r)]),
          el("span", { class: "when", text: shortDate(known(r).last) })])]);
      const line = lines.map(l => l.trim().replace(/^#+\s*/, "").replace(/^[-+]\s+/, ""))
        .find(l => !isPath(l) && l.replace(/^(?:Email|Emails|邮箱)[:：]\s*/i, "").trim().toLowerCase() !== r.title.trim().toLowerCase());
      const labelledLine = line && /[\[［](?:personal|sensitive)[\]］]/i.test(line);
      if (line) li.appendChild(el("div", { class: "hit", html: labelledLine ? inline(localDates(line), r.path) : highlight(searchSnippet(summaryLine(line)), needle) }));
      return li;
    };
    const DOM_CAP = 12;
    const ul = el("ul", { class: "hits" }, list.slice(0, DOM_CAP).map((hit, i) => {
      const li = buildHitRow(hit);
      if (i >= FIRST) li.hidden = true;
      return li;
    }));
    group.appendChild(ul);
    if (list.length > FIRST) {
      const more = el("button", { type: "button", class: "chip ghost search-more", text: t("Show all {n} results", { n: list.length }) });
      more.onclick = () => {
        ul.querySelectorAll("li[hidden]").forEach(li => { li.hidden = false; });
        if (list.length > DOM_CAP) ul.append(...list.slice(DOM_CAP).map(buildHitRow));
        more.remove();
      };
      group.appendChild(more);
    }
    if (c === "sessions") group.appendChild(el("a", { href: sessionHash({ find: q }),
      text: list.length === 1 ? t("Open in Agent sessions →") : t("{n} matching sessions →", { n: list.length }) }));
  }
}
// A search snippet reads as a sentence: dates in the reader's own form, never a raw source id, hash or uuid.
function searchSnippet(text) {
  return localDates(text).replace(/\b(?:codex|claude-code|gmail|outlook|whatsapp|lark|feishu|wechat|session):[^\s)\]，。,;]+/gi, "")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "").replace(/\b[0-9a-f]{20,}\b/gi, "")
    .replace(/\s+([，。,.;:])/g, "$1").replace(/\s{2,}/g, " ").trim();
}
// Every ISO date in a block's text, in the reader's form (links and code untouched).
function localDatesIn(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode())
    if (!node.parentElement.closest("pre, code") && /\d{4}-\d{2}-\d{2}/.test(node.nodeValue)) node.nodeValue = localDates(node.nodeValue);
  return root;
}
// ISO dates and timestamps (2026-10-01, 2026-10-01T10:00:00Z) as the reader's short date.
function localDates(text) {
  return String(text).replace(/\b(\d{4}-\d{2}-\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b/g, (m, day) => fmtDate(day));
}
function bestMatch(r) {
  const f = facts(r), k = known(r), parsed = parseFacts(r);
  const first = l => ((parsed.get(l) || [])[0] || {}).value || "";
  const cells = r.category === "people"
    ? [["Email", plainValue(first("Email") || f.email)], ["Phone", plainValue(first("Phone"))], ["Company", plainValue(first("Company") || f.company)], [mappedContact(r) ? "Last contact in map" : "Last contact", k.last ? fmtDate(k.last) : ""]]
    : r.category === "orgs"
      ? [["What they do", plainValue(first("What they do") || f.what)], ["Website", plainValue(first("Website") || f.domain)], ["Last contact", k.last ? fmtDate(k.last) : ""]]
      : [["Repository", plainValue(first("Repository"))], ["Status", plainValue(first("Status"))], ["Last activity", k.last ? fmtDate(k.last) : ""]];
  const open = f.open.find(o => !(privacyLevel === "public" && /[\[［](?:personal|sensitive)[\]］]/i.test(o.originalText || o.text || "")));
  const factCells = cells.filter(([, v]) => knownValue(v) && !(privacyLevel === "public" && /[\[［](?:personal|sensitive)[\]］]/i.test(v)));
  return el("section", { class: "best" }, [
    el("div", { class: "best-head" }, [el("span", { class: "lead", text: t("Best match") }), el("a", { href: href(r), text: pageName(r) }), statusPill(r)]),
    factCells.length ? el("dl", { class: "best-facts" }, factCells.flatMap(([name, v]) => [el("dt", { text: t(name) }), el("dd", { class: v ? "" : "none", text: v ? displayLine(v) : t("— not found") })])) : null,
    open && displayLine(open.text) ? el("div", { class: "best-open" }, [el("span", { class: "dir", text: t(DIRECTION_LABEL[open.dir]) }), el("span", { text: displayLine(open.text) })]) : null]);
}

// 问题与关联: the owner decides each review here, in place (POST /rem/review, reviews.decide), never by a
// command copied into a terminal (D-60). A snapshot only reads, and says so in one line.
function reviewPage() {
  const main = document.getElementById("main");
  main.textContent = "";
  main.appendChild(el("div", { class: "eyebrow" }, [el("a", { href: "#", text: t("Contents") }), el("span", { class: "sep", text: "/" }), el("span", { text: t("Review") })]));
  main.appendChild(el("h1", { text: t("Questions & connections") }));
  main.appendChild(el("p", { class: "lede", text: t("Evidence-linked suggestions, not established facts.") }));
  if (!REM.live) main.appendChild(liveReaderLine("This is a snapshot; decide these on the live page."));
  for (const row of REM.reviews || []) {
    if (row.subjects.some(path => privateTopicHidden(byPath(path) || {}))) continue;
    const box = el("section", { class: "review" });
    box.appendChild(el("div", { class: "eyebrow" }, [el("span", { class: "pill" + (row.status === "pending" ? " warn" : " quiet"), text: t(row.status) }), el("span", { text: t(row.kind || "") })]));
    box.appendChild(el("h2", { text: pageWords(row.question) }));
    box.appendChild(el("p", { class: "basis", ...(typeof inline === "function" ? { html: inline(pageWords(row.basis), row.subjects?.[0] || "") } : { text: pageWords(row.basis) }) }));
    box.appendChild(el("p", { class: "subjects" }, row.subjects.map(path => el("a", { href: "#r=" + encodeURIComponent(path), text: pageName(byPath(path)) || path }))));
    if (row.response) box.appendChild(el("p", { class: "response", text: t("{who}: {text}", { who: row.author === "owner" ? t("You") : row.author, text: pageWords(row.response) }) }));
    if (row.status === "pending" && REM.live) box.appendChild(reviewActions(row, box));
    main.appendChild(box);
  }
  if (!(REM.reviews || []).length) main.appendChild(emptyState("Nothing to review"));
}
// A link is yes or no; a question needs the owner's words (reviews.decide). 不确定 posts nothing:
// the review stays pending, so 改主意 can bring the choice back. A recorded verdict is final there.
function reviewActions(row, box) {
  const acts = el("div", { class: "review-acts" }), status = el("p", { class: "quiet-line", role: "status" });
  const answer = row.kind === "question" ? el("textarea", { rows: "2", "aria-label": t("Your answer"), placeholder: t("Your answer"), "data-keep": "review:" + row.id }) : null;
  const choices = row.kind === "question" ? [["answer", "Save answer"], [null, "Not sure"]] : [["yes", "Yes"], ["no", "No"], [null, "Not sure"]];
  const reset = () => { acts.textContent = ""; status.textContent = ""; if (answer) acts.appendChild(answer); acts.append(...choices.map(choose)); };
  const choose = ([verdict, words]) => {
    const button = el("button", { type: "button", text: t(words) });
    button.onclick = async () => {
      if (!verdict) {
        const back = el("button", { type: "button", class: "btn-quiet", text: t("Change my mind") });
        back.onclick = reset;
        acts.textContent = ""; acts.append(el("span", { text: t("Left for later; this one is still waiting for you.") }), back);
        return;
      }
      if (answer && !answer.value.trim()) { status.textContent = t("Write your answer first."); return; }
      acts.querySelectorAll("button").forEach(node => { node.disabled = true; });
      const reply = await reviewRequest({ id: row.id, verdict, ...(answer ? { response: answer.value.trim() } : {}) });
      acts.querySelectorAll("button").forEach(node => { node.disabled = false; });
      if (reply.error) { status.textContent = reply.error; return; }
      Object.assign(row, reply);
      box.querySelector(".pill").textContent = t(row.status);
      box.querySelector(".pill").className = "pill quiet";
      box.querySelector(".basis").textContent = t(row.status) + " · " + pageWords(row.basis);
      acts.replaceWith(el("p", { class: "review-done", text: verdict === "answer" ? t("Your answer is recorded: {answer}", { answer: row.response }) : t("Recorded: {verdict}", { verdict: t(words) }) }));
      status.remove();
    };
    return button;
  };
  reset();
  return el("div", {}, [acts, status]);
}
async function reviewRequest(body) {
  const response = await fetch("/rem/review", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => null);
  const words = !response ? "REM is not answering right now. Try again in a moment." : response.ok ? ""
    : { 401: "Your session expired. Reload the page.", 409: "Someone already decided this one. Reload to see it.", 404: "This one is no longer here. Reload the page.",
        400: "REM could not record that. Reload and try again." }[response.status] || "REM is not answering right now. Try again in a moment.";
  return words ? { error: t(words) } : response.json();
}

function cacheChineseInterface() {
  for (const r of REM.records) {
    if (r.translations?.zh) continue;
    const tag = (REM.your_languages || []).find(tag => /^zh-/i.test(tag) && r.translations?.[tag]);
    if (tag) r.translations.zh = r.translations[tag];
  }
}
let entranceView = "";
let detailLoad = null, detailReady = !REM?.deferred_details && !REM?.detail_url;
function needsDetails(state) {
  return state.record || state.category || state.query || state.reviews || ["activity", "changes", "graph"].includes(state.view);
}
function loadDetails() {
  if (detailReady) return Promise.resolve();
  if (detailLoad) return detailLoad;
  detailLoad = (REM.detail_url ? fetch(REM.detail_url).then(response => {
    if (!response.ok) throw Error("Could not load notebook (" + response.status + ")");
    return response.json();
  }) : new Promise(resolve => {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", resolve, { once: true });
    else resolve();
  }).then(() => JSON.parse(document.getElementById("rem-detail").textContent))).then(data => {
    const records = new Map(REM.records.map(r => [r.path, r]));
    // The Today shell can be newer after an owner action that did not rebuild the full notebook.
    const state = {};
    for (const key of ['drafts', 'threads', 'today_queue', 'ignored_senders', 'language', 'owner_language',
                       'your_languages', 'languages_from', 'as_of', 'day_plan', 'night_outcomes', 'approval_outcomes']) {
      if (key in REM) state[key] = REM[key];
    }
    for (const r of data.records) {
      const current = records.get(r.path);
      if (current) {
        Object.assign(current, r, { shown: "" });
        delete current.original;
      }
      else records.set(r.path, r);
    }
    const source_context = { ...data.source_context, ...REM.source_context };
    Object.assign(REM, data, state, { records: [...records.values()], source_context });
    KNOWN.clear(); FACTS.clear(); PARSED_FACTS.clear(); SESSION_TEXT.clear();
    if (typeof personOrg === "function" && personOrg._cache) personOrg._cache.clear();
    if (typeof sourceList === "function" && sourceList._cache) sourceList._cache.clear();
    if (typeof threads === "function" && threads._cache) threads._cache.clear();
    if (typeof listedRecords === "function") listedRecords._c = null;
    if (typeof byPath === "function") byPath._c = null;
    if (typeof threadEntries === "function") { threadEntries.cached = null; threadEntries.cachedKey = ""; }
    PEOPLE_BY_ADDRESS = null;
    detailReady = true;
  });
  return detailLoad;
}
