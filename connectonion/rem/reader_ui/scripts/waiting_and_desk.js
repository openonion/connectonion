let openMultiMode = false;
const openSelected = new Set();
const openSessionDone = new Set();
let openBatchQueue = null;

function openCounterpart(entry) {
  if (entry.r.path !== REM.owner) return entry.r;
  const direct = ownerCounterpart(entry);
  if (direct) return direct;
  // Fallback: check cited source_context sender/to addresses for a matching person record in REM.records
  const cites = [...(entry.t.originalText || entry.t.text || "").matchAll(/\[(W?\d{1,3})\]/g)].map(m => citationId(entry.r, m[1])).filter(Boolean);
  const ownerSet = new Set(ownerAddresses());
  for (const cid of cites) {
    const ctx = REM.source_context?.[cid];
    if (!ctx) continue;
    const rawAddrs = [ctx.sender, ...(ctx.participants?.from || []), ...(ctx.participants?.to || [])].filter(Boolean).join(" ");
    const emails = (rawAddrs.toLowerCase().match(/[^\s<>(),;"']+@[^\s<>(),;"']+/g) || []).filter(a => !ownerSet.has(a));
    for (const email of emails) {
      const hit = inCategory("people").find(p => p.path !== REM.owner && !p.private
        && (String(facts(p).email || "").toLowerCase().includes(email) || (p.index?.emails || []).some(e => e.toLowerCase() === email)));
      if (hit) return hit;
    }
  }
  return entry.r;
}
function cleanStitchedTitle(text) {
  return String(text || "")
    .replace(/<\/?artifact-content-authored-by-others\s*\/?>/gi, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/([.!?。！？][”"」』])\./g, "$1")
    .replace(/(?:[,，;；:：]\s*[—–-]+\s*)+/g, " — ")
    .replace(/^\s*(?:[,，;；:：—–-]+\s*)+/, "")
    .replace(/(?:\s*[,，;；:：—–-]+)+\s*$/, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}
function entryPrivacyLevel(entry) {
  const raw = String(entry?.t?.originalText || entry?.t?.text || "");
  if (/[\[［]sensitive[\]］]/i.test(raw)) return "sensitive";
  if (/[\[［]personal[\]］]/i.test(raw) || entry?.r?.private) return "personal";
  return "";
}
function openItemId(entry) {
  const raw = doneKey(entry);
  let h = 2166136261;
  for (let i = 0; i < raw.length; i++) { h ^= raw.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (entry?.r?.path || "item") + "#" + (h >>> 0).toString(36);
}
function matchesOpenItem(entry, param) {
  return !!param && (openItemId(entry) === param || doneKey(entry) === param);
}
function openDisplayTitle(entry) {
  const rawText = entry.t.text || "", level = entryPrivacyLevel(entry);
  const { lead, quote } = rowWords(youify(withoutDateClutter(rawText, entry.t)));
  let cleanLead = cleanStitchedTitle(lead.replace(/\[W?\d{1,3}\]/g, ""));
  if (level && !/[\[［](?:personal|sensitive)[\]］]/i.test(cleanLead)) cleanLead += " [" + level + "]";
  const cleanQuote = quote ? cleanStitchedTitle(quote.replace(/\s*[\[［](?:personal|sensitive)[\]］]/gi, "")) : "";
  return { title: cleanLead || cleanQuote || plainLine(rawText), quote: cleanQuote, level };
}
function dedupOpenEntries(items) {
  const byNorm = new Map(), out = [];
  for (const entry of items) {
    const cites = [...entry.t.text.matchAll(/\[(W?\d{1,3})\]/g)].map(m => citationId(entry.r, m[1])).filter(Boolean);
    const words = obligationWords(entry.t.originalText || entry.t.text).slice(0, 72);
    const sig = cites[0] ? "src:" + cites[0] + "|" + words.slice(0, 32) : "txt:" + words;
    const prev = byNorm.get(sig);
    if (prev && prev.entry !== entry) {
      prev.merged.push(entry);
      continue;
    }
    const bucket = { entry, merged: [entry] };
    byNorm.set(sig, bucket);
    out.push(bucket);
  }
  return out.map(({ entry, merged }) => {
    if (merged.length === 1) return entry;
    const preferred = merged.find(e => e.r.path !== REM.owner && e.r.category === "people")
      || merged.find(e => e.r.path !== REM.owner) || merged[0];
    const others = merged.filter(e => e !== preferred);
    const also = [...(preferred.also || []), ...others.map(e => e.r)]
      .filter((r, i, arr) => r && r.path !== preferred.r.path && arr.findIndex(x => x.path === r.path) === i);
    return { ...preferred, also, members: [...new Set([...(preferred.members || [preferred]), ...merged])], mergedCount: merged.length };
  });
}
function openPrimaryGroup(entry) {
  const tags = openTags(entry).filter(c => !c.id.startsWith("state:"));
  return tags[0] ? { id: tags[0].id, label: tags[0].label } : { id: "other", label: t("Other") };
}
function openHref(overrides = {}) {
  const cur = route();
  const params = new URLSearchParams({ view: "open" });
  const dir = overrides.dir !== undefined ? overrides.dir : cur.dir;
  const tag = overrides.tag !== undefined ? overrides.tag : cur.tag;
  const item = overrides.item !== undefined ? overrides.item : "";
  if (dir && dir !== "mine") params.set("dir", dir);
  if (tag) params.set("tag", tag);
  if (item) params.set("item", item);
  return "#" + params.toString();
}
const openSessionStates = new Map();
function bauCloseEntry(entry, done, state = "done", until = null) {
  const key = doneKey(entry);
  if (done) {
    openSessionDone.add(key);
    openSessionStates.set(key, state);
    openSelected.delete(key);
  } else {
    openSessionDone.delete(key);
    openSessionStates.delete(key);
  }
  if (liveHere()) {
    const members = entry.members || [entry];
    markThread(entry, done, state, members, until);
  }
  redrawKeepingScroll();
}
function bauRenderDetail(main, current, visibleList, dir, tag) {
  const key = doneKey(current), idx = Math.max(0, visibleList.findIndex(e => doneKey(e) === key));
  const who = openCounterpart(current), { title, quote, level: quoteLevel } = openDisplayTitle(current);
  const group = openPrimaryGroup(current), draft = threadDraft(current);
  const done = openSessionDone.has(key) || isDone(current);
  const late = current.t.due && current.t.due < calendarDay(REM.as_of) && !staleEntry(current);
  const goItem = target => { location.hash = openHref({ dir, tag, item: target ? openItemId(target) : "" }); };
  const advanceAfter = () => {
    const next = visibleList[idx + 1] || visibleList[idx - 1] || null;
    if (next && doneKey(next) !== key) goItem(next);
    else { openBatchQueue = null; location.hash = openHref({ dir, tag, item: "" }); }
  };

  const wrap = el("div", { class: "bau-detail" });
  const back = el("a", { class: "bau-back", href: openHref({ dir, tag, item: "" }) }, ["← ", t("Back to list")]);
  back.onclick = () => { openBatchQueue = null; };
  const prevBtn = el("button", { type: "button", class: "bau-back", text: "↑ " + t("Previous"), disabled: idx <= 0 ? "" : null });
  const nextBtn = el("button", { type: "button", class: "bau-back", text: "↓ " + t("Next"), disabled: idx >= visibleList.length - 1 ? "" : null });
  prevBtn.onclick = () => { if (idx > 0) goItem(visibleList[idx - 1]); };
  nextBtn.onclick = () => { if (idx < visibleList.length - 1) goItem(visibleList[idx + 1]); };
  wrap.appendChild(el("div", { class: "bau-dtop" }, [
    back,
    el("div", { class: "bau-dpos" }, [
      el("span", { class: "bau-pill", text: group.label }),
      el("span", { text: `${String(idx + 1).padStart(2, "0")} / ${String(visibleList.length).padStart(2, "0")} · ${t("Auto-advances after action")}` })
    ]),
    el("div", { class: "bau-dnav" }, [prevBtn, nextBtn])
  ]));

  const paper = el("article", { class: "bau-paper" });
  const whoOrg = who.category === "people" ? personOrg(who)?.name || "" : "";
  paper.appendChild(el("div", { class: "bau-phead" }, [
    el("div", {}, [el("a", { class: "bau-pwho", href: href(who), text: threadWho(who) }),
      whoOrg ? el("span", { class: "bau-porg", text: "· " + whoOrg }) : null]),
    el("span", { class: "when" + (late ? " overdue" : ""), text: threadAge(current.t) })
  ]));
  paper.appendChild(el("h2", { class: "bau-ptitle", html: inline(title, current.r.path) }));

  if (quote && !(quoteLevel && privacyLevel === "public")) {
    const qvNode = el("div", { class: "bau-qv" + (quoteLevel ? " private" : ""), ...(quoteLevel ? { "data-level": quoteLevel } : {}), text: "“" + quote + "”" });
    if (quoteLevel) applyPrivacy(qvNode);
    paper.appendChild(el("div", { class: "bau-quote" + (quoteLevel ? " private-item" : "") }, [
      el("span", { class: "bau-qk", text: t("Original message") }),
      qvNode
    ]));
  }
  const mergedPages = [current.r, ...(current.also || [])].filter((r, i, a) => r && r.path !== REM.owner && !privateTopicHidden(r) && a.findIndex(x => x.path === r.path) === i);
  if ((current.mergedCount || 1) > 1 && mergedPages.length > 1) {
    paper.appendChild(el("div", { class: "bau-chain-wrap" }, [
      el("div", { class: "bau-dbox-k", text: t("Merged context ({n} pages)", { n: Math.max(current.mergedCount || 1, mergedPages.length) }) }),
      el("div", { class: "bau-chain" }, mergedPages.map((p, i) =>
        el("div", { class: "bau-cn" + (i === mergedPages.length - 1 ? " now" : "") }, [
          el("a", { class: "bau-pwho", href: href(p), text: pageName(p) }),
          el("span", { class: "bau-porg", text: "· " + singular(p.category) })
        ])))
    ]));
  }
  if (draft) paper.appendChild(cardDraft(draft, { r: who, entries: [current] }));
  if (mergedPages.length) {
    paper.appendChild(el("div", { class: "bau-rel-foot" }, [
      el("span", { class: "bau-rel-k", text: t("Related pages") }),
      ...mergedPages.map(p => el("a", { class: "bau-rel-chip", href: href(p), text: pageName(p) + " · " + singular(p.category) }))
    ]));
  }

  const side = el("aside", { class: "bau-dside" });
  const mailLink = mailboxLink(current);
  const cta = draft
    ? el("button", { type: "button", class: "bau-cta" }, [el("span", { class: "bau-cta-t", text: t("Review & send reply") }), el("span", { class: "bau-cta-s", text: t("Auto-advances after action") })])
    : mailLink
      ? el("a", { class: "bau-cta", href: mailLink.href, target: "_blank", rel: "noopener" }, [el("span", { class: "bau-cta-t", text: mailLink.textContent }), el("span", { class: "bau-cta-s", text: threadWho(who) })])
      : el("button", { type: "button", class: "bau-cta" }, [el("span", { class: "bau-cta-t", text: t(done ? "Undo" : "Mark done") }), el("span", { class: "bau-cta-s", text: t("Auto-advances after action") })]);
  if (draft) cta.onclick = () => paper.querySelector(".qdraft .btn-act")?.click();
  else if (!mailLink) cta.onclick = () => { bauCloseEntry(current, !done); if (!done) advanceAfter(); };
  side.appendChild(cta);

  const statusBox = el("div", { class: "bau-dbox" }, [el("span", { class: "bau-dbox-k", text: t("Status actions") })]);
  const doneBtn = el("button", { type: "button", class: "bau-dact" }, [el("span", { text: "✓ " + t(done ? "Undo" : "Mark done") }), el("span", { text: "E" })]);
  doneBtn.onclick = () => { bauCloseEntry(current, !done); if (!done) advanceAfter(); };
  const laterBtn = el("button", { type: "button", class: "bau-dact" }, [el("span", { text: t("Put off until tomorrow") || t("Not now") }), el("span", { text: "S" })]);
  laterBtn.onclick = () => laterChooser(statusBox, until => () => { bauCloseEntry(current, true, "skipped", until); advanceAfter(); });
  const ignoreBtn = el("button", { type: "button", class: "bau-dact soft" }, [el("span", { text: t("Ignore") }), el("span", { text: "I" })]);
  ignoreBtn.onclick = () => { bauCloseEntry(current, true, "ignored"); advanceAfter(); };
  if (mailLink && draft) statusBox.appendChild(el("a", { class: "bau-dact soft", href: mailLink.href, target: "_blank", rel: "noopener" }, [el("span", { text: t("Open original mail") }), el("span", { text: "↗" })]));
  statusBox.append(doneBtn, laterBtn, ignoreBtn);
  side.appendChild(statusBox);

  const agentBox = el("div", { class: "bau-dbox agent-dock" }, [
    el("span", { class: "bau-dbox-k" }, [el("span", { class: "bau-dock-prompt", text: "> AGENT" }), el("span", { text: t("Delegate to agent") })])
  ]);
  const agentStatus = el("div", { class: "talk-slot" });
  const existingTask = rowTask(current);
  if (existingTask) {
    const st = taskStatusNode(existingTask, current);
    if (st) agentBox.appendChild(st);
  }
  const codexAct = el("button", { type: "button", class: "bau-dact soft", disabled: !liveHere() ? "" : null }, [el("span", { text: t("Hand to Codex") }), el("span", { text: "→" })]);
  codexAct.onclick = () => handOver(current, "codex", () => redrawKeepingScroll(), null, agentStatus);
  const claudeAct = el("button", { type: "button", class: "bau-dact soft", disabled: !liveHere() ? "" : null }, [el("span", { text: t("Hand to Claude") }), el("span", { text: "→" })]);
  claudeAct.onclick = () => handOver(current, "claude", () => redrawKeepingScroll(), null, agentStatus);
  agentBox.append(codexAct, claudeAct);
  const talk = liveHere() ? talkMenu(current, agentStatus) : null;
  if (talk) agentBox.appendChild(talk);
  if (!liveHere()) agentBox.appendChild(el("span", { class: "bau-dbox-k", text: t("Live reader required") }));
  agentBox.appendChild(agentStatus);
  side.appendChild(agentBox);

  wrap.appendChild(el("div", { class: "bau-dgrid" }, [paper, side]));
  main.appendChild(wrap);
}

function taskView(kind) {
  const main = document.getElementById("main");
  main.textContent = "";
  main.appendChild(el("div", { class: "eyebrow", text: t("Today") }));
  if (kind === "changes") {
    const pass = lastPass();
    main.appendChild(el("h1", { text: t("Memory changes") }));
    main.appendChild(el("p", { class: "lede", text: t("What last night changed in your notebook, each with its source. Rewritten pages are listed below.") }));
    const claims = firstBuild() ? [] : pass?.claims || [];
    const hasRewrites = !firstBuild() && !!(pass?.changed?.length);
    if (claims.length) main.appendChild(el("div", { class: "claim-grid standalone" }, claims.map(changeCard).filter(Boolean)));
    // #3438: show the "no changes last night" empty state ONLY when neither claims nor rewritten pages exist.
    else if (!hasRewrites) main.appendChild(emptyState(firstBuild() ? "No changes yet — this is the first build." : "No page content changed last night"));
    if (hasRewrites) main.appendChild(localDatesIn(el("div", { class: "changed-pages" }, [sectionHead("Pages rewritten", "Current context"),
      el("ul", { class: "hits" }, pass.changed.map(r => row(r, { kind: true, hideZeroUsage: true })))])));
    // REM's own run history stays out of the sidebar (D-03); this is its only door.
    main.appendChild(el("a", { class: "rem-activity", href: "#view=activity", text: t("REM activity →") }));
    // Questions & connections left the sidebar too (2026-11-09); its route stays and this is its door.
    main.appendChild(el("a", { class: "rem-activity", href: "#reviews=1", text: t("Questions & connections →") }));
    return;
  }
  main.appendChild(el("h1", { text: t("Open threads") }));
  approvalUndoBar(false);
  const snapshot = snapshotLine();
  if (snapshot) main.appendChild(snapshot);
  main.append(...whyNotes());
  const all = threadEntries(), open = all.filter(entry => !isDone(entry) || openSessionDone.has(doneKey(entry)));
  const curRoute = route(), tag = curRoute.tag, activeItem = curRoute.item;
  if (!open.length) {
    main.appendChild(emptyState("Nothing open"));
    const done = markedDone(all);
    if (done) main.appendChild(done);
    return;
  }
  const visibleUnderPrivacy = row => !(privacyLevel === "public" && entryPrivacyLevel(row));
  const byDirRaw = dir => open.filter(row => visibleUnderPrivacy(row) && (dir === "mine" ? waitingOnYou(row) : row.t.dir === dir && !row.t.quiet && !staleEntry(row)));
  const dirDefs = [
    { id: "mine", title: "Waiting on you", items: dedupOpenEntries(byDirRaw("mine")) },
    { id: "theirs", title: "Waiting on others", items: dedupOpenEntries(byDirRaw("theirs")) },
    { id: "plain", title: "Other open context", items: dedupOpenEntries(byDirRaw("plain")) },
  ];
  const activeDir = dirDefs.some(d => d.id === curRoute.dir && d.items.length) ? curRoute.dir
    : (dirDefs.find(d => d.items.length)?.id || "mine");
  const dirBucket = dirDefs.find(d => d.id === activeDir) || dirDefs[0];
  const entries = tag ? dirBucket.items.filter(entry => openTagged(entry, tag)) : dirBucket.items;

  // Group entries by primary tag so tags divide the work structurally and Screen 2 walks the exact same order!
  const grouped = new Map();
  for (const entry of entries) {
    const g = openPrimaryGroup(entry);
    if (!grouped.has(g.id)) grouped.set(g.id, { ...g, items: [] });
    grouped.get(g.id).items.push(entry);
  }
  const sections = [...grouped.values()].sort((a, b) => (a.id === "other") - (b.id === "other") || b.items.length - a.items.length);
  const orderedEntries = sections.flatMap(s => s.items);

  // Screen 2: Immersive Bauhaus Detail Console when ?item=<key> is active
  if (activeItem) {
    const queue = openBatchQueue?.length ? orderedEntries.filter(e => openBatchQueue.includes(doneKey(e)) || openBatchQueue.includes(openItemId(e))) : orderedEntries;
    const target = queue.find(e => matchesOpenItem(e, activeItem)) || dirDefs.flatMap(d => d.items).find(e => matchesOpenItem(e, activeItem));
    if (target) {
      bauRenderDetail(main, target, queue.length ? queue : [target], activeDir, tag);
      return;
    }
  }

  const isMulti = openMultiMode || openSelected.size > 0;
  const shell = el("div", { class: "bau-open" + (isMulti ? " multi" : "") });

  // Top bar: EITHER clean direction tabs (Normal Mode) OR high-contrast black/green Batch Bar (Multi-Select Mode)!
  if (isMulti) {
    const selectedEntries = entries.filter(e => openSelected.has(doneKey(e)));
    const selCount = selectedEntries.length;
    const batch = el("div", { class: "bau-batchbar", role: "toolbar", "aria-label": t("Batch select") });
    const left = el("div", { class: "bau-bb-l" }, [el("span", { text: t("Selected {n}", { n: selCount }) })]);
    const acts = el("div", { class: "bau-bb-acts" });
    const doneBtn = el("button", { type: "button", class: "bau-bb-btn primary", disabled: !selCount ? "" : null, text: "✓ " + t("Mark done") });
    doneBtn.onclick = () => {
      for (const e of selectedEntries) openSessionDone.add(doneKey(e));
      openSelected.clear(); openMultiMode = false;
      if (liveHere()) closeAll(selectedEntries, "done"); else redrawKeepingScroll();
    };
    const laterBtn = el("button", { type: "button", class: "bau-bb-btn", disabled: !selCount ? "" : null, text: t("Snooze") });
    laterBtn.onclick = () => laterChooser(batch, until => () => {
      openSelected.clear(); openMultiMode = false;
      if (liveHere()) closeAll(selectedEntries, "skipped", until); else redrawKeepingScroll();
    });
    const codexBtn = el("button", { type: "button", class: "bau-bb-btn", disabled: !selCount || !liveHere() ? "" : null, text: t("Hand to Codex") });
    codexBtn.onclick = () => {
      const list = [...selectedEntries];
      openSelected.clear(); openMultiMode = false;
      list.forEach(e => handOver(e, "codex", () => {}, null, el("span")));
      redrawKeepingScroll();
    };
    const ignoreBtn = el("button", { type: "button", class: "bau-bb-btn", disabled: !selCount ? "" : null, text: t("Ignore") });
    ignoreBtn.onclick = () => {
      openSelected.clear(); openMultiMode = false;
      if (liveHere()) closeAll(selectedEntries, "ignored"); else redrawKeepingScroll();
    };
    const seqBtn = el("button", { type: "button", class: "bau-bb-btn accent", disabled: !selCount ? "" : null, text: t("Process selected →") });
    seqBtn.onclick = () => {
      openBatchQueue = selectedEntries.map(openItemId);
      openSelected.clear(); openMultiMode = false;
      location.hash = openHref({ dir: activeDir, tag, item: openBatchQueue[0] });
    };
    const exitBtn = el("button", { type: "button", class: "bau-bb-btn exit", text: t("Exit select") });
    exitBtn.onclick = () => { openSelected.clear(); openMultiMode = false; redrawKeepingScroll(); };
    acts.append(doneBtn, laterBtn, codexBtn, ignoreBtn, seqBtn, exitBtn);
    batch.append(left, acts);
    shell.appendChild(batch);
  } else {
    const dirbar = el("div", { class: "bau-dirbar" });
    const dirs = el("nav", { class: "bau-dirs", role: "tablist" }, dirDefs.map(d =>
      el("a", { class: "bau-dir" + (d.id === activeDir ? " on" : ""), role: "tab", "aria-selected": String(d.id === activeDir),
        href: openHref({ dir: d.id, tag: "", item: "" }) }, [
        t(d.title), el("span", { class: "bau-dir-n", text: String(d.items.filter(e => !openSessionDone.has(doneKey(e))).length) })
      ])));
    const multiBtn = el("button", { type: "button", class: "bau-mode-btn", "aria-pressed": "false", text: "□ " + t("Batch select") });
    multiBtn.onclick = () => { openMultiMode = true; redrawKeepingScroll(); };
    dirbar.append(dirs, el("div", { class: "bau-dir-r" }, [multiBtn]));
    shell.appendChild(dirbar);
  }

  // Calm Single-Row Segmented Filter + 筛选标签 ▾ Dropdown
  const tagCounts = new Map();
  for (const e of dirBucket.items) {
    for (const c of openTags(e).filter(x => !x.id.startsWith("state:")))
      tagCounts.set(c.id, { id: c.id, label: c.label, n: (tagCounts.get(c.id)?.n || 0) + 1 });
  }
  const sortedTags = [...tagCounts.values()].sort((a, b) => b.n - a.n);
  const inlineTags = sortedTags.slice(0, 4);
  const moreTags = sortedTags.slice(4);
  if (tag && !inlineTags.some(c => c.id === tag)) {
    const chosen = sortedTags.find(c => c.id === tag);
    if (chosen) inlineTags.push(chosen);
  }
  const moreDropdown = moreTags.length ? el("details", { class: "bau-tag-dd" }, [
    el("summary", {}, [t("Filter tags"), " ", el("span", { class: "chip-n", text: String(sortedTags.length) }), " ▾"]),
    el("div", { class: "bau-dd-menu" }, sortedTags.map(c => el("a", {
      class: "bau-dd-item" + (c.id === tag ? " on" : ""),
      href: openHref({ dir: activeDir, tag: c.id === tag ? "" : c.id, item: "" })
    }, [el("span", { text: c.label }), el("span", { class: "chip-n", text: String(c.n) })])))
  ]) : null;
  const tagbar = el("nav", { class: "bau-tagbar open-chips", "aria-label": t("Filter the open items") }, [
    el("div", { class: "bau-tags" }, [
      el("a", { class: "bau-tag chip" + (tag ? "" : " on"), href: openHref({ dir: activeDir, tag: "", item: "" }) }, [
        t("All"), el("span", { class: "chip-n", text: String(dirBucket.items.filter(e => !openSessionDone.has(doneKey(e))).length) })
      ]),
      ...inlineTags.map(c => el("a", { class: "bau-tag chip" + (c.id === tag ? " on" : ""),
        href: openHref({ dir: activeDir, tag: c.id === tag ? "" : c.id, item: "" }) }, [
        c.label, el("span", { class: "chip-n", text: String(c.n) })
      ]))
    ]),
    moreDropdown
  ]);
  shell.appendChild(tagbar);

  for (const sec of sections) {
    const secKeys = sec.items.map(doneKey);
    const allSecSelected = secKeys.length > 0 && secKeys.every(k => openSelected.has(k));
    const secEl = el("section", { class: "task-band bau-group" });
    const ghead = el("div", { class: "bau-ghead" + (allSecSelected ? " sel" : "") });
    const selGroupBtn = el("button", { type: "button", class: "bau-gh-sel", text: (allSecSelected ? "☑ " + t("Clear group") : "□ " + t("Select group")) });
    selGroupBtn.onclick = () => {
      if (allSecSelected) secKeys.forEach(k => openSelected.delete(k));
      else { openMultiMode = true; secKeys.forEach(k => openSelected.add(k)); }
      redrawKeepingScroll();
    };
    ghead.append(
      el("div", { class: "bau-gh-l" }, [
        el("span", { class: "bau-gh-dot" + (sec.id === "other" ? " muted" : ""), "aria-hidden": "true" }),
        el("span", { class: "bau-gh-tag", text: sec.label }),
        el("span", { class: "bau-gh-n", text: String(sec.items.length) })
      ]),
      selGroupBtn
    );
    secEl.appendChild(ghead);

    const ul = el("ul", { class: "threads bau-list" });
    for (const entry of sec.items) {
      const key = doneKey(entry), done = openSessionDone.has(key), checked = openSelected.has(key);
      const who = openCounterpart(entry), { title, quote, level: quoteLevel } = openDisplayTitle(entry);
      const draft = threadDraft(entry), late = entry.t.due && entry.t.due < calendarDay(REM.as_of) && !staleEntry(entry);
      const task = rowTask(entry), taskNode = !done && task ? taskStatusNode(task, entry) : null;

      const selBox = el("button", { type: "button", class: "bau-selbox bau-edge-col", role: "checkbox", "aria-checked": String(checked),
        "aria-label": t("Batch select"), text: checked ? "✓" : "" });
      selBox.onclick = ev => {
        ev.stopPropagation();
        if (checked) openSelected.delete(key); else { openMultiMode = true; openSelected.add(key); }
        redrawKeepingScroll();
      };

      const circle = el("button", { type: "button", class: "bau-circle", "aria-label": t(done ? "Undo" : "Mark done"),
        title: t(done ? "Undo" : "Mark done"), text: done ? "✓" : "" });
      circle.onclick = ev => { ev.stopPropagation(); bauCloseEntry(entry, !done); };

      const whatNode = el("div", { class: "what", html: inline(title, entry.r.path) });
      const whatPublic = whatNode.cloneNode(true);
      whatPublic.querySelectorAll(".private").forEach(n => n.remove());
      const allPrivate = (whatNode.querySelector(".private") && !/[\p{L}\p{N}]/u.test(whatPublic.textContent || ""))
        || hasPrivacy(entry.t.originalText || entry.t.text || "");
      const snipNode = quote && !(quoteLevel && privacyLevel === "public")
        ? el("span", { class: "bau-snip" + (quoteLevel ? " private" : ""), ...(quoteLevel ? { "data-level": quoteLevel } : {}), text: "— " + quote.replace(RAW_MARK, "") }) : null;
      if (snipNode && quoteLevel) applyPrivacy(snipNode);
      const mainCell = el("div", { class: "bau-main" }, [
        whatNode,
        taskNode,
        snipNode
      ]);
      mainCell.onclick = () => {
        if (isMulti) { selBox.click(); return; }
        openBatchQueue = null;
        location.hash = openHref({ dir: activeDir, tag, item: openItemId(entry) });
      };

      const whoCell = el("div", { class: "bau-who" }, [
        el("a", { href: href(who), text: threadWho(who) })
      ]);

      const closedState = openSessionStates.get(key) || "done";
      const closedWord = closedState === "skipped" ? (uiLanguage === "zh" ? "已推迟 · 撤销" : "Snoozed · Undo")
        : closedState === "ignored" ? (uiLanguage === "zh" ? "已忽略 · 撤销" : "Ignored · Undo") : t("Done · Undo");
      const rest = el("div", { class: "bau-rest" }, [
        done ? el("button", { type: "button", class: "bau-undo-btn", text: closedWord }) : null,
        !done && draft ? el("span", { class: "bau-pill", text: t("Draft") }) : null,
        !done && (entry.mergedCount || 1) > 1 ? el("span", { class: "bau-pill merge", text: t("Merged {n}", { n: entry.mergedCount }) }) : null,
        !done ? el("span", { class: "when" + (late ? " overdue" : ""), text: threadAge(entry.t) }) : null
      ]);
      if (done) rest.querySelector(".bau-undo-btn").onclick = ev => { ev.stopPropagation(); bauCloseEntry(entry, false); };

      const snoozeBtn = el("button", { type: "button", class: "bau-hbtn", text: t("Snooze") });
      snoozeBtn.onclick = ev => { ev.stopPropagation(); laterChooser(snoozeBtn.parentElement, until => () => bauCloseEntry(entry, true, "skipped", until)); };
      const openBtn = el("button", { type: "button", class: "bau-hbtn g", text: t("Details →") });
      openBtn.onclick = ev => { ev.stopPropagation(); openBatchQueue = null; location.hash = openHref({ dir: activeDir, tag, item: openItemId(entry) }); };
      const hoverActs = el("div", { class: "bau-hover-acts" }, [snoozeBtn, openBtn]);

      ul.appendChild(el("li", { class: "thread bau-row " + entry.t.dir + (checked ? " sel" : "") + (done ? " done-inline" : "") + (allPrivate ? " private-item" : "") }, [
        selBox, circle, mainCell, whoCell, el("div", { class: "bau-right" }, [rest, hoverActs])
      ]));
    }
    secEl.appendChild(ul);
    shell.appendChild(secEl);
  }

  main.appendChild(shell);

  // Bottom in-place completion toast (lets you Undo or Hide completed cleanly)
  document.querySelector(".bau-toast")?.remove();
  if (openSessionDone.size) {
    const hideBtn = el("button", { type: "button", text: t("Hide completed") });
    hideBtn.onclick = () => { openSessionDone.clear(); redrawKeepingScroll(); };
    document.body.appendChild(el("div", { class: "bau-toast", role: "status" }, [
      el("span", { text: t("{n} checked off in place", { n: openSessionDone.size }) }),
      hideBtn
    ]));
  }

  const quiet = quietThreads(dirBucket.items);
  if (quiet) main.appendChild(quiet);
  const done = markedDone(all);
  if (done) main.appendChild(done);
}
// Filters over the open list (#3072: «你也没用上标签…学生的事我想一键全选标完成»). A chip is a tag in words with its
// count; one tap filters, a second clears. Pages carry no tags of their own yet, so the chips are built from what
// each row already knows: whether the last word was his (the night's reply state on the row, today.py), and
// where its page sits: the person's organisation, the organisation's own page, the project. The filter rides
// the address (tag=), so a reload or the back button keeps it.
function normalizeOpenOrgName(raw) {
  if (!raw) return "";
  const trimmed = String(raw).replace(CHIP_SUFFIX, "").replace(/\s{2,}/g, " ").replace(/[.,]+$/, "").trim();
  const match = inCategory("orgs").find(o => {
    const on = orgName(o).replace(CHIP_SUFFIX, "").replace(/\s{2,}/g, " ").replace(/[.,]+$/, "").trim();
    return on.toLowerCase() === trimmed.toLowerCase();
  });
  return match ? orgName(match) : trimmed || raw;
}
function openTags(entry) {
  const r = openCounterpart(entry);
  // A person's place is the organisation People names (personOrg), normalized so "Acme Pty Ltd" and "Acme" share one band.
  const rawPlace = r.category === "people" ? personOrg(r)?.name || "" : r.category === "orgs" ? orgName(r) : r.category === "projects" ? pageName(r) : "";
  const name = r.category === "projects" ? rawPlace : normalizeOpenOrgName(rawPlace);
  const place = name ? [{ id: (r.category === "projects" ? "project:" : "org:") + name.toLowerCase(), label: name }] : [];
  // The item's own tags (#3093): its queue row's, else its page's; each a chip, so "close all 9900" is one filter away.
  const row = (REM.today_queue || []).find(row => (row.keys || [row.key]).includes(doneKey(entry)));
  // A tag naming an organisation is that organisation's place chip, so "Harbour Uni" the place and "Harbour Uni" the tag are one
  // chip, not two (rc35 hunt).
  const tagChip = slug => {
    const page = byPath(REM.tags[slug].page || "");
    if (page?.private && privacyLevel !== "all") return null;
    if (page?.category === "orgs") {
      const oLabel = normalizeOpenOrgName(orgName(page));
      return { id: "org:" + oLabel.toLowerCase(), label: oLabel };
    }
    const cName = chipName(slug);
    return { id: "tag:" + slug, label: cName.name || tagLabel(slug) };
  };
  const pageTags = (row?.tags || r.tags || []).filter(slug => REM.tags?.[slug]).map(tagChip).filter(Boolean)
    .filter((chip, i, all) => !place.some(p => p.id === chip.id || p.label.toLowerCase() === chip.label.toLowerCase()) && all.findIndex(c => c.id === chip.id) === i);
  if (!waitingOnYou(entry)) return [...place, ...pageTags];
  const replied = queuedReply(entry)?.state === "replied";
  return [{ id: replied ? "state:replied" : "state:owe", label: t(replied ? "I replied, waiting on them" : "I still owe a reply or an action") }, ...place, ...pageTags];
}
function openTagged(entry, tag) { return openTags(entry).some(({ id }) => id === tag); }
function openChips(entries, active) {
  const found = new Map();
  for (const entry of entries.filter(row => !row.t.quiet && !staleEntry(row)))
    for (const { id, label } of openTags(entry)) found.set(id, { id, label, n: (found.get(id)?.n || 0) + 1 });
  // The two states first, then places by how many rows they hold; a place with one row filters nothing worth a chip.
  const chips = [...found.values()].filter(chip => chip.id.startsWith("state:") || chip.n > 1 || chip.id === active)
    .sort((a, b) => Number(b.id.startsWith("state:")) - Number(a.id.startsWith("state:")) || b.n - a.n).slice(0, 12);
  const all = el("a", { class: "chip" + (active ? "" : " on"), href: "#view=open", "aria-current": active ? null : "true", text: t("All") });
  return el("nav", { class: "open-chips", "aria-label": t("Filter the open items") }, [all, ...chips.map(({ id, label, n }) =>
    el("a", { class: "chip" + (id === active ? " on" : ""), href: "#view=open" + (id === active ? "" : "&tag=" + encodeURIComponent(id)),
      "aria-current": id === active ? "true" : null, title: id === active ? t("Clear this filter") : null }, [label, " ", el("span", { class: "chip-n", text: String(n) })]))]);
}
// With a filter on, one action for every row it shows, in words with the number: it asks nothing more, each row is
// its own mark in the notebook, and the page's one notice carries one Undo for all of them (closeAll).
function bulkBar(entries) {
  if (!entries.length) return emptyState("Nothing open under this filter", "Show everything open →", "#view=open");
  if (!liveHere()) return snapshotCloseLine();
  const n = entries.length, bar = el("div", { class: "bulk-bar handoff-line" });
  const done = el("button", { type: "button", class: "btn-line bulk-done", text: t("Mark all {n} done", { n }) });
  done.onclick = () => closeAll(entries);
  const later = el("button", { type: "button", class: "btn-quiet strip-later bulk-later", text: t("Put all {n} off until…", { n }) });
  later.onclick = () => laterChooser(bar, until => () => closeAll(entries, "skipped", until));
  bar.append(done, later);
  return bar;
}
function connectionReview() {
  const candidate = (REM.reviews || []).find(row => row.status === "pending" && row.kind === "link");
  if (!candidate) return null;
  return el("section", { class: "connection-review", "aria-label": t("Connection awaiting review") }, [
    el("span", { class: "label", text: t("A possible connection · Your judgment needed") }),
    el("h2", { text: pageWords(candidate.question) }),
    el("p", { text: pageWords(candidate.basis) }),
    el("div", { class: "subjects" }, [
      ...candidate.subjects.map(path => el("a", { href: "#r=" + encodeURIComponent(path), text: pageName(byPath(path)) || path })),
      el("a", { href: "#reviews=1", text: t("Review the evidence →") })])]);
}
function todayEntries(entries, section = "today") {
  // Python's snapshot is the ranking authority for both the reader and the night.
  return (REM.today_queue || []).filter(row => row.section === section).map(row =>
    entries.find(entry => (row.keys || [row.key]).includes(doneKey(entry))
      || entry.members?.some(member => (row.keys || [row.key]).includes(doneKey(member)))))
    .filter((entry, i, rows) => entry && !isDone(entry) && rows.indexOf(entry) === i);
}

function todayCards(groups) {
  const sent = sentNote();
  return el("section", { class: "today-brief", "aria-label": t("Needs you") }, [groups.length || sent
    ? el("ol", { class: "today-threads" }, [sent, ...groups.map((group, i) => personCard(group, i === 0, groups.length, i))])
    : el("p", { class: "quiet-line", text: t("Nothing is due in the next three days.") })]);
}
async function approvalRequest(payload) {
  const response = await fetch("/rem/approve", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || t("Could not approve. Try again."));
  return result;
}
function approvalProblems() {
  const issues = (REM.approval_pending || []).filter(item => ["error", "sending", "scheduling", "dispatching"].includes(item.status));
  if (!issues.length) return null;
  return el("section", {class: "approval-problems", "aria-label": t("Approval status")}, issues.map(item => {
    const row = el("p", {role: "status"}, [el("strong", {text: item.to || item.title || t("Task")}), " · ",
      t(item.status === "dispatching" ? "Task dispatch is in progress." : "Delivery not confirmed. Check the provider before sending again."),
      item.error ? " · " + item.error : ""]);
    return item.private ? privateFallback(el("div", {}, [el("div", {class: "private"}, [row])])) : row;
  }));
}
function approvalHeader() {
  const items = REM.approval_outcomes || [];
  if (!items.length && !REM.live) return approvalProblems() || el("span", { hidden: "" });  // a snapshot never gains outcomes later
  // The batch is a worded button that names what it does (owner: «数字给我能点的»), counting only what can go now:
  // an item waiting for the owner to fill a gap is not approved by it. With none that can go there is no button,
  // never a greyed one or a "0" (TOP10 #9); an Undo that brings items back draws the widget again, button and all.
  const ready = readyCount(items);
  const button = ready ? el("button", {id: "approve-all", class: "btn-line approve-all", type: "button", text: t("Approve the {n} REM prepared", {n: ready})}) : null;
  if (button) {
    button.disabled = !REM.live;
    button.onclick = () => openApprovalSheet(REM.approval_outcomes || []);
  }
  return el("div", {class: "approval-header"}, [button, approvalProblems()]);
}
// What can go now: an item waiting for the owner to fill a gap is not approved by the batch. The button and the
// sheet's title both say this number.
function readyCount(items) { return items.filter(item => !item.blocked).length; }
function approvalStatus(value) {
  return value.error || t({held: "Held for 10 minutes", done: "Marked done", queued: "Task queued", dispatched: "Task dispatched", sent: "Sent", cancelled: "Cancelled"}[value.status] || value.status);
}
function openApprovalSheet(items) {
  const bodies = {}, rows = [];
  let busy = false;
  const confirm = el("button", {id: "approval-confirm", type: "button", class: "btn-act", text: t("Confirm")});
  const close = el("button", {type: "button", class: "btn-quiet", text: t("Close")});
  const notice = el("p", {class: "quiet-line", role: "status"});
  const list = el("div", {class: "approval-list"});
  const dialog = el("dialog", {id: "approval-sheet", "aria-labelledby": "approval-title"}, [
    el("header", {}, [el("h2", {id: "approval-title", text: t("Approve the {n} REM prepared", {n: readyCount(items)})}), close]),
    el("p", {class: "quiet-line", text: t("Replies wait 10 minutes. Undo cancels held replies. Handled items are marked done; tasks are queued now.")}),
    list, el("footer", {}, [confirm, notice])]);
  const sync = () => {confirm.disabled = busy || !rows.some(row => row.check.checked && !row.check.disabled);};
  for (const item of items) {
    const check = el("input", {type: "checkbox", "aria-label": item.to || item.title || item.kind});
    check.checked = !item.blocked;
    check.disabled = !!item.blocked;
    check.onchange = sync;
    const result = el("p", {class: "approval-result quiet-line", role: "status"});
    const content = el("div", {class: "approval-content"}, [
      el("strong", {text: item.to || item.title}),
      el("span", {class: "kind-badge", text: t({reply: "Reply", handled: "Already handled", task: "Task"}[item.kind] || item.kind)}),
      item.subject ? el("p", {class: "approval-subject", text: item.subject}) : null,
      el("p", {class: "approval-preview", text: (item.body || item.text || "").split("\n").find(line => line.trim()) || ""})]);
    const row = el("section", {class: "approval-row"}, [el("label", {}, [check, content]), result]);
    if (item.kind === "reply") {
      const text = el("textarea", {"aria-label": t("Reply body"), "data-keep": "approval:" + item.id});
      text.value = item.body || "";
      const save = el("button", {type: "button", class: "btn-quiet", text: t("Save reply")});
      const warning = el("p", {class: "quiet-line", role: "status", text: item.blocked ? t("Fill the marked part first") : ""});
      const details = el("details", {open: !!item.blocked}, [el("summary", {text: t("Review reply")}), text, save, warning]);
      // Boolean HTML attributes must be absent when false.
      if (!item.blocked) details.removeAttribute("open");
      save.onclick = () => {
        const blocked = !text.value.trim() || /[\[\]［］【】]/.test(text.value);
        warning.textContent = blocked ? t("Fill the marked part first") : t("Reply saved for approval");
        check.disabled = blocked; check.checked = !blocked;
        if (!blocked) {
          bodies[item.id] = text.value;
          content.querySelector(".approval-preview").textContent = text.value.split("\n").find(line => line.trim()) || "";
        }
        sync();
      };
      text.oninput = () => {check.checked = false; check.disabled = true; sync();};
      row.appendChild(details);
    }
    rows.push({item, check, result, node: row});
    list.appendChild(item.private ? privateFallback(el("div", {}, [el("div", {class: "private"}, [row])])) : row);
  }
  confirm.onclick = async () => {
    const selected = rows.filter(row => row.check.checked && !row.check.disabled);
    busy = true;
    const controls = rows.flatMap(row => [row.check, ...row.node.querySelectorAll("textarea, button")]).map(node => [node, node.disabled]);
    controls.forEach(([node]) => {node.disabled = true;});
    confirm.disabled = true; close.disabled = true;
    notice.textContent = t("Working…");
    const reply = await approvalRequest({ids: selected.map(row => row.item.id), bodies}).catch(error => ({error: error.message}));
    busy = false; close.disabled = false;
    controls.forEach(([node, disabled]) => {node.disabled = disabled;});
    if (reply.error) {notice.textContent = reply.error; sync(); return;}
    const successful = new Set();
    for (const value of (reply.results || [])) {
      const row = rows.find(row => row.item.id === value.id);
      if (!row) continue;
      row.result.textContent = approvalStatus(value);
      if (value.status === "error") continue;
      successful.add(value.id); row.check.disabled = true;
      row.node.querySelectorAll("textarea, button").forEach(control => {control.disabled = true;});
      if (value.status === "done") for (const key of value.keys || []) threadStates[key] = notebookThreads[key] = {state: "done", at: new Date().toISOString()};
      if (value.draft_id) REM.drafts = (REM.drafts || []).map(d => d.id === value.draft_id ? {...d, status: value.status} : d);
      REM.approval_pending = [...(REM.approval_pending || []).filter(item => item.id !== value.id), {...row.item, ...value}];
    }
    REM.approval_outcomes = (REM.approval_outcomes || []).filter(item => !successful.has(item.id));
    notice.textContent = t("Review the result beside each item.");
    sync(); approvalUndoBar();
  };
  close.onclick = () => dialog.close();
  dialog.addEventListener("close", () => {dialog.remove(); render();});
  if (items.some(item => item.private)) {
    const reveal = el("button", {type: "button", class: "btn-quiet", text: t("Show labelled passages")});
    reveal.onclick = () => { revealLabelled(); reveal.remove(); };
    dialog.querySelector("header").appendChild(reveal);
  }
  document.body.appendChild(dialog); sync(); dialog.showModal();
}
let approvalTimer;
// onToday: Today's "Sent to …" line carries its own Undo, so the bar leaves that reply out there; on Waiting on you,
// where a held reply's row has left with the count, the bar is its Undo.
function approvalUndoBar(onToday = true) {
  clearInterval(approvalTimer);
  document.getElementById("approval-undo")?.remove();
  if (!REM.live) return;
  let held = (REM.approval_pending || []).filter(item => item.status === "held" && Date.parse(item.release_at) > Date.now() && !(onToday && todaySent?.ids?.includes(item.id)));
  if (!held.length) return;
  const status = el("span", {role: "status"});
  let undoFailure = "";
  const undo = el("button", {type: "button", class: "btn-quiet", text: t("Undo")});
  const bar = el("div", {id: "approval-undo", class: "approval-undo"}, [status, undo]);
  document.body.appendChild(bar);
  const tick = () => {
    const seconds = Math.max(0, Math.ceil((Math.max(...held.map(item => Date.parse(item.release_at))) - Date.now()) / 1000));
    const left = Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
    // One reply REM chose to send itself says to whom and when (#3121); several say how many.
    const own = held.length === 1 && held[0].by === "rem" ? held[0] : null;
    status.textContent = (undoFailure ? undoFailure + " · " : "") + (!seconds ? t("Hold ended. Delivery continues from the Host.")
      : own ? t("Sending to {name} at {time} · {left} to undo", { name: own.title, time: new Date(own.release_at).toLocaleTimeString(uiLanguage === "zh" ? "zh-CN" : "en", { hour: "2-digit", minute: "2-digit" }), left })
      : t("{n} replies held · {time} to undo", {n: held.length, time: left}));
    if (!seconds) {undo.disabled = true; clearInterval(approvalTimer);}
  };
  undo.onclick = async () => {
    undo.disabled = true;
    const reply = await approvalRequest({action: "undo", ids: held.filter(item => Date.parse(item.release_at) > Date.now()).map(item => item.id)}).catch(error => ({error: error.message}));
    if (reply.error) {status.textContent = reply.error; undo.disabled = false; return;}
    status.textContent = reply.results.map(approvalStatus).join(" · ");
    for (const value of reply.results) {
      const item = held.find(item => item.id === value.id);
      if (value.status !== "cancelled") continue;
      REM.approval_pending = (REM.approval_pending || []).filter(item => item.id !== value.id);
      REM.approval_outcomes = [...(REM.approval_outcomes || []), item];
      if (item.draft_id) REM.drafts = (REM.drafts || []).map(d => d.id === item.draft_id ? {...d, status: "prepared"} : d);
    }
    undoFailure = reply.results.filter(value => value.status === "error").map(approvalStatus).join(" · ");
    document.getElementById("today-others")?.replaceWith(othersWidget(threadCounts()));
    held = held.filter(item => !reply.results.some(value => value.id === item.id && value.status === "cancelled"));
    undo.disabled = !held.length;
    if (!held.length) clearInterval(approvalTimer);
    else status.textContent += " · " + t("Undo failed. Try again before the hold ends.");
  };
  tick(); approvalTimer = setInterval(tick, 1000);
}

// The receipt's reason is the runner's own English (codex_exec.py). Known ones are said in the reader's
// language; anything else gets a plain sentence for its kind, never the raw string (D-71). The raw
// reason stays on the line's title for whoever debugs it.
function turnTrouble(failure) {
  const evidence = String(failure.evidence || "");
  if (failure.failures) {
    // Local time in the reader's words (#3156: an ISO timestamp in UTC read as a system log).
    const zone = (typeof REM !== "undefined" && REM.status?.timezone) || undefined;
    const since = failure.since ? new Date(failure.since).toLocaleString(uiLanguage === "zh" ? "zh-CN" : "en-GB",
      { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: zone }) : "";
    // `empty`: turns that exited cleanly with no task served and nothing submitted (1.9.6rc18).
    const empty = failure.empty || 0, all = empty === failure.failures;
    // The same code error again and again is a bug a retry cannot fix: say so, and never "nothing to do"
    // (rc36 hunt: six turns on one AttributeError under "REM 会自动重试，不需要你做什么").
    if (failure.code_error) return uiLanguage === "zh"
      ? `后台：夜里的程序出错了（同一个错误 ${failure.code_error} 次），升级到新版本后会继续。自 ${since} 起。`
      : `Background: The night runner hit a code error ${failure.code_error} ${failure.code_error === 1 ? "time" : "times"}; it resumes after an update. Since ${since}.`;
    // The same error turn after turn will not clear by retrying (#3402: five turns on one page's
    // preparation under "REM 会自动重试，不需要你做什么"). Name what is stuck; say 已经跳过 only when the
    // ledger shows it was set aside (`stuck.skipped`, read by status, never assumed). The raw reason stays on the title.
    if (failure.same_error) {
      const n = failure.same_error, stuck = failure.stuck || {}, zh = uiLanguage === "zh";
      const kindZh = { skill: "技能", person: "人物", org: "组织", project: "项目" }[stuck.kind] || "页面";
      const kindEn = { skill: "A skill", person: "A person", org: "An organisation", project: "A project" }[stuck.kind] || "A";
      if (!stuck.kind) return zh
        ? `后台：最近 ${n} 轮都停在同一个错误上，自 ${since} 起。重试解决不了它，要等修复它的新版本。`
        : `Background: the last ${n} turns stopped on the same error, since ${since}. Retrying will not clear it; it needs a release that fixes it.`;
      const what = zh ? (stuck.not_installed ? "有一个技能页的技能已经不在了" : `有一个${kindZh}页准备不了`)
        : (stuck.not_installed ? "A skill page's skill is no longer installed" : `${kindEn} page cannot be prepared`);
      // The installed build already sets it aside (#3413, `stuck.handled` from status): rc21 was installed with
      // the fix while Today still said 「要等修复它的新版本」 for 14 hours. Name the next round instead.
      const nextRun = REM.status?.next_run ? new Date(REM.status.next_run) : null;
      const at = nextRun && !isNaN(nextRun) ? nextRun.toLocaleTimeString(zh ? "zh-CN" : "en-GB",
        { hour: "2-digit", minute: "2-digit", timeZone: zone }) : "";
      const next = stuck.handled
        ? (zh ? `这个问题新版本已经处理，下一轮会跳过它${at ? `（下一轮 ${at}）` : ""}。`
          : `This release already handles it; the next round${at ? ` (${at})` : ""} skips it.`)
        : stuck.skipped
        ? (zh ? `REM 已经跳过它，其余工作照常${stuck.not_installed ? "；要修好它得等新版本" : ""}。`
          : `REM has set it aside and the rest goes on${stuck.not_installed ? "; fixing it needs a new release" : ""}.`)
        : (zh ? "重试解决不了它，要等修复它的新版本。" : "Retrying will not clear it; it needs a release that fixes it.");
      return zh ? `后台：${what}，最近 ${n} 轮都停在它上面（自 ${since} 起）。${next}`
        : `Background: ${what}; the last ${n} turns stopped on it (since ${since}). ${next}`;
    }
    if (uiLanguage === "zh") return `后台：最近 ${failure.failures} 轮${all ? "运行了但没有产出" : "失败"}${empty && !all ? `（其中 ${empty} 轮运行了但没有产出）` : ""}，自 ${since} 起。REM 会自动重试，不需要你做什么。`;
    const said = all ? (failure.failures === 1 ? "turn ran but produced nothing" : "turns ran but produced nothing")
      : (failure.failures === 1 ? "turn failed" : "turns failed") + (empty ? ` (${empty} ran but produced nothing)` : "");
    return `Background: the last ${failure.failures} ${said}, since ${since}. REM retries by itself; nothing is needed from you.`;
  }
  if (/^Turn exceeded \d+ hours/.test(evidence)) return t("One round last night ran too long and was stopped; the next round continues.");
  if (/^MAINTENANCE_BUSY\b/.test(evidence)) return t("Another job was holding the notebook, so the last round did not run; the next round tries again.");
  return t(failure.code === "blocked" ? "The last scheduled round could not finish and is waiting for its blocker to clear."
    : "The last two scheduled rounds did not finish; REM retries them automatically.");
}
// Last night's numbers live with the processing details, not on the first screen.
function passSummary() {
  const pass = lastPass();
  return pass ? el("p", { class: "pass-summary" }, [t(firstBuild() ? "Built today: read {n} items · wrote {m} pages" : "Last night: read {n} items · rewrote {m} pages",
    { n: pass.items, m: pass.changed.length })]) : null;
}
function notebookLanguages() {
  const languages = REM.your_languages || [];
  // REM detects the languages you write (D-103); settings shows them, with no command to change them (D-60).
  return el("div", { class: "notebook-languages" }, [
    el("div", { text: t("Notebook languages") + (uiLanguage === "zh" ? "：" : ": ") + (languages.map(nativeName).join(" · ") || t("Unknown")) + " — " + t(REM.languages_from || "detected") })]);
}
// A page without a Chinese version keeps its original words everywhere; opening
// it in the live reader queues the translation once and says so under the title.
function translationQueued(r) {
  if (!REM.live || uiLanguage !== "zh" || r.translations?.zh || /^zh(?:-|$)/i.test(r.written_in || "")) return false;
  if (!r.translationRequested) {
    r.translationRequested = true;
    fetch("/rem/translation-request", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ page: r.path, language: "zh" }) });
  }
  return true;
}
function translationNotice() {
  if (uiLanguage !== "zh") return null;
  const pages = listedRecords().filter(r => r.written && ["people", "orgs", "projects", "decisions", "principles", "skills"].includes(r.category));
  const missing = pages.filter(r => !r.translations?.zh && !/^zh(?:-|$)/i.test(r.written_in || ""));
  if (!missing.length) return null;
  const run = (REM.logs || REM.brief_logs || []).find(run => /translat/.test(run.phase || ""));
  const failed = run?.translation_failures ?? (run?.pages || []).filter(page => page.outcome === "failed").length;
  const failure = failed ? t(failed === 1 ? "{n} page could not be translated." : "{n} pages could not be translated.", { n: failed }) + " " : "";
  const go = translateAll();
  return el("p", { class: "translation-note quiet-line", text: failure + t("Pages are translated when you open them.") }, go ? [go] : undefined);
}
// «全部翻译成中文» (#2999). The owner, 2026-11-13: «有的页面是中文，有的是英文，有的是中英文混合，一键让 Codex 全部都
// 翻译». One worded button starts the job `co rem translate` runs, on the Host (POST /rem/translate-all, the same
// loopback, cookie and JSON-only rules as every other write); it then says how far it is, «已翻译 120 / 639», and
// offers Stop. Every copy of the control on the page shows the same job; no command to copy anywhere (D-60).
let translateAllJob = null, translateAllPoll = null, translateAllAsked = false, translateAllWait = 1500;
function translateAllLanguage() {
  return /^zh(?:-|$)/i.test(REM.owner_language || "") ? REM.owner_language : "zh";
}
// Opening the reader asks the Host nothing (#3349): the job's state is read once, when the owner opens a control that
// starts or follows it (Settings, the language menu, the phone's 显示 menu). It used to be read on every page load and
// every reload: a POST that makes the Host count the whole translation queue (seconds on a real notebook), three times
// in one hunt session with no click. Until the owner opens one, the counts are the page's own.
function askTranslateStatus() {
  if (!liveHere() || translateAllAsked) return;
  translateAllAsked = true;
  translateAllSend("status");
}
function translateAll() {
  if (!liveHere() || !(uiLanguage === "zh" || /^zh(?:-|$)/i.test(REM.owner_language || ""))) return null;
  const box = el("span", { class: "translate-all", role: "status", "aria-live": "polite" });
  drawTranslateAll(box);
  return box;
}
function drawTranslateAll(box) {
  const job = translateAllJob || { state: "idle" }, busy = ["starting", "running", "stopping"].includes(job.state);
  const count = job.total != null ? t("Translated {n} / {m}", { n: job.done, m: job.total }) : "";
  const words = job.offline ? t("Lost touch with REM; trying again…")
    : job.state === "starting" ? t("Getting the pages ready…")
    : job.state === "stopping" ? count + " · " + t("Stopping after the pages already begun…")
    : job.state === "refused" ? t("The translation was refused; try again in a moment.")
    : job.state === "failed" && job.error ? t("Translation could not start: {why}.", { why: job.error })
    : job.halted ? t("Stopped: the rest of the Codex week is kept for your own work, at {n} / {m}.", { n: job.done, m: job.total })
    : job.total != null && job.done >= job.total ? t("Every page reads in Chinese.")
    : job.state === "stopped" ? t("Stopped.") + " " + count
    : count;
  const failed = !busy && job.failed ? t(job.failed === 1 ? "{n} page could not be translated." : "{n} pages could not be translated.", { n: job.failed }) : "";
  const parts = [words || failed ? el("span", { class: "ta-state", text: [words, failed].filter(Boolean).join(" ") }) : null];
  if (busy) {
    const stop = el("button", { type: "button", class: "ta-stop", text: t("Stop translating") });
    stop.disabled = job.state === "stopping";
    stop.onclick = () => translateAllSend("stop");
    parts.push(stop);
  } else if (!(job.total != null && job.done >= job.total)) {
    // The cost in words, on the button itself: no confirmation for a one-click he asked for.
    const left = job.total != null ? job.total - job.done : 0;
    const go = el("button", { type: "button", class: "ta-go",
      text: left ? t("Translate every page into Chinese ({n} pages)", { n: left }) : t("Translate every page into Chinese") });
    go.onclick = () => translateAllSend("start");
    parts.push(go);
  }
  box.replaceChildren(...parts.filter(Boolean));
}
// A refused request (409, a RemError) says so in words and offers the button again; a request that never
// arrived keeps asking, waiting longer each time, so the line is never left saying it is running.
async function translateAllSend(action) {
  clearTimeout(translateAllPoll);
  translateAllPoll = null;
  let response = null;
  try {
    response = await fetch("/rem/translate-all", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, language: translateAllLanguage() }) });
  } catch {
    translateAllJob = { ...(translateAllJob || { state: "idle" }), offline: true };
  }
  // A refused start or stop says so. A refused status read is a busy moment: the line keeps what it said (a
  // running job stays running) and asks again, waiting longer each time, like a request that never arrived.
  if (response && !response.ok && action === "status") translateAllJob = { ...(translateAllJob || { state: "idle" }), offline: false, retry: true };
  else if (response && !response.ok) translateAllJob = { ...(translateAllJob || {}), state: "refused", offline: false, retry: false };
  else if (response) { translateAllJob = await response.json(); translateAllWait = 1500; }
  for (const box of document.querySelectorAll(".translate-all")) drawTranslateAll(box);
  renderLangProgress();
  if (["starting", "running", "stopping"].includes(translateAllJob.state)) {
    translateAllWait = translateAllJob.offline || translateAllJob.retry ? Math.min(translateAllWait * 2, 30000) : 1500;
    translateAllPoll = setTimeout(() => translateAllSend("status"), translateAllWait);
  }
}

// ---------- Today as a card desk (N3, D-123) ----------
// The night chart and the faces of who waits on top; one raised card (the deck) with the page's one green
// action; at its side what others owe and what REM did overnight. Everything else of
// the old front page is one fold below.
let todayLead = null;
function deckOrder(groups) {
  const lead = groups.findIndex(group => group.r.path === todayLead);
  // Among cards ready to send, one whose draft needs nothing from the owner goes on top: a slot makes the top
  // card a question; with every draft slotted, the first still leads. A slot is what replyDraftCard holds Send
  // for (its isSlot: any [, ［ or 【 part), so the card on top is one whose Send works at once.
  const sendable = groups.map((group, i) => [i, groupStep(group.entries)]).filter(([, next]) => next.step === "send");
  const complete = sendable.find(([, next]) => !/[\[［【]/.test(threadDraft(next.entry)?.body || ""));
  const ready = (complete || sendable[0] || [-1])[0];
  const first = lead >= 0 ? lead : Math.max(0, ready);
  const ordered = [...groups.slice(first), ...groups.slice(0, first)];
  if (lead >= 0) return ordered;  // a card the owner raised stays where he put it
  // People waiting on him come before work an agent already holds (#3312): a handed-off item that is not overdue
  // goes behind the cards only he can answer (Mac rc11 pass: two Codex rows pushed the first reply below the fold).
  const agentWork = group => group.entries.every(entry => handed(rowTask(entry))) && !group.entries.some(entry => overdueDays(entry.t));
  return [...ordered.filter(group => !agentWork(group)), ...ordered.filter(agentWork)];
}
// Deal another card: the faces, J/K and Skip only change which card is raised; nothing is written and nothing
// is drawn again. Every card is already in the page, so what was typed in any of them stays where it was.
function dealCard(path) {
  const cards = [...document.querySelectorAll("#main .today-brief .qcard")];
  const next = cards.find(card => card.dataset.path === path);
  if (!next) return;
  todayLead = path;
  for (const card of cards) raiseCard(card, card === next);
  for (const face of document.querySelectorAll("#main .deal, #main .bau-strip-btn")) {
    const on = face.dataset.path === path;
    face.classList.toggle("on", on);
    face.setAttribute(face.classList.contains("bau-strip-btn") ? "aria-selected" : "aria-pressed", String(on));
  }
  const chart = document.querySelector("#main .night-card .hyp-wrap"), redrawn = chart && nightChart(path);
  if (redrawn) chart.replaceWith(redrawn.svg);
  next.focus({ preventScroll: true });
}
// The raised card is open and carries the page's one green action; a card behind its face carries none.
function raiseCard(card, raised) {
  card.classList.toggle("focal", raised);
  card.classList.toggle("open", raised);
  for (const button of card.querySelectorAll(":scope > .card-acts :is(.btn-act, .btn-line)")) {
    button.classList.toggle("btn-act", raised);
    button.classList.toggle("btn-line", !raised);
  }
}
// The next card is the next one in the page: the notebook may already hold someone the page has not drawn yet.
function dealNext(step) {
  const cards = [...document.querySelectorAll("#main .today-brief .qcard")];
  if (cards.length < 2) return;
  const at = cards.findIndex(card => card.classList.contains("focal"));
  dealCard(cards[(at + step + cards.length) % cards.length].dataset.path);
}
// An event that came without a title says what it is: focus time, out of office, or busy on a calendar
// shared without its details (with that calendar's name). Only an event of his own with no title is "No title".
function eventTitle(e) {
  if (e.title) return e.title;
  if (e.label === "Busy" && e.calendar_name) return t("Busy ({calendar})", {calendar: e.calendar_name});
  return t(e.label || "No title");
}
// A proposal is three things in words: when (or that there is no time), what in two lines with the whole
// sentence in its title, and one short link to its page. The sentence is not a link: a whole underlined
// paragraph read as an error, and five of them filled a phone.
// The plan saved the line as the night read it; the card above shows the same item in the reader's language and
// in the second person, so the proposal says it the card's way whenever the item is still on the page.
function proposalWords(item) {
  const keys = item.keys || [item.key];
  const entry = typeof threadEntries === "function" ? threadEntries().find(entry => keys.includes(doneKey(entry)) || entry.members?.some(member => keys.includes(doneKey(member)))) : null;
  return entry ? morningWords(entry.t.text, entry.r, entry.t).words : item.text;
}
function dayPlanVisible(item) {
  if (item.kind !== "proposal") return true;
  const keys = item.keys || [item.key], states = typeof threadStates === "undefined" ? REM.threads || {} : threadStates;
  if (keys.every(key => closedMark(states[key]))) return false;
  const current = REM.today_queue?.find(row => keys.includes(row.key) || row.keys?.some(key => keys.includes(key)));
  if (current && (current.closed || current.quiet || current.reply?.state === "replied")) return false;
  if (typeof threadEntries === "function") {
    const entry = threadEntries().find(entry => keys.includes(doneKey(entry)) || entry.members?.some(member => keys.includes(doneKey(member))));
    if (entry && !waitingOnYou(entry)) return false;
  }
  return true;
}
// To-dos are not events (#3087): they sit in their own short section, each row saying in words that it is a
// to-do, when it is due (or that it is overdue), and which list it is on. Nothing is ticked off here: that is
// done in Microsoft To Do, and the next read drops it. What could not be read is said, never skipped silently.
function todoDue(task, today) {
  if (!task.due) return t("no due date");
  return task.due === today ? t("due today") : t(task.due < today ? "overdue since {date}" : "due {date}", {date: calendarDate(task.due)});
}
function todoNotes(todos) {
  const last = !todos.read_at ? "" : " " + t(todos.tasks.length ? "These to-dos are from {when}." : "The last read, on {when}, found none open.", {when: fmtTime(todos.read_at)});
  const failed = todos.error && t("Microsoft To Do could not be read on {when} ({reason}).", {when: fmtTime(todos.error.at),
    reason: t(todos.error.reason) + (todos.error.error ? " · " + todos.error.error : "")}) + last;
  const google = todos.google === "reconnect" ? t("Google Tasks are not read: Google must be reconnected with access to tasks.")
    : todos.google === "not_read" ? t("Google Tasks are not read yet.") : null;
  return [failed, google].filter(Boolean);
}
function todoRow(task, today) {
  return el("li", {class: "day-plan-item todo-item"}, [
    el("p", {class: "day-plan-when", text: t("To-do") + " — " + todoDue(task, today)}),
    el("p", {class: "day-plan-text", title: task.title, text: task.title}),
    task.list ? el("p", {class: "todo-list-name", text: t("List: {list}", {list: task.list})}) : null]);
}
function todoSection() {
  const todos = REM.todos, limit = 8;
  if (!todos || REM.shared) return null;
  const today = calendarDay(REM.as_of), notes = todoNotes(todos);
  // Overdue first, then by due day; the ones with no date last.
  const tasks = [...todos.tasks].sort((a, b) => (a.due || "9999").localeCompare(b.due || "9999"));
  if (!tasks.length && !notes.length && !todos.read_at) return null;
  // One statement when nothing is listed (#3085: "no open to-dos" stood over "a task list was not read", a false
  // empty). "No open to-dos" is said only when every connected list was read and none holds one; with a list
  // unread the section says which, and why, and of the one that was read only that it has none open.
  const empty = tasks.length ? null : !notes.length ? t("No open to-dos.")
    : [todos.read_at && !todos.error ? t("Microsoft To Do has no open to-dos.") : null, ...notes].filter(Boolean).join(" ");
  return el("section", {class: "day-plan todos", "aria-label": t("To-dos")}, [el("h2", {text: t("To-dos")}),
    tasks.length ? el("ul", {class: "day-plan-list"}, tasks.slice(0, limit).map(task => todoRow(task, today))) : el("p", {class: "todo-empty", text: empty}),
    tasks.length > limit ? el("p", {text: t("{n} more to-dos in Microsoft To Do.", {n: tasks.length - limit})}) : null,
    ...(tasks.length ? notes.map(text => el("p", {class: "todo-note", text})) : [])]);
}

// Where a closed item went (#3072: «我想把它标成没完成怎么办»). Two folds under the deck, each named by its count:
// Finished today holds what was marked done or ignored on this calendar day, each with Bring back; Put off holds
// every Not now that has not come back yet, whenever it was put off, each saying when it returns, with Bring back
// now. Finished today empties at midnight; what was finished earlier stays in Waiting on you's closed list and on
// its own page's history, where Undo still works. A snapshot keeps no marks, so it has neither fold.
const CLOSED_OPEN = new Set();
function closedLists() {
  const closed = threadEntries().filter(isDone).map(entry => ({ entry, value: threadStates[doneKey(entry)] }));
  return { finished: closed.filter(({ value }) => value.state !== "skipped" && localDay(value.at || 0) === localDay(clockNow())),
    put: closed.filter(({ value }) => value.state === "skipped") };
}
function closedRow({ entry, value }) {
  const who = entry.who || (entry.r.path === REM.owner ? ownerCounterpart(entry) : null) || entry.r;
  const back = el("button", { type: "button", class: "btn-quiet bring-back", text: t(value.state === "skipped" ? "Bring back now" : "Bring back") });
  back.onclick = () => { todayLead = who.path; setDone(entry, false, "done", [entry]); };
  const when = value.state === "skipped" ? capFirst(value.until ? backWords(value.until) : t("back when new mail arrives"))
    : stateWord(value.state) + " · " + new Date(value.at).toLocaleTimeString(uiLocale(), { hour: "2-digit", minute: "2-digit" });
  return el("li", { class: "closed-row", "data-path": who.path }, [el("a", { href: href(who), text: threadWho(who) }),
    wordsLine("closed-what", morningWords(entry.t.text, entry.r, entry.t).words, entry.r, []), el("span", { class: "closed-when", text: when }), back]);
}
function closedFold(id, title, rows, note) {
  if (!rows.length) return null;
  const fold = el("details", { id, class: "closed-fold fold" }, [el("summary", { text: t(title, { n: rows.length }) }),
    el("p", { class: "quiet-line", text: t(note) }), el("ul", { class: "closed-rows" }, rows.map(closedRow))]);
  fold.open = CLOSED_OPEN.has(id);
  fold.addEventListener("toggle", () => CLOSED_OPEN[fold.open ? "add" : "delete"](id));
  return fold;
}
function closedToday() {
  if (!liveHere()) return null;
  const { finished, put } = closedLists();
  const folds = [closedFold("finished-today", "Finished today: {n}", finished, "This list is today's and empties at midnight. Earlier ones stay at the foot of Waiting on you."),
    closedFold("put-off", "Put off: {n}", put, "Each comes back to Today at the time it says, or sooner if new mail arrives.")].filter(Boolean);
  return folds.length ? el("section", { id: "today-closed", "aria-label": t("Finished and put off") }, folds) : null;
}
// The notice's last words: the list that now holds the item, with that list's own count, opening it in place.
function closedLink(id) {
  if (railActive() !== "today") return null;
  const lists = closedLists(), n = (id === "put-off" ? lists.put : lists.finished).length;
  if (!n) return null;
  const link = el("button", { type: "button", class: "closed-link", text: t(id === "put-off" ? "Put off: {n}" : "Finished today: {n}", { n }) });
  link.onclick = () => {
    const fold = document.getElementById(id);
    if (!fold) return;
    fold.open = true;
    fold.scrollIntoView({ block: "center" });
    fold.querySelector("summary").focus({ preventScroll: true });
  };
  return link;
}
// A put-off item that is back says so on its card: when it was put off, and what brought it back.
function putOffNote(entry) {
  const value = entry.r && REM.threads?.[doneKey(entry)];
  if (value?.state !== "skipped" || !(value.returned_at || putOffOver(value))) return null;
  const mail = value.returned_at && !(value.until && value.returned_at >= value.until);
  return el("p", { class: "put-off-note", text: t(mail ? "You put this off on {date}; new mail brought it back." : "You put this off on {date}; it is back as you asked.",
    { date: new Date(value.at).toLocaleDateString(uiLocale(), { day: "numeric", month: "short" }) }) });
}
// The deck deals the most pressing few; the header counts every item that waits on you. When they differ the deck
// says so in words and links the whole list (#3071, #3085: four different numbers on one page, none named).
function deckRest(groups, counts) {
  const shown = groups.reduce((n, group) => n + group.entries.length, 0);
  const held = threadEntries().filter(entry => !isDone(entry) && waitingOnYou(entry) && agentBusy(entry)).length;
  if (!shown || shown + held >= counts.mine) return null;
  return el("p", { class: "deck-rest quiet-line" }, [t(shown === 1 ? "This card is the most pressing 1 of the {n} waiting on you." : "These cards are the most pressing {k} of the {n} waiting on you.", { k: shown, n: counts.mine }), " ",
    el("a", { href: "#view=open", text: t("See all {n} →", { n: counts.mine }) })]);
}

// Today's order (#3072: the schedule opened the page, «全是信息，没有 call to action»): first what can be acted on,
// the count and the deck with the work in hand above it; then what was asked about and what was closed; then the
// lists that are only read, to-dos and the day's calendar; then the folds.
function bauTodayStrip(cards) {
  if (cards.length < 2) return null;
  return el("div", { class: "bau-strip", role: "tablist", "aria-label": t("Today") }, cards.slice(0, 5).map((group, i) => {
    const first = group.entries[0], { title } = openDisplayTitle(first), late = groupLate(group);
    const btn = el("button", { type: "button", class: "bau-strip-btn" + (i === 0 ? " on" : ""), "data-path": group.r.path, "aria-selected": String(i === 0) }, [
      el("div", { class: "bau-strip-k" }, [el("span", { text: String(i + 1).padStart(2, "0") }), el("span", { text: late ? t("{n} d", { n: late }) : threadAge(first.t) })]),
      el("div", { class: "bau-strip-t", text: title }),
      el("div", { class: "bau-strip-w", text: threadWho(group.r) })
    ]);
    btn.onclick = () => dealCard(group.r.path);
    return btn;
  }));
}
function overview() {
  document.querySelector(".bau-toast")?.remove();
  const cur = typeof route === "function" ? route() : {};
  const showCalendar = cur.view === "agenda" || cur.category === "agenda";
  const main = document.getElementById("main"), inDeck = !!document.activeElement?.closest("#main .qcard");
  main.textContent = "";
  const entries = threadEntries().filter(entry => !isDone(entry)), counts = threadCounts(), groups = todayGroups(entries.filter(entry => !agentBusy(entry)));
  approvalUndoBar();
  const cards = deckOrder(groups);
  const ticked = groups.length < shownCount;
  shownCount = groups.length;
  main.append(...whyNotes(), ...[snapshotLine(), firstMapBrief(), nightCard(groups, cards[0]?.r.path, ticked), workStrip(),
    todayNextLine(),
    el("div", { class: "tgrid" }, [el("div", { class: "deck" }, [deskHead(groups, cards[0]?.r.path, ticked), todayCards(cards), bauTodayStrip(cards), deckRest(groups, counts)]), todaySide(counts)]),
    showCalendar ? todayCalendar() : null, staleWidget(todayEntries(entries).filter(staleEntry)), closedToday(), todoSection(), todayFolds(entries, counts)].filter(Boolean));
  if (showCalendar) tcalScroll();
  if (inDeck) focusRaisedCard();  // a redraw (a save confirmed, new mail) never takes the keyboard out of the deck
}
function scheduleFailure() {
  const failure = REM.status?.schedule_failure;
  return failure ? el("p", { class: "schedule-failure", role: "status", title: failure.evidence || "", text: turnTrouble(failure) }) : null;
}
// The top bar names the day; on a phone the crumb is the page's title.
function todayCrumb() {
  const day = calendarDay(REM.as_of), date = new Date(day + "T00:00:00Z"), locale = uiLanguage === "zh" ? "zh-CN" : "en-GB";
  const weekday = date.toLocaleDateString(locale, { weekday: "short", timeZone: "UTC" });
  const calendar = date.toLocaleDateString(locale, { day: "numeric", month: "long", timeZone: "UTC" });
  return uiLanguage === "zh" ? calendar + " " + weekday : weekday + ", " + calendar;
}
// A face is a circle with initials; an overdue one wears a fuse ring burnt by overdue days / 14.
const RING = 314.16;
function fusedFace(r, late, size = "l") {
  const node = face(threadWho(r), size);
  const burn = Math.min(1, late / 14);
  node.append(el("span", { class: "ring-host", "aria-hidden": "true", html: '<svg class="ring" viewBox="-4 -4 108 108"><circle class="track" cx="50" cy="50" r="50"/>'
    + (burn ? '<circle class="burn" cx="50" cy="50" r="50" stroke-dasharray="' + (burn * RING).toFixed(1) + ' ' + RING + '"/>' : "") + "</svg>" }));
  return node;
}
function groupLate(group) { return Math.max(0, ...group.entries.filter(entry => entry.t.dir === "mine").map(entry => overdueDays(entry.t))); }
function faceStrip(groups, current) {
  return el("div", { class: "frow", role: "group", "aria-label": t("Who is waiting, and how late") }, groups.map(group => {
    const late = groupLate(group), name = threadWho(group.r);
    const button = el("button", { type: "button", class: "deal" + (group.r.path === current ? " on" : ""), "data-path": group.r.path,
      "aria-pressed": String(group.r.path === current), "aria-label": name + " · " + (late ? t(late === 1 ? "1 day overdue" : "{n} days overdue", { n: late }) : threadAge(group.entries[0].t)) }, [
      fusedFace(group.r, late), el("span", { class: "dd" + (late ? " late" : ""), text: late ? t("{n} d", { n: late }) : threadAge(group.entries[0].t) })]);
    button.onclick = () => dealCard(group.r.path);
    return button;
  }));
}
// The one "waiting on you" number is the rail badge's: the items in Waiting on you that need the owner, so the
// header, the badge and the list never disagree (sprint 14 #4). The faces beside it are the people to start with;
// their place and size say so, and the line "start with these N people" went (owner, 2026-11-13, #2994).
function countLine(ticked, cards = 0) {
  const mine = threadCounts().mine;
  if (!mine) return el("h1", { class: "count-line" }, [el("b", { class: "count", text: "0" }), el("span", { class: "count-words", text: t("Nobody is waiting on you today.") })]);
  return el("h1", { class: "count-line" }, [el("b", { class: "count" + (ticked ? " ticked" : ""), text: String(mine) }),
    el("span", { class: "count-words", text: t(mine === 1 ? "thing waiting on you" : "things waiting on you") }),
    // The deck deals fewer cards than the count; the title says which set its ‹ 1 / k › pages through (#3379:
    // «18 件在等你» over a card reading ‹ 1 / 2 ›, two numbers and nothing joining them).
    cards && cards < mine ? el("span", { class: "count-scope", text: t(cards === 1 ? "· start with this one" : "· start with these {k}", { k: cards }) }) : null]);
}
// On a phone the chart folds under its title; the title opens it.
function chartToggle() {
  const button = el("button", { type: "button", class: "chart-toggle", "aria-expanded": "false" }, [t("Night chart"), icon("down")]);
  button.onclick = () => button.setAttribute("aria-expanded", String(button.closest(".night-card").classList.toggle("chart-open")));
  return button;
}
// What last night produced, in words and counts (Mac review of rc30: the chart's flat lines, spikes and "RU +4"
// could not be read): mails read, pages written, replies and tasks prepared. Nothing done says so in one line.
// The whole night in one count: the curve's own stretches added up (#3396). Rc19 gave three totals for one night:
// the heading counted the latest 21 runs' reads as "mails" and the pass's investigations as pages written, the
// captions counted each stretch, and the side line counted items on the desk. Now the heading and the captions are
// the same numbers in the same words; the side line counts waiting items and says so.
function nightTotals(asOf) {
  const totals = { read: 0, rewrote: 0, translated: 0, runs: 0 };
  // 昨夜 is the last 18 hours: a pass days old is not last night, so a quiet night gives the row back.
  for (const segment of hypnoScale(asOf).segments.filter(segment => segment.end >= asOf - 18 * HOUR)) {
    const counts = stretchCounts(segment);
    for (const key of ["read", "rewrote", "translated"]) totals[key] += counts[key];
    totals.runs += segment.list.length;
  }
  return totals;
}
function nightWords(asOf = new Date(REM.as_of).getTime() || Date.now()) {
  const { read, rewrote, translated, runs } = nightTotals(asOf);
  if (!runs) return null;
  const parts = [read ? t(read === 1 ? "read {n} item" : "read {n} items", { n: num(read) }) : null,
    rewrote ? t(rewrote === 1 ? "rewrote {n} page" : "rewrote {n} pages", { n: rewrote }) : null,
    translated ? t(translated === 1 ? "translated {n} page" : "translated {n} pages", { n: translated }) : null].filter(Boolean);
  return parts.length ? parts.join(" · ") : t("nothing new to do");
}
// Today opens with the night (#3311, owner 2026-11-22: the sleep curve stays on top, it is REM's signature): the
// curve, the work under it on the same clock, what REM handled, and what it could not read, then who waits.
// Who is waiting is the desk's title, over its first card (art director on #3371): the night block speaks only of
// the night, on a phone too, where 昨夜's line says 昨夜 and nothing else.
function waitingLine(groups, current, ticked) {
  return el("div", { class: "nb solo" }, [el("div", { class: "faces" }, [countLine(ticked, groups.length), groups.length ? faceStrip(groups, current) : null])]);
}
// A phone says it in one plain line with no faces (art director, #3371): the card's own ‹ 1/4 › already counts and
// deals, and the four circles would cost 发送 its place on the first screen (D-10).
function deskHead(groups, current, ticked) {
  if (typeof window !== "undefined" && window.innerWidth <= 640) return el("div", { class: "desk-head plain" }, [countLine(ticked, groups.length)]);
  return el("div", { class: "desk-head" }, [waitingLine(groups, current, ticked)]);
}
function nightLogPopover(asOf, gap, stall) {
  const stretches = nightStretches(asOf);
  const foot = gap ? el("div", { class: "night-foot" }, [el("div", { class: "night-unread" }, [el("span", { class: "night-unread-k", text: t("Still unread") }), gap])]) : null;
  if (!stretches && !foot && !stall) return null;
  const pop = el("details", { class: "nh-log" }, [
    el("summary", {}, [el("span", { class: "nh-log-dot", "aria-hidden": "true" }), t("Night log"), " ▾"]),
    el("div", { class: "nh-log-pop" }, [stretches, stall, foot].filter(Boolean))
  ]);
  pop.addEventListener("keydown", event => { if (event.key === "Escape" && pop.open) { pop.open = false; pop.querySelector("summary").focus(); } });
  if (!nightLogPopover.listening && typeof document !== "undefined" && document.addEventListener) {
    nightLogPopover.listening = true;
    document.addEventListener("click", event => {
      for (const open of document.querySelectorAll(".nh-log[open]")) if (!open.contains(event.target)) open.open = false;
    });
  }
  return pop;
}
function nightCard(groups, current, ticked) {
  const words = nightWords(), asOf = new Date(REM.as_of).getTime() || Date.now();
  const gap = coverageLine(), handled = nightLine(), phone = typeof window !== "undefined" && window.innerWidth <= 640;
  const stall = nightStall(), logPop = nightLogPopover(asOf, gap, stall);
  const timeline = nightTimeline(asOf);
  return el("section", { class: "night-card card sparse" + (phone ? " phone" : ""), "aria-label": t("Last night") }, [
    phone ? el("div", { class: "nh" }, [icon("moon"), el("span", { class: "nt", text: t("Last night") })])
      : (words || handled || logPop) ? el("div", { class: "nh" }, [icon("moon"), el("span", { class: "nt", text: t("Last night") }), words ? el("span", { class: "night-sum", text: words }) : null,
        el("div", { class: "nh-end" }, [handled ? el("span", { class: "nh-handled" }, [handled]) : null, logPop].filter(Boolean))]) : null,
    timeline,
    phone ? logPop : null,
    // System health is the night's own business (#3156): one quiet line in its card, never above the work.
    scheduleFailure()].filter(Boolean));
}
// Why the nights read nothing (sprint 14): a mailbox failed while REM prepared a page. One plain sentence, never
// an exception name; the pages set aside fold under it with when each is tried again (fetch_stalls.last_night).
const STALL_WHY = { timeout: "timed out", not_found: "mail deleted or moved", server: "server error", network: "network down",
  auth: "authorization expired", denied: "permission denied", throttled: "throttled", refused: "request refused", unavailable: "unavailable" };
function stallSentence(s) {
  // A page whose mail the mailbox denied twice is not retried (#3392): it is never counted as "will try again".
  const waits = s.pages - (s.gone || 0);
  const values = { provider: s.provider, why: t(STALL_WHY[s.reason] || "unavailable"), times: s.times, n: waits };
  if (!waits) return t(s.gone === 1 ? "1 page cites mail no longer in {provider}; REM stopped waiting for it"
    : "{n} pages cite mail no longer in {provider}; REM stopped waiting for them", { provider: s.provider, n: s.gone });
  if (s.stopped) return t("Last night {provider} failed ({why}); REM stopped asking it for that turn and did the rest", values);
  if (s.times >= 3 && s.pages === 1) return t("Last night REM got stuck on {provider}: {why} {times} times; it set that page aside and did the rest", values);
  if (!s.times) return t(waits === 1 ? "1 page waits for {provider}; REM will try again" : "{n} pages wait for {provider}; REM will try again", values);
  return t(waits === 1 ? "Last night 1 page was set aside because {provider} {why}; REM will try again"
    : "Last night {n} pages were set aside because {provider} {why}; REM will try again", values);
}
function nightStall() {
  const s = REM.night_stall;
  if (!s) return null;
  const now = Date.parse(REM.as_of || new Date().toISOString());
  const when = at => new Date(at).toLocaleString(uiLocale(), { weekday: "short", hour: "2-digit", minute: "2-digit" });
  // A page the reader does not list (private, or gone) is not named: never a raw path.
  const rows = (s.parked || []).filter(row => byPath(row.record)).map(row => {
    const r = byPath(row.record), at = Date.parse(row.retry_at);
    return el("li", {}, [el("a", { href: href(r), text: r.title }),
      el("span", { class: "meta", text: row.gone ? t("Original mail is no longer in {provider} · not waiting", { provider: row.name || s.provider })
        : at > now ? t("tries again from {when}", { when: when(at) }) : t("tries again next round") })]);
  });
  return el("details", { class: "night-stall" }, [el("summary", { text: stallSentence(s) }), rows.length ? el("ul", {}, rows) : null]);
}
// The night chart: a hypnogram of REM's real work, read from the run logs (reading mail sits at the first
// depth, rewriting and translating pages at the deepest) and from when each reply or task was prepared (the
// rises, with the person's face). Only what the snapshot records is drawn: a stretch without a log is a flat
// line, never an invented stage. Three nights at most; a phone shows the last thirty hours.
const NIGHT_X = 8, LEVEL = { idle: 20, rise: 44, read: 66, deep: 92 };
const RUN_KIND = { sync: ["read", "Read mail and sessions"], "daily-update": ["deep", "Rewrote pages"], "daily-translation": ["deep", "Translated pages"] };
function nightRises() {
  const seen = new Set(), rises = [];
  for (const o of REM.night_outcomes || []) {
    const r = byPath(o.record);
    if (!["prepared", "task"].includes(o.kind) || !o.prepared_at || !r || r.private || r.path === REM.owner || seen.has(o.key)) continue;
    seen.add(o.key);
    rises.push({ at: Date.parse(o.prepared_at), r, kind: o.kind });
  }
  return rises;
}
function nightRuns() {
  return (REM.logs || REM.brief_logs || []).filter(run => run.started_at).map(run => {
    const from = Date.parse(run.started_at), [level, what] = RUN_KIND[run.phase] || ["read", run.phase || "sync"];
    return { from, to: Math.max(from + 4 * 60000, Date.parse(run.finished_at || "") || 0), level, what, items: run.items || 0 };
  });
}
// From the earliest night that has a record (at most three, thirty hours on a phone) to now. Times later than
// the snapshot's as_of (a clock ahead of it) still leave an hour to draw, never an empty or reversed axis.
function nightWindow(times, narrow) {
  const end = Date.parse(REM.as_of || new Date().toISOString());
  const early = new Date(Math.min(...times)); early.setHours(0, 0, 0, 0);
  const start = Math.max(end - (narrow ? 30 * 3600000 : 3 * DAY_MS), early.getTime());
  return { start: Math.min(start, end - 3600000), end };
}
// A phone draws a narrower chart, so its labels keep their size.
function nightChart(current, narrow = window.innerWidth <= 640) {
  const width = narrow ? 360 : 760;
  const runs = nightRuns(), rises = nightRises();
  const times = [...runs.map(run => run.from), ...rises.map(rise => rise.at)];
  if (!times.length) return null;
  const sparse = nightSparse(runs, nightWindow(times, false));
  if (sparse) return { sparse };
  const { start, end } = nightWindow(times, narrow), x = at => NIGHT_X + (Math.min(end, Math.max(start, at)) - start) / (end - start) * width;
  const shown = runs.filter(run => run.to >= start && run.from <= end).sort((a, b) => a.from - b.from);
  const marks = rises.filter(rise => rise.at >= start && rise.at <= end).sort((a, b) => a.at - b.at);
  const when = at => new Date(at).toLocaleString(uiLocale(), { weekday: "short", hour: "2-digit", minute: "2-digit" });
  const runTitles = shown.map(run => '<rect class="hit" x="' + x(run.from).toFixed(1) + '" y="12" width="' + Math.max(3, x(run.to) - x(run.from)).toFixed(1) + '" height="88"><title>'
    + esc(when(run.from) + " · " + t(run.what) + (run.items ? " · " + t("{n} read", { n: run.items }) : "")) + "</title></rect>");
  const path = nightPath([...shown.map(run => ({ a: x(run.from), b: x(run.to), y: LEVEL[run.level] })), ...marks.map(rise => ({ a: x(rise.at) - 3, b: x(rise.at) + 3, y: LEVEL.rise }))], width);
  const svg = el("div", { class: "hyp-wrap" });
  svg.innerHTML = '<svg class="hyp" viewBox="0 0 ' + (NIGHT_X * 2 + width) + ' 128" role="img" aria-label="' + esc(nightSummary(shown, marks)) + '">'
    + '<g class="lv">' + [LEVEL.rise, LEVEL.read, LEVEL.deep].map(y => '<line x1="0" x2="' + (NIGHT_X * 2 + width) + '" y1="' + y + '" y2="' + y + '"/>').join("") + "</g>"
    + '<path class="line" d="' + path + '"/>' + runTitles.join("")
    + marks.map(rise => '<line class="rise" x1="' + (x(rise.at) - 3).toFixed(1) + '" x2="' + (x(rise.at) + 3).toFixed(1) + '" y1="44" y2="44"><title>'
      + esc(when(rise.at) + " · " + t(rise.kind === "task" ? "Prepared a task for {name}" : "Drafted a reply to {name}", { name: threadWho(rise.r) })) + "</title></line>").join("")
    + nightFaces(marks, x, current, width) + nightDays(start, end, x) + '<circle class="now" cx="' + x(end).toFixed(1) + '" cy="' + LEVEL.idle + '" r="4"/></svg>';
  return { svg, legend: t("Rises: replies and tasks REM prepared · dips: reading mail, rewriting and translating pages") };
}
// The chart earns the top row only when the three nights hold at least two runs of reading or rewriting: with
// fewer it is a flat line with a dot or two and says no more than
// a sentence. Then it is that sentence, and the people waiting take the row. Decided on the desktop's three
// nights at every width, so a phone's shorter window never folds a chart the desk would draw.
const NIGHT_MIN_RUNS = 2;
function nightSparse(runs, { start, end }) {
  const shown = runs.filter(run => run.to >= start && run.from <= end).length;
  if (shown >= NIGHT_MIN_RUNS) return null;
  // Its count of what REM handled is the side line's (nightTally), so the two never read as a contradiction.
  const n = nightTally().n, values = { d: Math.max(1, Math.round((end - start) / DAY_MS)), n };
  return t(shown ? (n ? "Last {d} days: 1 run of reading or rewriting; REM handled {n} things in Today" : "Last {d} days: 1 run of reading or rewriting")
    : n ? "Last {d} days: no mail read and no page rewritten; REM handled {n} things in Today" : "Last {d} days: no mail read and no page rewritten", values);
}
// One stepped line: runs closer than a few pixels are one stretch at the deepest of their depths.
function nightPath(spans, width) {
  const merged = [];
  for (const span of spans.sort((p, q) => p.a - q.a)) {
    const last = merged.at(-1);
    if (last && span.a - last.b < 6) { last.b = Math.max(last.b, span.b); last.y = Math.max(last.y, span.y); }
    else merged.push({ ...span, b: Math.max(span.b, span.a + 3) });
  }
  return "M0 " + LEVEL.idle + merged.map(span => " H" + span.a.toFixed(1) + " V" + span.y + " H" + span.b.toFixed(1) + " V" + LEVEL.idle).join("") + " H" + (NIGHT_X * 2 + width);
}
// Faces on the rises, never overlapping: rises closer than a face are one face and a "+N".
function nightFaces(marks, x, current, width) {
  const clusters = [];
  for (const rise of marks) {
    const last = clusters.at(-1);
    if (last && x(rise.at) - last.x < 30) { if (!last.people.includes(rise.r)) last.people.push(rise.r); }
    else clusters.push({ x: Math.min(width - 6, Math.max(14, x(rise.at))), people: [rise.r] });
  }
  return clusters.map(({ x: cx, people }) => {
    const lead = people.find(r => r.path === current) || people[0];
    const initials = face(threadWho(lead)).textContent;
    return '<line class="stem" x1="' + cx.toFixed(1) + '" x2="' + cx.toFixed(1) + '" y1="33" y2="41"/><g class="fc' + (lead.path === current ? " sel" : "") + '" transform="translate(' + cx.toFixed(1) + ' 20)">'
      + '<circle r="12.5"/><text>' + esc(initials) + "</text>" + (people.length > 1 ? '<text class="plus" x="15" y="-10">+' + (people.length - 1) + "</text>" : "")
      + "<title>" + esc(people.map(threadWho).join(uiLanguage === "zh" ? "、" : ", ")) + "</title></g>";
  }).join("");
}
function nightDays(start, end, x) {
  const labels = [], day = new Date(start);
  day.setHours(0, 0, 0, 0);
  for (let at = day.getTime(); at < end; at += DAY_MS) {
    const a = Math.max(start, at), b = Math.min(end, at + DAY_MS);
    if (b - a < 4 * 3600000) continue;
    labels.push('<text x="' + ((x(a) + x(b)) / 2).toFixed(1) + '" y="122">' + esc(new Date(at + 12 * 3600000).toLocaleDateString(uiLocale(), { weekday: "short" })) + "</text>");
  }
  return '<g class="days">' + labels.join("") + "</g>";
}
function nightSummary(runs, marks) {
  return t("REM's work: {runs} runs, {n} replies and tasks prepared", { runs: runs.length, n: marks.length });
}
// The side column: what others owe and what can be approved at once, what REM did overnight. 「关于 X，有什么值得
// 记住？」 left Today in sprint 14: it picked a page REM already knew well, gave no reason and took no answer.
function todaySide(counts) {
  // A phone has no room in the night card for what REM settled (D-10: Send stays in the first screen), so there it
  // stays here, under the cards, as before sprint T3.
  const phone = typeof window !== "undefined" && window.innerWidth <= 640;
  const sideTop = !phone && counts.mine ? el("div", { class: "desk-bar-end" }, [
    el("a", { class: "desk-see-all", href: "#view=open", text: t("All waiting ({n}) →", { n: counts.mine }) })
  ]) : null;
  return el("aside", { class: "side", "aria-label": t("Around today") }, [sideTop, todayNext(), othersWidget(counts), phone ? nightLine() : null].filter(Boolean));
}
// What last night could not read, and one button that fixes it (#3353). Plain words, not internals (art director):
// "微信还有 10 个聊天库读不了（已读 2/12）". A key capture needs the owner to log into a WeChat copy, so the
// button opens his Terminal running it; a Host in launchd's Background session (#3317) can't open windows, so
// then it copies the command and says so. The phone-migration case opens the steps instead.
function coverageLine() {
  const gaps = REM.coverage_gaps || [], gap = gaps[0];
  if (!gap) return null;
  const more = gaps.length - 1, unread = Math.max((gap.found || 0) - (gap.read || 0), 0);
  const said = gap.fix_kind === "key_capture"
    ? t("WeChat has {n}\u00a0chat databases it can't read yet ({read} of {found} read)", { n: unread, read: gap.read, found: gap.found })
    : t("Many WeChat chats are still only on your phone");
  const note = el("span", { class: "meta coverage-note", text: gap.fix_kind === "key_capture"
    ? t("About 2 minutes; you log in once in the WeChat window that opens") : "" });
  let action;
  if (gap.fix_kind === "key_capture") {
    action = el("button", { type: "button", class: "link-btn coverage-fix", text: t("Complete WeChat →") });
    const copy = command => {
      navigator.clipboard?.writeText(command);
      note.textContent = t("Copied. Paste it into Terminal and run it: {command}", { command });
    };
    action.onclick = async () => {
      if (!liveHere()) return copy(gap.fix);
      action.disabled = true;
      const reply = await hostPost("/rem/source-fix", { fix: "key_capture" });
      action.disabled = false;
      if (reply.ok && reply.opened) note.textContent = t("Opened in Terminal: log in once in the WeChat window it opens");
      else copy(reply.command || gap.fix);
    };
  } else {
    action = el("details", { class: "coverage-steps" }, [el("summary", { class: "link-btn coverage-fix", text: t("Move chat history from your phone →") }),
      el("ol", {}, [t("On your phone: WeChat → Me → Settings → Chats → Chat history migration & backup"),
        t("Choose Migrate → to this computer, and pick the chats (or all)"), t("Keep both on the same Wi-Fi until it finishes"),
        t("REM reads the new history at the next night run")].map(step => el("li", { text: step })))]);
  }
  return el("div", { class: "closed coverage-gap", role: "status" }, [icon("ellipsis"),
    el("span", { class: "coverage-said" }, [said + (more > 0 ? " " + t("(+{n} more)", { n: more }) : "")]), action, note]);
}
// What is next, on the first screen beside the cards (rc34 hunt: the calendar sat ~989px down). The cards stay
// first; this is the calendar's head, not a second calendar: it reuses agendaEntries and agDetail.
// What starts next, in order from now. An event already under way is not "next": it went first in the list under its
// past start ("周日 09:00" ahead of 10:00 today, rc36 hunt) and is said apart, by nowEvents.
function nextEvents(limit = 3) {
  if (REM.shared) return [];
  const now = Date.parse(REM.as_of || "") || clockNow();
  return timedEvents(now).filter(e => Date.parse(e.start) > now).slice(0, limit);
}
function nowEvents() {
  if (REM.shared) return [];
  const now = Date.parse(REM.as_of || "") || clockNow();
  return timedEvents(now).filter(e => Date.parse(e.start) <= now);
}
function timedEvents(now) {
  return agendaEntries().filter(e => e.kind === "event" && !e.allDay && e.end && Date.parse(e.end) > now)
    .sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
}
function nextWhen(e) { return (e.first === agToday() ? "" : agFormat(e.first, { weekday: "short" }) + " ") + agTime(e.start); }
// Until when, in the fewest words: a time today, a weekday this week, a date further off.
function nowWhen(e) {
  const today = agToday(), until = e.last === today ? agTime(e.end)
    : agSpan(today, e.last) < 7 ? agFormat(e.last, { weekday: "short" }) : agFormat(e.last, { month: "short", day: "numeric" });
  return agT("Now · until {when}", { when: until });
}
function nextRow(e, when) {
  const open = el("button", { type: "button", class: "tnext-ev" }, [el("span", { class: "tnext-time", text: when }), el("span", { class: "tnext-title", text: e.title })]);
  open.onclick = () => agDetail(e, open);
  const join = e.meet ? el("a", { class: "tnext-join", href: e.meet.url, target: "_blank", rel: "noopener", text: agT("Join {service}", { service: e.meet.service }) }) : null;
  return el("li", {}, [open, join]);
}
function todayNext() {
  const events = nextEvents();
  if (REM.shared) return null;
  const today = agToday(), entries = agendaEntries(), under = nowEvents();
  const rows = events.map(e => nextRow(e, nextWhen(e)));
  const strip = el("div", { class: "tnext-strip", role: "group", "aria-label": agT("This week") }, Array.from({ length: 7 }, (_, i) => {
    const day = agDay(today, i), n = agOnDay(entries, day).length;
    const b = el("button", { type: "button", class: "tnext-day" + (day === today ? " today" : ""), ...(day === today ? { "aria-current": "date" } : {}),
      "aria-label": (day === today ? agT("Today") + agT(", ") : "") + agDate(day) + agT(", ") + (n ? agCount(n) : agT("nothing")) }, [
      el("span", { class: "tnext-wd", text: agFormat(day, { weekday: "narrow" }) }), el("span", { class: "tnext-num", text: String(Number(day.slice(8))) }),
      el("span", { class: "tnext-dots", "aria-hidden": "true", text: "•".repeat(Math.min(3, n)) })]);
    b.onclick = () => { todayCal.day = day; location.hash = "#view=agenda"; };
    return b;
  }));
  const all = el("a", { class: "tnext-all", href: "#view=agenda", text: agT("Full schedule ↓") });
  return el("section", { class: "widget tnext", "aria-label": agT("Next") }, [el("div", { class: "wt" }, [icon("calendar"), el("span", { text: agT("Next") }), el("span", { class: "end" }, [all])]),
    under.length ? el("ul", { class: "tnext-list tnext-now" }, under.map(e => nextRow(e, nowWhen(e)))) : null,
    rows.length ? el("ul", { class: "tnext-list" }, rows) : el("p", { class: "tnext-none", text: agT("Nothing else today") }), strip]);
}
// On a phone: one line above the cards, the next event, a tap to the calendar.
function todayNextLine() {
  const [e] = nextEvents(1);
  if (!e) return null;
  const line = el("button", { type: "button", class: "tnext-line" }, [el("span", { class: "tnext-label", text: agT("Next") }),
    el("span", { class: "tnext-time", text: nextWhen(e) }), el("span", { class: "tnext-title", text: e.title }), e.meet ? el("span", { class: "tnext-join", text: agT("Join {service}", { service: e.meet.service }) }) : null]);
  line.onclick = () => document.getElementById("today-calendar")?.scrollIntoView({ block: "start", behavior: "smooth" });
  return line;
}
// Promises long past their date with no word since (staleEntry): triage of the past, so not in the rail above the
// fold but one folded line under the desk, opening in place, never in red (sprint 14 #6). Mark done closes one the
// way the card's Mark done does; Still open puts it back among the people waiting; Mark all done closes every one
// of them at once, with the page's one Undo. Each row also says Not now and Ignore, the strip of every Today row
// (#2990: the owner looked for 忽略 here and found only 标为完成 / 还开着); Still open stays beside the name.
function staleWidget(entries) {
  if (!entries.length) return null;
  // The count is in the words: the fold shows three, and this closes every one of them.
  const all = el("button", { type: "button", class: "btn-quiet stale-all", text: t("Mark all {n} done", { n: entries.length }), ...snapshotWhy("This is an offline snapshot; open REM to mark it.") });
  all.onclick = () => closeAllStale(entries);
  const rows = () => entries.slice(0, 3).map(entry => {
    const who = entry.r.path === REM.owner ? ownerCounterpart(entry) || entry.r : entry.r;
    const keep = el("button", { type: "button", class: "btn-quiet", text: t("Still open"), ...snapshotWhy("This is an offline snapshot; open REM to mark it.") });
    keep.onclick = () => keepStale(entry);
    const { words } = morningWords(entry.t.text, entry.r, entry.t);
    return el("li", { "data-path": who.path }, [el("a", { href: href(who), text: threadWho(who) }), el("span", { class: "stale-acts" }, [keep]),
      wordsLine("stale-what", words, entry.r, [], { title: words }),
      el("p", { class: "stale-when", text: t("Due {date}; no new message for {n} days", { date: threadDate(entry.t.due), n: daysSince(entry.t.since) }) }),
      handOff(entry, null, null)]);
  });
  const n = entries.length;
  const fold = el("details", { id: "today-stale", class: "stale fold" }, [
    el("summary", { text: t(n === 1 ? "1 has gone quiet for a long time · Look" : "{n} have gone quiet for a long time · Look", { n }) }),
    el("div", { class: "stale-foot" }, [all, n > 3 ? staleMore(n - 3) : null])]);
  return lazyFold(fold, node => node.querySelector(":scope > summary").after(snapshotCloseLine() || "", el("ul", {}, rows())));
}
// Each promise is its own mark: one setDone over all of them would link unrelated rows as one thread in the
// notebook, so a later Undo of any one would reopen every one. The page is drawn once and says it once: one notice,
// one Undo that reopens only the marks the notebook kept, and for any it refused one Try again for just those.
function closeAllStale(entries) { return closeAll(entries); }
// state and until as setDone takes them: a filtered list is marked done, or put off to one moment, in one go.
async function closeAll(entries, state = "done", until = null) {
  if (!liveHere()) return;  // a snapshot keeps no mark (markThread)
  const marks = entries.map(entry => ({ entry, ...markThread(entry, true, state, [entry], until) }));
  redrawKeepingScroll();
  document.getElementById("done-notice")?.remove();
  const undo = el("button", { type: "button", text: t("Undo") }), status = el("span", { text: t("Saving…") });
  const words = state === "skipped" ? t("{n} put off · {back}", { n: marks.length, back: backWords(until) }) : marks.length > 1 ? t("{n} marked done", { n: marks.length }) : t("Marked done");
  const notice = el("div", { id: "done-notice", class: "done-notice", role: "status" }, [words, " · ", undo, " · ", status]);
  let undone = false;
  const reopen = list => () => { undone = true; list.forEach(mark => markThread(mark.entry, false)); redrawKeepingScroll(); notice.remove(); focusRaisedCard(); };
  undo.onclick = reopen(marks);
  document.body.appendChild(notice);
  undo.focus({ preventScroll: true });
  noticeLeaves(notice);
  const results = await Promise.all(marks.map(mark => mark.saved));
  const failed = marks.filter((mark, i) => results[i] === "refused");
  failed.forEach(mark => mark.restore());
  undo.onclick = reopen(marks.filter(mark => !failed.includes(mark)));
  // true is the notebook's; false waits on this device; "refused" is not saved, so it never reads as saved.
  status.textContent = t(results.every(result => result === true) ? "Saved in notebook" : failed.length ? "Not saved" : "Saved on this device — sync pending");
  // The refusal is added to this notice (own: null), so the Undo for the marks that were saved stays; once Undo ran
  // there is nothing to try again.
  if (failed.length && !undone) notSavedNotice(() => closeAll(failed.map(mark => mark.entry), state, until), null);
  redrawKeepingScroll();
}
function redrawKeepingScroll() {
  const scroll = window.scrollY;
  render();
  window.scrollTo(0, scroll);
}
// The rest are in Waiting's folded Gone quiet section: the link says so, opens it and brings it into view.
function staleMore(n) {
  const link = el("a", { class: "stale-more", href: "#view=open", text: t("{n} more in Gone quiet →", { n }) });
  link.onclick = () => addEventListener("hashchange", () => requestAnimationFrame(() => {
    const quiet = document.getElementById("gone-quiet");
    if (!quiet) return;
    quiet.open = true;
    quiet.fill?.();
    quiet.scrollIntoView({ block: "start" });
  }), { once: true });
  return link;
}
// What others owe and what can be approved at once. The three numbers on Today read as one set (rc36 hunt: «14 件在等你 /
// 55 件在等谁 / 批准 11 件» said nothing of how they relate): the big one is what waits on you, this link is the other
// direction (what you wait on others for), and the batch is what REM prepared, which it names as REM's. With nothing open either way and nothing to approve, one
// sentence says so, in a snapshot and live alike; with only your own items open, the link is to everything open.
// Either shape carries the same id: an Undo that brings approvals back draws it again in place.
function othersWidget(counts) {
  const outcomes = (REM.approval_outcomes || []).length, problems = approvalProblems();
  if (!counts.theirs && !counts.mine && !outcomes && !problems)
    return el("p", { id: "today-others", class: "quiet-line nothing-open", text: t("Nothing is open between you and anyone right now.") });
  // What others owe is a list to read, so it is a worded link to that list, not a big number to stare at.
  const cell = counts.theirs ? el("a", { class: "pair-cell waiting-more", href: "#view=open", text: t("See the {n} you are waiting on others for →", { n: counts.theirs }) })
    : counts.mine ? el("a", { class: "pair-cell waiting-more", href: "#view=open" }, [el("span", { text: t("Everything open") + " →" })]) : null;
  // A batch that can go names itself; a heading of "Waiting on others" over it read as if the batch were theirs.
  const ready = outcomes && (REM.approval_outcomes || []).some(item => !item.blocked);
  const title = ready ? null : counts.theirs ? "Waiting on others" : counts.mine ? "Open threads" : "Approval status";
  return el("section", { id: "today-others", class: "widget others" }, [title ? el("div", { class: "wt" }, [icon("clock"), el("span", { text: t(title) })]) : null,
    el("div", { class: "pair" }, [cell, outcomes || REM.live ? approvalHeader() : problems])]);
}
// What REM did overnight, as one quiet line; 看 opens the list with every name.
function nightLine() {
  const tally = nightTally(), done = nightDone(tally), n = tally.n;
  if (!done) return null;
  const look = el("button", { type: "button", class: "link-btn", text: t("See") });
  look.onclick = () => openNightSheet(done);
  return el("div", { class: "closed" }, [n ? icon("check") : null, el("span", { text: n ? t(n === 1 ? "REM handled 1 thing overnight" : "REM handled {n} things overnight", { n }) : t("What REM did overnight") }), look]);
}
function openNightSheet(done) {
  const close = el("button", { type: "button", class: "ibtn", "aria-label": t("Close") }, [icon("x")]);
  const dialog = el("dialog", { id: "night-sheet", class: "n3-sheet", "aria-labelledby": "night-title" }, [
    el("div", { class: "sheet-head" }, [el("h2", { id: "night-title", text: t("What REM did overnight") }), close]), done]);
  close.onclick = () => dialog.close();
  dialog.addEventListener("click", event => {
    if (event.target === dialog || event.target.closest?.('a[href^="#"]')) dialog.close();
  });
  dialog.addEventListener("close", () => dialog.remove());
  document.body.appendChild(dialog);
  dialog.showModal();
}
// Below the desk, folded: what changed overnight, a connection to judge, quiet threads, this week's pages,
// how the last pass ran and maintenance. All of it was on the old front page; none of it is gone.
function todayFolds(entries, counts) {
  const week = weekChanges();
  const weekPages = week.length ? el("details", { id: "week-pages", class: "week-details fold" }, [el("summary", { text: t(firstBuild() ? "Pages written in the first build ({n})" : "Pages rewritten this week ({n})", { n: week.length }) }),
    el("ol", { class: "week" }, week.slice(0, 8).map(({ r, day }) => el("li", {}, [
      el("span", { class: "d mono", text: shortDate(day) }), moon(known(r).status),
      el("span", { class: "w" }, [el("a", { href: href(r), text: r.title }), updatedMarker(r), el("span", { class: "meta", text: singular(r.category) }),
        known(r).summary ? el("span", { class: "s", text: summaryLine(known(r).summary) }) : null])])))]) : null;
  const recent = listedRecords().filter(r => ["people", "orgs", "projects"].includes(r.category) && known(r).status !== "Mapped" && !/\(automated candidate\)$/.test(r.title))
    .sort(byActivity).slice(0, 6);
  const recentFold = recent.length && !week.length ? el("details", { class: "week-details recent-details fold" }, [
    el("summary", { text: t("Recently active") }), el("ul", { class: "hits cols" }, recent.map(r => row(r, { kind: true })))]) : null;
  const processing = el("details", { id: "processing", class: "night-details fold" }, [el("summary", { text: t("How co rem processed the last pass") }), passSummary()]);
  return el("div", { class: "desk-more" }, [morningBrief(), connectionReview(), quietThreads(entries, true), weekPages, recentFold, processing,
    maintenance(REM.status || {})].filter(Boolean));
}

function maintenance(s) {
  const maint = el("details", { class: "maint" });
  const state = t(scheduleState(s).startsWith("Background updates off") ? "Nightly updates are off." : scheduleState(s));
  maint.appendChild(el("summary", {}, [el("span", {}, [el("h2", { text: t("Maintenance") })]), el("span", { class: "n", text: state ? plainLine(state) : "" })]));
  maint.appendChild(el("p", { class: "state", html: inline(state, "") }));
  const usage = s.usage_today || {};
  const cells = el("div", { class: "row" });
  const cell = (k, v) => cells.appendChild(el("div", {}, [el("div", { class: "k", text: t(k) }), el("div", { class: "v", text: v })]));
  cell("Batches today", String(s.batches_today ?? "—"));
  cell("Model turns today", String(s.runner_attempts_today ?? "—"));
  cell("Input tokens today", num(usage.input_tokens));
  cell("Output tokens today", num(usage.output_tokens));
  cell("Timezone", s.timezone || "—");
  maint.appendChild(cells);
  const subs = Object.entries(REM.subscriptions || {});
  if (subs.length) {
    const line = el("p", { class: "state" }, [t("Sources: ")]);
    subs.forEach(([name, sub]) => {
      const state = !sub.enabled ? "off" : sub.adapter === "available" ? (sub.consented ? "reading" : "waiting for start") : (sub.adapter || "");
      line.append(el("span", { class: "pill" + (state === "reading" ? "" : " quiet"), text: name + " · " + t(state) }), " ");
    });
    maint.appendChild(line);
  }
  const latest = (REM.logs || [])[0];
  if (latest) maint.appendChild(el("p", { class: "state" }, [t("Latest run ") + fmtTime(latest.started_at) + " · " + t(latest.outcome || "") + " · "
    + t("{n} pages changed · ", { n: (latest.changed || []).length }), el("a", { href: "#view=activity", text: t("Activity →") })]));
  return maint;
}

