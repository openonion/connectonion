// ---------- agenda: a calendar of the owner's next days (#2998, asked in #2841) ----------
// Owner, 2026-11-13: «我需要快速看到我最近日历上有什么事件». The week opens on today, not on Monday: on a Friday a
// Monday-first week is mostly finished days. Month is the usual Monday-first grid. Events are what the night
// saved from his connected calendars (calendar.py; the page never calls a calendar), beside the notebook's
// own dates: promises with a due date and agenda pages. Every item is a link: an event to the calendar it
// came from, a notebook item to its page.
// Owner, 2026-11-17: «The Agenda does not look like a calendar at all… show it with that kind of very fine,
// precise calendar.» So the week is a time grid (hours down a quiet axis, events as blocks placed by their start
// and sized by their length, overlaps side by side, an all-day strip where a three-day event is one bar, a now
// line on today) and the month is a grid of weeks whose bars run across cells and rows. No calendar library:
// minutes become pixels in agBlock, agLanes and agBars, which the unit tests run in Node.
// A dated notebook item that is late is shown on today, saying its due date: the line of "earlier, still open"
// links that used to sit under the calendar was a second list beside it (#3085 review).
const AG_ZH = {
  "Week": "周", "Month": "月", "Today": "今天", "Tomorrow": "明天", "Previous week": "上一周", "Next week": "下一周",
  "Previous month": "上个月", "Next month": "下个月", "All day": "全天", "Due": "期限", "Noted": "记下", "Late": "已过期", "No title": "无标题", "Until {time}": "到 {time}",
  "{n} more": "还有 {n} 项", "{n} guests": "{n} 位参会人", "1 guest": "1 位参会人", "Nothing in these days.": "这几天没有安排。",
  "Late, due {date}": "已过期，期限 {date}", "{n} due": "{n} 个期限", "Now {time}": "现在 {time}", "In {name}": "来自 {name}", "Open in {name}": "在 {name} 中打开", "Join {service}": "加入 {service}", "Next": "接下来", "Full schedule ↓": "完整日程 ↓", "Nothing else today": "今天没有别的安排了", "Now · until {when}": "进行中 · 至 {when}", "This week": "这一周", "Organised by {name}": "组织者：{name}",
  "{n} items": "{n} 项", "1 item": "1 项",
  "clear": "晴", "partly cloudy": "晴间多云", "cloudy": "阴", "fog": "雾", "rain": "雨", "showers": "阵雨", "snow": "雪", "storm": "雷暴",
  "{n}% chance of rain": "降雨概率 {n}%", "Weather for {place} from {source}, read {when}.": "{place} 的天气来自 {source}，{when}读取。",
  "Weather for {place} could not be read on {when} ({reason}).": "{when}没能读取 {place} 的天气（{reason}）。", "The forecast is from {when}.": "显示的是 {when}读到的预报。", "nothing": "没有安排", "Close": "关闭",
  "No calendar read yet: REM reads your connected Google and Outlook calendars each night.": "还没有读过日历：REM 每晚读你已连接的 Google 和 Outlook 日历。",
  "authorization expired": "授权已过期",
  "{name} · read {when}": "{name} · {when}读取",
  "Calendars last read on {when}; no events found.": "上次读取日历是 {when}；没有找到日程。",
  "No calendar is connected, so this shows only the notebook's own dates.": "还没有连接日历，这里只显示笔记里的日期。",
  "{name} could not be read on {when} ({reason}).": "{when}没能读取 {name}（{reason}）。", "Its events are from {when}.": "显示的是 {when}读到的日程。",
  "timed out": "超时", "network error": "网络出错", "server error": "服务器出错", "throttled": "被限流", "request refused": "请求被拒",
  "permission denied": "没有权限", "provider unavailable": "暂时不可用", "not found on the server (deleted or moved)": "服务器上找不到",
  "a fault in REM": "REM 自身出错",
  "{name} has more than {n} events in these weeks; REM kept the first {n} and skipped the rest.": "{name} 这几周的日程超过 {n} 条；REM 只保存了前 {n} 条，其余跳过了。",
  "{name}: 1 own calendar read": "{name}：读了 1 个自己的日历", "{name}: {n} own calendars read": "{name}：读了 {n} 个自己的日历",
  "none left out": "没有略过的日历", "{n} left out ({why})": "{n} 个没有读（{why}）", ", ": "，", "; ": "；", ".": "。",
  "{n} shared as free/busy": "{n} 个只共享忙闲", "{n} shared read-only": "{n} 个只读共享", "{n} not ticked in Google Calendar": "{n} 个没在 Google 日历里勾选",
};
function agT(key, values = {}) {
  const words = uiLanguage === "zh" ? AG_ZH[key] : null;
  return (words || t(key)).replace(/\{(\w+)\}/g, (match, name) => values[name] ?? match);
}
const agendaState = { view: "week", start: "", month: "", sel: "" };
const AG_HOUR = 44;  // pixels to an hour: 07:00–21:00 is 616 px, one screen at 1440×900
function agDay(day, n) {
  const d = new Date(day + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
function agSpan(a, b) { return Math.round((new Date(b + "T00:00:00Z") - new Date(a + "T00:00:00Z")) / 86400000); }
function agMinutes(clock) { const [h, m] = clock.split(":").map(Number); return h * 60 + m; }
// Minutes into pixels: where a block starts and how tall it is. A short event keeps the height of its title.
function agBlock(start, end, hour = AG_HOUR, least = 20) {
  return { top: start * hour / 60, height: Math.max(least, (end - start) * hour / 60) };
}
// Events that overlap share the column side by side. Each takes the first lane free at its start; every event
// in one run of overlaps is as wide as that run's lanes allow. Back-to-back events do not overlap.
function agLanes(segments) {
  const out = [];
  let run = [], ends = [], runEnd = -1;
  const close = () => { for (const item of run) item.lanes = ends.length; run = []; ends = []; };
  for (const seg of [...segments].sort((a, b) => a.start - b.start || b.end - a.end)) {
    if (seg.start >= runEnd) close();
    const free = ends.findIndex(end => end <= seg.start), lane = free < 0 ? ends.length : free;
    ends[lane] = seg.end;
    run.push({ ...seg, lane, lanes: 1 });
    out.push(run.at(-1));
    runEnd = Math.max(runEnd, seg.end);
  }
  close();
  return out;
}
// All-day bars for a row of `days` days from `start`: one bar an entry, clipped to the row and packed into the
// first line free at its first day. `before` and `after` say it runs past the row's edge.
function agBars(entries, start, days) {
  const end = agDay(start, days - 1), free = [], bars = [];
  const shown = entries.filter(e => e.first <= end && e.last >= start).sort((a, b) => a.first.localeCompare(b.first) || b.last.localeCompare(a.last) || a.title.localeCompare(b.title));
  for (const entry of shown) {
    const from = Math.max(0, agSpan(start, entry.first)), to = Math.min(days - 1, agSpan(start, entry.last));
    const open = free.findIndex(column => column <= from), line = open < 0 ? free.length : open;
    free[line] = to + 1;
    bars.push({ entry, from, to, line, before: entry.first < start, after: entry.last > end });
  }
  return bars;
}
function agToday() { return calendarDay(REM.as_of || new Date().toISOString()); }
function agNow() { return agMinutes(agTime(REM.as_of || new Date().toISOString())); }
function agLocale() { return uiLanguage === "zh" ? "zh-CN" : "en-GB"; }
function agFormat(day, options) { return new Date(day + "T00:00:00Z").toLocaleDateString(agLocale(), { timeZone: "UTC", ...options }); }
function agDate(day) { return agFormat(day, { weekday: "short", day: "numeric", month: "short" }); }
// 24-hour in the notebook's zone, the zone calendarDay files the event under.
function agTime(iso) { return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: REM.status?.timezone || "UTC" }); }
// Both calendars end an all-day event on the day after its last. A timed one runs to the day its last
// minute falls on: ending at midnight is the day before, and a week away covers each of its days.
function agLastDay(e, first) {
  if (e.all_day) return agDay(calendarDay(e.end) || agDay(first, 1), -1);
  const start = new Date(e.start), end = new Date(e.end);
  return end > start ? calendarDay(new Date(end - 1).toISOString()) : first;
}
const AG_SOURCE = { google: "Google Calendar", microsoft: "Outlook" };
function agEvent(e, first) {
  return { kind: "event", allDay: !!e.all_day, first, last: agLastDay(e, first), start: e.start, end: e.end, title: eventTitle(e), link: e.link || "", where: e.location || "", meet: e.meet || null, organizer: e.organizer || "", notes: e.notes || "",
    people: (e.people || []).map(byPath).filter(Boolean), guests: e.guests || 0, provider: e.calendar || "",
    source: [AG_SOURCE[e.calendar], e.calendar_name].filter(Boolean).join(" · ") };
}
// What the calendar holds: each event once, with the days it covers, and the notebook's own dates as all-day
// entries. A late one sits on today and keeps its due date in words.
function agendaEntries() {
  const today = agToday(), entries = [], placed = new Set();
  // One event once, though two calendars hold it (#3406: a Tuesday event twice in 接下来): the same id, or the same
  // start instant and title, is the same event. The first keeps its place; a later copy only fills what it lacks.
  const seen = new Map();
  for (const e of REM.calendar?.events || []) {
    if (!calendarDay(e.start)) continue;
    const keys = [e.id ? "id:" + e.id : "", "at:" + Date.parse(e.start) + "|" + eventTitle(e).trim().toLowerCase().replace(/\s+/g, " ")].filter(Boolean);
    const twin = keys.map(key => seen.get(key)).find(Boolean);
    if (twin) { twin.meet ||= e.meet || null; twin.where ||= e.location || ""; twin.link ||= e.link || ""; continue; }
    const entry = agEvent(e, calendarDay(e.start));
    entries.push(entry);
    keys.forEach(key => seen.set(key, entry));
  }
  const dated = (day, late, rest) => entries.push({ allDay: true, first: late ? today : day, last: late ? today : day, due: day, late, ...rest });
  for (const row of REM.today_queue || []) {
    if (!row.due || row.closed || row.quiet) continue;
    const page = byPath(row.record), mine = row.record === REM.owner, note = stripCites(row.text);
    placed.add(row.record + "@" + row.due);
    // A promise on the owner's own page is named by what it is, not by his name.
    dated(row.due, row.due < today, { kind: "due", title: mine ? datesInProse(note) : page ? page.title : row.title, href: "#r=" + encodeURIComponent(row.record), note: mine ? "" : note });
  }
  for (const r of inCategory("agenda")) {
    const due = (r.text || "").match(/\b(?:due|deadline|by)(?:\s+(?:on|is))?\s*[:：]?\s*(\d{4}-\d{2}-\d{2})/i)?.[1];
    // Otherwise the first date the page states (its status line, in whatever language its headings are), never its Sources.
    const noted = (r.text || "").split("\n").filter(line => !/^\s*Sources?:/i.test(line)).join("\n").match(/\b\d{4}-\d{2}-\d{2}\b/)?.[0];
    const day = due || noted || calendarDay(r.last_activity || r.updated);
    if (day && !placed.has(r.path + "@" + day)) dated(day, !!due && due < today, { kind: due ? "due" : "page", title: r.title, href: href(r) });
  }
  return entries;
}
// What goes in the all-day strip as a bar: an all-day event, and a timed one that lasts a day or more and so covers
// several days, as Google and Apple Calendar draw it; a block from midnight would hide its title above the first
// screen. It keeps its times in words. A shorter one past midnight (22:00 to 01:00) stays a block on both days.
function agOnStrip(e) { return e.allDay || (e.kind === "event" && e.first !== e.last && new Date(e.end) - new Date(e.start) >= 864e5); }
// A timed event's part of one day, in minutes of that day: its start on the first, midnight to its end on the last.
function agSegments(entries, day) {
  return entries.filter(e => !agOnStrip(e) && e.first <= day && e.last >= day).map(entry => ({ entry, day,
    start: entry.first === day ? agMinutes(agTime(entry.start)) : 0, end: entry.last === day ? agMinutes(agTime(entry.end)) || 1440 : 1440 }))
    .sort((a, b) => a.start - b.start || a.entry.title.localeCompare(b.entry.title));
}
function agClock(minutes) { return String(Math.floor(minutes / 60) % 24).padStart(2, "0") + ":" + String(minutes % 60).padStart(2, "0"); }
// A day's part of an event, in words: its hours; for one that runs over several days its start time on the
// first, "All day" between, "Until 17:00" on the last.
function agHours({ entry, day, start, end }) {
  const before = entry.first < day, after = entry.last > day;
  if (before && after) return agT("All day");
  if (before) return agT("Until {time}", { time: agClock(end) });
  return after ? agClock(start) : agClock(start) + " – " + agClock(end);
}
// When, in words: "All day, Mon 5 – Wed 7 Oct", "Fri 2 Oct, 09:30 – 10:00", "Late, due 25 Sep".
function agWhen(e) {
  if (e.kind !== "event") return e.kind === "page" ? agT("Noted") : e.late ? agT("Late, due {date}", { date: calendarDate(e.due) }) : agT("Due");
  if (e.allDay) return agT("All day") + agT(", ") + (e.first === e.last ? agDate(e.first) : agDate(e.first) + " – " + agDate(e.last));
  if (e.first === e.last) return agDate(e.first) + agT(", ") + agTime(e.start) + " – " + agTime(e.end);
  return agDate(e.first) + " " + agTime(e.start) + " – " + agDate(e.last) + " " + agTime(e.end);
}
function agSaid(e) { return [e.title, agWhen(e), e.where, e.source].filter(Boolean).join(" · "); }
function agGuests(e) {
  if (e.people.length) return el("p", { class: "cal-who" }, e.people.flatMap((r, i) => [i ? ", " : null, el("a", { href: href(r), text: r.title })]));
  return e.guests ? el("p", { class: "cal-who", text: e.guests === 1 ? agT("1 guest") : agT("{n} guests", { n: e.guests }) }) : null;
}
// An event's detail: beside the event on a desk, a sheet from the foot on a phone. Which calendar it is from is
// said in words here and on hover; the edge of a block is only the second cue.
function agDetail(e, anchor) {
  document.querySelector(".cal-detail")?.remove();
  const phone = innerWidth <= 640, close = el("button", { type: "button", class: "ibtn", "aria-label": agT("Close") }, [icon("x")]);
  const dialog = el("dialog", { class: "cal-detail" + (phone ? " n3-sheet" : ""), "aria-label": e.title }, [
    el("div", { class: "sheet-head" }, [el("h2", { text: e.title }), close]),
    el("p", { class: "cal-when", text: agWhen(e) }), agWeather(e.first) && e.first === e.last ? el("p", { class: "cal-wx-line", text: agWeatherSaid(agWeather(e.first)) }) : null,
    // The event's own details first (#3135): how to join, who called it, where, who comes, what it is about.
    e.meet ? el("a", { class: "btn-act cal-join", href: e.meet.url, target: "_blank", rel: "noopener", text: agT("Join {service}", { service: e.meet.service }) }) : null,
    e.organizer ? el("p", { class: "cal-org", text: agT("Organised by {name}", { name: e.organizer }) }) : null,
    e.where && e.where !== e.meet?.url ? el("p", { class: "cal-where", text: e.where }) : null, agGuests(e),
    e.notes ? el("p", { class: "cal-notes", text: e.notes }) : null,
    e.source ? el("p", { class: "cal-source", text: agT("In {name}", { name: e.source }) }) : null,
    e.link ? el("a", { class: "cal-open", href: e.link, target: "_blank", rel: "noopener", text: agT("Open in {name}", { name: AG_SOURCE[e.provider] || e.source }) + " ↗" }) : null]);
  close.onclick = () => dialog.close();
  dialog.addEventListener("close", () => dialog.remove());
  dialog.addEventListener("keydown", event => { if (event.key === "Escape") dialog.close(); });
  dialog.addEventListener("click", event => { if (event.target.closest("a[href^='#']")) dialog.close(); });
  document.body.appendChild(dialog);
  if (phone) return dialog.showModal();
  dialog.show();
  agPlaceBeside(dialog, anchor.getBoundingClientRect());
  close.focus();
}
// Beside the event when there is room on its right or left; otherwise (a wide block, as in Today's one-day timeline)
// under it, or over it, aligned to its start. Never over the rail and never over the event itself (#3188: it opened
// at x=8, over the rail and the event's own title).
function agPlaceBeside(dialog, at) {
  const width = dialog.offsetWidth, height = dialog.offsetHeight, gap = 8;
  const minX = Math.max(gap, document.getElementById("main")?.getBoundingClientRect().left || gap), maxX = innerWidth - gap - width;
  const clampX = x => Math.max(minX, Math.min(x, maxX)), clampY = y => Math.max(gap, Math.min(y, innerHeight - gap - height));
  const spots = [[at.right + gap, clampY(at.top)], [at.left - gap - width, clampY(at.top)],
    [clampX(at.left), at.bottom + gap], [clampX(at.left), at.top - gap - height]];
  const clear = ([x, y]) => x >= minX && x <= maxX && y >= gap && y + height <= innerHeight - gap
    && (x >= at.right || x + width <= at.left || y >= at.bottom || y + height <= at.top);
  const [left, top] = spots.find(clear) || [clampX(at.left), clampY(at.bottom + gap)];
  dialog.style.left = left + "px";
  dialog.style.top = top + "px";
}
// An entry as something to press: an event opens its detail, a notebook date goes to its page.
function agPress(e, cls, children) {
  if (e.kind !== "event") return el("a", { class: cls + " cal-" + e.kind + (e.late ? " late" : ""), href: e.href, title: agSaid(e) }, children);
  const button = el("button", { type: "button", class: cls + " cal-event cal-" + (e.provider || "other"), title: agSaid(e) }, children);
  button.onclick = () => agDetail(e, button);
  return button;
}
function agDayClass(day, today) {
  const weekday = new Date(day + "T00:00:00Z").getUTCDay();
  return (day === today ? " today" : "") + (weekday === 0 || weekday === 6 ? " weekend" : "") + (day < today ? " past" : "") + (day === agendaState.sel ? " sel" : "");
}
// A column's head: the weekday and the date; today is marked and says so.
function agHead(day, today) {
  return el("header", { class: "cal-head" + agDayClass(day, today), "data-day": day }, [day === today ? el("span", { class: "cal-today-word", text: agT("Today") }) : null,
    el("span", { class: "cal-wd", text: agFormat(day, { weekday: "short" }) }), el("span", { class: "cal-num", text: String(Number(day.slice(8))) }), agWeatherMark(day)]);
}
function agBar(bar, column) {
  const e = bar.entry, word = e.kind === "event" ? "" : agWhen(e) + " · ";
  const node = agPress(e, "cal-bar" + (bar.before ? " before" : "") + (bar.after ? " after" : ""), [el("span", { text: word + e.title })]);
  node.style.gridColumn = (bar.from + column) + " / " + (bar.to + column + 1);
  node.style.gridRow = String(bar.line + 1);
  return node;
}
// The lane is the calendar's: all-day and multi-day events as bars. The notebook's own dates (deadlines, notes) are
// Today's cards; here a day only says how many it has, in words, and that count opens them (#3152, #3188).
function agAllDay(entries, days, today) {
  const bars = agBars(entries.filter(e => e.kind === "event" && agOnStrip(e)), days[0], days.length);
  const dated = entries.filter(e => e.kind !== "event");
  const counts = days.map((day, i) => agDueCount(dated.filter(e => e.first <= day && e.last >= day), i)).filter(Boolean);
  const lines = Math.max(1, ...bars.map(bar => bar.line + 1)) + (counts.length ? 1 : 0);
  counts.forEach(node => { node.style.gridRow = String(lines); });
  return el("div", { class: "cal-allday" }, [el("span", { class: "cal-axis-word", text: bars.length || counts.length ? agT("All day") : "" }),
    ...days.map((day, i) => el("span", { class: "cal-allday-col" + agDayClass(day, today), style: `grid-column:${i + 2};grid-row:1 / span ${lines}` })),
    ...bars.map(bar => agBar(bar, 2)), ...counts]);
}
function agDueCount(items, i) {
  if (!items.length) return null;
  const late = items.some(e => e.late), one = items.length === 1;
  const node = el("a", { class: "cal-due-count" + (late ? " late" : ""), href: one ? items[0].href : "#",
    title: items.map(e => e.title + " · " + agWhen(e)).join("\n"),
    text: agT("{n} due", { n: items.length }) });  // short enough for a phone's day column, never cut
  node.style.gridColumn = String(i + 2);
  if (!one) node.onclick = event => { event.preventDefault(); location.hash = ""; requestAnimationFrame(() => document.querySelector("#main .today-brief")?.scrollIntoView({ block: "start" })); };
  return node;
}
function agEventBlock({ entry, day, start, end, lane, lanes }) {
  const { top, height } = agBlock(start, end), cls = "cal-ev" + (height < 34 ? " short" : height >= 56 ? " tall" : "");
  const node = agPress(entry, cls, [el("span", { class: "cal-ev-title", text: entry.title }), el("span", { class: "cal-ev-time", text: agHours({ entry, day, start, end }) }),
    entry.where ? el("span", { class: "cal-ev-where", text: entry.where }) : null]);
  Object.assign(node.style, { top: top + "px", height: height - 1 + "px", left: lane / lanes * 100 + "%", width: `calc(${100 / lanes}% - 3px)` });
  return node;
}
function agDayColumn(entries, day, today) {
  // A short event is drawn taller than its minutes, so what follows within that height stands beside it.
  const least = 20 * 60 / AG_HOUR, placed = agLanes(agSegments(entries, day).map(seg => ({ ...seg, end: Math.max(seg.end, seg.start + least), till: seg.end })));
  return el("div", { class: "cal-day" + agDayClass(day, today), "data-day": day }, [...placed.map(seg => agEventBlock({ ...seg, end: seg.till })),
    day === today ? el("div", { class: "cal-now", style: `top:${agNow() * AG_HOUR / 60}px`, "aria-hidden": "true" }) : null]);
}
// The hours, a quiet axis; on a week that holds today, where now is, in words.
function agAxis(now) {
  const near = hour => now != null && Math.abs(hour * 60 - now) < 24;
  return el("div", { class: "cal-axis" }, [...Array.from({ length: 23 }, (_, i) => near(i + 1) ? null : el("span", { class: "cal-hour", style: `top:${(i + 1) * AG_HOUR}px`, text: agClock((i + 1) * 60) })),
    now == null ? null : el("span", { class: "cal-hour cal-now-word", style: `top:${now * AG_HOUR / 60}px`, text: agT("Now {time}", { time: agClock(now) }) })]);
}
function agRules() {
  return Array.from({ length: 47 }, (_, i) => el("i", { class: "cal-rule" + (i % 2 ? "" : " half"), style: `top:${(i + 1) * AG_HOUR / 2}px`, "aria-hidden": "true" }));
}
function agendaWeek(entries, start, length = 7) {
  const today = agToday(), days = Array.from({ length }, (_, i) => agDay(start, i)), now = days.includes(today) ? agNow() : null;
  const grid = el("div", { class: "cal-grid", style: `height:${24 * AG_HOUR}px` }, [agAxis(now), ...agRules(), ...days.map(day => agDayColumn(entries, day, today))]);
  return el("div", { class: "cal-week" }, [el("div", { class: "cal-heads" }, [el("span", {}), ...days.map(day => agHead(day, today))]),
    agAllDay(entries, days, today), el("div", { class: "cal-scroll", tabindex: "0", "data-first": String(agFirstMinute(entries, days, now)) }, [grid])]);
}
// Where the grid opens: 07:00, so working hours to 21:00 are on screen; earlier when the week's first event or
// now is earlier, later only when now is past what would be shown.
// The grid opens at the earlier of the first event and now, an hour above it; an empty day opens at 07:00 or now.
// (#3188: at 23:00 the old rule jumped to now - 10 h, 13:00, with the morning's events out of view.)
function agFirstMinute(entries, days, now) {
  const starts = days.flatMap(day => agSegments(entries, day).filter(seg => seg.entry.first === day).map(seg => seg.start));
  if (!starts.length && now == null) return 7 * 60;  // an empty week opens on working hours
  const first = Math.min(...starts, now ?? Infinity);
  return Math.max(0, Math.floor((first - 60) / 60) * 60);
}
// The grid ends at the window's foot and scrolls inside it, so the heads and the all-day strip stay in view.
function agSizeWeek() {
  const scroll = document.querySelector(".agenda .cal-scroll");
  if (!scroll || !scroll.offsetParent || scroll.closest(".today-cal")) return;  // Today's calendar keeps its own height
  const height = Math.max(240, innerHeight - scroll.getBoundingClientRect().top - scrollY - 16);
  scroll.style.height = height + "px";
  // Whatever sits under the calendar (the page's own foot) comes off the grid, so the page itself has nothing to scroll.
  scroll.style.height = Math.max(240, height - Math.max(0, document.documentElement.scrollHeight - innerHeight)) + "px";
  scroll.scrollTop = Number(scroll.dataset.first) * AG_HOUR / 60 - 24;
}
function agMonthFirst() { return (agendaState.month || agToday().slice(0, 7)) + "-01"; }
function agMonthStep(first, n) {
  const d = new Date(first + "T00:00:00Z");
  d.setUTCMonth(d.getUTCMonth() + n);
  return d.toISOString().slice(0, 7);
}
function agOnDay(entries, day) { return entries.filter(e => e.first <= day && e.last >= day); }
function agCount(n) { return n === 1 ? agT("1 item") : agT("{n} items", { n }); }
// One week of the month: seven cells, the all-day bars running across them, then each day's timed events in the
// lines the bars leave, three lines in all; what does not fit is counted in words, and that count opens the day.
function agMonthWeek(entries, start, month, today) {
  const days = Array.from({ length: 7 }, (_, i) => agDay(start, i)), bars = agBars(entries.filter(agOnStrip), start, 7), parts = [];
  for (const bar of bars.filter(bar => bar.line < 3)) { const node = agBar(bar, 1); node.style.gridRow = String(bar.line + 2); parts.push(node); }
  days.forEach((day, i) => {
    const taken = new Set(bars.filter(bar => bar.from <= i && bar.to >= i).map(bar => bar.line)), timed = agSegments(entries, day);
    const free = [0, 1, 2].filter(line => !taken.has(line)), all = agOnDay(entries, day).length, shown = [...taken].filter(line => line < 3).length + Math.min(free.length, timed.length);
    const cell = el("div", { class: "cal-cell" + (day.slice(0, 7) !== month ? " out" : "") + agDayClass(day, today), "data-day": day, style: `grid-column:${i + 1}`, "aria-label": agDate(day) + agT(", ") + (all ? agCount(all) : agT("nothing")) }, [
      el("span", { class: "cal-num", text: String(Number(day.slice(8))) }), day === today ? el("span", { class: "cal-today-word", text: agT("Today") }) : null,
      agWeatherMark(day), all ? el("span", { class: "cal-count", text: String(all) }) : null]);
    cell.onclick = () => { agendaState.sel = day; agendaView(); };
    parts.push(cell, ...timed.slice(0, free.length).map((seg, n) => agMonthLine(seg, i, free[n])));
    if (all > shown) parts.push(agMore(day, all - shown, i));
  });
  return el("div", { class: "cal-mweek" }, parts);
}
function agMonthLine(seg, column, line) {
  const node = agPress(seg.entry, "cal-line", [el("span", { class: "cal-line-time", text: agHours(seg).split(" – ")[0] }), el("span", { class: "cal-line-title", text: seg.entry.title })]);
  Object.assign(node.style, { gridColumn: String(column + 1), gridRow: String(line + 2) });
  return node;
}
function agMore(day, n, column) {
  const more = el("button", { type: "button", class: "cal-more", style: `grid-column:${column + 1}`, text: "+" + agT("{n} more", { n }) });
  more.onclick = () => { Object.assign(agendaState, { view: "week", start: day, sel: day }); agendaView(); };
  return more;
}
function agendaMonth(entries, first) {
  const today = agToday(), lead = (new Date(first + "T00:00:00Z").getUTCDay() + 6) % 7, month = first.slice(0, 7);
  const length = agSpan(first, agMonthStep(first, 1) + "-01"), start = agDay(first, -lead), weeks = Math.ceil((lead + length) / 7);
  const sel = agendaState.sel && agendaState.sel.slice(0, 7) === month ? agendaState.sel : today.slice(0, 7) === month ? today : first;
  return el("div", { class: "cal-month" }, [el("div", { class: "cal-wds" }, Array.from({ length: 7 }, (_, i) => el("span", { class: "cal-wd" + (i > 4 ? " weekend" : ""), text: agFormat(agDay(start, i), { weekday: "short" }) }))),
    ...Array.from({ length: weeks }, (_, i) => agMonthWeek(entries, agDay(start, 7 * i), month, today)),
    el("div", { class: "cal-daylist agenda-days" }, [agDaySection(entries, sel, today, sel)])]);
}
// One day as a short list in time order, its all-day bars first. A bar that covers several days is listed once,
// on the first of them shown, with its whole range in words.
function agRow(e, when) {
  return agPress(e, "cal-row" + (agOnStrip(e) ? " cal-row-bar" : ""), [el("span", { class: "cal-row-time", text: when }), el("span", { class: "cal-row-title", text: e.title }),
    e.where ? el("span", { class: "cal-row-where", text: e.where }) : null]);
}
// The calendar's events only; the notebook's deadlines that day fold into one "N 个期限" line that opens them in
// place, the phone's form of the desk's count in the all-day lane (#3188: red late chips between real events).
function agDayRows(entries, day, from) {
  const events = entries.filter(e => e.kind === "event"), dated = entries.filter(e => e.kind !== "event" && e.first <= day && e.last >= day);
  const bars = events.filter(e => agOnStrip(e) && e.first <= day && e.last >= day && (e.first === day || day === from));
  const short = e => e.first === e.last ? agT("All day") : agWhen(e);
  return [...bars.map(e => agRow(e, short(e))), ...agSegments(events, day).map(seg => agRow(seg.entry, agHours(seg))), agDueLine(dated)].filter(Boolean);
}
function agDueLine(items) {
  if (!items.length) return null;
  const list = el("div", { class: "cal-due-list", hidden: "" }, items.map(e => agRow(e, agWhen(e))));
  const line = el("button", { type: "button", class: "cal-due-line" + (items.some(e => e.late) ? " late" : ""), "aria-expanded": "false",
    title: items.map(e => e.title + " · " + agWhen(e)).join("\n") }, [el("span", { text: agT("{n} due", { n: items.length }) })]);
  line.onclick = () => { const open = list.hidden; list.hidden = !open; line.setAttribute("aria-expanded", String(open)); };
  return el("div", { class: "cal-due-day" }, [line, list]);
}
function agDaySection(entries, day, today, from) {
  const rows = agDayRows(entries, day, from), name = day === today ? agT("Today") : day === agDay(today, 1) ? agT("Tomorrow") : "";
  return el("section", { class: "ag-day" + (day === today ? " today" : ""), id: "cal-day-" + day }, [
    el("h2", { class: "ag-dayhead" }, [name ? name + " · " + agDate(day) : agDate(day), agWeatherWords(day)]), ...rows]);
}
// A phone's week: the seven dates as a strip to jump by, then three weeks day by day. A day with nothing has no
// section and its date in the strip is quiet.
function agendaPhone(entries, start) {
  const today = agToday(), days = Array.from({ length: 21 }, (_, i) => agDay(start, i)), full = days.filter(day => day === today || agOnDay(entries, day).length);
  const strip = el("div", { class: "cal-strip" }, days.slice(0, 7).map(day => {
    const n = agOnDay(entries, day).length, jump = el("button", { type: "button", class: "cal-jump" + agDayClass(day, today), "aria-label": agDate(day) + agT(", ") + (n ? agCount(n) : agT("nothing")), ...(full.includes(day) ? {} : { disabled: "" }) }, [
      el("span", { class: "cal-wd", text: agFormat(day, { weekday: "narrow" }) }), el("span", { class: "cal-num", text: String(Number(day.slice(8))) }), agWeatherMark(day, true)]);
    jump.onclick = () => document.getElementById("cal-day-" + day)?.scrollIntoView({ block: "start" });
    return jump;
  }));
  return el("div", { class: "cal-phone" }, [strip, el("div", { class: "agenda-days" }, full.map(day => agDaySection(entries, day, today, start)))]);
}
// Only his own calendars are read (#3087): the page says how many, and how many were left out and why, in words.
function agendaCalendars(c) {
  const kinds = { freeBusyReader: "{n} shared as free/busy", reader: "{n} shared read-only", unticked: "{n} not ticked in Google Calendar" };
  const out = Object.entries(c.left_out || {}), total = out.reduce((sum, [, n]) => sum + n, 0);
  const why = out.map(([kind, n]) => agT(kinds[kind] || kinds.reader, { n })).join(agT(", "));
  return agT(c.calendars === 1 ? "{name}: 1 own calendar read" : "{name}: {n} own calendars read", { name: c.name, n: c.calendars })
    + agT("; ") + (total ? agT("{n} left out ({why})", { n: total, why }) : agT("none left out")) + agT(".");
}
// Small, under the header, on a desk and on a phone (#3085 review: under the week it was below a long scroll).
// A file saved before #3087 has no counts; the sentence appears after the next read.
function agendaRead() {
  const counted = (REM.calendar?.read || []).filter(c => c.calendars != null), weather = agendaWeather();
  return counted.length || weather ? el("p", { class: "agenda-note agenda-read" }, [counted.map(agendaCalendars).join(" "),
    weather ? el("span", { class: "agenda-weather", text: (counted.length ? " " : "") + weather }) : null]) : null;
}
function agendaNote() {
  if (REM.shared) return null;
  if (!REM.calendar) return el("p", { class: "agenda-note", text: agT("No calendar read yet: REM reads your connected Google and Outlook calendars each night.") });
  const { read = [], errors = [] } = REM.calendar;
  // A night ran and no calendar is connected: say so, or the empty week reads as "nothing on".
  if (!read.length && !errors.length) return el("p", { class: "agenda-note", text: agT("No calendar is connected, so this shows only the notebook's own dates.") });
  // When, from each calendar's own times: a failure is not always last night's, nor its events tonight's.
  const lines = [...errors.map(e => agT("{name} could not be read on {when} ({reason}).", {
    name: e.name, when: fmtTime(e.at), reason: agT(e.reason) + (e.error ? " · " + e.error : "") })
    + (e.read_at ? " " + agT("Its events are from {when}.", { when: fmtTime(e.read_at) }) : "")),
    // The night stops at a cap so a runaway series cannot fill the file; what it skipped is said, not hidden.
    ...read.filter(c => c.capped).map(c => agT("{name} has more than {n} events in these weeks; REM kept the first {n} and skipped the rest.", { name: c.name, n: c.capped }))];
  if (read.length && !REM.calendar.events?.length) {
    const latest = read.map(c => c.at).sort().at(-1);
    lines.push(agT("Calendars last read on {when}; no events found.", { when: fmtTime(latest) }));
  }
  return lines.length ? el("p", { class: "agenda-note", text: lines.join(" ") }) : null;
}
function agStep(n) {
  if (agendaState.view === "month") agendaState.month = agMonthStep(agMonthFirst(), n);
  else agendaState.start = agDay(agendaState.start || agToday(), 7 * n);
  agendaState.sel = "";
  agendaView();
}
function agendaBar(range) {
  const week = agendaState.view === "week";
  const button = (text, attrs, act) => { const b = el("button", { type: "button", ...attrs }, [text]); b.onclick = act; return b; };
  const views = el("div", { class: "seg ag-views", role: "group" }, [["week", "Week"], ["month", "Month"]].map(([view, name]) =>
    button(agT(name), { "aria-pressed": String(agendaState.view === view) }, () => { Object.assign(agendaState, { view, start: "", month: "", sel: "" }); agendaView(); })));
  const read = REM.calendar?.read?.length ? el("span", { class: "ag-source", text: REM.calendar.read.map(c =>
    agT("{name} · read {when}", { name: c.name, when: fmtTime(c.at) })).join(" · ") }) : null;
  return el("div", { class: "agenda-bar" }, [
    button("‹", { class: "ag-step", "aria-label": agT(week ? "Previous week" : "Previous month") }, () => agStep(-1)),
    button(agT("Today"), { class: "ag-today" }, () => { Object.assign(agendaState, { start: "", month: "", sel: "" }); agendaView(); }),
    button("›", { class: "ag-step", "aria-label": agT(week ? "Next week" : "Next month") }, () => agStep(1)),
    el("span", { class: "ag-range", text: range }), read, views]);
}
// Arrows move the chosen day (left and right a day, up and down a week) and the view follows it; T is today;
// Enter opens the chosen day's first event.
function agKey(event) {
  if (!document.querySelector(".agenda") || (document.querySelector(".today-cal") && !document.activeElement?.closest(".agenda")) || document.querySelector("dialog[open]") || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) || event.metaKey || event.ctrlKey || event.altKey) return;
  const move = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key];
  if (event.key === "Enter" && !event.target.closest("button, a")) {
    event.preventDefault();  // or the same Enter presses the detail's Close, which takes the focus
    return void document.querySelector(`.agenda .cal-day[data-day="${agendaState.sel || agToday()}"] .cal-event`)?.click();
  }
  if (!move && event.key.toLowerCase() !== "t") return;
  event.preventDefault();
  const sel = move ? agDay(agendaState.sel || agToday(), move) : agToday(), start = agendaState.start || agToday();
  Object.assign(agendaState, { sel, month: sel.slice(0, 7), start: sel < start || sel > agDay(start, 6) ? (move ? agDay(start, 7 * Math.sign(move)) : "") : agendaState.start });
  agendaView();
}
function agListen() {
  if (agendaState.listening || typeof addEventListener !== "function") return;  // a test harness has no window
  agendaState.listening = true;
  addEventListener("keydown", agKey);
  addEventListener("resize", agSizeWeek);
  addEventListener("mousedown", event => { if (!event.target.closest(".cal-detail, .cal-event")) document.querySelector(".cal-detail:not(.n3-sheet)")?.close(); });
}
// The week and month grids live in Today's calendar (#3152); every control that redrew the old Agenda page now
// redraws Today with the calendar open where it was.
function agendaView() {
  todayCal.expanded = true;
  const at = document.getElementById("today-calendar")?.getBoundingClientRect().top, focused = !!document.activeElement?.closest(".agenda");
  overview();
  const now = document.getElementById("today-calendar");
  if (now && at != null) scrollBy(0, now.getBoundingClientRect().top - at);
  // The keyboard stays in the calendar it was moving through (agKey answers only there on Today).
  if (focused) now?.querySelector(".agenda .cal-scroll")?.focus({ preventScroll: true });
}
function agendaBlock(entries) {
  const month = agendaState.view === "month", start = agendaState.start || agToday(), first = agMonthFirst();
  const range = month ? agFormat(first, { month: "long", year: "numeric" })
    : agFormat(start, { day: "numeric", month: "short" }) + " – " + agFormat(agDay(start, 6), { day: "numeric", month: "short", year: "numeric" });
  return el("div", { class: "agenda agenda-" + agendaState.view, "aria-label": label("agenda") }, [agendaBar(range), agendaRead(),
    ...(month ? [agendaMonth(entries, first)] : [agendaWeek(entries, start), agendaPhone(entries, start)])]);
}
// ---------- The calendar on Today (#3152) ----------
// Collapsed: the coming seven days as a strip (weather, how much is on, bars for what spans days) over the chosen
// day's timeline, with the day plan's proposals as dashed "suggested" blocks. Expanded: the week or month grid.
const todayCal = { day: "", expanded: false };
Object.assign(UI.zh, { "Schedule": "日程", "Show the week": "展开一周", "This month": "本月", "Back to the day": "收起",
  "Suggested": "建议", "Dismiss this suggestion": "不要这个建议", "Go to its card": "去这张卡片" });
function todayCalendar() {
  if (REM.shared) return null;
  const entries = agendaEntries();
  agListen();
  const button = (text, act, attrs = {}) => { const b = el("button", { type: "button", class: "chip ghost tcal-toggle", ...attrs, text }); b.onclick = act; return b; };
  const open = view => { Object.assign(agendaState, { view, start: "", month: "", sel: "" }); agendaView(); };
  const controls = todayCal.expanded
    ? [button(t("Back to the day"), () => { todayCal.expanded = false; overview(); })]
    : [button(t("Show the week"), () => open("week")), button(t("This month"), () => open("month"))];
  return el("section", { class: "today-cal" + (todayCal.expanded ? " expanded" : ""), id: "today-calendar", "aria-label": t("Schedule") }, [
    el("div", { class: "tcal-head" }, [el("h2", { text: t("Schedule") }), el("div", { class: "tcal-controls" }, controls)]),
    agendaNote(), ...(todayCal.expanded ? [agendaBlock(entries)] : [el("div", { class: "tcal-frame" }, [tcalWeek(entries), tcalDay(entries)])])]);
}
function tcalWeek(entries) {
  const today = agToday(), sel = todayCal.day || today, days = Array.from({ length: 7 }, (_, i) => agDay(today, i));
  const strip = el("div", { class: "tcal-strip" }, [el("span", {}), ...days.map(day => {
    const n = agOnDay(entries, day).length, jump = el("button", { type: "button", class: "cal-jump" + agDayClass(day, today) + (day === sel ? " on" : ""),
      "aria-pressed": String(day === sel), "aria-label": agDate(day) + agT(", ") + (n ? agCount(n) : agT("nothing")), "data-day": day }, [
      el("span", { class: "cal-wd", text: day === today ? agT("Today") : agFormat(day, { weekday: "short" }) }), el("span", { class: "cal-num", text: String(Number(day.slice(8))) }),
      el("span", { class: "tcal-dots", "aria-hidden": "true", text: "•".repeat(Math.min(3, n)) }), agWeatherMark(day, true)]);
    jump.onclick = () => { todayCal.day = day; overview(); document.getElementById("today-calendar")?.scrollIntoView({ block: "nearest" }); };
    return jump;
  })]);
  return el("div", { class: "tcal-week" }, [strip, agAllDay(entries, days, today)]);
}
function tcalUnscheduled(day) {
  const plan = REM.day_plan?.days?.find(d => d.date === day);
  const gone = tcalDismissed();
  return (plan?.items || []).filter(item => item.kind === "proposal" && !item.time && dayPlanVisible(item) && !gone.includes(item.key || item.record + "@unscheduled"));
}
function tcalDay(entries) {
  const day = todayCal.day || agToday(), node = el("div", { class: "tcal-day" }, [agendaWeek(entries, day, 1)]);
  const unscheduled = tcalUnscheduled(day);
  if (unscheduled.length) {
    const strip = el("div", { class: "tcal-proposals", style: "display:flex;flex-wrap:wrap;gap:6px;margin:0 0 8px" },
      unscheduled.map(item => {
        const words = proposalWords(item), chip = el("button", { type: "button", class: "chip ghost", text: t("Suggested") + " · " + words });
        chip.onclick = () => { dealCard(item.record); document.querySelector("#main .today-brief")?.scrollIntoView({ block: "start", behavior: "smooth" }); };
        return chip;
      }));
    node.prepend(strip);
  }
  const column = node.querySelector(".cal-day");
  const timed = tcalSuggestions(day);
  for (const item of timed) column.appendChild(tcalSuggestion(item));
  const scroll = node.querySelector(".cal-scroll");
  if (scroll && timed.length) {
    const earliest = Math.min(Number(scroll.dataset.first || 1440), ...timed.map(item => agMinutes(item.time)));
    scroll.dataset.first = String(earliest);
  }
  return node;
}
// The day plan's proposals with a time (day_plan.py), minus what was closed, answered or dismissed.
function tcalSuggestions(day) {
  const plan = REM.day_plan?.days?.find(d => d.date === day);
  const gone = tcalDismissed();
  return (plan?.items || []).filter(item => item.kind === "proposal" && item.time && dayPlanVisible(item) && !gone.includes(item.key || item.record + "@" + item.time));
}
function tcalDismissed() {
  try { return JSON.parse(localStorage.getItem("co-rem-dismissed-suggestions:" + calendarDay(REM.as_of)) || "[]"); } catch { return []; }
}
function tcalSuggestion(item) {
  const start = agMinutes(item.time), end = agMinutes(item.end_time || item.time) || start + 30, { top, height } = agBlock(start, Math.max(end, start + 20));
  const words = proposalWords(item), key = item.key || item.record + "@" + item.time;
  const go = el("button", { type: "button", class: "cal-ev cal-suggest", title: t("Suggested") + " · " + words + " — " + t("Go to its card") }, [
    el("span", { class: "cal-ev-title", text: t("Suggested") + " · " + words }), el("span", { class: "cal-ev-time", text: item.time + "–" + (item.end_time || "") })]);
  go.onclick = () => { dealCard(item.record); document.querySelector("#main .today-brief")?.scrollIntoView({ block: "start", behavior: "smooth" }); };
  const drop = el("button", { type: "button", class: "tcal-drop", "aria-label": t("Dismiss this suggestion"), title: t("Dismiss this suggestion"), text: "×" });
  drop.onclick = () => {
    try { localStorage.setItem("co-rem-dismissed-suggestions:" + calendarDay(REM.as_of), JSON.stringify([...tcalDismissed(), key])); } catch { /* the block still leaves this view */ }
    box.remove();
  };
  const box = el("div", { class: "tcal-suggest-box", style: `top:${top}px;height:${height - 1}px` }, [go, drop]);
  return box;
}
// Today's grids scroll inside a fixed height, opened at the first hour that matters (agFirstMinute).
function tcalScroll() {
  for (const scroll of document.querySelectorAll(".today-cal .cal-scroll")) scroll.scrollTop = Number(scroll.dataset.first) * AG_HOUR / 60 - 24;
}
// The forecast the night saved for these days (weather.py; the page never asks anyone). A day says its weather
// in words on hover and in its list; the small picture and "22° / 14°" are the second cue. A day with no
// forecast shows nothing.
const AG_CLOUD = "M7 13h10a3.5 3.5 0 0 0 .4-7A4.8 4.8 0 0 0 8 6.5 3.5 3.5 0 0 0 7 13Z";
const AG_WX = {
  clear: ["M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8Z", "M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"],
  "partly cloudy": ["M8 3v1.5M2.5 8.5H4M4 4.5l1.1 1.1M10.6 6.3A3.5 3.5 0 0 0 5.2 10.6", "M9 19h8a3.5 3.5 0 0 0 .4-7A4.8 4.8 0 0 0 10 12.5 3.5 3.5 0 0 0 9 19Z"],
  cloudy: ["M7 18h10a4 4 0 0 0 .5-8A5.5 5.5 0 0 0 7 9.5 4.3 4.3 0 0 0 7 18Z"],
  fog: [AG_CLOUD, "M5 17h14M7 20.5h10"], rain: [AG_CLOUD, "M8 16.5v3.5M12 16.5v3.5M16 16.5v3.5"],
  showers: [AG_CLOUD, "M9 16.5l-.8 1.6M12.5 19l-.8 1.6M15.5 16.5l-.8 1.6"], snow: [AG_CLOUD, "M8 17v.01M12 19.5v.01M16 17v.01M10 21v.01M14 21v.01"],
  storm: [AG_CLOUD, "M12.5 15l-2.5 3.5h3L11 22"],
};
function agWeather(day) { return (REM.weather?.days || []).find(w => w.date === day) || null; }
function agDegrees(w, brief) { return brief ? w.high + "°" : w.high + "° / " + w.low + "°"; }
function agWeatherSaid(w) {
  const word = agT(w.condition), rain = w.rain == null ? "" : agT("{n}% chance of rain", { n: w.rain });
  return [word[0].toUpperCase() + word.slice(1), rain, agDegrees(w)].filter(Boolean).join(agT(", "));
}
function agWeatherMark(day, brief = false) {
  const w = agWeather(day);
  if (!w) return null;
  const picture = svgEl("svg", { class: "cal-wx-ic", viewBox: "0 0 24 24", "aria-hidden": "true" }, (AG_WX[w.condition] || AG_WX.cloudy).map(d => svgEl("path", { d })));
  return el("span", { class: "cal-wx", title: agWeatherSaid(w), "aria-label": agWeatherSaid(w) }, [brief ? null : picture, agDegrees(w, brief)]);
}
function agWeatherWords(day) {
  const w = agWeather(day);
  return w ? el("span", { class: "cal-wx-words", text: agWeatherSaid(w) }) : null;
}
// Where the forecast is for and who it is from, in the small line under the header; a failed read says when and
// why, and how old the forecast shown is.
function agendaWeather() {
  const w = REM.weather;
  if (!w || (!w.read_at && !w.error)) return "";
  if (!w.error) return agT("Weather for {place} from {source}, read {when}.", { place: w.place, source: w.source, when: fmtTime(w.read_at) });
  return agT("Weather for {place} could not be read on {when} ({reason}).", { place: w.place, when: fmtTime(w.error.at), reason: agT(w.error.reason) + (w.error.error ? " · " + w.error.error : "") })
    + (w.read_at ? " " + agT("The forecast is from {when}.", { when: fmtTime(w.read_at) }) : "");
}

// ---------- projects: one directory, three views (墨与铅 · Ink & Pencil, art direction sprints 10–11) ----------
// Ink is what REM knows from a source; pencil (always dashed) is what REM infers or forecasts.
// Every number, sentence and mark here is computed in the browser from the snapshot's project
// data by a named rule. What REM does not have yet (families, a per-project line, a write path,
// last-visit data) is not drawn and never faked. Red is only for a promise past its date. The
// directory has no green: none of its record actions (accept a grouping, merge, ink a forecast)
// can write to the notebook yet, and a button that cannot act would be a lie.
const PD_ZH = {
  "No activity in the week of {date}": "{date} 那一周：没有活动", "1 activity in the week of {date}": "{date} 那一周：1 次活动",
  "{n} activities in the week of {date}": "{date} 那一周：{n} 次活动", "The week of {date} has not come yet": "{date} 那一周还没到",
  "No dated activity on record": "没有带日期的活动记录", "Busiest in {month}": "{month}最忙", "; ": "；",
  "active this week": "本周有活动", "active last week": "上周有活动", "quiet for {n} weeks": "已安静 {n} 周",
  "Nothing that week": "那一周没有活动", "{a} or more in a week": "一周 {a} 次或更多", "{a} to {b} in a week": "一周 {a} 到 {b} 次", "{a} in a week": "一周 {a} 次",
  "One square is one week; darker means more happened. Counted: {m} messages you typed to agents, {s} sessions with no kept message, {k} other dates a project page cites.":
    "一格是一周，越深活动越多。计入：你发给智能体的 {m} 条消息、{s} 个没有留存消息的会话、项目页面引用的其他 {k} 个日期。",
  "Less": "少", "More": "多", "Most recently active first, the same order as People; within a week, the busier project first.": "最近有活动的排在前面，和「人物」的排序一样；同一周里，更忙的在前。",
  "Quiet for more than {d} days · {n}": "安静超过 {d} 天 · {n}", "Activity by week. Left and right arrows move a month; Home returns to this week.": "按周的活动。左右方向键移动一个月，Home 回到本周。",
  "Not investigated yet": "还没调查", "{n} in Today": "「今天」里 {n} 项", "Project": "项目", "Status": "状态", "Last active": "最近活动", "Last 12 weeks": "最近 12 周", "Open": "未完成",
  "1 open item is in Today": "有 1 项未完成，在「今天」里", "{n} open items are in Today": "有 {n} 项未完成，在「今天」里",
  ".": "。", "Where it stands": "现状", "Activity": "活动", "What was decided": "定下来的事", "Who is involved": "谁参与", "Sessions by date": "会话，按日期", "All {n} decisions": "全部 {n} 项决定",
  "Projects": "项目", "Timeline": "时间线", "List": "列表", "Board": "看板", "View": "视图", "Zoom": "刻度",
  "Week": "周", "Month": "月", "Quarter": "季", "Year": "年",
  "Off track": "偏离", "At risk": "风险", "On track": "正常", "Quiet": "安静", "Done": "完成",
  "A dated promise has passed": "有期限的约定已过期", "Due within 7 days, waiting over 14 days, or blocked": "7 天内到期、等了 14 天以上或受阻",
  "Activity within 30 days": "30 天内有活动", "No activity for 30 days": "30 天没有活动",
  "Of the {n} projects with a coverage record, REM read {r} / {a} inputs": "有覆盖记录的 {n} 个项目里，REM 读了 {r} / {a} 份输入",
  "{n} projects moved this week: {names}.": "这周 {n} 个项目有动静：{names}。", "1 project moved this week: {names}.": "这周 1 个项目有动静：{names}。",
  "No project moved this week.": "这周没有项目有动静。",
  "{n} projects moved in the last 30 days; {risk} at risk, {off} off track.": "近 30 天 {n} 个项目有动静，{risk} 个有风险、{off} 个偏离。",
  "{total} projects on record; {n} had sessions this quarter, most often {names}. {quiet} have gone quiet.": "这一季记下 {total} 个项目，{n} 个有会话，最常出现的是 {names}；{quiet} 个已经安静。",
  "{total} projects on record; no project had sessions this quarter. {quiet} have gone quiet.": "这一季记下 {total} 个项目，没有项目有会话；{quiet} 个已经安静。",
  "{total} projects on record; the earliest, {first}, started {date}. Today {ok} are on track and {quiet} are quiet.": "记下的 {total} 个项目里，最早的 {first} 起于 {date}。今天 {ok} 个正常、{quiet} 个安静。",
  "{total} projects on record. Today {ok} are on track and {quiet} are quiet.": "记下 {total} 个项目。今天 {ok} 个正常、{quiet} 个安静。",
  "On {project}, a promise to {who} is {n} days late.": "{project} 上欠 {who} 的一件事已经晚了 {n} 天。",
  "On {project}, a promise is {n} days late.": "{project} 上有一件答应过的事已经晚了 {n} 天。",
  "1 promise is more than {d} days past its date with no word since; it may be over.": "有 1 件承诺过期超过 {d} 天、之后没有新消息，可能已经结束。",
  "{n} promises are more than {d} days past their date with no word since; they may be over.": "有 {n} 件承诺过期超过 {d} 天、之后没有新消息，可能已经结束。",
  ", ": "、",
  "REM · snapshot {when} · made by rule from {n} project pages, {m} session days and {k} overdue promises · a dashed underline is an inference · change the zoom and this sentence changes":
    "REM {when} 的快照 · 按规则生成，依据 {n} 个项目页、{m} 个会话日与 {k} 条逾期承诺 · 虚线下划线是推测 · 换刻度，这句话跟着换",
  "Sorted by health; a sub-project sits under its project": "按健康排列；子项目缩在它的项目下", "session": "会话", "forecast · 30-day rule": "推测 · 30 天规则",
  "overdue promise": "逾期承诺", "quiet": "安静", "Mostly {a} and {b}": "多在 {a} 与 {b}",
  "Mostly {a}": "多在 {a}", "One line a month · by session days": "每月一句 · 按会话日",
  "Today": "今天", "forecast →": "推测 →", "REM's notes {n} · at most 5": "REM 的批注 {n} 条 · 上限 5", "Days REM wrote pages": "写页的日子",
  "due {date}": "{date} 期限", "{n} days late": "晚 {n} 天", "from {date}": "{date}起", "read {r}/{a}": "读 {r}/{a}",
  "Turns quiet on {date} by the 30-day rule if no session comes": "若再没有会话，按 30 天规则 {date} 转为安静",
  "{n} quiet": "安静 {n} 个", "Show": "展开", "Hide": "收起", "Inference": "推测",
  "Overdue": "过期", "Same?": "重复?", "Part of?": "子项目?", "{k} of its {n} sessions are also {other}'s. It may be part of {other}.": "它的 {n} 个会话里有 {k} 个也属于 {other}。可能是 {other} 的一部分。", "Read a corner": "只读了一角", "Forecast": "推演",
  "{who}: {what}. Due {date}, still open, {n} days late.": "{who}：{what}。期限 {date}，至今仍开着，晚了 {n} 天。",
  "{what}. Due {date}, still open, {n} days late.": "{what}。期限 {date}，至今仍开着，晚了 {n} 天。",
  "{k} of its {n} sessions also appear in {other}. It may be the same project.": "它的 {n} 个会话里有 {k} 个也出现在 {other} 里。可能是同一个项目。",
  "Its page marks it as possibly the same project as {other}.": "它的页面标记它可能和 {other} 是同一个项目。",
  "Of {of} inputs in the last {days} days, REM read {read}. Its picture of this project rests on a corner of them.": "近 {days} 天 {of} 份输入只读了 {read} 份，这一页的判断只基于其中一角。",
  "If no session comes, by the 30-day rule these turn quiet within a week: {list}.": "若再没有会话，按 30 天规则，一周内转为安静的有：{list}。",
  "{name} ({date})": "{name}（{date}）",
  "Project · REM's line": "项目 · REM 的一句", "Project": "项目", "Health": "健康", "Latest": "最近", "Open promises": "开着的约定",
  "On file (7)": "资料（7 项）", "REM read": "REM 读了", "{n} session days": "{n} 个会话日", "1 session day": "1 个会话日", "No sessions": "无会话",
  "You owe {n}": "你欠 {n}", "Waiting {n}": "等人 {n}", "Handed to agents {n}": "交给智能体 {n}", "All 7 on file": "七项齐全", "Not investigated": "未调查",
  "Missing: {list}": "缺 {list}", "Only: {list}": "只有 {list}", "No record": "无记录",
  "repository": "仓库", "stack": "技术栈", "status": "状态", "people": "人", "organisation": "组织", "start": "开始", "last activity": "最近活动",
  "On file: {known}. Not on file: {missing}.": "已有：{known}。没有：{missing}。", "nothing": "无",
  "latest {date}": "{date} 最晚", "Sub-project of {name}": "{name} 的子项目",
  "The board's axis is a question:": "看板的轴是一个问题：", "By health": "按健康", "By state": "按状态",
  "Active": "进行中", "Waiting": "等待", "Show {n} more": "再看 {n} 个", "Who waits on whom": "谁在等谁",
  "What can be set down": "哪些可以放下", "What may be one project": "哪些可能是同一个",
  "{off} off track, {risk} at risk, {ok} on track, {quiet} quiet.": "偏离 {off}、风险 {risk}、正常 {ok}、安静 {quiet}。",
  "If no session comes, {n} more turn quiet by {date} under the 30-day rule, the first on {first}.": "若再没有会话，到 {date} 为止还有 {n} 个会按 30 天规则挪进「安静」，最早的是 {first}。",
  "Pencil · arriving here by {date}": "铅笔 · {date} 前会到这里", "{n} already quiet": "已经安静的 {n} 个",
  "You owe others": "你欠别人", "You wait on others": "你在等别人", "Only with agents": "只交给了智能体", "No open promise": "没有开着的约定",
  "someone owes the owner": "对方欠你", "the owner owes someone": "你欠对方", "instructions to agents": "交给智能体的指示", "nothing open": "什么都没开着",
  "You owe {n} things across {p} projects and wait on others for {w}; {a} projects hold only agent instructions.": "你在 {p} 个项目里欠别人 {n} 件，在等别人 {w} 件；{a} 个项目只有交给智能体的事。",
  "You owe: {names}": "你欠：{names}", "Waiting on: {names}": "在等：{names}", "{n} things": "{n} 件", "{n} handed to agents": "交给智能体 {n} 件",
  "Can be set down": "可以放下", "Quiet, promises still open": "安静，但约定还开着", "Still moving": "还在动",
  "quiet and nobody waiting": "安静，也没人在等", "quiet, someone still waits": "安静，但还有人在等", "activity within 30 days": "30 天内有活动",
  "{n} projects have had no activity for 30 days and nobody waits on them: they {can}. {m} are quiet with a promise still open.": "{n} 个项目 30 天没有活动、也没有人在等，{can}；{m} 个安静但还有约定开着。",
  "can be set down": "可以放下",
  "Shared sessions": "共用会话", "Marked on the page": "页面上标过", "Similar names": "名字相近", "No signal": "没有信号",
  "85% or more of the smaller one's sessions": "小的那个有 85% 以上的会话重合", "REM's same_as suggestion": "REM 的同一项目建议", "a distinctive shared word": "共用一个少见的词",
  "{g} groups may each be one project: {s} share sessions, {t} are marked on their page, {u} have similar names; the other {rest} show no signal. All are inferences; REM merges nothing by itself.":
    "{g} 组可能各是同一个项目：{s} 组共用会话、{t} 组页面上标过、{u} 组名字相近；其余 {rest} 个没有信号。这些都是推测，REM 不会自己合并。",
  "{k}/{n} sessions shared · may be one project": "共用 {k}/{n} 个会话 · 可能是同一个", "{k} of {a}'s {n} sessions are {b}'s too · may be part of it": "{a} 的 {n} 个会话里 {k} 个也属于 {b} · 可能是它的一部分",
  "all contain “{word}”": "名字里都有「{word}」",
  "{a} and {b}": "{a} 与 {b}", "{n} projects": "{n} 个项目", "Nothing here": "这里没有", "No project has a coverage record yet": "还没有项目有覆盖记录",
};
function pdT(key, values = {}) {
  const words = uiLanguage === "zh" ? PD_ZH[key] : null;
  return (words || t(key)).replace(/\{(\w+)\}/g, (match, name) => values[name] ?? match);
}

const PD_TIERS = ["off_track", "at_risk", "on_track", "quiet"];
const PD_HEALTH = { off_track: "Off track", at_risk: "At risk", on_track: "On track", quiet: "Quiet", done: "Done" };
// [label, days back, days forward]: the window around the snapshot's day.
const PD_VIEWS = [["timeline", "Timeline"], ["list", "List"], ["board", "Board"]];
const PD_ASKS = [["state", "By state"], ["waiting", "Who waits on whom"], ["drop", "What can be set down"], ["same", "What may be one project"]];
const PD_QUIET_DAYS = 30, PD_NOTES = 5, PD_FOLD_AT = 6;
// The board's columns (#2993), named for who holds the next step; projectState says how each is decided.
const PD_STATES = [["active", "Active"], ["waiting", "Waiting"], ["quiet", "Quiet"], ["done", "Done"]];
let PD_SESSIONS = null;
const pdStateOpen = new Set();

// ---- data: ported from the sprint-10 project views (their UI was rejected, their rules were not) ----
function projectLast(r) { return facts(r).last || r.last_activity || ""; }
function projectDone(r) { return (r.reasons || []).some(reason => reason.text === "Project explicitly marked completed"); }
function projectMapped(r) { return known(r).status === "Mapped"; }
function projectTier(r) { return projectDone(r) ? "done" : PD_TIERS.includes(r.health) ? r.health : "quiet"; }
// Health already accounts for dated promises and the 30-day activity rule. A moving project waits
// only when every confirmed step belongs to someone else; an unclassified step cannot imply that.
function projectState(r) {
  const tier = projectTier(r);
  if (tier === "done" || tier === "quiet") return tier;
  const open = (r.open || []).filter(item => !item.project_match?.needs_review);
  return open.length && open.every(item => ["waiting", "agent", "answerable"].includes(item.kind)) ? "waiting" : "active";
}
// The structured item behind a line of the page's Open threads: its kind and who it names.
function projectOpenItem(r, thread) {
  const key = stripCites(thread.originalText || thread.text);
  return (r.open || []).find(item => stripCites(item.text) === key);
}
// Who holds a step, in the words Today uses; an agent's instruction and a named person are said as such.
function projectStepOwner(r, thread) {
  const item = projectOpenItem(r, thread);
  if (item?.kind === "answerable") return { owner: "answerable", label: t("Answer available") };
  if (item?.kind === "unconfirmed" || item?.needs_review) return { owner: "", label: t("Owner unconfirmed") };
  if (item?.kind === "agent") return { owner: "agent", label: t("Agent request") };
  if (item?.kind === "waiting") return { owner: "them", label: pdWho(item.who) || t(DIRECTION_LABEL.theirs) };
  if (item?.kind === "owed" || thread.dir === "mine") return { owner: "you", label: t(DIRECTION_LABEL.mine) };
  return { owner: thread.dir === "theirs" ? "them" : "", label: t(DIRECTION_LABEL[thread.dir] || "Open") };
}
// The step itself, not the conversation it came from: the words after "open:" when the page wrote them, else
// the line without its leading date, quote and speaker. Its privacy label travels with it.
function projectStepWhat(text) {
  const plain = stripCites(text).replace(/\*\*/g, "");
  const open = /(?:^|[—–;；]\s*)(?:still open|open|未解决|仍未解决|待解决)\s*[:：]\s*(.+)$/i.exec(plain)?.[1];
  let what = open || plain.replace(/^\d{4}-\d{2}-\d{2}\s*[—–:：-]\s*/, "");
  if (!open) {
    const rest = what.replace(/^[^“"「]{0,40}[“"「][^”"」]*[”"」]\s*[—–,，。.;；]?\s*/, "");
    if (rest !== what && rest.length >= 8 && /[\p{L}\p{N}]{2}/u.test(rest)) what = rest;
  }
  what = what.trim().replace(/[.。;；]$/, "");
  return hasPrivacy(text) && !hasPrivacy(what) ? what + " [personal]" : what;
}
// The step a card shows: one past its date first, then the owner's, then someone else's, then an agent's.
function projectSteps(r) {
  const today = calendarDay(REM.as_of), rank = step => step.thread.due && step.thread.due < today && step.owner === "you" ? 0
    : ({ you: 1, them: 2, agent: 3 })[step.owner] ?? 4;
  return threads(r).items.map(thread => ({ thread, ...projectStepOwner(r, thread) }))
    .sort((a, b) => rank(a) - rank(b) || (a.thread.due || "9999").localeCompare(b.thread.due || "9999"));
}
// Someone else waits on the owner. Agent instructions and unconfirmed organisation joins never count.
function projectOwed(r) { return (r.open || []).filter(item => item.kind === "owed" && !item.project_match?.needs_review); }
function projectOverdue(r) { return r.overdue_days || 0; }
// The same order as rank_key in project_priority.py: pinned, an overdue explicit promise, score,
// then days overdue, distinct people owed, and a casefolded title.
function projectPeopleOwed(r) { return new Set(projectOwed(r).filter(item => item.who && !item.needs_review).map(item => item.who)).size; }
function projectTitleKey(title) { return String(title).toLowerCase().normalize("NFKC"); }
function projectRank(a, b) {
  const title = r => projectTitleKey(r.title);
  return Number(!!b.pinned) - Number(!!a.pinned) || Number(projectOverdue(b) > 0) - Number(projectOverdue(a) > 0)
    || (b.score || 0) - (a.score || 0) || projectOverdue(b) - projectOverdue(a)
    || projectPeopleOwed(b) - projectPeopleOwed(a) || (title(a) < title(b) ? -1 : title(a) > title(b) ? 1 : 0);
}
function stripCites(text) { return String(text).replace(/\s*\[W?\d{1,3}\]/g, "").trim(); }
function projectShort(text) { return firstClause(stripCites(text)).replace(/[.。]$/, ""); }
// The snapshot's calendar day, or the clock's when a snapshot carries no date (as daysSince does).
function projectAsOfDay(asOf) { return calendarDay(asOf || new Date().toISOString()); }
function pdAddDays(day, n) { return new Date(Date.parse(day + "T00:00:00Z") + n * DAY_MS).toISOString().slice(0, 10); }
function pdBetween(a, b) { return Math.round((Date.parse(b + "T00:00:00Z") - Date.parse(a + "T00:00:00Z")) / DAY_MS); }
function pdDay(day, year = false) {
  return new Date(day + "T00:00:00Z").toLocaleDateString(uiLocale(), { timeZone: "UTC", month: "short", day: "numeric", ...(year ? { year: "numeric" } : {}) });
}
function pdList(names) {
  if (names.length <= 1) return names[0] || "";
  return names.slice(0, -1).join(pdT(", ")) + (uiLanguage === "zh" ? " 和 " : " and ") + names.at(-1);
}
function pdWho(who) { const page = who && byPath(who); return page ? page.title : who && !String(who).includes("/") ? String(who) : ""; }

// ---- the tree: sub-projects and possible duplicates hang under the page they point to; nothing is merged ----
function projectHost(r, order) {
  if (r.parent?.path && r.parent.path !== r.path && order.has(r.parent.path)) return r.parent.path;
  return (r.same_as || []).map(match => match.path).find(path => order.has(path) && order.get(path) < order.get(r.path)) || "";
}
// One level only: a page that is itself attached to another stays a top-level row.
function projectTree(ranked) {
  const order = new Map(ranked.map((r, i) => [r.path, i])), kids = new Map(), top = [];
  for (const r of ranked) {
    const host = projectHost(r, order);
    if (host && !projectHost(byPath(host), order)) kids.set(host, [...(kids.get(host) || []), r]);
    else top.push(r);
  }
  return { top, kids };
}

// ---- dates someone wrote down. The same filter as overdue_promise in project_priority.py:
// only a confirmed owed item with an explicit due date can be late. ----
function projectDueItems(r) { return projectOwed(r).filter(item => item.due && !item.needs_review); }
// Written dates as {day, text, state, who}. Waiting, answerable, review and milestone dates that have
// passed are "past", never "late". Two deadlines on one day are two marks.
function projectMarks(r, today = projectAsOfDay(REM.as_of)) {
  const marks = new Map(), covered = new Set();
  for (const item of projectDueItems(r)) {
    const promise = (item.promised || []).find(p => p.date === item.due);
    (item.promised || []).forEach(p => covered.add(p.date + "|" + p.text));
    marks.set(item.due + "|" + item.text, { day: item.due, text: promise?.text || projectShort(item.text), owed: true, who: item.who || "", item: item.text, since: projectItemSince(item) });
  }
  for (const p of [...(r.promised || []), ...(r.written_deadlines || [])])
    if (p.date && !covered.has(p.date + "|" + p.text) && !marks.has(p.date + "|" + p.text)) marks.set(p.date + "|" + p.text, { day: p.date, text: p.text, owed: false, who: "" });
  return [...marks.values()].map(mark => ({ ...mark, state: mark.day >= today ? "next" : mark.owed ? "late" : "past" }))
    .sort((a, b) => a.day.localeCompare(b.day) || a.text.localeCompare(b.text));
}
// A promise whose only words are a date is labelled by its open item's own words.
function projectMarkWhat(mark) {
  if (!(/\d{4}-\d{2}-\d{2}/.test(mark.text) && mark.text.length < 24)) return projectShort(mark.text);
  return mark.item ? projectItemWhat(mark.item) : t("Written date");
}
// The thing itself: no debtor prefix, no quoted original, no trailing due date or labels.
function projectItemWhat(text) {
  let what = stripCites(text).replace(/\s*\[(?:personal|private|sensitive)[^\]]*\]/gi, "").replace(/\s+[—–-]\s*due\s+\d{4}-\d{2}-\d{2}.*$/i, "")
    .replace(/^(?:the user owes [^:：]{1,60}|[^:：]{1,60} asked the user)[:：]\s*/i, "");
  what = what.split(/\s+[—–]\s+|\s*[“"「]/)[0].trim().replace(/[.。:：]$/, "");
  return what.length > 72 ? what.slice(0, 70).replace(/\s+\S*$/, "") + "…" : what;
}
// The thread's last word, as Today reads it (today.py: the latest cited message): project_obligations.py's
// own since is the request day, which would call a promise stale on Projects while a message last week keeps it
// live on Today.
function projectItemSince(item) {
  const days = (item.sources || []).map(s => REM.source_context?.[s.source]?.time).filter(Boolean).map(calendarDay).sort();
  return days.at(-1) || item.since || "";
}
// The oldest late mark, with its age in days.
function projectLate(r) {
  const mark = projectMarks(r).find(m => m.state === "late");
  return mark ? { ...mark, days: daysSince(mark.day) } : null;
}
// Late marks the headline may shout about, and those it only mentions: Today's rule (stalePromise) decides.
function projectLateMarks(r, stale) { return projectMarks(r).filter(m => m.state === "late" && stalePromise(m.day, m.since) === stale); }

// ---- sessions: the days an agent session touched the project (relations and session records) ----
function projectSessionIndex() {
  if (PD_SESSIONS) return PD_SESSIONS;
  PD_SESSIONS = new Map();
  const add = (path, session, day) => {
    if (!day) return;
    const entry = PD_SESSIONS.get(path) || { days: new Set(), paths: new Set() };
    entry.days.add(day); entry.paths.add(session); PD_SESSIONS.set(path, entry);
  };
  for (const s of REM.records) if (s.category === "sessions" && s.session_project) add(s.session_project, s.path, calendarDay(s.session_date || ""));
  for (const p of inCategory("projects")) for (const rel of p.relations || []) {
    const day = /^sessions\/(\d{4}-\d{2}-\d{2})/.exec(rel.path || "")?.[1];
    if (day) add(p.path, rel.path, day);
  }
  return PD_SESSIONS;
}
function projectSessionDays(r) { return [...(projectSessionIndex().get(r.path)?.days || [])].sort(); }
function projectSessionPaths(r) { return projectSessionIndex().get(r.path)?.paths || new Set(); }
// Pencil: an on-track project turns quiet on day 31 without activity (health() in project_priority.py).
function projectQuietOn(r) {
  const last = projectLast(r) && calendarDay(projectLast(r));
  return projectTier(r) === "on_track" && last ? pdAddDays(last, PD_QUIET_DAYS + 1) : "";
}
function projectCoverage(r) {
  const c = r.project_coverage;
  return c && c.inputs_available ? { read: c.inputs_read || 0, of: c.inputs_available, days: c.days || 30 } : null;
}

// ---- inferences: possible duplicates. Shared sessions and page suggestions, then distinctive words. ----
function projectPairs(all) {
  const pairs = [], same = (p, a, b) => (p.a === a && p.b === b) || (p.a === b && p.b === a);
  for (const a of all) for (const b of all) {
    if (a === b) continue;
    const A = projectSessionPaths(a), B = projectSessionPaths(b);
    if (A.size < 5 || B.size < A.size || (B.size === A.size && a.path > b.path)) continue;
    const k = [...A].filter(path => B.has(path)).length;
    if (k / A.size >= 0.85) pairs.push({ kind: "sessions", a, b, k, n: A.size, m: B.size, inside: B.size > A.size * 1.5 });
  }
  for (const a of all) for (const match of a.same_as || []) {
    const b = byPath(match.path);
    if (b && b !== a && !pairs.some(p => same(p, a, b))) pairs.push({ kind: "page", a, b });
  }
  // A word shared by two or three titles; a word in more is a prefix (an organisation), not a signal.
  const generic = new Set(["android", "macos", "windows", "landingpage", "landing", "browser", "project", "website", "service", "client", "server"]);
  const words = new Map();
  for (const r of all) for (const word of new Set(String(r.title).toLowerCase().split(/[^a-z0-9一-鿿]+/)))
    if (word.length >= 5 && !generic.has(word)) words.set(word, [...(words.get(word) || []), r]);
  for (const [word, rows] of words) if (rows.length >= 2 && rows.length <= 3 && !rows.every((r, i) => !i || pairs.some(p => same(p, rows[0], r))))
    pairs.push({ kind: "name", rows, word });
  return pairs;
}

// ---- REM's notes in the margin: rule-made only, at most five, one per project. Order: overdue (fact),
// the week's forecast (P大: "tell me which go cold next week"), a likely duplicate, thin coverage. ----
function projectNotes(all, pairs) {
  const notes = new Map(), today = projectAsOfDay(REM.as_of), put = (r, note) => { if (notes.size < PD_NOTES && !notes.has(r.path)) notes.set(r.path, note); };
  for (const [r, late] of all.map(r => [r, projectLate(r)]).filter(([, late]) => late).sort((a, b) => b[1].days - a[1].days)) {
    const who = pdWho(late.who), values = { who, what: projectMarkWhat(late), date: pdDay(late.day), n: late.days };
    put(r, { kind: "fact", kicker: "Overdue", text: pdT(who ? "{who}: {what}. Due {date}, still open, {n} days late." : "{what}. Due {date}, still open, {n} days late.", values), red: true });
  }
  const soon = all.map(r => [r, projectQuietOn(r)]).filter(([, day]) => day && day > today && pdBetween(today, day) <= 7).sort((a, b) => a[1].localeCompare(b[1]));
  if (soon.length) put(soon[0][0], { kind: "pencil", kicker: "Forecast",
    text: pdT("If no session comes, by the 30-day rule these turn quiet within a week: {list}.", { list: soon.map(([r, day]) => pdT("{name} ({date})", { name: r.title, date: pdDay(day) })).join(pdT(", ")) }) });
  for (const p of pairs.filter(p => p.kind === "sessions" && !p.inside))
    put(p.a, { kind: "inference", kicker: "Same?", text: pdT("{k} of its {n} sessions also appear in {other}. It may be the same project.", { k: p.k, n: p.n, other: p.b.title }) });
  for (const r of all) {
    const c = projectCoverage(r);
    if (c && c.of >= 20 && c.read / c.of < 0.2) put(r, { kind: "fact", kicker: "Read a corner", text: pdT("Of {of} inputs in the last {days} days, REM read {read}. Its picture of this project rests on a corner of them.", c) });
  }
  for (const p of pairs.filter(p => p.kind === "page"))
    put(p.a, { kind: "inference", kicker: "Same?", text: pdT("Its page marks it as possibly the same project as {other}.", { other: p.b.title }) });
  for (const p of pairs.filter(p => p.kind === "sessions" && p.inside))
    put(p.a, { kind: "inference", kicker: "Part of?", text: pdT("{k} of its {n} sessions are also {other}'s. It may be part of {other}.", { k: p.k, n: p.n, other: p.b.title }) });
  return notes;
}
function projectNoteNode(note, inline = false) {
  return el(inline ? "p" : "div", { class: "pd-note pd-note-" + note.kind }, [
    el("b", { class: "pd-kicker" + (note.red ? " red" : ""), text: pdT(note.kicker) }), " ",
    el("span", { class: note.kind === "fact" ? "" : "pd-inf", text: note.text })]);
}

// ---- activity by week (#3096): counted in project_activity.py, drawn here ----
// The window is in weeks (Mondays). It opens a year back and two months ahead and grows at whichever
// edge he scrolls to, so time has no end stop in either direction.
const PA_BACK = 52, PA_AHEAD = 8, PA_GROW = 26, PA_MINI = 12, PA_RECORD = 26;
const paWin = { from: "", to: "" };
function paActivity(r) { return r.activity || { weeks: {}, kinds: {}, first: "", last: "", recent: 0, rank: Infinity, quiet: true }; }
function paWeekOf(day) { return pdAddDays(day, -((new Date(day + "T00:00:00Z").getUTCDay() + 6) % 7)); }
function paMeta() {
  return REM.project_activity || { scale: [1, 2, 3, 4], kinds: {}, first: "", this_week: paWeekOf(projectAsOfDay(REM.as_of)), quiet_days: PD_QUIET_DAYS, recent_weeks: PA_MINI };
}
// One scale for every row: the same count is the same step of ink on every project.
function paLevel(n) { return paMeta().scale.filter(bound => n >= bound).length; }
// The order is decided once, where the counting is (project_activity.order): People's rule, for projects.
function paOrder(all) { return [...all].sort((a, b) => paActivity(a).rank - paActivity(b).rank || projectRank(a, b)); }
function paWeeks(from, to) {
  const out = [];
  for (let week = from; week <= to; week = pdAddDays(week, 7)) out.push(week);
  return out;
}
function paCellWords(week, n) {
  const date = pdDay(week, true);
  if (week > paMeta().this_week) return pdT("The week of {date} has not come yet", { date });
  return pdT(!n ? "No activity in the week of {date}" : n === 1 ? "1 activity in the week of {date}" : "{n} activities in the week of {date}", { n, date });
}
function paCell(r, week) {
  const a = paActivity(r), n = a.weeks[week] || 0, now = paMeta().this_week;
  // Before its first dated week a project is not on record: nothing is drawn there, so a row begins where it does.
  const when = week > now ? " ahead" : !a.first || week < paWeekOf(a.first) ? " before" : "";
  return el("i", { class: "pa-c l" + paLevel(n) + (week === now ? " now" : "") + when, "data-w": week, "data-n": String(n),
    tabindex: "-1", role: "img", "aria-label": paCellWords(week, n) });
}
function paStrip(r, weeks) { return el("div", { class: "pa-strip", "data-path": r.path }, weeks.map(week => paCell(r, week))); }
function paMonthName(month, year) {
  return new Date(month + "-01T00:00:00Z").toLocaleDateString(uiLocale() || "en", { timeZone: "UTC", month: uiLanguage === "zh" ? "numeric" : "long", ...(year ? { year: "numeric" } : {}) });
}
// The row's sentence, worked out from its weeks: when it was busiest and how long it has been still.
function paSentence(r) {
  const a = paActivity(r), now = paMeta().this_week, months = new Map();
  for (const [week, n] of Object.entries(a.weeks)) months.set(week.slice(0, 7), (months.get(week.slice(0, 7)) || 0) + n);
  if (!months.size) return pdT("No dated activity on record");
  const busiest = [...months].sort((x, y) => y[1] - x[1] || y[0].localeCompare(x[0]))[0][0];
  const gap = Math.round(pdBetween(paWeekOf(a.last), now) / 7);
  return pdT("Busiest in {month}", { month: paMonthName(busiest, busiest.slice(0, 4) !== now.slice(0, 4)) }) + pdT("; ")
    + pdT(gap <= 0 ? "active this week" : gap === 1 ? "active last week" : "quiet for {n} weeks", { n: gap });
}
// The last weeks only, for a list row, a card and a record: the same squares on the same scale.
function paMini(r, n = PA_MINI) {
  const now = paMeta().this_week;
  return el("div", { class: "pa-strip pa-mini", role: "group", "aria-label": paSentence(r) }, paWeeks(pdAddDays(now, -7 * (n - 1)), now).map(week => paCell(r, week)));
}
// A month is named over the first week that starts in it; January carries the year.
function paMonths(weeks) {
  const now = paMeta().this_week;
  return el("div", { class: "pa-months" }, weeks.map((week, i) => {
    if (i ? weeks[i - 1].slice(0, 7) === week.slice(0, 7) : week.slice(8) > "07") return null;
    const text = new Date(week + "T00:00:00Z").toLocaleDateString(uiLocale() || "en", { timeZone: "UTC", month: "short", ...(week.slice(5, 7) === "01" ? { year: "numeric" } : {}) });
    return el("span", { class: "pa-month" + (week.slice(0, 7) === now.slice(0, 7) ? " now" : ""), style: "--i:" + i, "data-m": week.slice(0, 7), text });
  }));
}
// What a square counts and what a shade means, in words: a strip is never left to be guessed at.
function paScale() {
  const s = paMeta().scale;
  const step = i => i === 0 ? pdT("Nothing that week") : i === 4 ? pdT("{a} or more in a week", { a: s[3] })
    : s[i] - 1 > s[i - 1] ? pdT("{a} to {b} in a week", { a: s[i - 1], b: s[i] - 1 }) : pdT("{a} in a week", { a: s[i - 1] });
  return el("div", { class: "pa-scale" }, [el("span", { text: pdT("Less") }),
    ...[0, 1, 2, 3, 4].map(i => el("i", { class: "pa-c l" + i, tabindex: "-1", role: "img", "aria-label": step(i) })), el("span", { text: pdT("More") })]);
}
// The order and what a square counts, in words, with the five steps beside them: a strip is never left to be guessed at.
function paKey(extra) {
  const k = paMeta().kinds || {};
  return el("div", { class: "pa-key" }, [el("div", { class: "pa-words" }, [
    el("p", { class: "pa-order", text: pdT("Most recently active first, the same order as People; within a week, the busier project first.") }),
    el("p", { class: "pa-counted", text: pdT("One square is one week; darker means more happened. Counted: {m} messages you typed to agents, {s} sessions with no kept message, {k} other dates a project page cites.",
      { m: k.messages || 0, s: k.sessions || 0, k: (k.mail || 0) + (k.page || 0) }) })]),
    el("div", { class: "pa-tools" }, [paScale(), extra || null])]);
}
function paSplit(all) {
  const rows = paOrder(all);
  return [rows.filter(r => !paActivity(r).quiet), rows.filter(r => paActivity(r).quiet)];
}
function paDividerWords(n) { return pdT("Quiet for more than {d} days · {n}", { d: paMeta().quiet_days, n }); }
function paRowName(r) {
  return el("div", { class: "pa-name", "data-path": r.path }, [el("a", { class: "pa-title", href: href(r), text: r.title }), el("span", { class: "pa-say", text: paSentence(r) })]);
}

// ---- the timeline: one row a project, one square a week ----
function projectTimeline(all) {
  const [live, still] = paSplit(all), now = paMeta().this_week;
  Object.assign(paWin, { from: pdAddDays(now, -7 * PA_BACK), to: pdAddDays(now, 7 * PA_AHEAD) });
  const weeks = paWeeks(paWin.from, paWin.to), rows = [...live, ...still];
  const names = [el("div", { class: "pa-corner" }), ...live.map(paRowName),
    still.length ? el("div", { class: "pa-divider", text: paDividerWords(still.length) }) : null, ...still.map(paRowName)];
  const canvas = el("div", { class: "pa-canvas" }, [paMonths(weeks), ...live.map(r => paStrip(r, weeks)),
    still.length ? el("div", { class: "pa-divider" }) : null, ...still.map(r => paStrip(r, weeks))]);
  const time = el("div", { class: "pa-time", tabindex: "0", role: "region", "aria-label": pdT("Activity by week. Left and right arrows move a month; Home returns to this week.") }, [canvas]);
  const today = el("button", { type: "button", class: "pa-today", text: pdT("Today") });
  today.onclick = () => paToday(time);
  time.addEventListener("scroll", () => paEdge(time, rows), { passive: true });
  time.addEventListener("keydown", event => paKeyDown(event, time));
  return el("section", { class: "pa" }, [paKey(today), el("div", { class: "pa-grid" }, [el("div", { class: "pa-names" }, names), time])]);
}
function paStep(time) {
  const cells = time.querySelector(".pa-strip").children;
  return cells[1].offsetLeft - cells[0].offsetLeft;
}
// The corner over the names says which year the weeks in view belong to; a month alone does not.
function paYear(time) {
  const cells = time.querySelector(".pa-strip").children, step = paStep(time);
  const at = x => cells[Math.max(0, Math.min(cells.length - 1, Math.floor(x / step)))].dataset.w.slice(0, 4);
  const from = at(time.scrollLeft), to = at(time.scrollLeft + time.clientWidth - 1);
  time.parentNode.querySelector(".pa-corner").textContent = from === to ? from : from + " – " + to;
}
// This week sits two columns in from the right edge, so what comes next is visibly empty rather than cut off.
function paToday(time) {
  const upTo = paWeeks(paWin.from, paMeta().this_week).length;
  const step = paStep(time);
  time.scrollLeft = Math.max(0, Math.ceil(((upTo + 2) * step - time.clientWidth) / step) * step);  // whole columns: no square is cut at the left
  paYear(time);
}
// Near either edge the window grows by half a year. Going back, the view is held where it was.
function paEdge(time, rows) {
  const step = paStep(time);
  paYear(time);
  if (time.scrollLeft < 8 * step) paExtend(time, rows, true);
  else if (time.scrollLeft + time.clientWidth > time.scrollWidth - 8 * step) paExtend(time, rows, false);
}
function paExtend(time, rows, back) {
  const from = back ? pdAddDays(paWin.from, -7 * PA_GROW) : pdAddDays(paWin.to, 7), to = back ? pdAddDays(paWin.from, -7) : pdAddDays(paWin.to, 7 * PA_GROW);
  const added = paWeeks(from, to), held = time.scrollLeft, step = paStep(time);
  time.querySelectorAll(".pa-strip").forEach((strip, i) => strip[back ? "prepend" : "append"](...added.map(week => paCell(rows[i], week))));
  Object.assign(paWin, back ? { from } : { to });
  time.querySelector(".pa-months").replaceWith(paMonths(paWeeks(paWin.from, paWin.to)));
  if (back) time.scrollLeft = held + added.length * step;
}
// ← and → land on the column where the previous or the next month begins.
function paKeyDown(event, time) {
  if (event.key === "Home") { event.preventDefault(); paToday(time); return; }
  const dir = event.key === "ArrowLeft" ? -1 : event.key === "ArrowRight" ? 1 : 0;
  if (!dir) return;
  event.preventDefault();
  const step = paStep(time), weeks = paWeeks(paWin.from, paWin.to);
  let i = Math.round(time.scrollLeft / step) + dir;
  while (i > 0 && i < weeks.length - 1 && weeks[i].slice(0, 7) === weeks[i - 1].slice(0, 7)) i += dir;
  time.scrollLeft = Math.max(0, i) * step;
}
// A square says its week and its count in words, on hover, on focus and on a tap.
function paTipShow(event) {
  const cell = event.target.closest?.(".pa-c[aria-label]");
  paTipHide();
  if (!cell) return;
  const tip = el("div", { id: "pa-tip", class: "pa-tip", role: "tooltip", text: cell.getAttribute("aria-label") });
  document.body.appendChild(tip);
  const box = cell.getBoundingClientRect();
  tip.style.left = Math.max(12, Math.min(box.left + box.width / 2 - tip.offsetWidth / 2, innerWidth - tip.offsetWidth - 12)) + "px";
  tip.style.top = Math.max(12, box.top - tip.offsetHeight - 8) + "px";
}
function paTipHide() { document.getElementById("pa-tip")?.remove(); }

// ---- what a row says about a project ----
// One sentence about what the project is, in the reading language when its page has been translated.
function projectSentence(r) {
  const tag = uiLanguage === "zh" ? Object.keys(r.translations || {}).find(tag => /^zh(?:-|$)/i.test(tag)) : uiLanguage === "en" ? "" : uiLanguage;
  const text = (tag && r.translations?.[tag]) || r.original || r.text;
  for (const name of ["What it is", "Where it stands"]) {
    const body = (text.split(/^## /m).find(part => part.startsWith(name + "\n")) || "").slice(name.length + 1);
    const line = plainLine(body.split("\n").find(l => l.trim()) || "");
    if (line && !/^(?:Unknown\b|未知)/i.test(line)) return (/^(.*?[.。!?！？])(?:\s|$)/.exec(line)?.[1] || line).trim();
  }
  return "";
}
function projectSayNode(r, name = "pa-say") {
  const say = projectSentence(r);
  return el("span", { class: name + (say ? "" : " pd-pencil-word"), text: say || pdT("Not investigated yet") });
}
function projectStateWord(r) { return pdT(PD_STATES.find(([key]) => key === projectState(r))[1]); }
function projectLastDay(r) { return paActivity(r).last || (projectLast(r) ? calendarDay(projectLast(r)) : ""); }
function projectLastWords(r) {
  const day = projectLastDay(r);
  return day ? pdDay(day, day.slice(0, 4) !== projectAsOfDay(REM.as_of).slice(0, 4)) : "";
}
// What is still open lives in Today; a row and a record only count it and point there.
// A promise past its date that still has a live thread (Today's rule, stalePromise): one that went stale is
// asked about in Today, never shouted on a row.
function projectLiveLate(r) {
  const mark = projectLateMarks(r, false)[0];
  return mark ? { ...mark, days: daysSince(mark.day) } : null;
}
function projectTodayCount(r) { return (REM.today_queue || []).filter(row => row.record === r.path && !row.closed && !row.quiet).length; }
function projectTodayLink(r, words) {
  // A project's open items live in Today under their correspondents, never as one project card in the reply deck,
  // so this opens the Waiting view filtered to the project — the very place and filter id ("project:" + title)
  // that project's own chip uses there (openTags/openChips) — instead of the deck. todayLead could only reorder
  // the deck, which holds no card keyed to a project, so a project page's "N open items are in Today" line used to
  // land on an unrelated card or an empty, off-screen panel (#3165). One shared filter, same as every chip.
  return el("a", { class: "project-today-link", href: "#view=open&tag=" + encodeURIComponent("project:" + r.title), text: words });
}

// ---- the head: the page's name and its three views ----
function pdParams() {
  const p = new URLSearchParams(location.hash.slice(1));
  return { view: PD_VIEWS.some(([k]) => k === p.get("v")) ? p.get("v") : "board", ask: PD_ASKS.some(([k]) => k === p.get("ask")) ? p.get("ask") : "state" };
}
function pdHref(change) {
  const s = { ...pdParams(), ...change };
  return "#c=projects&v=" + s.view + (s.view === "board" && s.ask !== "state" ? "&ask=" + s.ask : "");
}
function projectHead(all, state) {
  return el("header", { class: "pd-head" }, [
    el("h1", { class: "pd-title" }, [pdT("Projects"), el("span", { class: "pd-count", text: String(all.length) })]),
    el("div", { class: "pd-views", role: "navigation", "aria-label": pdT("View") }, PD_VIEWS.map(([key, name]) =>
      el("a", { href: pdHref({ view: key }), class: key === state.view ? "on" : "", ...(key === state.view ? { "aria-current": "page" } : {}), text: pdT(name) }))),
    state.view === "board" ? el("div", { class: "pd-head-end" }, [el("div", { class: "pd-seg pd-asks", role: "group" }, PD_ASKS.map(([key, name]) =>
      el("a", { href: pdHref({ ask: key }), class: key === state.ask ? "on" : "", "aria-pressed": String(key === state.ask), text: pdT(name) })))]) : null]);
}
function projectDot(r) {
  const tier = projectTier(r), word = pdT(PD_HEALTH[tier]);
  return el("span", { class: "pd-dot " + tier, title: word, role: "img", "aria-label": word });
}
function projectNameNode(r) {
  return el("span", { class: "pd-name-line" }, [projectDot(r), el("a", { href: href(r), class: projectTier(r) === "off_track" ? "red" : "", text: r.title })]);
}

// ---- the list: the timeline's rows as a table, at body size ----
function projectListRow(r) {
  const late = projectLiveLate(r), open = projectTodayCount(r);
  return el("div", { class: "pl-row", role: "row", "data-path": r.path }, [
    el("div", { class: "pl-name", role: "cell" }, [el("a", { class: "pa-title", href: href(r), text: r.title }), projectSayNode(r)]),
    el("div", { class: "pl-state", role: "cell" }, [el("span", { text: projectStateWord(r) }), late ? el("span", { class: "red", text: pdT("{n} days late", { n: late.days }) }) : null]),
    el("div", { class: "pl-last", role: "cell", "data-label": pdT("Last active"), text: projectLastWords(r) || "—" }),
    el("div", { class: "pl-strip", role: "cell" }, [paMini(r)]),
    el("div", { class: "pl-open", role: "cell" }, [open ? projectTodayLink(r, pdT("{n} in Today", { n: open })) : el("span", { class: "mut", text: "—" })])]);
}
function projectList(all) {
  const [live, still] = paSplit(all);
  const head = el("div", { class: "pl-row pl-head", role: "row" }, ["Project", "Status", "Last active", "Last 12 weeks", "Open"].map(name =>
    el("div", { role: "columnheader", text: pdT(name) })));
  return el("section", { class: "pa pl-wrap" }, [paKey(),
    el("div", { class: "pl", role: "table" }, [head, ...live.map(projectListRow),
      still.length ? el("div", { class: "pa-divider", text: paDividerWords(still.length) }) : null, ...still.map(projectListRow)])]);
}

// ---- the board: the axis is a question ----
function projectCard(r, note, extra) {
  return el("article", { class: "pd-card" + (projectTier(r) === "off_track" ? " late" : ""), "data-path": r.path }, [
    el("div", { class: "pd-card-head" }, [projectNameNode(r), el("span", { class: "pd-when", text: projectLastWords(r) })]),
    note ? projectNoteNode(note, true) : null, extra ? el("p", { class: "pd-card-extra", text: extra }) : null,
    el("div", { class: "pd-card-foot" }, [paMini(r)])]);
}
function projectCompact(rows, line) {
  return el("ul", { class: "pd-compact" }, rows.map(r => el("li", {}, [line ? el("span", { class: "mut", text: line(r) }) : null, el("a", { href: href(r), text: r.title })])));
}
function projectColumn(title, caption, children, red = false) {
  return el("section", { class: "pd-colm" + (red ? " red" : "") }, [
    el("h2", {}, [el("span", { text: title }), el("small", { text: caption })]), ...(children.length ? children : [el("p", { class: "pd-empty", text: pdT("Nothing here") })])]);
}
// ---- the board by state (#2993): one column per state, one card per project ----
// A card is the name, one sentence about the project, its last twelve weeks and when it last moved. The step
// it waits on, quoted from a request, was not something to scan (#3096): open work is counted and lives in Today.
function projectStateCard(r) {
  const late = projectLiveLate(r);
  return el("article", { class: "pd-card pd-state-card" + (late ? " late" : ""), "data-path": r.path }, [
    el("a", { href: href(r), class: "pa-title pd-card-name", text: r.title }), projectSayNode(r, "pa-say pd-card-say"),
    el("div", { class: "pd-card-foot" }, [paMini(r), el("span", { class: "pd-card-when" }, [
      late ? el("span", { class: "red", text: pdT("{n} days late", { n: late.days }) }) : null, el("span", { class: "pd-when", text: projectLastWords(r) })])])]);
}
function projectStateColumn(state, name, rows) {
  const open = pdStateOpen.has(state) || rows.length <= PD_FOLD_AT + 1, shown = open ? rows : rows.slice(0, PD_FOLD_AT);
  const more = el("button", { type: "button", class: "pd-fold-btn pd-col-more", text: pdT("Show {n} more", { n: rows.length - shown.length }) });
  more.onclick = () => { pdStateOpen.add(state); projectsView(); };
  return el("section", { class: "pd-colm pd-state-col" + (rows.length ? "" : " is-empty"), "data-state": state }, [
    el("h2", {}, [el("i", { class: "pd-state-dot " + state, "aria-hidden": "true" }), el("span", { text: pdT(name) }), el("small", { text: String(rows.length) })]),
    ...shown.map(projectStateCard), shown.length < rows.length ? more : null, rows.length ? null : el("p", { class: "pd-empty", text: "—" })]);
}
function projectBoardState(all) {
  const rows = paOrder(all);  // the one order of the page, in every column
  return PD_STATES.map(([state, name]) => projectStateColumn(state, name, rows.filter(r => projectState(r) === state)));
}
function projectBoardWaiting(all, notes) {
  const owedRows = all.filter(r => projectOwed(r).length), waitRows = all.filter(r => !owedRows.includes(r) && (r.open || []).some(i => i.kind === "waiting"));
  const agentRows = all.filter(r => !owedRows.includes(r) && !waitRows.includes(r) && (r.open || []).some(i => i.kind === "agent" || i.kind === "answerable"));
  const none = all.filter(r => ![owedRows, waitRows, agentRows].some(rows => rows.includes(r)));
  const names = (r, kind) => [...new Set((r.open || []).filter(i => i.kind === kind && !(kind === "owed" && i.project_match?.needs_review)).map(i => pdWho(i.who)).filter(Boolean))];
  const line = r => [projectOwed(r).length ? (names(r, "owed").length ? pdT("You owe: {names}", { names: names(r, "owed").join(pdT(", ")) }) + " · " : "") + pdT("{n} things", { n: projectOwed(r).length }) : "",
    names(r, "waiting").length ? pdT("Waiting on: {names}", { names: names(r, "waiting").join(pdT(", ")) }) : ""].filter(Boolean).join(" ／ ");
  const agents = r => pdT("{n} handed to agents", { n: (r.open || []).filter(i => i.kind === "agent" || i.kind === "answerable").length });
  const say = pdT("You owe {n} things across {p} projects and wait on others for {w}; {a} projects hold only agent instructions.",
    { n: owedRows.reduce((n, r) => n + projectOwed(r).length, 0), p: owedRows.length, w: all.reduce((n, r) => n + (r.open || []).filter(i => i.kind === "waiting").length, 0), a: agentRows.length });
  return [say, [
    projectColumn(pdT("You owe others"), pdT("the owner owes someone"), owedRows.sort(projectRank).map(r => projectCard(r, null, line(r)))),
    projectColumn(pdT("You wait on others"), pdT("someone owes the owner"), waitRows.sort(projectRank).map(r => projectCard(r, null, line(r)))),
    projectColumn(pdT("Only with agents"), pdT("instructions to agents"), agentRows.length ? [projectCompact(agentRows.sort(projectRank), agents)] : []),
    projectColumn(pdT("No open promise"), pdT("nothing open"), none.length ? [projectCompact(none.sort(projectRank))] : [])]];
}
function projectBoardDrop(all, notes) {
  const quiet = all.filter(r => ["quiet", "done"].includes(projectTier(r)));
  const held = r => projectOwed(r).length || (r.open || []).some(i => i.kind === "waiting");
  const drop = quiet.filter(r => !held(r)), open = quiet.filter(held), moving = all.filter(r => !quiet.includes(r));
  const say = el("span", {}, pdT("{n} projects have had no activity for 30 days and nobody waits on them: they {can}. {m} are quiet with a promise still open.", { n: drop.length, m: open.length, can: "\u0000" })
    .split("\u0000").flatMap((part, i) => i ? [el("span", { class: "pd-inf", text: pdT("can be set down") }), part] : [part]));
  const last = r => projectLast(r) ? pdDay(calendarDay(projectLast(r))) : "";
  return [say, [
    projectColumn(pdT("Can be set down"), pdT("quiet and nobody waiting"), drop.length ? [el("span", { class: "tag", text: pdT("Inference") }), projectCompact(drop.sort((a, b) => projectLast(a).localeCompare(projectLast(b))), last)] : []),
    projectColumn(pdT("Quiet, promises still open"), pdT("quiet, someone still waits"), open.map(r => projectCard(r, notes.get(r.path)))),
    projectColumn(pdT("Still moving"), pdT("activity within 30 days"), moving.length ? [projectCompact(moving.sort(projectRank), last)] : [])]];
}
function projectBoardSame(all, pairs) {
  const sessions = pairs.filter(p => p.kind === "sessions"), page = pairs.filter(p => p.kind === "page"), name = pairs.filter(p => p.kind === "name");
  const touched = new Set(pairs.flatMap(p => p.rows || [p.a, p.b]));
  const rest = all.filter(r => !touched.has(r));
  // Names first, as links; then the basis and REM's reading of it, in pencil.
  const pairCard = (rows, basis) => el("article", { class: "pd-card pd-pair" }, [
    el("div", { class: "pd-pair-names" }, rows.flatMap((r, i) => [i ? el("span", { class: "mut", text: rows.length === 2 ? " · " : pdT(", ") }) : null, el("a", { href: href(r), text: r.title })])),
    el("p", { class: "pd-card-extra" }, [el("span", { class: "pd-inf", text: basis }), el("span", { class: "tag", text: pdT("Inference") })])]);
  const say = pdT("{g} groups may each be one project: {s} share sessions, {t} are marked on their page, {u} have similar names; the other {rest} show no signal. All are inferences; REM merges nothing by itself.",
    { g: pairs.length, s: sessions.length, t: page.length, u: name.length, rest: rest.length });
  return [say, [
    projectColumn(pdT("Shared sessions"), pdT("85% or more of the smaller one's sessions"), sessions.map(p => pairCard([p.a, p.b], pdT(p.inside ? "{k} of {a}'s {n} sessions are {b}'s too · may be part of it" : "{k}/{n} sessions shared · may be one project", { a: p.a.title, b: p.b.title, k: p.k, n: p.n })))),
    projectColumn(pdT("Marked on the page"), pdT("REM's same_as suggestion"), page.map(p => pairCard([p.a, p.b], pdT("REM's same_as suggestion")))),
    projectColumn(pdT("Similar names"), pdT("a distinctive shared word"), name.map(p => pairCard(p.rows, pdT("all contain “{word}”", { word: p.word })))),
    projectColumn(pdT("No signal"), pdT("{n} projects", { n: rest.length }), rest.length ? [projectCompact(rest.sort(projectRank))] : [])]];
}
// By state the columns say it all; the other questions are inferences, so each keeps its one sentence.
function projectBoard(all, notes, pairs, ask) {
  if (ask === "state") {
    const cols = projectBoardState(all);
    return el("section", { class: "pd-board", "data-ask": ask }, [el("div", { class: "pd-cols" }, cols)]);
  }
  const [say, cols] = ask === "waiting" ? projectBoardWaiting(all, notes) : ask === "drop" ? projectBoardDrop(all, notes)
    : projectBoardSame(all, pairs);
  return el("section", { class: "pd-board", "data-ask": ask }, [el("p", { class: "pd-answer" }, [say]), el("div", { class: "pd-cols" }, cols)]);
}

// ---- the page ----
// Every count and row comes from all project pages, sub-projects included; nothing is merged.
function projectsView() {
  PD_SESSIONS = null;
  const state = pdParams(), all = listRows("projects").sort(projectRank);
  const asked = state.view === "board" && state.ask !== "state";
  const pairs = asked ? projectPairs(all) : [], notes = asked ? projectNotes(all, pairs) : new Map();
  const body = state.view === "list" ? projectList(all) : state.view === "board" ? projectBoard(all, notes, pairs, state.ask) : projectTimeline(all);
  document.getElementById("main").replaceChildren(el("div", { class: "pd", "data-view": state.view }, [projectHead(all, state), body]));
  const time = document.querySelector(".pa-time");
  if (time) paToday(time);
}

// The hero line is a glance: each part is cut at its first clause.
function firstClause(text) {
  const clause = plainLine(text).replace(/^\d{4}-\d{2}-\d{2}\s*[—–:：-]\s*/, "").split(/[，,；;。]|\s[—–]\s/)[0].trim();
  const unquoted = clause.split(/[：:]?\s*[“"「]/)[0].trim();
  const short = unquoted.length >= 6 ? unquoted : clause;
  if (short.length <= 40) return short;
  const cut = short.slice(0, 39), space = cut.lastIndexOf(" ");
  return (space > 24 ? cut.slice(0, space) : cut) + "…";
}
// The second half of a page title: same line on desktop, its own line on phone.
function pageStateSub(text) { return el("span", { class: "page-state-sub" }, [el("span", { class: "sep", text: " · " }), text]); }

