// ---- Today: one card per person ----------------------------------------------
// Python ranks the rows (today.py); a person's later rows join the card of their
// first one, so the order stays Python's and one reply can answer both.
function personGroups(entries) {
  const groups = new Map();
  for (const entry of entries) {
    const r = entry.who || entry.r;
    if (!groups.has(r.path)) groups.set(r.path, { r, entries: [] });
    groups.get(r.path).entries.push(entry);
  }
  return [...groups.values()];
}
function todayGroups(entries) {
  // A reply you sent, or one held for its 10 minutes, answers the person: they leave Today until Undo.
  // A promise gone stale is asked about at the side, not counted as someone waiting.
  entries = entries.filter(waitingOnYou);
  // The owner's own rows are re-homed or dropped before the five places are counted, so none is wasted.
  const home = list => list.map(entry => entry.r.path !== REM.owner ? entry : (who => who && { ...entry, who })(ownerCounterpart(entry))).filter(Boolean);
  const today = home(todayEntries(entries)), shown = new Set(today.slice(0, 5).map(doneKey));
  return personGroups([...today.slice(0, 5), ...home(morningEntries(entries.filter(entry => !shown.has(doneKey(entry)))))]);
}
// A row on your own page is waiting on whoever it names: the person who asked or is owed. When it
// names nobody it is your own note, and it is not a person waiting on you (build 3b review).
function ownerCounterpart(entry) {
  if (entry._counterpart !== undefined) return entry._counterpart;
  const recs = REM?.records || [];
  if (ownerCounterpart._c?.recs !== recs || ownerCounterpart._c.len !== recs.length) {
    const list = recs.filter(r => r.category === "people" && r.path !== REM.owner && !r.private)
      .map(person => ({ person, hasSpace: person.title.includes(" "), full: " " + obligationWords(person.title) + " ", first: " " + obligationWords(person.title.split(/\s+/)[0]) + " " }));
    ownerCounterpart._c = { recs, len: recs.length, list };
  }
  const list = ownerCounterpart._c.list;
  const named = list.find(item => threadCounterpart(entry, item.person));
  if (named) return (entry._counterpart = named.person);
  const text = " " + obligationWords(entry.t.originalText || entry.t.text) + " ";
  const full = list.filter(item => item.hasSpace && text.includes(item.full));
  if (full.length === 1) return (entry._counterpart = full[0].person);
  const first = list.filter(item => text.includes(item.first));
  return (entry._counterpart = first.length === 1 ? first[0].person : null);
}
function entryKeys(entry) { return (entry.members || [entry]).map(doneKey); }
// A yes/no the night prepared: an agent task waiting for the owner's approval.
function approvalTask(entry) {
  const keys = entryKeys(entry);
  return (REM.approval_outcomes || []).find(item => item.kind === "task" && item.keys?.some(key => keys.includes(key)));
}
// The most likely next step: a ready reply, a reply REM can write now, a yes/no,
// a reply to write; closing only what already looks handled. Never the mailbox.
const STEPS = ["send", "draft", "live", "approve", "write", "done", "open"];
function cardStep(entry) {
  const draft = threadDraft(entry), reply = queuedReply(entry);
  if (draft?.status === "prepared") return "send";
  if (reply?.state === "queued" && reply.thread) return REM.live ? "draft" : "live";
  if (REM.live && approvalTask(entry)) return "approve";
  if (draft?.status === "no_reply" || looksDone(entry)) return "done";
  // A snapshot cannot draft: an unanswered mail thread opens the live reader, never a dead end.
  if (!REM.live && (reply?.provider || threadKind(entry)?.mail) && !["replied", "task", "unarchived"].includes(reply?.state)) return "live";
  // A mail-app compose cannot join an existing thread; only a person with no thread gets one.
  if (threadContact(entry) && !queuedReply(entry)?.provider && !threadKind(entry)?.mail) return "write";
  return "open";
}
function groupStep(entries) {
  return entries.map(entry => ({ entry, step: cardStep(entry) })).sort((a, b) => STEPS.indexOf(a.step) - STEPS.indexOf(b.step))[0];
}
function stepAction({ entry, step }, group, cls) {
  const name = firstName(group.r);
  if (step === "draft") {
    const reply = queuedReply(entry);
    return draftNowButton(entry, { kind: reply.provider, thread: reply.thread }, null, cls);
  }
  if (step === "write") return mailtoLink(threadContact(entry), cls, t("Write to {name}", { name }), true);
  if (step === "live") return liveReaderAction(cls);
  if (step === "open") return null;  // the name above already opens the page; opening it does nothing about the item
  const button = el("button", { type: "button", class: cls + (step === "send" ? " review-reply" : ""),
    text: t({ send: "Review the reply to {name}", approve: "Approve", done: "Mark done" }[step], { name }) });
  button.onclick = event => {
    if (step === "send") return openDraft(event.currentTarget.closest(".qcard"));
    if (step === "approve") return openApprovalSheet([approvalTask(entry)]);
    closeEntries(event.currentTarget.closest(".qcard"), group.entries.filter(item => cardStep(item) === "done"));
  };
  return button;
}
// A snapshot cannot draft: the step is named and disabled; the page's one snapshot line says why (D-60).
function liveReaderAction(cls) {
  return el("button", { type: "button", class: cls, disabled: "", text: t("Draft in the live reader") });
}
// "Not done yet": REM decided the item looks handled by your reply; you say it is not. Kept on this device,
// it stays in Today and on the People list until it is marked done.
function keepOpen(entry) {
  notDoneKeys.add(doneKey(entry));
  readerStorage(notDoneStorageKey(), JSON.stringify([...notDoneKeys]));
  const scroll = window.scrollY;
  render();
  window.scrollTo(0, scroll);
}
function notDoneAction({ entry, step }) {
  if (step !== "done" || !looksDone(entry)) return null;
  // Kept on this device only, as in the live reader, but it answers REM's guess, so a snapshot says the same as its closes.
  const button = el("button", { type: "button", class: "btn-quiet", text: t("Not done yet"), ...snapshotWhy("This is an offline snapshot; open REM to mark it.") });
  button.onclick = () => keepOpen(entry);
  return button;
}
// Motion is stilled by the system's setting or by the reader's own Reduce motion switch: then nothing waits for it.
function motionStilled() {
  return matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.classList.contains("calm");
}
// A handled card slides right and fades, then the page re-renders with an Undo.
// A snapshot keeps no mark (stripDone says why), so E and the palette's Mark done do nothing there either.
function closeEntries(node, entries, state = "done", extra = null, until = null) {
  if (!entries.length || !liveHere()) return;
  node?.classList.add("leaving");
  leadAfter(node?.closest(".qcard"), entries.length);
  setTimeout(() => setDone(entries[0], true, state, entries, extra, until), motionStilled() ? 0 : 240);
}
// What is in front once `gone` rows of this card have left (#3072: «它又回到那个东西»). A card that empties gives its
// place to the card after it; the deck used to deal its first card again, the one he had just skipped past. A card
// with rows left stays where it is, its next row moving up.
function leadAfter(card, gone) {
  if (!card) return;
  const cards = [...document.querySelectorAll("#main .today-brief .qcard")], at = cards.indexOf(card);
  const empties = card.querySelectorAll(".qitem").length <= gone;
  todayLead = empties && cards.length > 1 ? cards[(at + 1) % cards.length].dataset.path : card.dataset.path;
}
// The card's head: the name (→ their page), their organisation as a chip, and the fuse: days overdue in red,
// or how long it has waited. Skip to the next card appears on hover (S), and on a card of several rows so
// does the tick that marks all of them done at once (E). A card of one row has no tick: it would only repeat that
// row's own Mark done (one control per row, owner 2026-11-11); E still closes it. In a snapshot it is disabled.
// tick: false where another control on the card already closes every row (personCard says when).
function cardHead(group, late, skippable, tick = group.entries.length > 1, pos = null) {
  const { r, entries } = group;
  const role = contactFields(r).find(f => f.label === "Role")?.value;
  const org = r.path === REM.owner ? "" : company(r), page = r.organisations?.length ? byPath(r.organisations[0]) : null;
  // Each glyph carries its word: a bare » beside the name read as nothing on a phone (sprint 14 #5).
  const doneWord = t(entries.length > 1 ? "Mark all done" : "Mark done");
  const done = tick
    ? el("button", { type: "button", class: "ibtn", "aria-label": doneWord + " · E", title: doneWord + " · E", ...snapshotWhy("This is an offline snapshot; open REM to mark it.") }, [icon("check"), el("span", { text: doneWord })]) : null;
  if (done) done.onclick = event => event.currentTarget.closest(".qcard").markDone();
  // ‹ 3 / 19 › at the top right, always visible (#3312 G): 下一张 used to be 11 px grey text that showed on hover.
  const step = (dir, label, key) => {
    const button = el("button", { type: "button", class: "ibtn qnav-step", "aria-label": t(label) + " · " + key, title: t(label) + " · " + key, text: dir < 0 ? "‹" : "›" });
    button.onclick = () => dealNext(dir);
    return button;
  };
  const skip = skippable ? el("span", { class: "qnav", role: "group", "aria-label": t("Next or previous card") }, [step(-1, "Previous card", "K"),
    pos ? el("span", { class: "qcount", text: pos.i + " / " + pos.n }) : null, step(1, "Next card", "J")]) : null;
  return el("div", { class: "qhead" }, [
    el("span", { class: "qmark" + (r.category === "orgs" ? " org" : ""), title: t(r.category === "orgs" ? "Organisation" : "Person") }),
    el("a", { class: "today-who", href: href(r), text: threadWho(r) }),
    org ? el(page ? "a" : "span", { class: "meta org-chip", title: role ? plainLine(role) : "", ...(page ? { href: href(page) } : {}) }, [el("span", { class: "org-mark", "aria-hidden": "true", text: org.trim()[0]?.toUpperCase() || "" }), org]) : null,
    el("span", { class: "qhead-acts" }, [done, skip]),
    qageNode(late, entries[0].t, r)]);
}
// On a 中文 reader the card speaks his language where REM already wrote it: the draft's gist.
function ownerLine(draft) {
  if (uiLanguage === "en" || draft?.private || !["prepared", "no_reply"].includes(draft?.status) || !/\p{Script=Han}/u.test(draft.gist || "")) return null;
  return t(draft.status === "no_reply" ? "No reply needed: " : "REM drafted: ") + draft.gist;
}
// handled: REM thinks the row is done and no green step on the card closes it, so its strip (Mark done, and the
// reason) shows without a hover. Where the green step closes it, that step is the card's lead and the strips wait
// for a hover: three visible Mark done on a phone read as noise (team, re-review of #2955).
function cardItem(entry, many, seen = new Set(), more = null, handled = false, lead = null) {
  const { words, context } = morningWords(entry.t.text, entry.r, entry.t);
  // One draft answering several items is said once, on the first of them.
  const draft = threadDraft(entry), own = draft && !seen.has(draft.id) ? ownerLine(draft) : null;
  if (own) seen.add(draft.id);
  // One Mark done per row (owner, 2026-11-11): the strip's, which closes the row, or the card when it is the only
  // one, by sliding it out.
  // E closes the whole card, so a row that is one of several does not claim the key.
  // Mark done, Not now and Ignore all leave this way (state), so the three closes look alike.
  const close = (event, state = "done", extra = null, until = null) => closeEntries(event.currentTarget.closest(many ? ".qitem" : ".qcard"), [entry], state, extra, until);
  // Its actions, context and source show on hover or focus (D-120); a tap opens them on a phone.
  const item = el("li", { class: "qitem" + (overdueDays(entry.t) ? " late" : "") + (handled ? " handled" : "") }, [
    own ? el("p", { class: "words own", text: own, title: words })
      : wordsLine("words", words, entry.r, [context ? el("span", { html: inline(context, entry.r.path) }) : null]),
    el("div", { class: "qmore" }, [el("div", { class: "qkind" }, [el("span", {}, [kindBadge(entry), many ? " · " + threadAge(entry.t) : null, blockerTag(entry.t)]), handOff(entry, close, lead), more]),
      alsoOn(entry.also), own ? null : draftNote(draft, entry), taskResult(entry),
      own ? el("p", { class: "qorig", lang: "en", text: words }) : null])]);
  item.onclick = event => { if (!event.target.closest("a, button, textarea, input, select, summary, .talk")) item.classList.toggle("show"); };
  return item;
}
function cardDraft(draft, group) {
  const n = group.entries.length;
  const sent = held => {
    // Sent at once: one reply answers every item on the card. Held: Undo must bring them all back.
    if (!held && n > 1) setDone(group.entries[0], true, "done", group.entries);
    todaySent = { name: threadWho(group.r), path: group.r.path, ...(held || {}) };
    const card = document.querySelector('.qcard[data-path="' + CSS.escape(group.r.path) + '"]');
    card?.classList.add("leaving");
    // The card after it comes forward, as after every action; when another reply is ready to send, that one does
    // (deckOrder puts it on top), so a run of Sends goes on without a card in between.
    leadAfter(card, n);
    if ([...document.querySelectorAll('#main .today-brief .qcard[data-step="send"]')].some(other => other !== card)) todayLead = null;
    setTimeout(render, motionStilled() ? 0 : 320);
  };
  const entry = group.entries[0], ask = morningWords(entry.t.text, entry.r, entry.t).words;
  const close = (event, state = "done", extra = null, until = null) => closeEntries(event.currentTarget.closest(".qcard"), [entry], state, extra, until);
  return el("div", { class: "qdraft" }, [n > 1 ? el("p", { class: "quiet-line", text: t(n === 2 ? "One reply can answer both." : "One reply can answer all {n}.", { n }) }) : null,
    replyDraftCard(draft, sent, group.r, { ask, triage: n === 1 && liveHere() ? handOff(entry, close, null, true) : null })]);
}
// A snapshot can show the work but not do it: one plain line per page says so, never a command (D-60).
function snapshotLine() {
  return REM.live ? null : liveReaderLine("This is a snapshot: sending and handing work to an agent happen in the live reader.");
}
// One sentence and, when this computer has a live reader, the link to it.
function liveReaderLine(words) {
  return el("p", { class: "snapshot-line" }, [t(words), REM.live_link ? " " : null,
    REM.live_link ? el("a", { href: REM.live_link, text: t("Open the live reader") }) : null]);
}
// After Send: who it went to and, while the 10-minute hold lasts, the one Undo.
let todaySent = null, shownCount = 0;
function sentNote() {
  if (!todaySent) return null;
  const held = todaySent.ids && Date.parse(todaySent.release_at) > Date.now();
  const status = el("span", { role: "status" }), undo = el("button", { type: "button", class: "btn-quiet", text: t("Undo") });
  undo.onclick = async () => {
    undo.disabled = true;
    const reply = await approvalRequest({ action: "undo", ids: todaySent.ids }).catch(error => ({ error: error.message }));
    const cancelled = (reply.results || []).filter(value => value.status === "cancelled").map(value => value.id);
    if (!cancelled.length) { status.textContent = reply.error || (reply.results || []).map(approvalStatus).join(" · "); undo.disabled = false; return; }
    for (const item of (REM.approval_pending || []).filter(item => cancelled.includes(item.id))) {
      REM.approval_outcomes = [...(REM.approval_outcomes || []), item];
      if (item.draft_id) REM.drafts = (REM.drafts || []).map(d => d.id === item.draft_id ? { ...d, status: "prepared" } : d);
    }
    REM.approval_pending = (REM.approval_pending || []).filter(item => !cancelled.includes(item.id));
    todayLead = todaySent.path;  // the reply he took back is in front again
    todaySent = null;
    render();
  };
  if (held) {
    clearTimeout(sentNote.timer);
    sentNote.timer = setTimeout(() => document.querySelector(".qsent")?.replaceWith(sentNote() || ""), Date.parse(todaySent.release_at) - Date.now() + 50);
  }
  return el("li", { class: "qsent" }, [el("p", { class: "lede", text: held ? t("Sending to {name} at {time}.", { name: todaySent.name, time: fmtTime(todaySent.release_at) })
    : t("Sent to {name}.", { name: todaySent.name }) }),
    el("p", { class: "meta" }, held ? [t("You can still undo it."), " ", undo, " ", status]
      : [t(todaySent.ids ? "Hold ended. Delivery continues from the Host." : "It went out now and cannot be undone.")])]);
}
// 交给 Codex / 交给 Claude (D-100) on every unfinished row: REM starts the work now, with that agent
// and full access. The row then says where the work is, in place: working (Stop, Take back), then See result.
const AGENT_NAMES = { codex: "Codex", claude: "Claude" }, ACTIVE_TASK = ["queued", "starting", "running"];
// An open conversation outlives a redraw: the same panel, its turns and its typed words, goes back in place.
const OPEN_TALKS = new Map();
function todayRow(entry) {
  if (entry.row) return entry.row;
  const key = doneKey(entry);
  return (REM.today_queue || []).find(row => (row.keys || [row.key]).includes(key));
}
function obligationKey(entry) { return todayRow(entry)?.keys?.[0] || doneKey(entry); }
// The night's prepared task, or the run the owner started from any list (reader.py puts it on the row).
function rowTask(entry) {
  const key = obligationKey(entry);
  if (PENDING_HANDOFFS.has(key)) return PENDING_HANDOFFS.get(key);
  const row = todayRow(entry);
  return row?.outcome?.kind === "task" ? row.outcome.task : row?.task || null;
}
function keepTask(entry, task) {
  const row = todayRow(entry);
  if (task?.sending || task === null || !row) PENDING_HANDOFFS.set(obligationKey(entry), task);
  else PENDING_HANDOFFS.delete(obligationKey(entry));
  if (!row) return;
  if (row.outcome?.kind === "task") row.outcome = { ...row.outcome, task: task || { id: row.outcome.task.id, prompt: row.outcome.task.prompt, result: "ready" } };
  else row.task = task;
}
function handed(task) { return !!task?.result && !["ready", "waiting"].includes(task.result); }
function hostPost(url, body) {
  return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    .then(async response => { hostFound(); return { ...await response.json().catch(() => ({})), ok: response.ok, code: response.status }; })
    .catch(() => { hostLost(); return { ok: false, code: 0 }; });
}
// A request that never reached the Host (status 0) means the Host this page came from is gone: restarted for an
// upgrade, or the Mac slept. The page says that once, in a quiet bar over the page with one Reconnect, and the
// click that found out says the same, never "REM is busy" (#3139, owner 2026-11-19: «有的时候我点那调查的时候说
// REM 暂时没有回应 过会儿再试 这是什么原因»). The bar leaves when the Host answers again.
Object.assign(UI.zh, { "This page lost touch with REM (it was just restarted).": "这页连不上 REM 了（REM 刚重启过）。", "Reconnect": "重新连接",
  "This page lost touch with REM (it was just restarted), so nothing was handed over. Reconnect and try again.": "这页连不上 REM 了（REM 刚重启过），所以没有交出去。重新连接后再试。" });
const HOST_LOST_WORDS = "This page lost touch with REM (it was just restarted).";
function hostLost() {
  if (!liveHere() || document.getElementById("host-lost")) return;
  const again = el("button", { type: "button", class: "lang-act", text: t("Reconnect") });
  again.onclick = () => reconnect();  // onto the new build when an upgrade restarted the Host
  document.body.appendChild(el("div", { id: "host-lost", class: "host-lost", role: "status" }, [el("span", { text: t(HOST_LOST_WORDS) }), again]));
}
function hostFound() { document.getElementById("host-lost")?.remove(); }
function liveHere() { return REM.live && location.protocol !== "file:"; }
// mark: how this row's Mark done closes it, when the page has its own way (Today slides the row out).
// lead: on a Today card, which of the row's controls is its one primary ("task", "done" or null); see todayStrip.
// The single-item reply footer shares the row's talk panel and leaves status notes on the row.
const ROW_TALK_SLOTS = new Map();
function handOff(entry, mark, lead, draftFooter = false) {
  const key = obligationKey(entry);
  // A Today card's handed row: one primary step, the three closes in words, the rest under a worded More (#3312).
  // An unhanded row already has one lead and its hand-offs stay visible words (D-100), so it keeps its strip.
  const compact = !!mark && !draftFooter;
  const parts = () => handed(rowTask(entry)) ? handState(entry, show, panel, mark, compact) : handButtons(entry, show, panel, mark, lead, draftFooter);
  const show = () => line.replaceChildren(...parts());
  const panel = draftFooter ? ROW_TALK_SLOTS.get(key) || el("div", { class: "talk-slot" }) : el("div", { class: "talk-slot" }, [OPEN_TALKS.get(key)]);
  if (!draftFooter) ROW_TALK_SLOTS.set(key, panel);
  const line = el("div", { class: "handoff-line" }, parts());
  line.handoffKey = key; line.handoffRefresh = show;
  // What the row has to say about itself before anything is pressed: a hand-off the Host refused, a put-off that is back.
  return el("div", { class: "handoff" }, draftFooter ? [line] : [line, panel, handFailedNote(entry), putOffNote(entry)]);
}
// 标为完成 sits in the strip on every row, before and after a hand-off (owner, 2026-11-11: «为什么不能标记
// 已完成呢？标记完成不在那个里面啊»). It is the row's own setDone, so a failure or an offline save reads the
// same as everywhere else. The strip is only drawn on unfinished rows (Waiting on you and Today both leave a
// done row out, and its Undo is the page's done notice), so there is no done state to show here.
// Closing an item is Today's core verb (owner, 2026-11-12: «忽略和标记完成很重要，有的任务就是线下说了，或者现在不需要
// 处理，或者广告要忽略»), so the strip says three ways to close it, in words, never an icon (owner: «你要有个文字按钮»):
// 标为完成 — handled, settled offline included (state done);
// 暂不处理 — not needed now: the notebook's "skipped", which leaves Today and returns when new mail arrives on the thread;
// 忽略 — an ad or a notification: the state "ignored", which closes like done and never returns, and reads 已忽略. Its
// notice then offers, in words, to stop the row's sender (owner, 2026-11-13: «广告要忽略»). It never stops a sender by
// itself: a relay address carries many different people, so the owner taps it.
// An ask (让 Codex 查), or a row with no record, is not an item and has nothing to close.
// A snapshot shows the three words but cannot keep them: a file:// page's storage is not the live reader's, and
// nothing carries a mark from one to the other, so a close there would vanish (#2990 review). They are drawn
// disabled, each saying why, and the card or fold says it once in words (snapshotCloseLine).
function stripDone(entry, mark, lead = false) {
  if (entry.ask || !entry.r || !entry.t) return [];
  // mark: the page's way of closing (Today slides the row out); all three use it, so they leave alike.
  const close = (state, extra = null, until = null) => event => mark ? mark(event, state, extra, until) : setDone(entry, true, state, [entry], extra, until);
  const why = snapshotWhy("This is an offline snapshot; open REM to mark it.");
  const done = el("button", { type: "button", class: "btn-quiet strip-done" + (lead ? " strip-lead" : ""), text: t("Mark done"), ...why });
  done.onclick = close("done");
  const later = el("button", { type: "button", class: "btn-quiet strip-later", "aria-haspopup": "true", text: t("Not now"), ...why });
  later.onclick = event => laterChooser(event.currentTarget.closest(".handoff-line"), until => close("skipped", null, until));
  const ignore = el("button", { type: "button", class: "btn-quiet strip-ignore", text: t("Ignore"), ...why });
  const sender = todayRow(entry)?.sender;
  ignore.onclick = close("ignored", sender ? () => stopSenderButton(entry, sender) : null);
  return [done, later, ignore];
}
// Not now asks when (#3072: «暂不处理应该是比如过几天再看，或者今晚再看»). Before this it had no date: the item came
// back only when new mail arrived on its thread, and nothing on the page said so after the notice left. The four
// choices are moments on the reader's clock; new mail still brings the item back sooner. Tonight is 18:00 and is
// not offered after it; next week is the coming Monday.
function laterChoices() {
  const now = new Date(clockNow()), at = (days, hour = 0) => new Date(now.getFullYear(), now.getMonth(), now.getDate() + days, hour).toISOString();
  return [now.getHours() < 18 ? ["Tonight", at(0, 18)] : null, ["Tomorrow", at(1)], ["In 3 days", at(3)],
    ["Next week", at((8 - now.getDay()) % 7 || 7)]].filter(Boolean);
}
// "back tonight at 18:00", "back on Mon 5 Oct": the same words in the notice, the Put off list and the returned card.
function backWords(until) {
  const at = new Date(until), day = { weekday: "short", day: "numeric", month: "short" };
  return localDay(at) === localDay(clockNow()) ? t("back tonight at {time}", { time: at.toLocaleTimeString(uiLocale(), { hour: "2-digit", minute: "2-digit" }) })
    : t("back on {date}", { date: at.toLocaleDateString(uiLocale(), day) });
}
// The choices take the strip's place, in words, and Cancel or Escape puts the strip back with the focus on Not now.
function laterChooser(line, choose) {
  const kept = [...line.childNodes];
  const back = () => { line.replaceChildren(...kept); line.onkeydown = null; line.querySelector(".strip-later")?.focus(); };
  const choices = laterChoices().map(([label, until]) => {
    const button = el("button", { type: "button", class: "btn-quiet later-choice", text: line.closest(".draft-triage") ? t(label) + " · " + new Date(until).toLocaleDateString(uiLocale(), {weekday: "short", month: "short", day: "numeric"}) : t(label) });
    button.onclick = choose(until);
    return button;
  });
  const cancel = el("button", { type: "button", class: "btn-quiet later-cancel", text: t("Cancel") });
  cancel.onclick = back;
  line.replaceChildren(el("span", { class: "later-ask", text: t("Bring it back:") }), ...dotted([...choices, cancel]));
  line.onkeydown = event => { if (event.key === "Escape") { event.stopPropagation(); back(); } };
  choices[0].focus();
}
// Why a snapshot's button does nothing, said on the button (its title, and for a screen reader aria-describedby,
// pointing at the page's hidden sentence for that reason, whyNotes) and, for the closes, once in words on the card,
// band or fold. why: a close's reason, else a hand-off's.
function snapshotWhy(why) {
  return liveHere() ? {} : { disabled: "disabled", title: t(why), "aria-describedby": why.includes("offline") ? "why-close" : "why-hand" };
}
function whyNotes() {
  return liveHere() ? [] : [el("span", { id: "why-close", class: "visually-hidden", text: t("This is an offline snapshot; open REM to mark it.") }),
    el("span", { id: "why-hand", class: "visually-hidden", text: t("Handing work to an agent happens in the live reader.") })];
}
// The open-REM link is the live reader's, when this computer has one.
function snapshotCloseLine() {
  return liveHere() ? null : el("p", { class: "close-why" }, [t("This is an offline snapshot; open REM to mark it."), REM.live_link ? " " : null,
    REM.live_link ? el("a", { href: REM.live_link, text: t("Open the live reader") }) : null]);
}
// The notice's "stop showing mail from x": once saved, the notice says what was ignored and its one Undo
// reopens the item and lets the sender back. A save the Host refused says so, with Try again, and changes nothing.
function stopSenderButton(entry, address) {
  const shown = shownAddress(address, entry);
  const button = el("button", { type: "button", class: "sender-ignore", text: t("Stop showing mail from {address}", { address: shown }) });
  const stop = async () => {
    button.disabled = true;
    if (!await saveIgnoredSender(address, true)) {
      button.disabled = false;
      return notSavedNotice(retryReplacing(stop), null);
    }
    const notice = document.getElementById("done-notice"), undo = el("button", { type: "button", text: t("Undo") });
    const back = async () => {
      if (!await saveIgnoredSender(address, false)) return notSavedNotice(retryReplacing(back), null);
      document.getElementById("done-notice")?.remove();
      setDone(entry, false, "done", [entry]);
      focusRaisedCard();
    };
    undo.onclick = back;
    notice?.replaceChildren(t("Ignored · mail from {address} no longer shows here", { address: shown }), " · ", undo, " · ", t("Saved in notebook"));
    undo.focus({ preventScroll: true });
  };
  button.onclick = stop;
  return button;
}
// Try again replaces the notice's earlier Not saved line instead of adding another.
function retryReplacing(retry) {
  return () => { document.querySelector("#done-notice [role=alert]")?.remove(); retry(); };
}
// With labelled passages hidden, an address shows only its domain: always in Settings, which cannot tell
// which row it came from, and in a notice when its row carries a [personal] or [sensitive] passage.
function shownAddress(address, entry = null) {
  const hidden = document.documentElement.classList.contains("hide-private");
  return hidden && (!entry || hasPrivacy(entry.t.originalText || entry.t.text)) ? "•••@" + address.split("@").pop() : address;
}
// The Host's list comes back whole; the page redraws from it, so every row from that sender goes or returns together.
async function saveIgnoredSender(address, ignored) {
  const reply = await hostPost("/rem/sender", { address, ignored });
  if (!reply.ok) return false;
  REM.ignored_senders = reply.ignored || {};
  threadEntries.cached = null;
  render();
  if (document.getElementById("settings")?.open) renderSettings();
  return true;
}
// One line of actions, a quiet dot between each: 标为完成 · 暂不处理 · 忽略 · 交给 Codex · 交给 Claude · 更多 ▾
function dotted(nodes) {
  return nodes.filter(Boolean).flatMap((node, i) => i ? [el("span", { class: "sep", "aria-hidden": "true", text: "·" }), node] : [node]);
}
// One rule for every dotted row (Mac review of rc30: "· 在 Codex 里接着做" started a line): a "·" whose neighbours sit
// on different lines is where the row wrapped, so it is hidden, at either end of the break. Rechecked whenever the
// page changes or resizes, so rows redrawn in place (a hand-off's steps) stay tidy.
function tidyDots(root = document.getElementById("main")) {
  if (!root?.querySelectorAll) return;
  for (const sep of root.querySelectorAll(".sep")) {
    sep.classList.remove("sep-wrap");
    const prev = sep.previousElementSibling, next = sep.nextElementSibling;
    if (!prev || !next || !sep.offsetParent) continue;
    const a = prev.getBoundingClientRect(), b = next.getBoundingClientRect();
    if (b.top >= a.bottom - 2 || b.left < a.left) sep.classList.add("sep-wrap");
  }
}
let tidyFrame = 0;
function tidyDotsSoon() { cancelAnimationFrame(tidyFrame); tidyFrame = requestAnimationFrame(() => tidyDots()); }
if (typeof MutationObserver === "function" && typeof document !== "undefined" && document.getElementById?.("main")) {
  new MutationObserver(tidyDotsSoon).observe(document.getElementById("main"), { childList: true, subtree: true });
  addEventListener("resize", tidyDotsSoon);
}
// One primary step per Today card, the rest one click away (#3312, sprint T3): the card offers the step that moves it
// on, bold, and the three closes stay in words beside it (owner, 2026-11-11/12: «标记完成不在那个里面啊», «忽略和标记
// 完成很重要»; the Ignore-everywhere tests pin it). Everything else, the agents, the terminal, the result, take back,
// show more, waits under a worded 更多操作 disclosure; Escape and a click outside fold it back. The Codex to-do rows had
// eight links in one line (Mac rc11 pass); now it is the status, one step, the three closes and 更多操作.
function oneAction(status, primary, keep, rest) {
  const others = [...new Set(rest)].filter(node => node && node !== primary && !keep.includes(node));
  primary?.classList?.add("strip-lead");
  // One thing left over is shown as itself: a menu holding one item is a click for nothing (art director, #3371).
  if (others.length === 1) return [...(status ? [status] : []), ...dotted([primary, ...keep.filter(node => node !== primary), others[0]])];
  const more = others.length > 1 ? el("details", { class: "row-more" }, [
    el("summary", { class: "row-more-btn", text: t("More actions") }),  // a word, never a bare glyph (D-100)
    el("div", { class: "row-more-menu" }, others)]) : null;
  more?.addEventListener?.("keydown", event => { if (event.key === "Escape" && more.open) { more.open = false; more.querySelector("summary").focus(); } });
  if (more && !oneAction.listening && typeof document !== "undefined" && document.addEventListener) {
    oneAction.listening = true;  // one page-wide listener: a click outside folds any open ⋯ back
    document.addEventListener("click", event => {
      for (const open of document.querySelectorAll(".row-more[open]")) if (!open.contains(event.target)) open.open = false;
    });
  }
  return [...(status ? [status] : []), ...dotted([primary, ...keep.filter(node => node !== primary), more])];
}
function handButtons(entry, show, panel, mark, lead, draftFooter = false) {
  const status = el("span", { class: "handoff-status", role: "status" });
  const buttons = Object.entries(AGENT_NAMES).map(([agent, name]) => {
    const button = el("button", { type: "button", class: "btn-quiet" + (lead === "task" && agent === "codex" ? " strip-lead" : ""), "data-agent": agent,
      text: t(entry.ask ? "Ask {agent} to look" : "Hand to {agent}", { agent: draftFooter && agent === "claude" ? "Claude Code" : name }), ...snapshotWhy("Handing work to an agent happens in the live reader.") });
    button.onclick = event => handOver(entry, agent, show, event?.currentTarget?.closest(".qcard"), status);
    return button;
  });
  const talk = entry.ask ? null : talkMenu(entry, panel), closes = stripDone(entry, mark, lead === "done");
  if (draftFooter) return [el("div", {class: "triage-row"}, closes), el("div", {class: "triage-row"}, buttons),
    moreButton(entry, talk), status].filter(Boolean);
  return [...dotted(todayStrip(buttons, talk, closes, entry)), status];
}
// The click is the hand-off (#3072: «点了交给 Codex 就显示正在交给 Codex，也不跳到下一张»). The row is the agent's from
// that moment: on a Today card it leaves the deck and the next card comes forward, and the work shows in the one
// strip above the deck (workStrip); in a list the row says so in place. It used to wait for the Host's answer to
// POST /rem/task with the buttons greyed, and that answer comes only after the agent's process has started. A
// hand-off the Host refuses takes the row back: the card returns in front and says why (handFailedNote). A page
// that cannot reach its Host at all says to open REM again, in words and never as a command to copy (D-60).
const HAND_FAILED = new Map(), PENDING_HANDOFFS = new Map();
function handRefusal(code) {
  return code === 400 ? "REM did not recognise this item. Reload the page and try again."
    : code === 401 ? "Your session expired. Reload the page."
    : code === 409 ? "This item has changed. Reload and try again."
    : code === 0 ? "This page lost touch with REM (it was just restarted), so nothing was handed over. Reconnect and try again."
    : "REM is not answering right now. Try again in a moment.";
}
function handOver(entry, agent, show, card, status) {
  const key = obligationKey(entry), onDeck = card && railActive() === "today";
  const redraw = () => onDeck && railActive() === "today" ? redrawKeepingScroll() : refreshHandoff(entry, show);
  HAND_FAILED.delete(key);
  if (!todayRow(entry)) status.textContent = taskStatus({ result: "starting", agent });  // a row the queue does not hold keeps its words in place
  keepTask(entry, { result: "starting", agent, queued_at: new Date(clockNow()).toISOString(), sending: true });
  if (onDeck) { workOpen = true; leadAfter(card, card.querySelectorAll(".qitem").length); }
  redraw();
  return hostPost("/rem/task", { action: "run", key, agent }).then(({ ok, code, ...task }) => {
    // The row turned at the click; any answer but a run takes it back and says why (a Host that never answered,
    // code 0, included), so a card never sits on "working" for a hand-off that did not happen.
    // A gateway's 502-504 may come after the Host started the run (Codex's app-server is slow to answer, #3147):
    // the row stays turned and asks the Host, three times; anything else takes it back at once.
    const refuse = why => { keepTask(entry, null); HAND_FAILED.set(key, { agent, why }); if (onDeck) todayLead = card.dataset.path;
      if (!todayRow(entry)) status.textContent = t(why); redraw(); };
    if (ok) keepTask(entry, { ...rowTask(entry), ...task, sending: false, agent: task.agent || agent });
    else if ([502, 503, 504].includes(code)) return confirmHandoff(entry, redraw, () => refuse(handRefusal(code)));
    else return refuse(handRefusal(code));
    redraw();
  });
}
function confirmHandoff(entry, redraw, giveUp, tries = 3) {
  setTimeout(async () => {
    const pending = rowTask(entry);
    if (!pending?.sending) return;
    const { ok, ...task } = await hostPost('/rem/task', { action: 'status', key: obligationKey(entry) });
    if (ok && task.id && handed(task)) { keepTask(entry, { ...pending, ...task, sending: false }); redraw(); }
    else if (tries > 1) confirmHandoff(entry, redraw, giveUp, tries - 1);
    else giveUp();
  }, 2000);
}
function taskElapsed(at) {
  const seconds = Math.max(0, Math.floor((clockNow() - Date.parse(at)) / 1000) || 0);
  return Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0');
}
function taskFailure(task) {
  if (task.failure) return task.failure;
  const agent = AGENT_NAMES[task.agent || 'codex'];
  if (task.reason?.includes('Operation not permitted') && agent === 'Codex') return 'Codex 当时无法启动（已修复），可以重试';
  return task.result === 'timed-out' ? `${agent} 超时了，可以重试` : task.result === 'stopped' ? `${agent} 已停止，可以重试` : `${agent} 这次未能完成，可以重试`;
}
// A run's one-line summary goes on its row only in the reader's language: runs from before the language rule wrote
// English headings ("… — written feedback preparation", rc34 check). The row already says the item in its own words;
// the agent's heading stays inside the report.
function summaryHere(summary) {
  const clean = summary ? String(summary).replace(/[ \t]*[\[［](?:personal|sensitive)[\]］]/gi, "").trim() : "";
  return clean && (uiLanguage !== "zh" || /[\u4e00-\u9fff]{2}/.test(clean)) ? clean : "";
}
function taskStatus(task, entry = null) {
  const pLevel = typeof privacyLevel === "string" ? privacyLevel : "all";
  const rawCtx = [entry?.t?.originalText || entry?.t?.text || "", task?.summary || "", task?.reason || "", task?.reply || "", task?.step?.summary || ""].join(" ");
  const level = /[\[［]sensitive[\]］]/i.test(rawCtx) ? "sensitive" : (/[\[［]personal[\]］]/i.test(rawCtx) || entry?.r?.private ? "personal" : "");
  if (level && pLevel === "public") return "";
  const agent = AGENT_NAMES[task.agent || 'codex'];
  if (ACTIVE_TASK.includes(task.result)) return t('{agent} is working', { agent }) + ' · ' + taskElapsed(task.started_at || task.queued_at) + (taskStep(task) && !(level === "sensitive" && pLevel === "cover") ? ' · ' + taskStep(task) : '');
  // State in words first (owner: words for state), then what it found in one line (#3436: never leak sensitive summary at cover/public).
  const sum = level === "sensitive" && pLevel === "cover" ? "" : summaryHere(task.summary);
  return task.result === 'completed' ? t('{agent} finished', { agent }) + (sum ? ' · ' + sum : '') : taskFailure(task);
}
function taskStatusNode(task, entry = null) {
  const pLevel = typeof privacyLevel === "string" ? privacyLevel : "all";
  const rawCtx = [entry?.t?.originalText || entry?.t?.text || "", task?.summary || "", task?.reason || "", task?.reply || "", task?.step?.summary || ""].join(" ");
  const level = /[\[［]sensitive[\]］]/i.test(rawCtx) ? "sensitive" : (/[\[［]personal[\]］]/i.test(rawCtx) || entry?.r?.private ? "personal" : "");
  if (level && pLevel === "public") return null;
  if (ACTIVE_TASK.includes(task.result)) startTaskClock();
  const agent = AGENT_NAMES[task.agent || 'codex'], sum = summaryHere(task.summary);
  if (task.result === 'completed' && sum && level === 'sensitive' && pLevel === 'cover') {
    return el('span', { class: 'handed', role: 'status' }, [
      t('{agent} finished', { agent }) + ' · ',
      el('span', { class: 'private', 'data-level': 'sensitive', text: sum })
    ]);
  }
  return el('span', { class: 'handed' + (level ? ' private' : ''), ...(level ? { 'data-level': level } : {}), role: 'status', text: taskStatus(task, entry),
    ...(ACTIVE_TASK.includes(task.result) ? { 'data-task-start': task.started_at || task.queued_at || new Date(clockNow()).toISOString(),
      'data-task-agent': task.agent || 'codex', 'data-task-step': level === 'sensitive' && pLevel === 'cover' ? '' : taskStep(task) } : {}) });
}
// The running rows' elapsed clocks tick once a second, started by the first running row drawn (not at load).
function startTaskClock() {
  if (startTaskClock.timer || typeof document === "undefined" || typeof document.querySelectorAll !== "function") return;
  startTaskClock.timer = setInterval(() => document.querySelectorAll('[data-task-start]').forEach(node => {
    node.textContent = t('{agent} is working', { agent: AGENT_NAMES[node.dataset.taskAgent] }) + ' · ' + taskElapsed(node.dataset.taskStart) + (node.dataset.taskStep ? ' · ' + node.dataset.taskStep : '');
  }), 1000);
}

function refreshHandoff(entry, fallback) {
  const lines = typeof document === 'undefined' ? [] : [...document.querySelectorAll('.handoff-line')].filter(line => line.handoffKey === obligationKey(entry));
  if (lines.length) lines.forEach(line => line.handoffRefresh());
  else fallback();
}

function handFailedNote(entry) {
  const failed = HAND_FAILED.get(obligationKey(entry));
  return failed ? el("p", { class: "hand-failed", role: "alert", text: t("{agent} did not take this: {why}", { agent: AGENT_NAMES[failed.agent], why: t(failed.why) }) }) : null;
}
// An agent holds the row: handed over and not finished. Such a row is out of the deck and in the work strip.
function agentBusy(entry) { return ACTIVE_TASK.includes(rowTask(entry)?.result); }
function sinceWords(at) {
  const minutes = Math.floor((clockNow() - Date.parse(at)) / 60000);
  return isNaN(minutes) ? "" : minutes < 1 ? t("started just now") : minutes < 60 ? t("started {n} min ago", { n: minutes }) : t("started {time}", { time: fmtTime(at) });
}
// Work that goes on after a click, in one place off the cards: every row an agent holds, and every row an agent
// finished or dropped today, read from the rows' own receipts (reader.py puts each task's receipt on its row; no
// second store). One line of words; it opens to the rows, each with its item, what the agent is doing and since
// when, Stop and Take back while it runs, then See result. A finished row's card is back in the deck by then.
let workOpen = false;
function workRows() {
  const pLevel = typeof privacyLevel === "string" ? privacyLevel : "all";
  return threadEntries().filter(entry => !isDone(entry)).map(entry => ({ entry, task: rowTask(entry) }))
    .filter(({ entry, task }) => {
      if (!handed(task)) return false;
      if (pLevel === "public" && (/[\[［](?:personal|sensitive)[\]］]/i.test([entry?.t?.originalText || entry?.t?.text || "", task?.summary || "", task?.reason || ""].join(" ")) || entry?.r?.private)) return false;
      return ACTIVE_TASK.includes(task.result) || task.result !== "completed" || task.finished_at && localDay(task.finished_at) === localDay(clockNow());
    });
}
function workSummary(rows) {
  const count = (agent, test) => rows.filter(({ task }) => (task.agent || "codex") === agent && test(task)).length;
  const say = (n, one, many, agent, more = "") => n ? t(n === 1 ? one : many, { n, agent: AGENT_NAMES[agent] }) + more : null;
  return Object.keys(AGENT_NAMES).flatMap(agent => {
    const first = rows.filter(({ task }) => (task.agent || "codex") === agent && ACTIVE_TASK.includes(task.result))
      .map(({ task }) => task.started_at || task.queued_at).filter(Boolean).sort()[0];
    return [say(count(agent, task => ACTIVE_TASK.includes(task.result)), "{agent} is working on 1 thing", "{agent} is working on {n} things", agent, first ? " · " + taskElapsed(first) : ""),
      say(count(agent, task => task.result === "completed"), "{agent} finished 1 thing", "{agent} finished {n} things", agent),
      // Beside "working on 1 thing", a stopped one is another task: «正在做 1 件事 · 有 1 件事没做完就停了» read as one
      // task both running and stopped (#3396).
      count(agent, task => ACTIVE_TASK.includes(task.result))
        ? say(count(agent, task => !ACTIVE_TASK.includes(task.result) && task.result !== "completed"), "another 1 stopped before finishing", "another {n} stopped before finishing", agent)
        : say(count(agent, task => !ACTIVE_TASK.includes(task.result) && task.result !== "completed"), "{agent} stopped before finishing 1 thing", "{agent} stopped before finishing {n} things", agent)];
  }).filter(Boolean).join(" · ");
}
// What the agent is doing now (#3138): the latest step its run reported, in the Work Room's safe words.
function taskStep(task) {
  const step = task.step;
  return step?.summary ? t(step.summary) : "";
}
// Watch the running session in Terminal, or carry on with the finished one in its agent: on this computer only.
function terminalButtons(entry, task, active) {
  const agent = AGENT_NAMES[task.agent || "codex"] || task.agent;
  const want = active ? (task.tmux ? "watch" : null) : (task.session_id ? "resume" : null);
  if (!want) return [];
  if (!liveHere()) return [el("span", { class: "handoff-status", text: t("Watching and continuing happen on your computer.") })];
  const button = el("button", { type: "button", class: "btn-quiet task-" + want, text: want === "watch" ? t("Watch in Terminal") : t("Continue in {agent}", { agent }) });
  button.onclick = async () => {
    button.disabled = true;
    const { ok, error } = await hostPost("/rem/task", { id: task.id, action: want });
    button.disabled = false;
    if (!ok) button.textContent = error || t("Could not do that. Try again.");
  };
  return [button];
}
function workRow({ entry, task }) {
  const agent = AGENT_NAMES[task.agent || "codex"] || task.agent, active = ACTIVE_TASK.includes(task.result), who = entry.who || entry.r;
  const act = (action, label) => {
    const button = el("button", { type: "button", class: "btn-quiet", text: label });
    button.onclick = async () => {
      button.disabled = true;
      const { ok, code, ...reply } = await hostPost("/rem/task", { id: task.id, action });
      if (!ok) { button.disabled = false; button.textContent = t("Could not do that. Try again."); return; }
      keepTask(entry, action === "undo" ? null : { ...task, ...reply });
      if (action === "undo") todayLead = who.path;
      redrawKeepingScroll();
    };
    return button;
  };
  const show = el("button", { type: "button", class: "btn-quiet", text: t("Show its card") });
  show.onclick = () => { todayLead = who.path; redrawKeepingScroll(); focusRaisedCard(); };
  const [see] = active ? [null] : seeResult(task);
  return el("li", { class: "work-row" }, [el("a", { href: href(who), text: threadWho(who) }),
    wordsLine("work-what", morningWords(entry.t.text, entry.r, entry.t).words, entry.r, []),
    el("p", { class: "work-state" }, dotted([taskStatusNode(task, entry),
      ...(task.sending ? [] : active ? [...terminalButtons(entry, task, true), act("stop", t("Stop")), act("undo", t("Take back from {agent}", { agent }))]
        : [taskPrimary(entry, task, redrawKeepingScroll), see, ...terminalButtons(entry, task, false), show, act("undo", t("Take back from {agent}", { agent }))])]))]);
}
function workStrip() {
  const rows = liveHere() ? workRows() : [];
  if (!rows.length) return null;
  const strip = el("details", { id: "work-strip", class: "work-strip" }, [el("summary", { text: workSummary(rows) }), el("ul", { class: "work-rows" }, rows.map(workRow))]);
  const failed = rows.filter(({ task }) => !ACTIVE_TASK.includes(task.result) && task.result !== 'completed');
  if (failed.length) {
    const clear = el('button', { type: 'button', class: 'btn-quiet clear-failed', text: t('Clear failed runs') });
    clear.onclick = async () => {
      const reply = await hostPost('/rem/task', { action: 'clear_failed' });
      if (!reply.ok) { clear.textContent = t('Could not do that. Try again.'); return; }
      for (const { entry, task } of failed) if (reply.cleared.includes(task.id)) keepTask(entry, null);
      redrawKeepingScroll();
    };
    strip.appendChild(clear);
  }
  strip.open = workOpen;
  strip.addEventListener("toggle", () => { workOpen = strip.open; });
  followWork();
  return strip;
}
// The strip follows the runs by itself, one timer for all of them; a run that ends redraws only the strip, so
// words being typed into a card are never drawn over. The next redraw of the page puts the finished row's card back.
function followWork() {
  clearTimeout(followWork.timer);
  followWork.timer = setTimeout(async () => {
    if (!document.getElementById("work-strip")) return;
    let changed = false;
    for (const { entry, task } of workRows().filter(({ task }) => ACTIVE_TASK.includes(task.result) && !task.sending)) {
      const { ok, code, ...latest } = await hostPost("/rem/task", { id: task.id });
      if (ok && latest.result && rowTask(entry)?.id === task.id) { changed ||= latest.result !== task.result; keepTask(entry, { ...task, ...latest }); }
    }
    const strip = document.getElementById("work-strip");
    if (strip) strip.replaceWith(workStrip() || "");
    if (changed && !document.activeElement?.closest("#main :is(textarea, input)")) redrawKeepingScroll();
  }, 4000);
}
// A Today row had eight equal links (sprint 14 #5). Now its three ways to close come first, as words (principle
// 10), then 交给 Codex · 交给 Claude, which stay visible quiet words on every unfinished row (D-100, the owner's
// «权限问题都给了»); only the talk folds under a worded 更多. Every strip has this one order, Waiting's and the
// folds' included: 标为完成 · 暂不处理 · 忽略 · 交给 Codex · 交给 Claude · 更多 (#2990 review). One of them is the row's lead, in bold, chosen by
// what the item is (lead, set where the buttons are made): 交给 Codex for a debt REM prepared as a task
// (principle 8), else 标为完成; lead null: the card's green step or the draft's Send is the primary.
// Since #3072 the last control is Show more, one door to the item's second level: why it is here, who waits and
// since when, the message itself, the pages it touches, and Talk it over, which used to be the only thing under
// 更多. The row passes its entry so the sheet is built from what the row already carries.
function todayStrip(agents, talk, closes, entry = null) {
  return [...closes, ...agents, moreButton(entry, talk)];
}
// Only a row of the notebook has a second level: an ask (让 Codex 查) has no item behind it.
function moreButton(entry, talk) {
  if (!talk || !entry?.r || !entry.t) return null;
  const more = el("button", { type: "button", class: "btn-quiet strip-more", "aria-haspopup": "dialog", text: t("Show more") });
  more.onclick = () => openContext(entry, talk);
  return more;
}
// The second level of an item (#3072: context as a second level): a panel at the side of a wide page, a sheet
// from the foot of a phone. It is a dialog over the page, so the card under it is not redrawn, and closing it
// gives the focus back to the button that opened it. Nothing here asks a model: the words are the row's own line,
// its dates, the mail its citations name (the excerpts the page already carries) and the pages it sits on.
function contextWhy(entry) {
  const thread = entry.t, who = firstName(entry.who || entry.r), late = overdueDays(thread);
  return [thread.due ? (late ? t(late === 1 ? "1 day overdue" : "{n} days overdue", { n: late }) + " · " : "") + t("due {date}", { date: threadDate(thread.due) }) : null,
    thread.since ? t(thread.dir === "mine" ? "{name} has waited since {date}" : "Open since {date}", { name: who, date: threadDate(thread.since) }) : null,
    looksDone(entry) ? t("Your later mail looks like it settled this.") : null].filter(Boolean);
}
function contextMessages(entry) {
  const ids = [...new Set([...entry.t.text.matchAll(/\[(W?\d{1,3})\]/g)].map(m => citationId(entry.r, m[1])))];
  return ids.map(id => [id, REM.source_context?.[id]]).filter(([, c]) => c && (c.excerpt || c.subject)).map(([id, c]) => {
    const from = mailbox(Array.isArray(c.participants?.from) ? c.participants.from[0] : c.participants?.from || c.sender || "");
    const head = [from.name, c.time ? fmtTime(c.time) : "", c.subject].filter(Boolean).join(" · ");
    const body = c.excerpt && !hasPrivacy(c.excerpt) ? c.excerpt.slice(0, 700) + (c.excerpt.length > 700 || c.truncated ? "…" : "") : "";
    return el("li", { class: "context-message" }, [el("p", { class: "context-from", text: head }), body ? el("p", { class: "context-excerpt", text: body }) : null]);
  });
}
function contextLinks(entry) {
  const who = entry.who || entry.r, org = who.organisations?.length ? byPath(who.organisations[0]) : null;
  const pages = [...new Map([who, entry.r, org, ...(entry.also || [])].filter(Boolean).map(r => [r.path, r])).values()];
  return [...pages.map(r => el("a", { href: href(r), text: threadWho(r) + " · " + singular(r.category) })), mailboxLink(entry)].filter(Boolean);
}
function openContext(entry, talk) {
  const part = (title, nodes) => nodes.length ? el("section", { class: "context-part" }, [el("h3", { text: t(title) }), ...nodes]) : null;
  const close = el("button", { type: "button", class: "ibtn", "aria-label": t("Close") }, [icon("x")]);
  const messages = contextMessages(entry);
  const dialog = el("dialog", { id: "item-context", class: "n3-sheet context-sheet", "aria-labelledby": "context-title" }, [
    el("div", { class: "sheet-head" }, [el("h2", { id: "context-title", text: threadWho(entry.who || entry.r) }), close]),
    part("Why it is here", [wordsLine("context-words", morningWords(entry.t.text, entry.r, entry.t).words, entry.r, []), putOffNote(entry),
      ...contextWhy(entry).map(text => el("p", { class: "context-fact", text }))].filter(Boolean)),
    part("The message", messages.length ? [el("ul", { class: "context-messages" }, messages)] : [el("p", { class: "quiet-line", text: t("This item cites no message the page carries.") })]),
    part("Related", [el("p", { class: "context-links" }, dotted(contextLinks(entry)))]),
    part("Talk it over", [talk])]);
  close.onclick = () => dialog.close();
  // A link or a talk leaves the sheet: the page it opens, or the conversation in the card, is what he asked for.
  dialog.addEventListener("click", event => { if (event.target.closest("a[href^='#'], [data-talk]") || event.target === dialog) dialog.close(); });
  dialog.addEventListener("close", () => dialog.remove());
  document.body.appendChild(dialog);
  talk.open = true;
  dialog.showModal();
}
// Codex is working · Stop · Take back, then Codex finished · See result · Take back; it follows the run by itself.
// The three closes stay first, as before the hand-off (D-100's order).
function handState(entry, show, panel, mark, compact = false) {
  const task = rowTask(entry), agent = AGENT_NAMES[task.agent || "codex"] || task.agent, active = ACTIVE_TASK.includes(task.result);
  const status = taskStatusNode(task, entry);
  const act = (action, label) => {
    const button = el("button", { type: "button", class: "btn-quiet", text: label });
    button.onclick = async () => {
      button.disabled = true;
      const { ok, code, ...reply } = await hostPost("/rem/task", { id: task.id, action });
      if (!ok) { button.disabled = false; button.textContent = t("Could not do that. Try again."); return; }
      keepTask(entry, action === "undo" ? null : { ...task, ...reply });
      show();
    };
    return button;
  };
  if (liveHere() && active && !task.sending && status) followTask(entry, task, status, show);
  const by = task.by === "rem" ? el("span", { class: "handoff-status", text: t("REM started this") }) : null;
  const [see] = active || !liveHere() ? [null] : seeResult(task);
  // Taking the task back is not undoing the item: its own words, so it never reads like the done Undo.
  const actions = task.sending ? [] : [...terminalButtons(entry, task, active), ...(liveHere() ? [active ? act("stop", t("Stop")) : see, act("undo", t("Take back from {agent}", { agent }))] : [])];
  const primary = !active && liveHere() && (!entry.ask || task.result !== 'completed') ? taskPrimary(entry, task, show) : null;
  const work = [status, by, primary, ...actions, entry.ask ? null : moreButton(entry, talkMenu(entry, panel))];
  // The closes stay on every row, before and after the run (owner, 2026-11-11/12: mark done, not now, ignore in words).
  const closes = stripDone(entry, mark);
  if (compact && closes.length) {
    // The one step: a drafted reply to open, the result to read, the stopped run to carry on (or retry); while it
    // runs there is nothing to press but the status says what it is doing.
    const resume = actions.find(node => node?.classList?.contains("task-resume"));
    const lead = active ? null : primary || (task.result === "completed" ? see : resume) || closes[0];
    return oneAction(el("span", { class: "task-line" }, [status, by].filter(Boolean)), lead, closes, [...actions, primary, see,
      entry.ask ? null : moreButton(entry, talkMenu(entry, panel))]);
  }
  return dotted([...closes, ...work]);
}
// 让 Codex 查 (#2909): automatic investigations skip a private project, so the owner asks here. The same
// /rem/task run as 交给 Codex, keyed by the project's own page; its progress and result show in place.
function investigateRequest(r) {
  if (!REM.live) return liveReaderLine("This is a snapshot: ask Codex to look from the live reader.");
  // Its own row: r.investigation is the Investigate button's state (#3105), and sharing it crashed the page.
  r.codex_look ||= { keys: [r.path], task: r.task || null };
  return handOff({ key: r.path, row: r.codex_look, ask: true });
}
function followTask(entry, task, status, show) {
  setTimeout(async () => {
    if (!status.isConnected) return;
    const { ok, code, ...latest } = await hostPost("/rem/task", { id: task.id });
    if (ok && latest.result !== task.result) { keepTask(entry, { ...task, ...latest }); show(); return; }
    // Still working: the latest step shows in place, so the card under the owner's hand is not redrawn.
    if (ok && latest.step?.at !== task.step?.at) {
      task = { ...task, ...latest };
      keepTask(entry, task);
      status.textContent = taskStatus(task, entry);
      status.dataset.taskStep = taskStep(task);
    }
    followTask(entry, task, status, show);
  }, 4000);
}
// One next step: prepare the proposed reply locally, close the item, or retry a failed run.
function taskPrimary(entry, task, show) {
  const completed = task.result === 'completed', reply = completed && !!task.reply;
  // A finished run with no reply to draft has the strip's own Mark done as its next step; no second one.
  if (completed && !reply) return null;
  const button = el('button', { type: 'button', class: 'btn-quiet strip-lead', text: t(completed ? reply ? task.draft_id ? 'Open reply draft' : 'Draft with this reply' : 'Mark done' : 'Retry') });
  button.onclick = async () => {
    if (completed && !reply) { setDone(entry, true); return; }
    if (!completed) keepTask(entry, { ...task, result: 'starting', started_at: null, queued_at: new Date(clockNow()).toISOString(), sending: true });
    button.disabled = true;
    if (!completed) show();
    const result = await hostPost('/rem/task', { id: task.id, action: reply ? 'prepare_reply' : 'retry' });
    if (!result.ok) {
      if (!completed && ![400, 401, 409].includes(result.code)) { confirmHandoff(entry, show); return; }
      if (!completed) keepTask(entry, task);
      button.disabled = false; button.textContent = result.error || t('Could not do that. Try again.');
      if (!completed) show();
      return;
    }
    if (reply) {
      REM.drafts = [...(REM.drafts || []).filter(d => d.id !== result.id), result];
      keepTask(entry, { ...task, draft_id: result.id });
      redrawKeepingScroll();
      openTaskPanel(t('Reply draft prepared'), replyDraftCard(result, () => redrawKeepingScroll(), entry.who || entry.r), button);
    } else { keepTask(entry, { ...result, sending: false }); show(); }
  };
  return button;
}
function seeResult(task) {
  if (task.has_output === false || (task.result !== 'completed' && !task.has_output)) return [null, null];
  const button = el('button', { type: 'button', class: 'btn-quiet', text: t('See result') });
  button.onclick = async () => {
    const reply = await hostPost('/rem/task', { id: task.id, action: 'result' });
    openTaskPanel(task.title || t('Task result'), reply.ok ? taskReport(reply.text || reply.reason || '', task) : el('p', { text: reply.error || t('Could not do that. Try again.') }), button);
  };
  return [button, null];
}
function openTaskPanel(title, content, trigger) {
  const panel = evidencePanel(), close = el('button', { type: 'button', class: 'evidence-close', text: t('Close ×'), 'aria-label': t('Close source context') });
  close.onclick = closeEvidence;
  panel.replaceChildren(el('div', { class: 'evidence-handle', 'aria-hidden': 'true' }),
    el('div', { class: 'evidence-top' }, [el('span', { text: title }), close]), content);
  evidenceTrigger = trigger;
  panel.parentElement.hidden = false;
  document.body.classList.add('evidence-open');
  evidenceLayout(); panel.scrollTop = 0; close.focus({ preventScroll: true });
}
function taskSource(id, trigger) {
  const context = REM.source_context?.[id];
  const quote = el('blockquote', { text: context?.excerpt || t("The original isn't in this snapshot.") });
  const content = context ? el('div', {}, [evidenceOriginal(context, quote)]) : quote;
  if (context) {
    const reveal = el('button', { type: 'button', class: 'btn-action', text: t('Show labelled passages') });
    reveal.onclick = () => revealLabelled();
    content.prepend(el('div', { class: 'private-hidden-notice' }, [reveal]));
  }
  openTaskPanel(context?.subject || sourceLabel(id), content, trigger);
}
function taskReport(text, task) {
  const box = agentText(taskReportLinks(text, task.id), task.record);
  wireTaskFiles(box);
  wireTaskSources(box);
  return box;
}
function taskReportLinks(text, id) {
  return text.split(/(```[\s\S]*?```)/g).map((part, i) => i % 2 ? part : part.replace(/\[([^\]]+)\]\(([^\s)]+)\)/g, (all, label, path) =>
    /^(?:[a-z][a-z0-9+.-]*:|#|\/)/i.test(path) ? all : '[' + label + '](/rem/task-file?' + new URLSearchParams({ id, path: taskLinkPath(path) }) + ')')).join('');
}
function taskLinkPath(path) {
  // URLSearchParams tolerates malformed percent escapes in an agent's Markdown.
  return new URLSearchParams('path=' + path.split(/[?#]/)[0].replaceAll('+', '%2B')).get('path');
}

function wireTaskFiles(box) {
  for (const link of box.querySelectorAll('a[href]')) {
    const path = link.getAttribute('href');
    if (!path?.startsWith('/rem/task-file?')) continue;
    const url = path;
    link.onclick = async event => {
      event.preventDefault();
      const response = await fetch(url);
      if (!response.ok) { openTaskPanel(link.textContent, el('p', { text: t('Could not do that. Try again.') }), link); return; }
      if (!(response.headers.get('content-type') || '').startsWith('text/')) { window.open(url, '_blank', 'noopener'); return; }
      openTaskPanel(link.textContent, el('pre', { class: 'task-file', text: await response.text() }), link);
    };
  }
}
function wireTaskSources(box) {
  const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT), nodes = [];
  while (walker.nextNode()) if (!walker.currentNode.parentElement.closest('a, button, pre')) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const parts = node.textContent.split(/((?:outlook|gmail|codex|claude-code):[^\s<>`，。；、（）()\[\]]+)/g);
    if (parts.length < 2) continue;
    node.replaceWith(...parts.map((part, i) => {
      if (i % 2 === 0) return document.createTextNode(part);
      const chip = el('button', { type: 'button', class: 'chip task-source', text: sourceChannel(part.split(':')[0]) + (REM.source_context?.[part]?.subject ? ' · ' + REM.source_context[part].subject : ''), title: part });
      chip.onclick = () => taskSource(part, chip);
      return chip;
    }));
  }
}
// 和 Codex 聊这件事: a real conversation with the agent about this row, under it, in this page.
function talkMenu(entry, panel) {
  const menu = el("details", { class: "talk-menu" }, [el("summary", {}, [t("Talk it over"), " ", el("span", { class: "caret", "aria-hidden": "true", text: "▾" })])]);
  menu.append(el("div", { class: "talk-choices" }, Object.entries(AGENT_NAMES).map(([agent, name]) => {
    const button = el("button", { type: "button", class: "btn-quiet", "data-talk": agent, text: t("With {agent}", { agent: name }),
      "aria-label": t("Talk with {agent} about this", { agent: name }) });
    button.disabled = !liveHere();
    button.onclick = () => {
      menu.open = false;
      const talk = talkPanel({ action: "begin", agent, key: obligationKey(entry) });
      OPEN_TALKS.set(obligationKey(entry), talk);
      panel.replaceChildren(talk);
    };
    return button;
  })));
  return menu;
}
// What an agent wrote, as the notebook's own Markdown: escaped first, so no HTML from the model runs;
// fenced code is a code block with its Copy button. `from` is the page its citations belong to.
function agentText(text, from) {
  const box = el("div", { class: "agent-text", html: markdown(text, from || "") });
  for (const block of box.querySelectorAll(".code-block")) {
    const copy = block.querySelector(".code-copy");
    copy.onclick = () => copyToClipboard(block.querySelector("code").textContent, copy, t("Copied"));
  }
  return box;
}
function talkTurn(turn, name, from) {
  if (turn.role === "context") return el("details", { class: "talk-context" }, [el("summary", { text: t("What {agent} was given", { agent: name }) }), el("pre", { text: turn.text })]);
  return el("div", { class: "talk-turn " + turn.role }, [el("span", { class: "talk-who", text: turn.role === "owner" ? t("You") : name }),
    turn.role === "owner" ? el("p", { text: turn.text }) : agentText(turn.text, from)]);
}
// One conversation: each message is a turn of the same agent session; the page follows it while it answers.
function talkPanel(begin) {
  const turns = el("div", { class: "talk-turns" }), status = el("p", { class: "talk-status", role: "status", text: t("Opening the conversation…") });
  const input = el("textarea", { rows: "2", "aria-label": t("Your message"), "data-keep": "talk:" + (begin.agent || "codex") + ":" + (begin.key || begin.session) });
  const send = el("button", { type: "submit", class: "btn-line", text: t("Send"), disabled: "" });
  const form = el("form", { class: "talk-form" }, [input, send]), box = el("section", { class: "talk", "aria-live": "polite" }, [turns, status, form]);
  box.talkBegin = begin;  // Reloads reopen this same Host conversation, even before begin has answered.
  let talk = null;
  const paint = ({ ok, code, error, ...value }) => {
    if (!ok) { status.textContent = error || t("REM is not answering right now. Try again in a moment."); send.disabled = !talk; return; }
    talk = value;
    const name = AGENT_NAMES[talk.agent] || talk.agent, working = talk.state === "working";
    const from = talk.about.session || talk.about.key.split("\n")[0];
    turns.replaceChildren(...talk.turns.map(turn => talkTurn(turn, name, from)));
    status.textContent = working ? t("{agent} is answering…", { agent: name }) : talk.reason || "";
    input.placeholder = t("Write to {agent}…", { agent: name });
    send.disabled = working;
    if (working) setTimeout(() => box.isConnected && hostPost("/rem/talk", { action: "read", id: talk.id }).then(paint), 2500);
  };
  form.onsubmit = async event => {
    event.preventDefault();
    if (!talk || !input.value.trim()) return;
    send.disabled = true;
    const reply = await hostPost("/rem/talk", { action: "say", id: talk.id, text: input.value });
    if (reply.ok) input.value = "";
    paint(reply);
  };
  hostPost("/rem/talk", begin).then(paint);
  return box;
}
// The first card is open and carries the page's one green action; the others
// show who and what, and reveal their action on hover, focus or tap.
function personCard(group, focal, total = 1, index = 0) {
  const { r, entries } = group, next = groupStep(entries), late = groupLate(group);
  const draft = next.step === "send" ? threadDraft(next.entry) : null, seen = new Set();
  const more = draft ? el("button", { type: "button", class: "btn-quiet qfull", text: t("More of this card") }) : null;
  // A green Mark done that would close just one row only repeats that row's strip button, so it is not drawn;
  // closing several handled rows at once, it does what no row's button does and stays.
  const closing = next.step === "done" ? entries.filter(item => cardStep(item) === "done") : [];
  // One primary per card (principle 5), by what the item is: the draft's Send, or the green step that answers or
  // approves; a debt REM prepared as a task goes to Codex (principle 8); anything else is closed. "Open {name}" is
  // not a step: the name above already opens the page, and opening it does nothing about the item.
  const task = rowTask(next.entry), byAgent = liveHere() && !!task && !handed(task) && !["send", "draft", "approve"].includes(next.step);
  const closesHere = closing.length === 1;
  const step = byAgent || closesHere ? null : stepAction(next, group, focal ? "btn-act" : "btn-line");
  // The bold lead sits on the row it is about: the task's own row, else the row that closes.
  const leadEntry = step || draft ? null : byAgent ? next.entry : closing[0] || next.entry, leadKind = byAgent ? "task" : "done";
  // When every row is handled, that green step and the head's tick would both close all of them: the green step
  // stays (it is the card's lead, shown without a hover, and the reason REM gives sits above it); E still closes.
  const allClosed = step && liveHere() && entries.length > 1 && closing.length === entries.length;
  const triageInFooter = !!draft && entries.length === 1 && liveHere();
  const card = el("li", { class: "qcard" + (focal ? " open focal" : "") + (late ? " late" : "") + (triageInFooter ? " triage-footer" : ""), tabindex: "-1", "data-path": r.path, "data-step": next.step }, [
    cardHead(group, late, total > 1, allClosed ? false : undefined, { i: index + 1, n: total }), el("ul", { class: "qitems" }, entries.map((entry, i) => cardItem(entry, entries.length > 1, seen, i ? null : more,
      cardStep(entry) === "done" && !(step && closing.includes(entry)), entry === leadEntry ? leadKind : null))),
    draft ? cardDraft(draft, group) : null,
    el("div", { class: "card-acts" }, [step, notDoneAction(next), mailboxLink(next.entry)]), snapshotCloseLine()]);
  card.markDone = () => closeEntries(card, entries);
  let touch = null;
  card.ontouchstart = event => { touch = card.classList.contains("focal") && event.touches.length === 1 ? event.touches[0] : null; };
  card.ontouchend = event => {
    const end = event.changedTouches[0];
    if (!touch || event.target.closest("textarea, input, .mail-text, .mail-channels")) return;
    const dx = end.clientX - touch.clientX, dy = end.clientY - touch.clientY;
    if (Math.abs(dx) > 60 && Math.abs(dx) > 2 * Math.abs(dy)) dealNext(dx < 0 ? 1 : -1);
    touch = null;
  };
  card.reply = () => replyFrom(card);
  // With a draft open the context is two lines; More shows the rest, so Send stays on the first screen.
  if (more) more.onclick = () => { card.classList.add("full"); more.remove(); };
  // The talk menu and an open conversation are the card's own controls: using them never folds it. Nor does a
  // click in the raised card, and which card that is changes with every deal, so it is read at the click.
  card.onclick = event => { if (!card.classList.contains("focal") && !event.target.closest("a, button, textarea, input, select, summary, .mailcard, .talk")) card.classList.toggle("open"); };
  return card;
}
function openDraft(card) {
  card.classList.add("open");
  card.querySelector(".qdraft .btn-act")?.focus();
}
// R: the writer when a draft is ready, REM drafting when it can, else your mail app's reply.
function replyFrom(card) {
  card.classList.add("open");
  card.querySelector('.qdraft [data-key="r"], .qdraft .btn-act, .card-acts [data-reply]')?.click();
}
function mailboxLink(entry) {
  const reply = queuedReply(entry), kind = threadKind(entry);
  const url = threadUrl(reply, kind);
  return url ? el("a", { class: "btn-quiet", href: url.href, target: "_blank", rel: "noopener", text: t("Open the {channel} thread", { channel: url.channel }) }) : null;
}
// A Waiting row with the hand-off strip, whoever it waits on: its closes, then 交给 Codex / 交给 Claude.
// grouped rows carry no direction label, so the row's body is its first child, else its second.
function stripRow(entry, grouped = false) {
  const node = threadRow(entry.r, entry.t, true, entry.also, grouped, true);
  node.children[grouped ? 0 : 1].append(handOff(entry));
  return node;
}
// Gone quiet: on Today five rows in a fold, on Waiting all of them. Each row is still open, so each says the three
// closes in words, with the hand-offs after them (#2990, D-100); on Today the strip sits under the row's preview.
// On Today a long-quiet promise is already a row of its own fold above (staleWidget), so it is left out here: one
// item, one row on the page (#2990 review). Waiting has no such fold and keeps it.
// The count is the rows' own (items), so the summary never disagrees with what opens under it.
function quietThreads(entries, home = false) {
  const items = entries.filter(entry => home ? entry.t.quiet && !staleEntry(entry) : entry.t.quiet || staleEntry(entry));
  if (!items.length) return null;
  const rows = () => home ? el("ul", { class: "quiet-list" }, items.slice(0, 5).map(entry => el("li", {}, [
    el("div", {}, [el("a", { href: href(entry.r), text: threadWho(entry.r) }), el("p", { text: threadPreview(entry.t.text) }), alsoOn(entry.also),
      handOff(entry, null, null)]), el("span", { class: "quiet-age", text: age(entry.t.since) })])))
    : el("ul", { class: "threads" }, items.map(entry => stripRow(entry)));
  const fold = el("details", { id: "gone-quiet", class: "gone-quiet" }, [el("summary", { text: t("Gone quiet") + " (" + items.length + ")" }),
    home ? el("a", { href: "#view=open", text: t("See all quiet threads →") }) : null]);
  return lazyFold(fold, node => node.querySelector(":scope > summary").after(snapshotCloseLine() || "", rows()));
}
// A fold's rows are drawn when it first opens (#2990 review): Waiting's Gone quiet can hold sixty rows, each with
// its strip, and none is seen until the owner opens it. The summary's click fills it before the browser opens it,
// so the rows are there as it opens; an open set by code (a redraw keeping the fold open) calls fill itself.
function lazyFold(details, fill) {
  let filled = false;
  details.fill = () => { if (!filled) { filled = true; fill(details); } };
  details.querySelector(":scope > summary").addEventListener("click", details.fill);
  details.addEventListener("toggle", () => { if (details.open) details.fill(); });
  return details;
}

