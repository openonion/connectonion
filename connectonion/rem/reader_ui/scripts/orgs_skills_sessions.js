// ---------- organisations: the list (#c=orgs) and one organisation's page ----------
// An organisation answers, in this order: what it is to you, what you owe it,
// who you know there by where they sit, and what happened lately. Organisations
// are neutral rounded squares; people stay coloured circles. Most pages were
// written before Kind, To you and Team existed, so every unknown has a quiet
// finished form instead of an empty slot (art direction, 2026-11-08).
const ORG_UI_ZH = {
  "faculty": "学部", "school": "学院", "department": "部门", "course": "课程", "team": "团队", "programme": "项目组", "venue": "场所", "lab": "实验室", "Units": "所属单位",
  "University": "大学", "Investor": "投资方", "Client or partner": "客户与合作", "Supplier": "供应商",
  "Community and events": "社区与活动", "Your company": "你的公司", "Personal": "个人",
  "Your side": "你这边对接的人",
  "Not sure what this is yet": "还不清楚是什么机构",
  "{n} organisations": "{n} 个组织",
  "{org} has {n} waiting on you; most urgent: {who}, {thing}": "{org} 有 {n} 件在等你，最急的是 {who}：{thing}",
  "{org} is waiting on one thing: {who}, {thing}": "{org} 有 1 件在等你：{who}，{thing}",
  "{n} people you know": "{n} 位你认识的人", "1 person you know": "1 位你认识的人",
  "Filter organisations, people, domains": "筛选组织、人名、域名",
  "All": "全部", "Waiting on you": "在等你", "Recently in touch": "最近有往来", "Quiet": "安静",
  "overdue first": "逾期的在前", "within 45 days": "45 天内", "no contact for over 45 days": "45 天以上没有往来",
  "{n} more →": "其余 {n} 个 →", "{n} more": "还有 {n} 件", "Overdue": "逾期", "{n} items": "{n} 件",
  "Overdue {n} days": "逾期 {n} 天", "Personal · shown only on this Mac": "个人事项 · 只在这台 Mac 上显示",
  "Show": "显示", "No organisation matches": "没有符合的组织",
  "Reply to {name} · {thing}": "回复 {name} · {thing}", "Follow up with {name} · {thing}": "跟进 {name} · {thing}",
  "people you know": "位你认识的人", "teams or departments": "个团队/部门", "things you owe": "件你欠的",
  "{n} overdue": "{n} 件逾期", "last contact": "最近往来",
  "You owe {org}": "你欠 {org} 的", "Colleagues waiting on you": "同事在等你的",
  "{n} more items": "其余 {n} 件", "{n} more with them": "这里还有 {n} 件",
  "Waiting on them, {n}: ": "在等对方 {n} 件：",
  "You owe {org} nothing": "你不欠 {org} 什么", "{n} waiting on them": "{n} 件在等对方",
  "People you know here": "你在这里认识的人", "by where they sit": "按所在部门",
  "{n} more people in {org}, department not known yet: ": "还有 {n} 人在 {org}，还不清楚在哪个部门：",
  "Department not known yet: ": "还不清楚在哪个部门：", "Department not known yet": "还不清楚在哪个部门",
  "Lately": "最近往来", "newest first": "最新在前", "Show all {n} entries": "显示全部 {n} 条",
  "About": "关于", "What": "是什么", "Website": "网站", "Where": "所在",
  "Related projects": "相关项目", "REM is not sure yet": "REM 还不确定",
  "What kind of organisation this is": "它是哪一类机构", "What it is to you": "它对你来说是什么",
  "Which department {n} people sit in": "{n} 个人在哪个部门",
  "{n} sources": "{n} 个来源",
  "REM only knows its domain and {n} people": "REM 只知道它的域名和 {n} 位联系人",
  "Not investigated yet": "还没调查", "writes from it": "从这里来信",
  "You": "你",
  "Close": "关闭", "In touch": "常来往", "Cooling": "在变冷", "Gone cold": "冷了", "Warmth not known yet": "冷热还不知道", "Open {name}": "打开 {name}",
  "Today": "今天", "Who to ask at {org}": "在 {org} 找谁", "who does what · who replies fast": "谁管什么 · 谁回得快",
  "usually replies in {d}": "通常 {d} 内回", "{n} more people": "还有 {n} 人", "less mail than before · 52 weeks": "邮件比以前少 · 52 周",
  "{n} days without mail": "{n} 天没有邮件", "{n}% less mail in the last 30 days": "最近 30 天少了 {n}%",
  "REM has {n} questions for you": "REM 还有 {n} 个问题想问你", "Where this sits": "所在位置", "{n} units": "{n} 个单位",
  "In touch since {date}": "{date}起有往来", "Last contact {date}": "最近往来 {date}", "Most recently in touch": "最近联系的人",
  "1 thing in Today involves {org} →": "今天里有 1 件和 {org} 有关的事 →", "{n} things in Today involve {org} →": "今天里有 {n} 件和 {org} 有关的事 →", "How {org} is built": "{org} 的结构",
  "Size = people you know there": "大小 = 你在那里认识的人数", "In touch within 45 days": "45 天内有往来", "When you were in touch": "你们什么时候有往来",
  "First contact": "第一次往来", "Latest contact": "最近一次往来", "{n} people here": "{n} 人", "Units and people": "分支与团队",
  "{n} units · {m} people": "{n} 个单位 · {m} 人", "Projects with {org}": "和 {org} 有关的项目"
};
function orgT(key, values = {}) {
  const words = uiLanguage === "zh" ? ORG_UI_ZH[key] : null;
  return words ? words.replace(/\{(\w+)\}/g, (match, name) => values[name] ?? match) : t(key, values);
}
const ORG_KINDS = { university: "University", investor: "Investor", client_partner: "Client or partner", supplier: "Supplier",
  community: "Community and events", own_company: "Your company", personal: "Personal" };
const ORG_RECENT_DAYS = 45;
const ORG_ICONS = {
  lock: '<rect x="4" y="11" width="16" height="10"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  chev: '<path d="m9 6 6 6-6 6"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'
};
const revealedOrgs = new Set();
let orgFilter = { query: "", tab: "all" };

function orgIcon(name) {
  const box = el("span", { "aria-hidden": "true", html: '<svg class="ov-i" viewBox="0 0 24 24">' + ORG_ICONS[name] + "</svg>" });
  return box.firstChild;
}
// "University of New South Wales (UNSW)" is UNSW in lists and headings.
function orgName(r) { return codedOrgName(r) || /\(([^()]{2,24})\)\s*$/.exec(r.title)?.[1] || r.title; }
function orgUnknown(r) { return /^[\w-]+(?:\.[\w-]+)+$/.test(r.title.trim()); }
function orgKind(r) { return r.unit_kind ? orgT(r.unit_kind) : r.kind ? orgT(ORG_KINDS[r.kind]) : orgUnknown(r) ? orgT("Not sure what this is yet") : ""; }
function firstSentence(text) { return (text || "").split(/(?<=[.。!?！？])\s+/)[0]; }
// Translation caches can retain "Unknown" beside a translated status. Normalize only
// for comparison; findings keep their wording, markup and privacy boundaries.
function orgSummary(text) {
  const value = (text || "").trim();
  const marker = value.normalize("NFKC").replace(/^\s*[-*]\s+/, "").replace(/[*`]/g, "")
    .replace(/\s*\[W?\d{1,3}\]/g, "").replace(/未知|not known/gi, "Unknown")
    .replace(/尚未\s*调查/g, "not investigated yet").replace(/尚未\s*(?:核实|验证)/g, "not verified")
    .replace(/(Unknown)\s*(?:[—–-]+|:)\s*/gi, "$1 — ").replace(/[。；！]/g, ".")
    .replace(/[.;!]+\s*$/, "").replace(/\s+/g, " ").trim();
  return !value || UNFILLED_LEAD.test(marker) || UNFILLED_LINE.test(marker)
    || /^unknown$/i.test(marker) ? "" : value;
}
// The first sentence of what the organisation is to you, labels kept: a labelled passage is held as one
// token so it never ends the sentence, and orgProse shows it behind its own reveal. The source is the
// first one with something public in it, so hiding labelled passages never empties the line.
function orgRelation(r) {
  const k = known(r), lead = k.intro || (k.kept.find(s => !MECHANICAL.has(s.title.toLowerCase())) || { text: "" }).text;
  const toYou = (parseFacts(r).get("To you") || r.facts?.["To you"] || []).map(item => orgSummary(item.value)).filter(Boolean).join("; ");
  const text = [toYou, r.to_you, facts(r).how, lead].map(orgSummary).find(value => plainLine(value)) || "", held = [];
  const masked = privatePassages(plainLine(text, true), passage => "\u0006" + (held.push(passage) - 1) + "\u0006");
  return orgSummary(firstSentence(masked).replace(/\u0006(\d+)\u0006/g, (_, i) => held[i]));
}
// Organisation prose with each labelled passage in its own .private span, as on a person's page.
// `quote` is off where the prose sits in a line that is mostly Chinese (the overview's opening): a line of the
// reader's words never carries 原文 (art director on #3416). Elsewhere only a whole English sentence is marked.
function orgProse(text, { quote = true } = {}) {
  if (!text) return null;
  const words = factWords(sectionWords(text)), prose = privateFallback(el("span", { class: "ov-prose", html: inline(words, "") }));
  return quote && englishProse(words.replace(/^[^:：]{1,12}：/, "")) ? originalQuote(prose) : prose;
}
// A section heading that leaked into prose as a sentence ("Who they are.", the old 仍不明确 bug) is the reader's own
// word, translated through the same table as the headings; it is never quoted as the page's English (#3416).
function sectionWords(text) {
  const name = String(text || "").trim().replace(/[.。]$/, "");
  return uiLanguage === "zh" && /^[A-Z][a-z]+(?: [a-z]+){0,4}$/.test(name) && t(name) !== name ? t(name) + "。" : text;
}
// Labels are the reader's vocabulary, not sentences (art director on #3416): a kind, a role, a place word. They are
// said in Chinese through this reviewed table, never machine-translated; a label the table does not know stays as the
// page wrote it, and only a whole English sentence is shown behind 原文. A Facts line quoted as prose ("Parent: [[…]]",
// "Company: …", "Kind: course") says its label in Chinese too; only labels the table knows (#3410).
const KIND_WORDS = { course: "课程", university: "大学", school: "学校", team: "团队", company: "公司", startup: "初创公司",
  department: "部门", lab: "实验室", club: "社团", community: "社区", government: "政府", nonprofit: "非营利组织",
  faculty: "学院", program: "项目", programme: "项目", group: "小组", agency: "机构", investor: "投资方", client: "客户" };
const ROLE_WORDS = { "team member": "团队成员", member: "成员", founder: "创始人", "co-founder": "联合创始人", cofounder: "联合创始人",
  "co founder": "联合创始人", ceo: "CEO", cto: "CTO", student: "学生", mentor: "导师", tutor: "助教", "teaching assistant": "助教",
  lecturer: "讲师", professor: "教授", "course convenor": "课程负责人", supervisor: "导师", client: "客户", customer: "客户",
  investor: "投资人", advisor: "顾问", adviser: "顾问", consultant: "顾问", contractor: "外包", engineer: "工程师",
  "software engineer": "软件工程师", developer: "开发者", designer: "设计师", "product manager": "产品经理", manager: "经理",
  director: "总监", "project manager": "项目经理", intern: "实习生", recruiter: "招聘", partner: "合作伙伴", friend: "朋友",
  colleague: "同事", classmate: "同学", "team lead": "组长", "team leader": "组长", lead: "负责人", owner: "负责人",
  "product owner": "产品负责人", researcher: "研究员", volunteer: "志愿者", organiser: "组织者", organizer: "组织者",
  "account manager": "客户经理", sales: "销售", marketing: "市场", operations: "运营", accountant: "会计", lawyer: "律师" };
Object.assign(ROLE_WORDS, { coo: "COO", cfo: "CFO", cmo: "CMO", cpo: "CPO", "chief executive officer": "首席执行官",
  "chief technology officer": "首席技术官", "chief operating officer": "首席运营官", "chief financial officer": "首席财务官",
  "chief marketing officer": "首席营销官", "chief product officer": "首席产品官", president: "总裁", "vice president": "副总裁",
  vp: "副总裁", "managing director": "董事总经理", "general manager": "总经理", head: "负责人", "founding engineer": "创始工程师",
  "founding member": "创始成员", "solo founder": "独立创始人", "technical co-founder": "技术联合创始人", partnerships: "合作",
  "business development": "业务拓展", bd: "业务拓展", "head of": "负责人", specialist: "专员", coordinator: "协调人",
  executive: "主管", associate: "专员", analyst: "分析师", officer: "主管", administrator: "管理员", assistant: "助理" });
// The department a title names: "Head of Partnerships" → 合作负责人, "Sales Director" → 销售总监 (art director on #3423:
// 「Head of Partnerships」 was still marked 原文). Only departments and titles in these reviewed tables; anything else
// leaves the title as the page wrote it.
const DEPARTMENT_WORDS = { partnerships: "合作", partnership: "合作", sales: "销售", marketing: "市场", operations: "运营",
  ops: "运营", engineering: "工程", product: "产品", design: "设计", growth: "增长", finance: "财务", people: "人力",
  hr: "人力", "human resources": "人力资源", technology: "技术", tech: "技术", data: "数据", research: "研究", strategy: "战略",
  communications: "传播", legal: "法务", it: "IT", ai: "AI", "business development": "业务拓展", bd: "业务拓展",
  "customer success": "客户成功", support: "支持", "customer support": "客服", content: "内容", community: "社区",
  brand: "品牌", platform: "平台", infrastructure: "基础设施", security: "安全", software: "软件" };
const TITLE_SUFFIX = { director: "总监", manager: "经理", lead: "负责人", head: "负责人", engineer: "工程师", specialist: "专员",
  coordinator: "协调人", executive: "主管", associate: "专员", analyst: "分析师", officer: "主管", designer: "设计师", intern: "实习生" };
function titleWord(key) {
  if (ROLE_WORDS[key] || KIND_WORDS[key]) return ROLE_WORDS[key] || KIND_WORDS[key];
  // "Founder & CEO", "Co-founder and CTO", "Founder / Director": each part known, joined with 兼.
  const parts = key.split(/\s*(?:&|\band\b|\/|,|\+)\s*/).filter(Boolean);
  if (parts.length > 1) { const words = parts.map(titleWord); return words.every(Boolean) ? words.join("兼") : ""; }
  let m = /^(?:head|director|vp|vice president|chief) of (.+)$/.exec(key);
  if (m && DEPARTMENT_WORDS[m[1]]) return DEPARTMENT_WORDS[m[1]] + ({ head: "负责人", director: "总监", vp: "副总裁", "vice president": "副总裁", chief: "负责人" })[key.split(" of ")[0]];
  m = /^(.+?) (director|manager|lead|head|engineer|specialist|coordinator|executive|associate|analyst|officer|designer|intern)$/.exec(key);
  if (m && DEPARTMENT_WORDS[m[1]]) return DEPARTMENT_WORDS[m[1]] + TITLE_SUFFIX[m[2]];
  m = /^(senior|junior|lead|principal|staff|associate|assistant) (.+)$/.exec(key);
  if (m) { const rest = titleWord(m[2]); return rest ? ({ senior: "高级", junior: "初级", lead: "首席", principal: "首席", staff: "资深", associate: "助理", assistant: "助理" })[m[1]] + rest : ""; }
  return "";
}
function labelWord(value) {
  const word = String(value || "").trim(), key = word.toLowerCase().replace(/\s+/g, " ");
  return uiLanguage === "zh" ? titleWord(key) || word : word;
}
function kindWord(value) { return labelWord(value); }
function ourRole(role) {
  const word = labelWord(role);
  return englishProse(word) ? originalQuote(document.createTextNode(role)) : word;
}
function factWords(text) {
  if (uiLanguage !== "zh") return text;
  return String(text).replace(/^([A-Z][A-Za-z /]{1,30}):\s*/, (m, label) => t(label) !== label ? t(label) + "：" : m)
    .replace(/^((?:类别|职位)：)\s*([A-Za-z][A-Za-z -]*?)\s*$/, (m, head, word) => head + labelWord(word));
}
function orgHidden(r) {
  const seen = new Set();
  for (let page = r; page && !seen.has(page.path); page = byPath(page.parent)) {
    seen.add(page.path);
    if (page.private && !revealedOrgs.has(page.path)) return true;
  }
  return false;
}
function orgTile(r, size = "") { return el("span", { class: "ov-tile " + size, "aria-hidden": "true", text: [...orgName(r)][0].toUpperCase() }); }
function orgFace(p, size = "") {
  const words = p.title.replace(/[^\p{L}\p{N} ]/gu, " ").trim().split(/\s+/);
  const initials = (words.length > 1 ? words[0][0] + words.at(-1)[0] : [...(words[0] || "?")].slice(0, 2).join("")).toUpperCase();
  return el("span", { class: "ov-av " + size, "aria-hidden": "true", text: initials });
}
function orgChip(tone, text) { return el("span", { class: "ov-chip " + tone, text }); }
function orgLock() { return el("span", { class: "ov-lock" }, [orgIcon("lock"), orgT("Personal · shown only on this Mac")]); }
function orgFirstName(p) { return p.title.trim().split(/\s+/)[0]; }

// The organisation's deduplicated obligations (reader_model.organisation_obligations),
// joined back to their page thread so done keys, drafts and actions are Today's own.
function orgEntries(r) {
  return (r.obligations || []).filter(row => !(row.units || []).some(path => byPath(path) && orgHidden(byPath(path)))).map(row => {
    const page = byPath(row.record);
    if (!page) return null;
    const found = threads(page).items.find(item => doneKey({ r: page, t: item }) === row.key);
    const members = row.keys.map(key => {
      const text = key.slice(key.indexOf("\n") + 1);
      return { r: byPath(key.slice(0, key.indexOf("\n"))) || page, t: { text, originalText: text } };
    });
    return { r: page, row, members, t: { ...(found || { text: row.text, originalText: row.text }), since: row.since, due: row.due, quiet: row.quiet, dir: row.dir } };
  }).filter(entry => entry && !isDone(entry));
}
function overdue(entry) { return !!entry.t.due && entry.t.due < calendarDay(REM.as_of); }
function owedFirst(a, b) {
  return Number(overdue(b)) - Number(overdue(a)) || (overdue(a) ? a.t.due.localeCompare(b.t.due) : 0)
    || (a.t.since || "9999").localeCompare(b.t.since || "9999");
}
function orgOwed(r) { return orgEntries(r).filter(entry => entry.t.dir === "mine" && !entry.t.quiet).sort(owedFirst); }
function orgTheirs(r) { return orgEntries(r).filter(entry => entry.t.dir === "theirs" && !entry.t.quiet); }
function owedPerson(entry) {
  const path = (entry.row.people || [])[0];
  return path ? byPath(path) : entry.r.category === "people" ? entry.r : null;
}
// The thing owed as a noun phrase, and the quoted words that prove it.
function owedWords(entry) {
  const { words } = morningWords(entry.t.text, entry.r, entry.t);
  const quote = /“([^”]+)”|"([^"]+)"|「([^」]+)」/.exec(words);
  const lead = (quote ? words.slice(0, quote.index) : words).replace(/[\s—–:：,，;；.。(（-]+$/, "").trim();
  // "Weiwei wrote, “…”" names a speaker, not the thing: then the sentence itself is the title.
  const frame = !lead || lead.split(/\s+/).length < 3 || /\b(?:wrote|writes|asked|asks|said|says|replied|followed up)(?: you| him| her)?$|\byou$/i.test(lead);
  if (frame) return { title: capFirst(words), quote: "" };
  const said = quote ? quote[1] || quote[2] || quote[3] : "";
  return { title: capFirst(lead), quote: /^0x[0-9a-f]{24,}$/i.test(said) ? said.slice(0, 10) + "…" + said.slice(-9) : said };
}

// ---------- the list ----------
// Two pages with one name (one company, two mail domains) are one organisation. A unit is part of
// the organisation it sits in (#2992): it is drawn inside that row's shape, not listed beside it.
// A page titled by a person's role is a person filed as a unit (#3160), not an organisation.
const ROLE_TITLE = /\b(?:Deputy|Director|Manager|Officer|Coordinator|Lecturer|Professor|Dean|Head of|Chair(?:man|woman)?|Founder|CEO|CTO|COO|CFO)\b/i;
function personAsOrg(r) { return ROLE_TITLE.test(orgName(r)) && !(r.people || []).length && !(r.children || []).length; }
function orgRows() {
  const byName = new Map();
  for (const r of listRows("orgs").filter(page => !byPath(page.parent) && !personAsOrg(page))) {
    // Same-named units are one row (#3160: a faculty listed twice); a private page stays its own.
    const key = (orgHidden(r) ? "page:" + r.path + ":" : r.unit_kind ? "unit:" : "visible:") + orgName(r).toLowerCase();
    byName.set(key, [...(byName.get(key) || []), r]);
  }
  return [...byName.values()].map(pages => {
    const r = [...pages].sort((a, b) => (b.people || []).length - (a.people || []).length)[0];
    const people = [...new Map(pages.flatMap(page => orgMembers(page)).map(p => [p.path, p])).values()];
    // Last contact is the newest exchange with anyone there: the page's own date lags until REM re-reads it.
    return { r, pages, people, units: pages.flatMap(page => orgUnitNames(page)), last: [...pages.map(page => known(page).last), ...people.map(orgLast)].filter(Boolean).sort().at(-1) || "" };
  });
}
// Organisations use the same chooser, blank-last sorter and phone cards as People.
const ORG_TABLE_ZH = {
  "By structure": "按结构", "Flat": "平铺", "List layout": "列表布局", "Subordinate units": "下属单位", "{n} units · {m} people": "{n} 个下属单位 · {m} 人",
  "Kind": "类别", "Unclassified": "未分类", "Derived": "推断", "What they do / to you": "业务 / 与你的关系", "Website": "官网", "People known there": "认识的人", "Activity": "活跃度", "Legal entity": "法律实体", "Parent": "上级组织", "{n} messages · 90 days": "90 天 · {n} 条消息",
  "company": "公司", "service": "服务", "team": "团队", "course": "课程", "event": "活动",
  "club": "社团",
  "Filter organisations, people, domains": "搜索组织、联系人或域名",
};
function orgTableT(key, values = {}) {
  return uiLanguage === "zh" && ORG_TABLE_ZH[key] ? ORG_TABLE_ZH[key].replace(/\{(\w+)\}/g, (_, name) => values[name] ?? "") : orgT(key, values);
}
let orgTableColumns = null;
const ORG_SORT = { sort: "last", desc: true, text: "" };
let orgListMode = "tree";
let orgCollapsed = new Set();
function orgFact(r, key, raw = false) {
  const fields = parseFacts(r).get(key) || r.facts?.[key] || [];
  const summary = ["What they do", "To you"].includes(key);
  // A qualifier has no provenance-note type: retain it with the address.
  return fields.map(f => f.value + (key === "Location" && f.qualifier ? " (" + f.qualifier + ")" : ""))
    .map(value => raw ? unlabelled(value) : plainValue(value))
    .map(value => summary ? orgSummary(value) : value)
    .filter(v => v && (summary || !/^unknown\b/i.test(v))).join("; ");
}
function orgWebsite(r, people) {
  const explicit = orgFact(r, "Website", true);
  if (explicit) {
    const raw = /\[[^\]]*\]\(([^)]+)\)/.exec(explicit)?.[1] || explicit;
    const url = /^https?:\/\//i.test(raw) ? raw : /^[\w.-]+\.[a-z]{2,}(?:\/[^\s]*)?$/i.test(raw) ? "https://" + raw : "";
    return url && /^https?:\/\/[^\s/]+(?:\/[^\s]*)?$/i.test(url) ? { url, derived: false } : null;
  }
  const shared = /(?:^|\.)(?:student|students|alumni|stu|mail|my)\.|\.(?:edu|ac)(?:\.[a-z]{2})?$/i;
  const free = /^(?:(?:gmail|googlemail|outlook|hotmail|live|msn|yahoo|ymail|icloud|me|mac|aol|proton|protonmail|pm|gmx|mail|fastmail|hey|qq|163|126|139|yeah|foxmail|sina|sohu|naver|daum|hanmail|rediffmail|zoho|yandex|tuta|tutanota)\.[a-z.]+)$/i;
  // The mailbox and home-internet providers excluded by scan.personal_mailbox are not employers.
  const home = new Set(["bigpond.com", "bigpond.net.au", "optusnet.com.au", "xtra.co.nz", "tpg.com.au", "iinet.net.au", "internode.on.net", "ozemail.com.au", "dodo.com.au", "comcast.net", "verizon.net", "att.net", "btinternet.com", "sky.com", "virginmedia.com"]);
  for (const p of people) {
    const domains = unlabelled(orgFact(p, "Email", true)).matchAll(/@[a-z0-9.-]+\.[a-z]{2,}/gi);
    for (const match of domains) {
      const domain = match[0].slice(1).toLowerCase();
      // A university's mail is shared by every student and staff member: it is the university's, never a team's or
      // a course's website (13:25 hunt: a student team's 网站 read as the university's student mail domain).
      if (!free.test(domain) && !home.has(domain) && !shared.test(domain)) return { url: "https://" + domain, derived: true };
    }
  }
  return null;
}
function orgActivity(people) {
  const unique = [...new Map(people.map(p => [p.path, p])).values()];
  const stats = unique.map(relation).filter(s => s && s.messages_90d != null);
  if (!stats.length) return null;
  return { messages_90d: stats.reduce((n, s) => n + s.messages_90d, 0),
    weekly_messages: Array.from({length: 52}, (_, i) => stats.reduce((n, s) => n + (s.weekly_messages?.[i] || 0), 0)),
    last_mail: stats.map(s => s.last_mail || "").sort().at(-1) || "" };
}
function orgTableRow(o) {
  const {r, people} = o, hidden = orgHidden(r);
  const rel = hidden ? null : orgActivity(people);
  const dates = [r, ...people].map(p => orgFact(p, "First contact")).filter(Boolean).sort();
  return { ...o, rel, website: hidden ? null : orgWebsite(r, people),
    first: hidden ? "" : dates[0] || "", last: hidden ? "" : [o.last, rel?.last_mail?.slice(0, 10)].filter(Boolean).sort().at(-1) || "",
    kind: hidden ? "" : r.unit_kind || r.kind || orgFact(r, "Kind"),
    summary: hidden ? "" : orgSummary(orgFact(r, "What they do")) || orgSummary(orgRelation(r)),
    location: hidden ? "" : orgFact(r, "Location"), legal: hidden ? "" : orgFact(r, "Legal entity"),
    text: [orgName(r), hidden ? "" : [orgRelation(r), ...people.map(p => p.title), ...(o.units || []), r.domain || ""].join(" ")].join(" ").toLowerCase() };
}
function orgVisibleRows(rows, collapsed, depth = 0, seen = new Set()) {
  return rows.flatMap(d => {
    if (seen.has(d.r.path)) return [];
    seen.add(d.r.path);
    const expanded = !collapsed.has(d.r.path);
    return [{...d, depth, expanded}, ...(expanded ? orgVisibleRows(d.children || [], collapsed, depth + 1, seen) : [])];
  });
}
function orgNameCell(d, draw) {
  const {r} = d, hidden = orgHidden(r);
  const logo = !hidden && /^data:image\/(?:png|jpeg|gif|webp);base64,/.test(r.logo || "")
    ? el("img", {class: "org-logo", src: r.logo, alt: ""}) : orgTile(r, "org-logo");
  const toggle = !d.flat && d.children?.length ? el("button", {type: "button", class: "org-disclosure", "aria-label": orgTableT("Units and people") + " · " + orgName(r),
    "aria-expanded": String(!!d.expanded), text: d.expanded ? "▾" : "▸"}) : null;
  if (toggle) toggle.onclick = () => {
    const collapsed = d.expanded;
    d.expanded = !collapsed;
    for (const paths of [orgCollapsed, ORG_SORT.search?.collapsed].filter(Boolean)) {
      collapsed ? paths.add(r.path) : paths.delete(r.path);
    }
    readerStorage("co-rem-org-collapsed", [...orgCollapsed].join("\n"));
    draw();
  };
  const summary = d.unitCount && !hidden ? el("small", {class: "org-unit-summary", text: orgTableT("{n} units · {m} people", {n: d.unitCount, m: d.people.length})}) : null;
  const path = d.flat && d.ancestors?.length ? el("small", {class: "org-unit-path", text: [...d.ancestors, orgName(r)].join(" › ")}) : null;
  const guides = Array.from({length: d.depth || 0}, (_, i) => el("span", {class: "org-tree-guide", "aria-hidden": "true", style: `left:${i * 18 + 8}px`}));
  const disclosure = toggle || (!d.flat ? el("span", {class: "org-disclosure-space", "aria-hidden": "true"}) : null);
  return el("span", {class: "nm org-table-name", style: `padding-left:${(d.depth || 0) * 18}px`},
    [...guides, disclosure, logo, el("span", {class: "org-name-text"}, [el("a", {href: href(r), text: orgName(r)}), summary, path]), hidden ? orgLock() : null]);
}
function orgWebsiteCell(d) {
  return d.website ? el("span", {class: "org-site"}, [el("a", {href: d.website.url, target: "_blank", rel: "noopener",
    text: d.website.url.replace(/^https?:\/\//, "").replace(/\/$/, "")}), d.website.derived ? el("span", {class: "org-derived", title: orgTableT("Derived"), "aria-label": orgTableT("Derived")}) : null]) : textCell("");
}
const ORG_COLUMNS = [
  {key: "name", label: "Organisation", sort: d => orgName(d.r), cell: orgNameCell},
  {key: "kind", label: "Kind", sort: d => blank(d.kind), cell: d => textCell(ORG_KINDS[d.kind] ? orgTableT(ORG_KINDS[d.kind]) : orgTableT(d.kind))},
  {key: "summary", label: "What they do / to you", sort: d => blank(d.summary), cell: d => textCell(d.summary)},
  {key: "website", label: "Website", sort: d => blank(d.website?.url), cell: orgWebsiteCell},
  {key: "location", label: "Location", sort: d => blank(d.location), cell: d => textCell(d.location)},
  {key: "people", label: "People known there", num: true, desc: true, sort: d => orgHidden(d.r) ? null : d.people.length,
    cell: d => orgHidden(d.r) ? textCell("") : el("span", {class: "mono", text: String(d.people.length)})},
  {key: "activity", label: "Activity", desc: true, sort: d => d.rel?.messages_90d || null, cell: d => d.rel?.messages_90d ? el("span", {class: "org-activity"},
    [el("span", {class: "mono", text: orgTableT("{n} messages · 90 days", {n: d.rel.messages_90d})})]) : textCell("")},
  {key: "last", label: "Last contact", desc: true, sort: d => blank(d.last), cell: d => d.last ? el("span", {class: "mono", text: calendarDate(d.last)}) : textCell("")},
  {key: "first", label: "First contact", extra: true, sort: d => blank(d.first), cell: d => d.first ? el("span", {class: "mono", text: calendarDate(d.first)}) : textCell("")},
  {key: "units", label: "Subordinate units", extra: true, num: true, desc: true, sort: d => orgHidden(d.r) ? null : d.unitCount,
    cell: d => orgHidden(d.r) ? textCell("") : el("span", {class: "mono", text: String(d.unitCount)})},
  {key: "legal", label: "Legal entity", extra: true, sort: d => blank(d.legal), cell: d => textCell(d.legal)},
  {key: "parent", label: "Parent", extra: true, sort: d => blank(byPath(d.r.parent)?.title), cell: d => byPath(d.r.parent) ? el("a", {href: href(byPath(d.r.parent)), text: orgName(byPath(d.r.parent))}) : textCell("")}
];
function orgTableChildren(d, seen = new Set()) {
  if (seen.has(d.r.path) || orgHidden(d.r)) return [];
  const next = new Set([...seen, d.r.path]);
  const named = new Map();  // two child pages with one name under one parent are one unit (#3160)
  for (const r of d.pages.flatMap(r => (r.children || []).map(byPath).filter(Boolean)).filter(r => !next.has(r.path) && !personAsOrg(r)))
    if (!named.has(orgName(r).toLowerCase()) || orgHidden(r)) named.set(orgHidden(r) ? r.path : orgName(r).toLowerCase(), r);
  return [...named.values()].map(r => {
    const people = orgMembers(r), last = [known(r).last, ...people.map(orgLast)].filter(Boolean).sort().at(-1) || "";
    const child = orgTableRow({r, pages: [r], people, last, units: orgUnitNames(r)});
    child.ancestors = [...(d.ancestors || []), orgName(d.r)];
    child.children = orgTableChildren(child, next);
    child.unitCount = child.children.length;
    return child;
  });
}
function orgsView() {
  document.getElementById("main").textContent = "";
  const rows = orgRows().map(orgTableRow);
  // A column empty for 80% or more of the rows is left out of the default set (#3131, #3160); Columns still offers it.
  const sparse = ORG_COLUMNS.filter(c => c.key !== "name" && rows.length >= 5 && rows.filter(d => c.sort(d) == null || c.sort(d) === "").length / rows.length >= 0.8).map(c => c.key);
  orgTableColumns ??= peopleColumnKeys(null, ORG_COLUMNS).filter(key => !sparse.includes(key));
  for (const d of rows) { d.children = orgTableChildren(d); d.unitCount = d.children.length; }
  if (orgFilter.tab !== "all" && !rows.some(d => [d, ...orgDescendants(d)].some(child => child.kind === orgFilter.tab))) orgFilter.tab = "all";
  peopleView([], {category: "orgs", translate: orgTableT,
    widths: {name: 20, kind: 8, summary: 22, website: 13, location: 13, people: 6, activity: 10, last: 8, first: 9, legal: 16, parent: 14}, columns: ORG_COLUMNS, state: ORG_SORT, rows,
    chosen: () => orgTableColumns, choose: keys => { orgTableColumns = keys; }, storage: "co-rem-org-columns",
    clear: () => { ORG_SORT.text = ""; orgFilter.tab = "all"; orgsView(); },
    className: "ov-list org-directory", tableClass: "org-table", rowClass: "org-table-row",
    title: orgTableT("{n} organisations", {n: rows.length}), placeholder: "Filter organisations, people, domains",
    matches: (d, needle) => orgFilterRows([d], orgFilter.tab, needle).length > 0,
    visible: orgListRows, filters: draw => orgListControls(rows, draw)});
  const directory = document.querySelector(".org-directory");
  // Capture the user's sort intent, including clicking the already selected Last contact.
  directory.addEventListener("click", event => { if (event.target.closest("th button")) orgListMode = "flat"; }, true);
  directory.addEventListener("change", event => { if (event.target.matches(".people-sort")) orgListMode = "flat"; }, true);
}
function orgListRows(rows, col, state) {
  const all = rows.flatMap(d => [d, ...orgDescendants(d)]);
  for (const d of all) d.keys = {[col.key]: col.sort(d)};
  const order = list => list.sort(peopleOrder(col, state.desc));
  const needle = state.text.trim().toLowerCase();
  if (state.search?.text !== needle) state.search = {text: needle, collapsed: new Set()};
  document.querySelectorAll(".org-layout-switch button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode === orgListMode)));
  if (orgListMode === "flat") return order(all.filter(d => (orgFilter.tab === "all" || d.kind === orgFilter.tab) && (!needle || d.text.includes(needle))))
    .map(d => ({...d, flat: true, depth: 0}));
  const sortTree = list => order(list).map(d => ({...d, children: sortTree(d.children || [])}));
  const filtered = sortTree(orgFilterRows(rows, "all", needle));
  return orgVisibleRows(filtered, needle ? state.search.collapsed : orgCollapsed);
}
function orgListControls(rows, draw) {
  const layout = el("div", {class: "org-layout-switch", role: "group", "aria-label": orgTableT("List layout")});
  for (const [mode, label] of [["tree", "By structure"], ["flat", "Flat"]]) {
    const button = el("button", {type: "button", "data-mode": mode, "aria-pressed": String(orgListMode === mode), text: orgTableT(label)});
    button.onclick = () => {
      orgListMode = mode;
      if (mode === "tree") { orgFilter.tab = "all"; ORG_SORT.sort = "last"; ORG_SORT.desc = true; orgsView(); }
      else draw();
    };
    layout.append(button);
  }
  return el("div", {class: "org-list-controls"}, [layout, orgKindFilters(rows, draw)]);
}
function orgFilterRows(rows, kind, needle) {
  return rows.flatMap(d => {
    const children = orgFilterRows(d.children || [], kind, needle);
    const matches = (kind === "all" || d.kind === kind) && (!needle || d.text.includes(needle));
    return matches || children.length ? [{...d, children}] : [];
  });
}
function orgDescendants(d) { return (d.children || []).flatMap(child => [child, ...orgDescendants(child)]); }
function orgKindFilters(rows, draw) {
  const kinds = [...new Set(rows.flatMap(d => [d, ...orgDescendants(d)]).map(d => d.kind))].sort();
  const bar = el("div", {class: "org-kind-filters", role: "group", "aria-label": orgTableT("Kind")});
  const tabs = ["all", ...kinds];
  if (!tabs.includes(orgFilter.tab)) orgFilter.tab = "all";
  bar.append(...tabs.map(kind => {
    const button = el("button", {type: "button", "aria-pressed": String(orgFilter.tab === kind), text: kind === "all" ? orgTableT("All") : orgTableT(ORG_KINDS[kind] || kind || "Unclassified")});
    button.onclick = () => { orgFilter.tab = kind; orgListMode = "flat"; bar.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b === button))); draw(); };
    return button;
  }));
  return bar;
}
function orgUnitNames(r, seen = new Set()) {
  if (!r || seen.has(r.path)) return [];
  seen.add(r.path);
  return (r.children || []).map(byPath).filter(child => child && !seen.has(child.path) && !orgHidden(child))
    .flatMap(child => [child.title, ...orgUnitNames(child, seen)]);
}
// The organisation's shape, compact: an icicle with one band per level (deeper units fold into the
// second), each cell as wide as the people you know there. Both bands share the first band's
// widths, so a unit sits under its branch; a branch's own people leave its part of band two empty.
function orgShapeLine(r, people) {
  const { tree } = orgUnitTree(r, people, []);
  if (!tree.units.length) return null;
  const loose = orgLoose(tree), branches = [...tree.units].sort(orgByActivity);
  const cell = (n, name, cls = "") => el("i", { class: cls, style: `flex-grow:${n}`, title: name + " · " + n });
  const part = (n, kids) => el("span", { style: `flex-grow:${n}` }, [...kids, el("b", { style: `flex-grow:${Math.max(0, n - kids.reduce((sum, kid) => sum + Number(kid.style.flexGrow), 0))}` })]);
  const top = [...branches.map(u => cell(unitPeople(u).length, u.name)), loose.length ? cell(loose.length, orgT("Department not known yet"), "loose") : null].filter(Boolean);
  const under = [...branches.map(u => part(unitPeople(u).length, [...u.units].sort(orgByActivity).map(child => cell(unitPeople(child).length, child.name)))),
    loose.length ? part(loose.length, []) : null].filter(Boolean);
  const bands = [el("span", { class: "ov-band" }, top), branches.some(u => u.units.length) ? el("span", { class: "ov-band" }, under) : null];
  return el("div", { class: "ov-shape" }, [el("span", { class: "ov-icicle", "aria-hidden": "true" }, bands),
    el("small", { class: "ov-meta", text: orgT("{n} units · {m} people", { n: orgUnitCount(tree), m: people.length }) })]);
}
function orgFaces(people) {
  if (!people.length) return el("span", { class: "ov-stack" });
  const shown = [...people].sort((a, b) => known(b).last.localeCompare(known(a).last)).slice(0, 3);
  return el("span", { class: "ov-stack", title: people.map(p => p.title).join(", ") },
    [...shown.map(p => orgFace(p, "xs")), people.length > 3 ? el("em", { text: "+" + (people.length - 3) }) : null]);
}

// ---------- one organisation: a knowledge article (#3036), read like a book ----------
// Facts belong in sentences; the tree preserves the recorded structure (#2992).
let orgCurrent = null;

function orgPage(r) {
  const box = el("div", { class: "ov ov-page ov-r6" });
  orgCurrent = null;
  if (orgHidden(r)) {
    box.append(el("section", { class: "ov-stage ov-closed" }, [orgOver(r), el("div", { class: "ov-say" }, [el("h1", { class: "ov-name", text: orgName(r) })])]), orgCurtain(r));
    return box;
  }
  const v = orgView(r);
  orgCurrent = v;
  box.append(...[orgStage(v), orgMilestones(v), orgConnections(v), orgCoda(v)].filter(Boolean));
  return box;
}
function svgEl(tag, attrs = {}, children = []) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  node.append(...children.filter(child => child != null));
  return node;
}

function orgView(r) {
  const people = orgMembers(r), { tree } = orgUnitTree(r, people, []);
  const v = { r, people, tree };
  v.events = orgEvents(r, people);
  return v;
}
// A person's last contact: the page's own date, or the newest dated History line on it.
function orgLast(p) {
  const days = [known(p).last, ...historyItems((section(p, "history") || { text: "" }).text).map(item => item.day).filter(day => day.length === 10)];
  return days.filter(Boolean).sort().at(-1) || "";
}
function orgUnitRole(p, path) { return (p.units || []).find(edge => edge.path === path)?.role || ""; }
function orgPersonRole(p) { return orgUnitRole(p, (p.units || [])[0]?.path) || orgRole(p, "span")?.textContent || ""; }

// ---------- the first screen: name, what it is, how you are connected, its structure ----------
// A unit's crumb is its whole chain, so a team opens back up to its course and university.
function orgCrumb(r) {
  const chain = [], seen = new Set([r.path]);
  for (let page = byPath(r.parent); page && !seen.has(page.path); page = byPath(page.parent)) { seen.add(page.path); chain.unshift(page); }
  const links = chain.length ? chain.map(page => el("a", { href: href(page), text: orgName(page) }))
    : [el("a", { href: categoryHref("orgs"), text: label("orgs") }), ...(r.kind ? [document.createTextNode(orgTableT(ORG_KINDS[r.kind] || r.kind))] : [])];
  return el("div", { class: "ov-crumb", role: "navigation", "aria-label": orgT("Where this sits") }, links.flatMap((node, i) => i ? [" › ", node] : [node]));
}
function orgOver(r) {
  return el("header", { class: "ov-over" }, [orgCrumb(r)]);
}
function orgStage(v) {
  const r = v.r;
  return el("section", { class: "ov-stage" }, [orgOver(r),
    el("div", { class: "ov-say" }, [el("h1", { class: "ov-name", lang: nameLang(orgName(r)), "aria-label": orgName(r), text: orgName(r) }),
      pageTagRow(r), orgOpening(v), recordActs(r)]), orgTree(v)]);
}
function stripStaleOrgPeopleCount(text) {
  if (!text) return "";
  return String(text)
    .split(/(?<=[。.!?！？])\s*/)
    .filter(sent => !/(?:认识[^。.!?！？]{0,24}?\b\d+\s*(?:个人|位|人|名)|(?:没有|不)认识[^。.!?！？]{0,16}?(?:人|联系人)|\bknow(?:s)?\s+(?:no|\d+)\s+(?:people|person|contacts?|members?)\b)/i.test(sent))
    .join(" ")
    .trim();
}
function orgOpening(v) {
  const cleanCount = txt => txt ? String(txt).split(/(?<=[。.!?！？])\s*/).filter(sent => !/(?:认识[^。.!?！？]{0,24}?\b\d+\s*(?:个人|位|人|名)|(?:没有|不)认识[^。.!?！？]{0,16}?(?:人|联系人)|\bknow(?:s)?\s+(?:no|\d+)\s+(?:people|person|contacts?|members?)\b)/i.test(sent)).join(" ").trim() : "";
  const summary = cleanCount(orgSummary(known(v.r).summary));
  const relation = cleanCount(orgRelation(v.r));
  // Mapped organisations often have no History: their contacts still carry mail/index dates.
  const first = [...[v.r, ...v.people].flatMap(p => [facts(p).first, orgFact(p, "First contact")]),
    ...v.events.map(e => e.day)].filter(Boolean).sort()[0];
  const last = [known(v.r).last, ...v.people.map(orgLast), ...v.events.map(e => e.day)].filter(Boolean).sort().at(-1);
  const sentence = text => text ? text + (/[。.!?！？]$/.test(text) ? " " : uiLanguage === "zh" ? "。" : ". ") : "";
  const count = uiLanguage === "zh" ? `你认识这里的 ${v.people.length} 个人。` : `You know ${v.people.length} ${v.people.length === 1 ? "person" : "people"} here. `;
  const through = [...v.people].sort((a, b) => orgLast(b).localeCompare(orgLast(a)) || a.title.localeCompare(b.title))
    .slice(0, 4).map(orgPersonLabel).join(uiLanguage === "zh" ? "、" : ", ");
  const recent = v.people.length > 4;
  const contact = through ? (uiLanguage === "zh" ? `${recent ? "最近往来的 4 位联系人是" : "往来联系人包括"} ${through}。` : `${recent ? "Your most recent 4 contacts are" : "Your contacts include"} ${through}. `) : "";
  const normalized = text => text.toLocaleLowerCase().replace(/[\s。.!?！？]+$/u, "").replace(/\s+/g, " ");
  return el("p", { class: "ov-sub ov-opening" }, [orgProse(sentence(summary), { quote: false }),
    relation && !normalized(summary).includes(normalized(relation)) ? orgProse(sentence(relation), { quote: false }) : null, count, contact,
    first ? sentence(orgT("In touch since {date}", { date: calendarDate(first) })) : "",
    last ? sentence(orgT("Last contact {date}", { date: calendarDate(last) })) : ""]);
}
// ---------- the tree: organisation → units → people (#2992) ----------
// The radial picture read as scattered dots (owner, 2026-11-13: «那应该是一个树状图吧»). Real
// organisations are shallow (three levels) but wide, with long unit codes and most people not yet
// placed in a unit, so an indented tree is the form that keeps every name whole at 390px: an org
// chart runs off the side and an icicle has no room for the names. The most recently
// active branch comes first; people whose unit is not known are the last row, never a branch.
function orgUnitCount(unit) { return unit.units.reduce((n, child) => n + 1 + orgUnitCount(child), 0); }
function orgBranchLast(unit) { return unitPeople(unit).map(orgLast).filter(Boolean).sort().at(-1) || ""; }
function orgByActivity(a, b) { return orgBranchLast(b).localeCompare(orgBranchLast(a)) || unitPeople(b).length - unitPeople(a).length || a.name.localeCompare(b.name); }
function orgByLast(people) { return [...people].sort((a, b) => orgLast(b).localeCompare(orgLast(a)) || a.title.localeCompare(b.title)); }
// People with no unit edge sit under the organisation itself; once it has units they are "not placed yet".
function orgLoose(tree) { return tree.units.length ? tree.people.filter(p => !(p.units || []).length) : []; }
function orgTree(v) {
  const loose = orgLoose(v.tree);
  const shown = new Set(), unitNames = new Map();
  const collect = u => { if (u.path) unitNames.set(u.path, u.name); u.units.forEach(collect); };
  collect(v.tree);
  const person = (p, unitPath, level) => {
    if (shown.has(p.path)) return null;
    shown.add(p.path);
    const roles = (p.units || []).filter(edge => unitNames.has(edge.path) && edge.role);
    const scoped = roles.length > 1 || roles.some(edge => edge.path !== unitPath);
    const meta = scoped ? roles.map(edge => unlabelled(edge.role) + " · " + unitNames.get(edge.path)).join("; ")
      : unlabelled(orgUnitRole(p, unitPath)) || orgRole(p, "span")?.textContent || "";
    return orgTreeItem({ level, kind: "person", label: orgPersonLabel(p), link: href(p), tip: orgPersonTip(p),
      meta: meta || orgPersonNote(p) });
  };
  const unit = (u, level) => {
    const kids = [...orgByLast(u.people).map(p => person(p, u.path, level + 1)), ...[...u.units].sort(orgByActivity).map(child => unit(child, level + 1))].filter(Boolean);
    // A branch opens when its rows fit a glance; a unit with dozens of rows stays one line until asked.
    return orgTreeItem({ level, kind: "unit", label: u.name, link: u.path ? href(byPath(u.path)) : "",
      open: kids.length <= 8, kids });
  };
  const kids = [...orgByLast(v.tree.people.filter(p => !loose.includes(p))).map(p => person(p, v.r.path, 2)), ...[...v.tree.units].sort(orgByActivity).map(u => unit(u, 2)),
    loose.length ? orgTreeItem({ level: 2, kind: "loose", label: orgT("Department not known yet"), open: false,
      kids: orgByLast(loose).map(p => person(p, v.r.path, 3)).filter(Boolean) }) : null].filter(Boolean);
  const root = orgTreeItem({ level: 1, kind: "root", label: orgName(v.r), open: true, kids });
  root.tabIndex = 0;
  const tree = el("ul", { role: "tree", "aria-label": orgT("How {org} is built", { org: orgName(v.r) }) }, [root]);
  tree.addEventListener("keydown", event => orgTreeKey(tree, event));
  return el("section", { class: "ov-org-tree" }, [el("h2", { class: "ov-tree-h", text: uiLanguage === "zh" ? "人物与组织结构" : "People and structure" }),
    tree, orgYourSide(v)]);
}
// The owner's own people this org's page names deal with it; they are not its members (#3397). They sit
// below the tree under a light heading with no fold: level with the org's units, they read as one of its departments.
// A teammate whose page is titled by an address (#3157: REM does not know the name). A local part that reads as a
// name becomes that name (dana → Dana, john.smith → John Smith); anything else (digits, j23x, a role mailbox such as
// info@ or noreply@) keeps the whole address, since half an address is neither a name nor a way to reach them (#3397).
function addressName(address) {
  const roles = ["info", "admin", "noreply", "no-reply", "donotreply", "support", "hello", "contact", "sales", "office",
    "team", "mail", "accounts", "billing", "enquiries", "inquiries", "help", "hr", "jobs", "careers", "marketing",
    "news", "newsletter", "notifications", "service", "webmaster", "postmaster", "reception", "bookings"];
  const local = String(address).trim().split("@")[0].toLowerCase();
  if (roles.includes(local)) return "";
  const parts = local.split(/[._-]+/).filter(Boolean);
  if (!parts.length || parts.length > 3 || !parts.every(part => /^[a-z]{2,}$/.test(part) && /[aeiouy]/.test(part))) return "";
  return parts.map(part => part[0].toUpperCase() + part.slice(1)).join(" ");
}
function orgPersonLabel(p) { return addressTitle(p) ? (addressName(p.title) || String(p.title).trim()) : p.title; }
// The second line under an address-titled person: the address in the muted note when the label is a derived name,
// 只知道邮箱 when the label is the address itself. Never 未知姓名 under a name REM just derived.
function orgPersonNote(p) { return !addressTitle(p) ? "" : addressName(p.title) ? String(p.title).trim() : t("Only the email is known"); }
function orgPersonTip(p) { return addressTitle(p) ? String(p.title).trim() : ""; }
function orgYourSide(v) {
  const ours = orgByLast((v.r.your_side || []).map(byPath).filter(Boolean));
  return ours.length ? el("div", { class: "ov-yours" }, [el("h3", { class: "ov-yours-h", text: orgT("Your side") }),
    el("ul", {}, ours.map(p => el("li", {}, [el("a", { href: href(p), text: orgPersonLabel(p), ...(orgPersonTip(p) ? { title: orgPersonTip(p) } : {}) }),
      orgRole(p, "span") ? el("small", { class: "ov-tk" }, [ourRole(orgRole(p, "span").textContent)])
        : orgPersonNote(p) ? el("small", { class: "ov-tk" }, [orgPersonNote(p)]) : null])))]) : null;
}
function orgTreeItem(d) {
  const row = el("div", { class: "ov-trow", "data-kind": d.kind }, [el("span", { class: "ov-twisty", "aria-hidden": "true" }),
    el("span", { class: "ov-tl1" }, [d.link ? el("a", { href: d.link, tabindex: "-1", text: d.label, ...(d.tip ? { title: d.tip } : {}) }) : el("b", { text: d.label }),
      // A role the page wrote in English stays the page's words, marked as the original (#3410: 「team member」).
      d.meta ? el("small", { class: "ov-tk" }, [ourRole(d.meta)]) : null])]);
  const item = el("li", { role: "treeitem", "aria-level": String(d.level), tabindex: "-1", "aria-label": [d.label, d.meta].filter(Boolean).join(" · ") }, [row]);
  if (d.kids?.length) {
    item.setAttribute("aria-expanded", String(!!d.open));
    item.append(el("ul", { role: "group" }, d.kids));
  }
  // The name is a link; the rest of the row opens and closes the branch.
  row.addEventListener("click", event => {
    if (event.target.closest("a")) return;
    orgTreeToggle(item);
    orgTreeFocus(item.closest("[role=tree]"), item);
  });
  return item;
}
function orgTreeToggle(item, open) {
  if (!item.hasAttribute("aria-expanded")) return;
  item.setAttribute("aria-expanded", String(open ?? item.getAttribute("aria-expanded") !== "true"));
}
// One Tab stop for the whole tree; the arrow keys move inside it (WAI-ARIA tree pattern).
function orgTreeFocus(tree, item) {
  if (!item) return;
  tree.querySelectorAll("[role=treeitem][tabindex='0']").forEach(node => { node.tabIndex = -1; });
  item.tabIndex = 0;
  item.focus();
}
function orgTreeKey(tree, event) {
  const item = event.target.closest("[role=treeitem]");
  if (!item || event.altKey || event.ctrlKey || event.metaKey) return;
  const shown = [...tree.querySelectorAll("[role=treeitem]")].filter(node => node.checkVisibility());
  const at = shown.indexOf(item), open = item.getAttribute("aria-expanded");
  const keys = {
    ArrowDown: () => orgTreeFocus(tree, shown[at + 1]),
    ArrowUp: () => orgTreeFocus(tree, shown[at - 1]),
    Home: () => orgTreeFocus(tree, shown[0]),
    End: () => orgTreeFocus(tree, shown.at(-1)),
    ArrowRight: () => open === "false" ? orgTreeToggle(item, true) : open === "true" ? orgTreeFocus(tree, item.querySelector("[role=treeitem]")) : null,
    ArrowLeft: () => open === "true" ? orgTreeToggle(item, false) : orgTreeFocus(tree, item.parentElement.closest("[role=treeitem]")),
    Enter: () => { const link = item.querySelector(":scope > .ov-trow a"); link ? link.click() : orgTreeToggle(item); },
    " ": () => orgTreeToggle(item)
  };
  if (!keys[event.key]) return;
  event.preventDefault();
  keys[event.key]();
}

// ---------- the time line: when you were in touch, from dated History only ----------
// One event written on two pages ("Basil Thorne confirmed…" on the org, "Basil confirmed…" on
// his own page) is one event: same day, same words once the person's name is set aside.
function orgEventKey(day, words, people) {
  let text = words.toLowerCase().replace(/[\s.。!！]+$/, "");
  for (const p of people) {
    const name = [p.title, orgFirstName(p)].map(n => n.toLowerCase()).find(n => text.startsWith(n + " "));
    if (name) { text = text.slice(name.length + 1); break; }
  }
  return day + "\n" + text;
}
function orgHistory(r, people) {
  const seen = new Set();
  return [r, ...people].flatMap(page => historyItems((section(page, "history") || { text: "" }).text)
    .filter(item => item.day.length === 10).map(item => ({ ...item, page, words: withoutDateClutter(plainLine(item.text, true)) })))
    .filter(item => /[\p{L}\p{N}]/u.test(item.words))
    .filter(item => { const key = orgEventKey(item.day, item.words, people); return !seen.has(key) && seen.add(key); });
}
function orgEvents(r, people) {
  // Contact dates can use labelled history without copying its private words into the opening.
  return orgHistory(r, people).map(item => ({ day: item.day, words: unlabelled(item.words).trim(), kind: /^you\b/i.test(item.words) ? "me" : "them" }))
    .filter(e => /[\p{L}\p{N}]/u.test(e.words)).sort((a, b) => a.day.localeCompare(b.day));
}
// The organisation's own History is the distilled relationship story. Correspondents'
// asks and promises remain in full memory rather than becoming the article's body.
function orgMilestones(v) {
  const items = orgHistory(v.r, []).sort((a, b) => a.day.localeCompare(b.day));
  if (!items.length) return null;
  return el("section", { class: "ov-milestones" }, [el("h2", { text: uiLanguage === "zh" ? "往来历程" : "How the relationship developed" }),
    ...items.map(item => el("p", {}, [el("time", { datetime: item.day, text: calendarDate(item.day) }), " — ", orgProse(item.words)]))]);
}
function orgConnections(v) {
  const paths = [...(v.r.projects || []), ...(v.r.organisations || []), ...(v.r.topics || []), ...(v.r.relations || []).map(edge => edge.path || edge.target)];
  const pages = [...new Set(paths)].map(byPath).filter(p => p && p.path !== v.r.path && ["projects", "orgs", "knowledge"].includes(p.category) && !orgHidden(p));
  if (!pages.length) return null;
  // The reason is the line on THIS page that links the two, never the other page's own summary: that summary
  // is about the other page (its latest version note, on the rc19 hunt), not about this pair (#3397).
  const edges = new Map((v.r.relations || []).map(link => [link.path || link.target, link]));
  const reasons = new Map([...edges].filter(([, link]) => link.basis)
    .map(([path, link]) => [path, relationReason(localizedRelation(link, v.r.path).basis, byPath(path), v.r)]).filter(([, reason]) => reason));
  // No line says why: name only how the two pages meet, never borrow a sentence from elsewhere.
  // Which page names which: the edge says so; without one, this page's own organisations are named here and a
  // project or topic listed on it named this org from its own page.
  const mine = p => edges.get(p.path) ? edges.get(p.path).kind === "linked" : (v.r.organisations || []).includes(p.path);
  const how = p => mine(p) ? "Mentioned on this page" : "Its page mentions this one";
  return el("section", { class: "ov-connections" }, [el("h2", { text: uiLanguage === "zh" ? "关联" : "Connections" }),
    ...pages.map(p => {
      const reason = reasons.get(p.path);
      return el("p", {}, [el("a", { href: href(p), text: pageName(p) }), " — ",
        reason ? orgProse(reason) : el("span", { class: "ov-conn-kind", text: singular(p.category) + " · " + t(how(p)) })]);
    })]);
}
function orgCoda(v) {
  const fact = name => (parseFacts(v.r).get(name) || [])
    .map(item => item.value + (name === "Location" && item.qualifier ? " (" + item.qualifier + ")" : ""))
    .map(value => orgSummary(plainLine(value, true))).filter(value => value && (name === "What they do" || !/^unknown\b/i.test(value))).join("; ");
  const what = fact("What they do"), place = fact("Location"), website = orgWebsite(v.r, v.people || [])
    || (/^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$/i.test(v.r.domain || "") ? {url: "https://" + v.r.domain} : null);
  const row = (label, value) => value ? el("div", {}, [el("dt", {text: label}), el("dd", {}, [value])]) : null;
  return el("footer", { class: "ov-coda" }, [
    el("dl", { class: "ov-about" }, [row(t("What they do"), orgProse(what)),
      row(orgT("Where"), orgProse(place)), row(orgT("Website"), website ? el("a", {
        href: website.url, target: "_blank", rel: "noopener", text: website.url.replace(/^https?:\/\//, "").replace(/\/$/, "")}) : null)]),
    el("a", { class: "ov-src", href: href(v.r) + "&h=full-memory-heading", text: t("Read full memory →") })]);
}

function orgCurtain(r) {
  const show = el("button", { type: "button", class: "ov-btn ghost", text: orgT("Show") });
  show.onclick = () => {
    const seen = new Set();
    for (let page = r; page && !seen.has(page.path); page = byPath(page.parent)) {
      seen.add(page.path);
      if (page.private) revealedOrgs.add(page.path);
    }
    revealedOrgs.add(r.path);
    render();
  };
  return el("div", { class: "ov-curtain" }, [orgLock(), show]);
}
// Validated Parent edges and direct Unit memberships form the explicit tree;
// old free-text Team values remain a flat fallback without inventing an edge.
function orgMembers(r, seen = new Set()) {
  if (!r || seen.has(r.path) || orgHidden(r)) return [];
  seen.add(r.path);
  const people = [...(r.people || []).map(byPath), ...(r.children || []).flatMap(path => orgMembers(byPath(path), seen))]
    .filter(p => p && !p.service && !p.needs_review && p.path !== REM.owner);
  return [...new Map(people.map(p => [p.path, p])).values()];
}
function orgTeamLabel(p) {
  const names = (p.units || []).map(edge => byPath(edge.path)).filter(unit => unit && !orgHidden(unit)).map(orgName);
  if (names.length) return names.join(" · ");
  return /\[\[|\]\(/.test(p.team || "") ? "" : plainLine(p.team || "");
}
function orgUnitTree(r, people, owed) {
  const owing = owed.reduce((map, entry) => map.set(owedPerson(entry)?.path, [...(map.get(owedPerson(entry)?.path) || []), entry]), new Map());
  const build = (page, seen = new Set()) => {
    if (seen.has(page.path)) return null;
    const next = new Set([...seen, page.path]);
    const units = (page.children || []).map(byPath).filter(child => child && !orgHidden(child)).map(child => build(child, next)).filter(Boolean);
    const placed = new Set(units.flatMap(unitPeople).map(p => p.path));
    return {name: orgName(page), path: page.path, units,
      people: (page.people || []).map(byPath).filter(p => p && people.some(member => member.path === p.path) && (!placed.has(p.path) || (p.units || []).some(edge => edge.path === page.path))),
      owed: owed.filter(entry => (entry.row.units || []).includes(page.path) || !(entry.row.units || []).length && page.path === r.path)};
  };
  const tree = build(r), teams = new Map();
  const loose = tree.people.filter(p => !(p.units || []).length);
  for (const p of loose) if (orgTeamLabel(p)) teams.set(orgTeamLabel(p), [...(teams.get(orgTeamLabel(p)) || []), p]);
  tree.people = tree.people.filter(p => !loose.includes(p) || !orgTeamLabel(p));
  tree.units.push(...[...teams].map(([name, members]) => ({name, people: members, units: [], owed: members.flatMap(p => owing.get(p.path) || [])})));
  return {tree, owing};
}
function unitOwed(unit) { return [...new Map([...unit.owed, ...unit.units.flatMap(unitOwed)].map(entry => [entry.row.key, entry])).values()]; }
function unitPeople(unit) { return [...new Map([...unit.people, ...unit.units.flatMap(unitPeople)].map(p => [p.path, p])).values()]; }
function orgRole(p, tag = "small") {
  const role = contactFields(p).find(f => f.label === "Role")?.value;
  return role && !UNKNOWN_TEXT.test(role) && !/^unknown\b/i.test(role) ? el(tag, { class: "ov-role" }, [roleSummary(role, p.path)]) : null;
}

const SKILL_FAMILY_NAMES = { lark: "Lark", linkedin: "LinkedIn", wecomcli: "WeCom", connectonion: "ConnectOnion", co: "co", oo: "oo", x: "X" };
const SKILL_NO_DESCRIPTION = /^Unknown\s*—\s*description not provided\.?$/i;
const SKILL_ABBREVIATION = /(?:\b(?:e\.g|i\.e|vs|etc|cf|approx|Mr|Mrs|Ms|Dr|St|No)|(?:^|[\s(])(?:\p{L}\.)*\p{L})$/iu;

function skillClause(line) {
  const whole = plainLine(line).replace(/\s*\((?:user|project|plugin)\)\s*$/i, "").trim();
  if (!whole || UNFILLED_LINE.test(whole) || SKILL_NO_DESCRIPTION.test(whole)) return "";
  const text = whole.replace(/^(?:This|The) skill\s+(\w)/i, (_, ch) => ch.toUpperCase());
  const han = /\p{Script=Han}/u.test(text);
  let depth = 0, cut = text.length;
  for (let i = 0; i < text.length && cut === text.length; i++) {
    const ch = text[i], rest = text.slice(i);
    if ("([{（【「".includes(ch)) depth++;
    else if (")]}）】」".includes(ch)) depth = Math.max(0, depth - 1);
    if (depth || !/[\p{L}\p{N}]/u.test(text.slice(0, i))) continue;
    const sentence = /^[.!?](?=\s|$)/.test(rest) && !SKILL_ABBREVIATION.test(text.slice(0, i)) || /^[。！？]/.test(rest);
    const aside = i >= 4 && !/^(?:unknown|not known)$/i.test(text.slice(0, i)) && /^(?:\s[—–]\s|——|;\s|；|,\s(?:with|so|from|which|while|and then)\s)/.test(rest);
    const longHan = han && text.length > 40 && i >= 8 && /^[：，]/.test(rest);
    if (sentence || aside || longHan) cut = i;
  }
  return text.slice(0, cut).replace(/[\s.。;；,，:：]+$/, "") || text;
}
// In the reader's language when the skill has it (its own Chinese description, or a translation
// already made); otherwise the original, quietly (D-103). Never a model call at render time.
function skillLine(r) {
  const what = text => rawSection({ text }, "What it does").split("\n").find(Boolean) || "";
  const installed = text => (/^- Installed description[:：]\s*(.+)$/m.exec(text) || [])[1] || "";
  // A regional tag ("zh-CN") reads as the interface language, as cacheChineseInterface() does for pages.
  const tag = uiLanguage === "en" ? "" : Object.keys(r.translations || {}).find(tag => tag === uiLanguage)
    || Object.keys(r.translations || {}).find(tag => tag.toLowerCase().startsWith(uiLanguage + "-"));
  const original = r.original ?? r.text, translated = tag ? r.translations[tag] : "";
  const lines = [what(translated), what(original), installed(original)].map(skillClause).filter(Boolean);
  const han = line => /\p{Script=Han}/u.test(line);
  return (uiLanguage === "zh" ? lines.find(han) : lines.find(line => !han(line))) || lines[0] || "";
}
function skillFamily(title) {
  const prefix = title.split(/[-:]/)[0];
  return SKILL_FAMILY_NAMES[prefix] || capFirst(prefix);
}
const SKILL_HOMES = [[/\/\.claude\/plugins\//, "Claude Code plugin"], [/\/\.claude\//, "Claude Code"], [/\/\.codex\//, "Codex"],
  [/\/\.cursor\//, "Cursor"], [/\/\.kiro\//, "Kiro"], [/\/\.agents\//, "Shared agent skills"], [/\/connectonion\//, "ConnectOnion"]];
function skillHome(path) {
  path = path.replace(/\\/g, "/");  // a Windows install path reads the same as a POSIX one
  const home = SKILL_HOMES.find(([pattern]) => pattern.test(path));
  return home ? t(home[1]) : path.split("/").slice(-3, -1).join("/");
}
function skillUses(r) { return skillUsage(r)?.count || 0; }
function bySkillUse(a, b) {
  return skillUses(b) - skillUses(a) || (skillUsage(b)?.last || "").localeCompare(skillUsage(a)?.last || "") || a.title.localeCompare(b.title);
}
// ---------- Skills (#3094): the People table, family tabs, a few views ----------
// The owner: the tabs are good, "but the table underneath is too overwhelming; do it like the People table; you
// can add a few views." So Skills is a third caller of peopleView: one line a skill, a tab per family that shows
// only it, and a view switch that re-orders in one click. The eight most-used cards are gone: with Most used as
// the default view the first eight rows are those skills, and the cards pushed the table under the first screen.
// A view is [key in the address, name, the column it sorts by].
const SKILL_VIEWS = [["most", "Most used", "uses"], ["recent", "Recently used", "last"], ["family", "By family", "uses"]];
const SKILL_SORT = { sort: "uses", desc: true, text: "", view: "most" };
let skillColumns = null;
readerStorage("co-rem-skill-columns").then(saved => { if (saved) skillColumns = peopleColumnKeys(saved, SKILL_COLUMNS); });
// "3 weeks ago" is read faster than a date in a column scanned for what has gone stale; the date is one hover away.
function skillAgo(day) {
  const today = calendarDay(REM.as_of || new Date().toISOString());
  const days = Math.round((new Date(today + "T00:00:00Z") - new Date(day + "T00:00:00Z")) / 86400000);
  if (days < 2) return t(days < 1 ? "Today" : "Yesterday");
  if (days < 14) return t("{n} days ago", { n: days });
  return days < 60 ? t("{n} weeks ago", { n: Math.floor(days / 7) }) : t("{n} months ago", { n: Math.round(days / 30) });
}
function skillLastCell(u) {
  if (!u) return textCell("");
  return u.last ? el("span", { title: calendarDate(u.last), text: skillAgo(u.last) }) : el("span", { class: "unk", text: t("Never") });
}
// Times used is the skill-name match count of the usage window (docs/cli/rem.md), not runs. Its header carries the
// window, as People's "Messages · 90 days" does, so the page needs no caption about how the count is made.
const SKILL_COLUMNS = [
  { key: "name", label: "Skill", sort: d => d.r.title, cell: d => el("span", { class: "nm" }, [el("a", { href: href(d.r), text: d.r.title }), updatedMarker(d.r), skillCopies(d.r)]) },
  { key: "what", label: "What it does", sort: d => blank(d.line), cell: d => d.line ? el("span", { class: "clamp", title: d.line, text: d.line }) : textCell("") },
  { key: "family", label: "Family", sort: d => skillFamilyName(d.family), cell: d => el("span", { text: skillFamilyName(d.family) }) },
  { key: "last", label: "Last used", num: true, desc: true, sort: d => blank(d.u?.last), cell: d => skillLastCell(d.u) },
  { key: "uses", label: "Times used · {days} days", num: true, desc: true, sort: d => blank(d.u?.count),
    cell: d => d.u ? el("span", { class: d.u.count ? "mono" : "mono unk", text: String(d.u.count) }) : textCell("") }];
// Copies that may differ are a quiet fact beside the name; the skill's page compares them.
function skillCopies(r) {
  const n = r.installations?.length || 0;
  return n > 1 ? el("small", { class: "skill-copies", text: t("{n} installed copies", { n }) }) : null;
}
// A family is the name's prefix; one of fewer than three skills in all goes under Other, so a tab is worth a tap.
function skillRows(items) {
  const size = new Map();
  for (const r of items) size.set(skillFamily(r.title), (size.get(skillFamily(r.title)) || 0) + 1);
  return items.map(r => {
    const line = skillLine(r), family = size.get(skillFamily(r.title)) >= 3 ? skillFamily(r.title) : "Other";
    return { r, u: skillUsage(r), line, family, text: (r.title + " " + line + " " + r.text).toLowerCase() };
  });
}
function skillFamilyName(family) { return family === "Other" ? t("Other") : family; }
// The largest family first, Other last.
function skillFamilyCounts(rows) {
  const counts = new Map();
  for (const d of rows) counts.set(d.family, (counts.get(d.family) || 0) + 1);
  return [...counts].sort(([a, x], [b, y]) => (a === "Other") - (b === "Other") || y - x || a.localeCompare(b));
}
// The tab and the view live in the address (#c=skills&family=Lark&v=recent), so Back and a bookmark return to them.
function skillsState(rows) {
  const params = new URLSearchParams(location.hash.replace(/^#/, "")), family = params.get("family") || "";
  return { family: rows.some(d => d.family === family) ? family : "", view: SKILL_VIEWS.some(([key]) => key === params.get("v")) ? params.get("v") : "most" };
}
function skillsHref({ family, view }) {
  return "#c=skills" + (family ? "&family=" + encodeURIComponent(family) : "") + (view === "most" ? "" : "&v=" + view);
}
function skillTabs(rows, state) {
  const tab = (family, name, n) => el("a", { href: skillsHref({ ...state, family }), ...(state.family === family ? { "aria-current": "true" } : {}) },
    [name, el("span", { class: "n", text: String(n) })]);
  return el("nav", { class: "skill-tabs", "aria-label": t("Family") },
    [tab("", t("All"), rows.length), ...skillFamilyCounts(rows).map(([family, n]) => tab(family, skillFamilyName(family), n))]);
}
function skillViews(state) {
  return el("nav", { class: "skill-views", "aria-label": t("View") }, SKILL_VIEWS.map(([view, name]) =>
    el("a", { href: skillsHref({ ...state, view }), ...(state.view === view ? { "aria-current": "true" } : {}), text: t(name) })));
}
function skillGroups(shown) {
  return skillFamilyCounts(shown).flatMap(([family, n]) =>
    [{ heading: [skillFamilyName(family), el("span", { class: "n", text: String(n) })] }, ...shown.filter(d => d.family === family)]);
}
function skillsView() {
  const items = listRows("skills"), rows = skillRows(items), state = skillsState(rows);
  const days = rows.find(d => d.u)?.u.days ?? 180;
  document.getElementById("main").textContent = "";
  // Choosing a view sets the order once; a header click after that sorts inside the view.
  if (SKILL_SORT.view !== state.view) Object.assign(SKILL_SORT, { view: state.view, sort: SKILL_VIEWS.find(([key]) => key === state.view)[2], desc: true });
  skillColumns ??= peopleColumnKeys(null, SKILL_COLUMNS);
  peopleView([], { category: "skills", columns: SKILL_COLUMNS, state: SKILL_SORT, rows, tie: (a, b) => bySkillUse(a.r, b.r),
    chosen: () => skillColumns, choose: keys => { skillColumns = keys; }, storage: "co-rem-skill-columns",
    widths: { name: 22, what: 42, family: 11, last: 12, uses: 13 }, className: "skills-view", tableClass: "skill-table", findClass: "skills-find",
    translate: key => t(key, { n: items.length, days }), placeholder: "Find among {n} skills…",
    matches: (d, needle) => (!state.family || d.family === state.family) && (!needle || d.text.includes(needle)),
    visible: shown => state.view === "family" && !state.family ? skillGroups(shown) : shown,
    clear: () => { SKILL_SORT.text = ""; if (location.hash === "#c=skills") render(); else location.hash = "#c=skills"; },
    views: skillViews(state), filters: () => skillTabs(rows, state) });
}

// ---------- sessions: structure first, conversations searchable ----------
let lastSessionListHash = "#c=sessions";
const SESSION_TEXT = new Map();
const SESSION_KEYS = ["find", "project", "agent", "when", "from", "to", "person", "tag", "outcome"];
const SESSION_OUTCOMES = { done: "Done", partial: "Partial", abandoned: "Abandoned", unknown: "Unknown" };
function sessionText(r) {
  const variant = r.shown || "";
  let bucket = SESSION_TEXT.get(r.path);
  if (bucket?.[variant]?.text === r.text) return bucket[variant].value;
  const clean = text => unlabelled(text || "").replace(/^### (?:\d{4}-\d{2}-\d{2} )?\d{2}:\d{2}$/gm, "").replace(/^> ?/gm, "").replace(/\s+/g, " ").trim();
  const quoted = name => clean((r.text.split(/^## /m).find(part => part.startsWith(name + "\n")) || "").slice(name.length + 1));
  const fields = { title: clean(r.session_title || r.title), summary: ownerAsYou(clean(r.session_summary)),
    // "you" is what search and excerpts read: only the turns that carry no privacy level (#3425 follow-up).
    tags: (r.session_tags || []).join(" "), you: sessionMessages(r).length ? clean(sessionMessages(r).filter(sessionOpen).map(m => m.text).join("\n")) : quoted("What you typed"),
    agent: quoted("Final reply"), artifacts: quoted("Artifacts") };
  fields.lower = Object.values(fields).join("\n").toLowerCase();
  if (!bucket) SESSION_TEXT.set(r.path, bucket = Object.create(null));
  bucket[variant] = { text: r.text, value: fields };
  return fields;
}
function sessionTerms(query) { return [...new Set((query || "").toLowerCase().split(/\s+/).filter(Boolean))]; }
function sessionHash(state) {
  const params = new URLSearchParams({ c: "sessions" });
  for (const key of SESSION_KEYS) if (state[key]) params.set(key, state[key]);
  return "#" + params.toString();
}
function sessionActive(state) { return SESSION_KEYS.filter(key => state[key]); }
function sessionAgent(r) { return (r.session_agent || "").toLowerCase().replaceAll(" ", "-"); }
function sessionStart(when) {
  const today = calendarDay(REM.as_of);
  if (when === "month") return today.slice(0, 8) + "01";
  if (when !== "week") return today;
  const monday = new Date(today + "T00:00:00Z");
  monday.setUTCDate(monday.getUTCDate() - (monday.getUTCDay() + 6) % 7);
  return monday.toISOString().slice(0, 10);
}
function sessionMatches(r, state, terms, structure = true) {
  if (state.project && (state.project === "none" ? !!r.session_project : r.session_project !== state.project)) return false;
  if (state.agent && sessionAgent(r) !== state.agent) return false;
  if (state.person && !(byPath(state.person)?.session_mentions || []).includes(r.path)) return false;
  const from = state.from || (state.when ? sessionStart(state.when) : "");
  const to = state.to || (state.when ? calendarDay(REM.as_of) : "");
  if (from && (r.session_date || "") < from || to && (!r.session_date || r.session_date > to)) return false;
  if (structure && state.tag && !(r.session_tags || []).includes(state.tag)) return false;
  if (structure && state.outcome && r.session_outcome !== state.outcome) return false;
  return terms.every(term => sessionText(r).lower.includes(term));
}
function sessionHighlight(text, terms) {
  if (!terms.length) return esc(text);
  const lower = text.toLowerCase(), spans = [];
  for (const term of terms) {
    if (!term) continue;
    let at = lower.indexOf(term);
    while (at !== -1) { spans.push([at, at + term.length]); at = lower.indexOf(term, at + term.length); }
  }
  spans.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const span of spans) {
    const last = merged[merged.length - 1];
    if (last && span[0] <= last[1]) last[1] = Math.max(last[1], span[1]); else merged.push(span);
  }
  let at = 0, html = "";
  for (const [start, end] of merged) {
    html += esc(text.slice(at, start)) + highlight(text.slice(start, end), lower.slice(start, end));
    at = end;
  }
  return html + esc(text.slice(at));
}
function sessionPreview(text) {
  const links = [];
  return unlabelled(text || "")
    .replace(/https?:\/\/[^\s<>"'`]+/g, url => { links.push(url); return "\u0007" + (links.length - 1) + "\u0007"; })
    .replace(/([`"'])(?:\/(?!\/)|~\/|[A-Za-z]:[\\/])[^\n]*?\1/g, "")
    .replace(/(?:file:\/\/)?(?:\/(?!\/)|~\/|[A-Za-z]:[\\/])[^\s<>"'`]+/g, "")
    .replace(/(?:\.\.?\/|\b[\w.-]+\/)[^\s<>"'`]+/g, "")
    .replace(/\u0007(\d+)\u0007/g, (_, i) => links[i]).replace(/\s+/g, " ").trim();
}

function sessionExcerpt(r, terms) {
  const text = Object.fromEntries(Object.entries(sessionText(r)).map(([key, value]) => [key, sessionPreview(value)]));
  if (terms.length && !terms.some(term => text.title.toLowerCase().includes(term))) {
    for (const key of ["summary", "tags", "you", "agent", "artifacts"]) {
      const positions = terms.map(term => text[key].toLowerCase().indexOf(term)).filter(at => at >= 0);
      if (!positions.length) continue;
      const start = Math.max(0, Math.min(...positions) - 50), end = start + 160;
      return { speaker: key === "you" ? t("You:") : key === "agent" ? t("Agent:") : "", text: (start ? "…" : "") + text[key].slice(start, end) + (end < text[key].length ? "…" : "") };
    }
  }
  return { speaker: "", text: text.summary || text.agent };
}
function sessionTool(r) {
  const kind = r.session_kind || sessionAgent(r);
  return { kind, name: kind === "codex" ? "Codex" : kind === "claude-code" ? "Claude Code" : r.session_agent || t("Agent") };
}
function sessionToolMark(r) {
  const { kind } = sessionTool(r);
  // Original geometric marks: a prompt bracket and a four-point compass.
  const path = kind === "claude-code" ? '<path d="M12 3v18M3 12h18M6 6l12 12M6 18L18 6"/>'
    : '<path d="m8 5-5 7 5 7m8-14 5 7-5 7M13 8l-2 8"/>';
  return el("span", { class: "session-tool-mark " + kind, "aria-hidden": "true", html:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' + path + '</svg>' });
}
function sessionDuration(r) {
  const messages = sessionMessages(r), first = messages[0]?.time, last = r.session_ended || messages.at(-1)?.time;
  const date = stamp => !stamp ? NaN : Date.parse((stamp.length <= 5 ? r.session_date + " " + stamp : stamp).replace(" ", "T") + ":00Z");
  const minutes = Math.round((date(last) - date(first)) / 60000);
  if (!Number.isFinite(minutes) || minutes < 0 || !r.session_ended && messages.length < 2) return t("Duration not archived");
  const duration = minutes >= 60 ? Math.floor(minutes / 60) + "h " + minutes % 60 + "m" : minutes + "m";
  return r.session_ended ? duration : t("At least {duration}", { duration });
}
// Continue the session with its own agent, here (D-60: never a command to copy): the agent
// resumes its session in the folder it ran in, and the reply shows in this page.
function sessionComposer(r) {
  const box = el("div", { class: "session-composer", id: "session-continue" });
  const { kind, name } = sessionTool(r);
  if (!liveHere()) box.append(liveReaderLine("Continuing this session with its agent happens in the live reader."));
  else if (!r.session_id || !["codex", "claude-code"].includes(kind)) box.append(el("p", { class: "session-composer-note", text: t("Session id not archived") }));
  else {
    const start = el("button", { type: "button", class: "btn-line", text: t("Continue with {agent}", { agent: name }) });
    start.onclick = () => {
      OPEN_TALKS.set(r.path, talkPanel({ action: "begin", session: r.path }));
      box.replaceChildren(OPEN_TALKS.get(r.path));
    };
    box.append(OPEN_TALKS.get(r.path) || start);
  }
  return box;
}
function sessionArchivedTools(r) {
  const artifacts = sessionSection(r, "Artifacts"), notable = /; notable: (.+)/.exec(artifacts)?.[1] || "";
  const commands = r.session_commands || [...notable.matchAll(/`([^`]+)`/g)].map(match => ({ text: match[1], private: hasPrivacy(artifacts) }));
  if (!commands.length) return null;
  return el("section", { class: "session-tool-archive" }, [el("p", { text: t("Archived commands · execution order not retained") }),
    ...commands.map(command => el("details", { class: "session-tool-call" + (command.private || hasPrivacy(command.text) ? " private" : "") }, [
      el("summary", {}, [el("span", { text: "›", "aria-hidden": "true" }), el("span", { text: t("Terminal") }), el("code", { text: command.text })]),
      el("pre", {}, [el("code", { text: command.text })]), el("p", { text: t("Tool output not archived") })]))]);
}
function sessionTranscriptTurn(r, message) {
  const owner = message.role === "user", quote = sessionQuote(message.text, message.level);
  quote.sessionFullText = message.text;
  return el("section", { class: "session-turn " + (owner ? "owner-turn" : "assistant-turn") + (hasPrivacy(message.text) ? " private" : ""), id: message.id, "data-source": message.source || "" }, [
    el("div", { class: "session-turn-label" }, [owner ? null : sessionToolMark(r), el("span", { text: owner ? t("You") : sessionTool(r).name }),
      el("time", { text: message.time || t("Time not archived"), datetime: (message.time.length === 5 ? r.session_date + "T" + message.time : message.time.replace(" ", "T")) })]), quote]);
}
function sessionMissingReply() {
  return el("details", { class: "session-missing" }, [el("summary", { text: t("Assistant activity · not archived") }),
    el("p", { text: t("This archive keeps your turns and the final reply. Intermediate replies and tool results were not retained.") })]);
}
function sessionFrame(r) {
  const tool = sessionTool(r), messages = Array.isArray(r.session_messages) ? r.session_messages
    : [...sessionMessages(r).map(m => ({ ...m, role: "user" })), ...(sessionSection(r, "Final reply") ? [{ id: "session-final", role: "assistant", time: "", text: sessionUnquote(sessionSection(r, "Final reply")) }] : [])];
  const body = el("div", { class: "session-transcript", id: "original-conversation" });
  for (const message of messages) {
    if (message.role === "assistant") body.appendChild(sessionArchivedTools(r) || document.createDocumentFragment());
    body.appendChild(sessionTranscriptTurn(r, message));
    if (message.role === "user") body.appendChild(sessionMissingReply());
  }
  if (!messages.some(m => m.role === "assistant")) body.appendChild(sessionArchivedTools(r) || document.createDocumentFragment());
  if (!messages.length) body.appendChild(el("p", { class: "session-archive-note", text: t("No visible turns in this archive.") }));
  const node = el("section", { class: "session-device " + tool.kind, "aria-label": tool.name + " " + t("session transcript") });
  const find = sessionFind(node, body, route().find || route().query);
  const folder = (r.session_folder || "").split(/[\\/]/).filter(Boolean).pop() || t("No project");
  node.append(el("div", { class: "session-window-bar" }, [el("span", { class: "session-window-dots", "aria-hidden": "true", text: "● ● ●" }),
    el("strong", {}, [sessionToolMark(r), tool.name]), el("span", { class: "session-window-folder", text: folder, title: r.session_folder || "" }), el("time", { text: fmtDate(r.session_date) })]),
    el("div", { class: "session-app-heading" }, [el("span", { text: t("SESSION ARCHIVE") }), el("span", { text: sessionDuration(r) + " · " + t("{n} turns", { n: r.session_turns || 0 }) })]),
    find.node, body, sessionComposer(r), el("div", { class: "session-home-indicator", "aria-hidden": "true" }));
  return { node, find };
}

// A session row names its project, never its path: the home folder is "Home folder", others keep two segments at most.
function sessionPlace(r) {
  const project = byPath(r.session_project);
  if (project) return project.title;
  // Machine-named folders (hashes, run ids) say nothing; the readable parent names the work.
  const parts = (r.session_folder || "").split(/[\\/]/).filter(part => part && !/^[0-9a-f-]{16,}$/i.test(part));
  if (!parts.length) return t("No project");
  return /^(?:Users|home)$/.test(parts[0]) && parts.length <= 2 ? t("Home folder") : parts.slice(-2).join("/");
}
const SESSION_FOLLOW_UPS = new Map();
function sessionFollowUps(r) {
  if (!SESSION_FOLLOW_UPS.has(r.path)) SESSION_FOLLOW_UPS.set(r.path, listItems(sessionSection(r, "Follow-ups")).map(item => plainLine(item)).filter(Boolean));
  return SESSION_FOLLOW_UPS.get(r.path);
}
const SESSION_STATE_MARK = { done: "✓", partial: "◐", abandoned: "–" };
function sessionStateMark(r) {
  const outcome = r.session_summary ? r.session_outcome : "";
  return el("span", { class: "session-state " + (SESSION_STATE_MARK[outcome] ? outcome : "pending"), "aria-hidden": "true", text: SESSION_STATE_MARK[outcome] || "" });
}
function sessionRow(group, terms) {
  const r = group[0], state = route(), text = sessionText(r), todo = sessionFollowUps(r).length;
  const pending = !r.session_summary;
  const title = (pending ? t("Still being summarised") + " · " : "") + sessionPreview(text.title);
  const meta = [sessionPlace(r), t(r.session_turns === 1 ? "{n} turn" : "{n} turns", { n: r.session_turns || 0 }),
    group.length > 1 ? t("{n} sessions", { n: group.length }) : "", todo ? t(todo === 1 ? "{n} to-do" : "{n} to-dos", { n: todo }) : ""].filter(Boolean).join(" · ");
  const excerpt = terms.length ? sessionExcerpt(r, terms) : null;
  return el("li", { class: "session-row" + (pending ? " pending" : "") }, [sessionStateMark(r), el("div", { class: "session-card-content" }, [
    el("a", { class: "session-title", href: href(r) + (state.find ? "&find=" + encodeURIComponent(state.find) : ""), html: sessionHighlight(title, terms) }),
    excerpt ? el("div", { class: "session-excerpt" }, [excerpt.speaker ? el("span", { class: "session-speaker", text: excerpt.speaker + " " }) : null,
      el("span", { html: sessionHighlight(excerpt.text, terms) })]) : null,
    el("div", { class: "session-meta", text: meta })]), el("span", { class: "session-agent", text: sessionTool(r).name })]);
}
// A day's private-project sessions sit behind one curtain; nothing of them is in the DOM until shown.
function sessionCurtain(groups, terms) {
  const count = groups.reduce((n, group) => n + group.length, 0);
  const row = el("li", { class: "session-row session-curtain" });
  row.dataset.sessionDay = groups[0][0].session_date || "";
  const show = sessionButton("Show", () => row.replaceWith(...groups.map(group => {
    const revealed = sessionRow(group, terms);
    revealed.dataset.revealedSession = row.dataset.sessionDay;
    return revealed;
  })), { class: "session-curtain-show" });
  row.append(el("span", { class: "session-state lock", "aria-hidden": "true" }), el("div", { class: "session-card-content" }, [
    el("span", { class: "session-title", text: t(count === 1 ? "{n} personal session" : "{n} personal sessions", { n: count }) }),
    el("div", { class: "session-meta", text: sessionPlace(groups[0][0]) + " · " + t("Shown only on this Mac") })]), show);
  return row;
}
function sessionPrivate(r) { return !!byPath(r.session_project)?.private_project; }
// Same-titled sessions in a row are one piece of work: one row that says how many.
function sessionDayRows(records, terms) {
  const groups = [];
  for (const r of records) {
    const last = groups.at(-1);
    if (last && sessionText(last[0]).title === sessionText(r).title) last.push(r); else groups.push([r]);
  }
  const hidden = groups.filter(group => sessionPrivate(group[0]));
  const rows = groups.filter(group => !hidden.includes(group)).map(group => sessionRow(group, terms));
  if (hidden.length) rows.splice(groups.indexOf(hidden[0]), 0, sessionCurtain(hidden, terms));
  return rows;
}
function sessionDayTitle(day) {
  if (!day) return t("Undated");
  const date = new Date(day + "T00:00:00Z"), format = options => new Intl.DateTimeFormat(uiLocale(), { timeZone: "UTC", ...options }).format(date);
  const name = daysSince(day) === 0 ? t("Today") : daysSince(day) === 1 ? t("Yesterday") : format({ month: "short", day: "numeric" });
  const weekday = format({ weekday: "short" });
  return [el("span", { text: name }), el("span", { class: "session-weekday", text: weekday })];
}
const SESSION_PAGE = 60;
function sessionGroups(records, terms, limit = SESSION_PAGE) {
  const days = new Map(), content = document.createDocumentFragment();
  for (const r of records.slice(0, limit)) days.set(r.session_date || "", [...(days.get(r.session_date || "") || []), r]);
  for (const [day, rows] of days) content.append(el("h2", { class: "session-day" }, sessionDayTitle(day)), el("ul", { class: "session-rows" }, sessionDayRows(rows, terms)));
  if (records.length > limit) {
    const more = sessionButton("Earlier sessions", () => more.replaceWith(sessionGroups(records.slice(limit), terms)), { class: "session-more" });
    content.appendChild(more);
  }
  return content;
}
function sessionButton(text, action, attrs = {}) {
  const button = el("button", { type: "button", ...attrs, text: attrs["data-topic"] ? text : t(text) });
  button.onclick = action;
  return button;
}
// "You stopped here": the newest unfinished session, with its to-dos and one way back in.
function sessionStopped(records) {
  const r = records.find(r => r.session_outcome === "partial" && r.session_summary && !sessionPrivate(r));
  if (!r) return null;
  const tool = sessionTool(r), todos = sessionFollowUps(r).slice(0, 3);
  return el("section", { class: "session-stopped", "aria-label": t("You stopped here") }, [
    el("p", { class: "session-stopped-kicker" }, [el("span", { class: "chip lamp", text: t("Unfinished") }),
      [t("You stopped here"), fmtDate(r.session_date), sessionPlace(r), tool.name].join(" · ")]),
    el("h2", {}, [el("a", { href: href(r), text: sessionPreview(sessionText(r).title) })]),
    el("p", { class: "session-stopped-summary", text: ownerAsYou(plainLine(r.session_summary)) }),
    todos.length ? el("ul", { class: "session-stopped-todos" }, todos.map(item => el("li", { text: item }))) : null,
    el("div", { class: "session-stopped-actions" }, [
      el("a", { class: "btn-act play", href: href(r) + "&h=session-continue", text: t("Continue in {tool}", { tool: tool.name }) }),
      el("a", { class: "session-stopped-full", href: href(r), text: t("Full record") })])]);
}
const SESSION_TABS = [["", "", "All"], ["outcome", "partial", "Unfinished"], ["agent", "codex", "Codex"], ["agent", "claude-code", "Claude Code"]];
function sessionTabs(records, change) {
  const unfinished = records.filter(r => r.session_outcome === "partial").length;
  return el("div", { class: "session-tabs", role: "group", "aria-label": t("Show") }, SESSION_TABS.map(([key, value, name]) =>
    sessionButton(name, () => change("tab", key + "=" + value), { "data-tab": key + "=" + value, "aria-pressed": "false",
      "data-count": key === "outcome" ? String(unfinished) : "" })));
}
function sessionFilterNames(state) {
  const names = { find: t("Search") + ': “' + state.find + '”',
    project: t("Project") + ": " + (byPath(state.project)?.title || (state.project === "none" ? t("No project") : state.project)),
    agent: t("Agent") + ": " + state.agent, when: t(({ today: "Today", week: "This week", month: "This month" })[state.when] || state.when),
    from: t("From") + ": " + state.from, to: t("To") + ": " + state.to,
    person: t("Mentioning {name}", { name: byPath(state.person)?.title || state.person }),
    tag: t("Topic") + ": " + state.tag, outcome: t("Outcome") + ": " + t(SESSION_OUTCOMES[state.outcome] || state.outcome) };
  return sessionActive(state).map(key => names[key]).join(" · ");
}
function sessionResults(records, total, state, terms, change) {
  const active = sessionActive(state), results = document.createDocumentFragment();
  if (state.person) results.appendChild(sessionButton(t("Mentioning {name}", { name: byPath(state.person)?.title || state.person }) + " ×", () => change("person", ""), { class: "session-person" }));
  if (active.length) results.appendChild(el("div", { class: "session-result-line" }, [el("span", { role: "status", text: t("{n} of {m} sessions", { n: records.length, m: total }) }),
    sessionButton(t("Clear"), () => change("clear", ""))]));
  if (records.length) results.appendChild(sessionGroups(records, terms));
  else {
    const empty = emptyState("No session matches", "Clear filters →", "#c=sessions", () => change("clear", ""));
    empty.insertBefore(el("p", { text: sessionFilterNames(state) }), empty.lastChild);
    results.appendChild(empty);
  }
  return results;
}
function sessionsView() {
  const main = document.getElementById("main"), records = inCategory("sessions").sort(sessionOrder);
  if (!records.length) {
    main.replaceChildren(el("h1", { text: label("sessions") }), el("p", { class: "quiet-line", text: t(REM.status?.worker?.enabled ? "Agent sessions queued for tonight" : "Agent sessions pending — background updates off") }));
    return;
  }
  const state = Object.fromEntries(SESSION_KEYS.map(key => [key, route()[key] || ""]));
  if (state.from || state.to) state.when = "";
  const view = el("section", { class: "sessions-view r4" }), results = el("div", { id: "session-results" }), tabs = sessionTabs(records, change);
  const search = el("input", { id: "session-search", type: "search", "aria-label": t("Search sessions"), placeholder: t("Search what you typed and what the agent replied"), value: state.find });
  let timer;
  search.oninput = () => { clearTimeout(timer); timer = setTimeout(() => { if (view.isConnected) change("find", search.value); }, 120); };
  view.append(el("p", { class: "page-kicker", text: label("sessions") }),
    el("h1", { class: "page-state", text: t("{n} sessions", { n: records.length }) }),
    sessionStopped(records) || document.createDocumentFragment(), el("div", { class: "session-controls" }, [search, tabs]), results);
  main.replaceChildren(view);
  function change(key, value) {
    clearTimeout(timer);
    state.find = search.value;
    if (key === "clear") for (const name of SESSION_KEYS) state[name] = "";
    else if (key === "tab") { const [name, chosen] = value.split("="); state.agent = name === "agent" ? chosen : ""; state.outcome = name === "outcome" ? chosen : ""; }
    else state[key] = value;
    if (key === "from" || key === "to") state.when = "";
    history.replaceState(null, "", sessionHash(state));
    update();
  }
  function update() {
    lastSessionListHash = sessionHash(state);
    const terms = sessionTerms(state.find), matches = records.filter(r => sessionMatches(r, state, terms));
    if (search.value !== state.find) search.value = state.find;
    const tab = state.outcome === "partial" ? "outcome=partial" : state.agent ? "agent=" + state.agent : "=";
    for (const button of tabs.children) {
      button.setAttribute("aria-pressed", String(button.dataset.tab === tab));
      button.textContent = t(SESSION_TABS.find(([key, value]) => key + "=" + value === button.dataset.tab)[2]) + (button.dataset.count ? " " + button.dataset.count : "");
    }
    results.replaceChildren(sessionResults(matches, records.length, state, terms, change));
  }
  update();
  if (matchMedia("(min-width: 720px)").matches) search.focus({ preventScroll: true });
}

function sessionOrder(a, b) {
  return Number(b.session_status === "running") - Number(a.session_status === "running") || ((b.session_date || "") + (b.session_time || "")).localeCompare((a.session_date || "") + (a.session_time || "")) || b.path.localeCompare(a.path);
}

function sessionContextRow(r, find = "") {
  return el("li", { class: "session-context-row" }, [
    el("a", { href: href(r) + (find ? "&find=" + encodeURIComponent(find) : ""), text: sessionPreview(r.title) }),
    el("span", { class: "session-context-summary", text: sessionPreview(ownerAsYou(r.session_summary || r.session_reply || sessionText(r).agent)) }),
    el("time", { text: fmtDate(r.session_date) }),
    el("span", { class: "session-tags" }, (r.session_tags || []).slice(0, 3).map(tag => el("a", {
      href: sessionHash({ project: r.session_project, tag }), text: tag })))]);
}
function projectSessions(r) {
  const sessions = inCategory("sessions").filter(s => s.session_project === r.path).sort(sessionOrder);
  if (!sessions.length) return null;
  const counts = new Map();
  for (const s of sessions) for (const tag of new Set(s.session_tags || [])) counts.set(tag, (counts.get(tag) || 0) + 1);
  return el("section", { class: "focus-section project-sessions" }, [el("h2", { text: t("Sessions") }),
    el("ul", { class: "session-context-rows" }, sessions.slice(0, 10).map(s => sessionContextRow(s))),
    el("a", { href: sessionHash({ project: r.path }), text: t("All {n} sessions", { n: sessions.length }) }),
    el("div", { class: "session-tags" }, [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 5)
      .map(([tag, count]) => el("a", { href: sessionHash({ project: r.path, tag }), text: tag + " " + count })))]);
}
// A project's record is knowledge (#3096, the designer's review in #3085): what it is, where it stands, how
// active it has been, what was decided, who is involved and its sessions by date. What is still open is one
// line that counts it and leads to Today; nothing on a record is marked done.
function projectProse(r, name, limit) {
  const part = section(r, name);
  return part ? listItems(part.text).filter(item => !/^(?:Unknown\b|未知)/i.test(item)).slice(0, limit)
    .map(item => privateFallback(el("p", { html: inline(stripCites(item), r.path) }))) : [];
}
function projectLinked(r, category) {
  const seen = new Set();
  return (r.relations || []).map(rel => byPath(rel.path))
    .filter(page => page && page.category === category && page.path !== REM.owner && !seen.has(page.path) && seen.add(page.path));
}
function projectPart(name, title, children) {
  return el("section", { class: "project-part " + name }, [el("h2", { text: pdT(title) }), ...children]);
}
// Half a year of weeks under their months, on the scale every project shares.
function projectActivityPart(r) {
  const now = paMeta().this_week, weeks = paWeeks(pdAddDays(now, -7 * (PA_RECORD - 1)), now);
  return projectPart("project-activity", "Activity", [el("p", { text: paSentence(r) + pdT(".") }),
    el("div", { class: "project-weeks" }, [el("div", { class: "project-weeks-in" }, [paMonths(weeks), paStrip(r, weeks)])])]);
}
function projectDecided(r) {
  const pages = projectLinked(r, "decisions"), prose = pages.length ? [] : projectProse(r, "key decisions", 3);
  if (!pages.length && !prose.length) return null;
  return projectPart("project-decided", "What was decided", [
    pages.length ? el("ul", { class: "project-links" }, pages.slice(0, 6).map(page => el("li", {}, [el("a", { href: href(page), text: pageName(page) })]))) : null, ...prose,
    pages.length > 6 ? el("a", { class: "project-more", href: "#c=decisions", text: pdT("All {n} decisions", { n: pages.length }) }) : null]);
}
function projectPeople(r) {
  const people = projectLinked(r, "people");
  return people.length ? projectPart("project-people", "Who is involved", [
    el("p", {}, people.slice(0, 12).flatMap((page, i) => [i ? pdT(", ") : null, el("a", { href: href(page), text: page.title })]))]) : null;
}
// Its newest sessions by date, or, without sessions, the newest of its dated history. The rest is one link away.
function projectRecent(r) {
  const sessions = inCategory("sessions").filter(s => s.session_project === r.path).sort(sessionOrder);
  if (!sessions.length) return activityPanel(r, true, 3);
  return projectPart("project-recent", "Sessions by date", [
    el("ul", {}, sessions.slice(0, 6).map(s => el("li", {}, [el("time", { text: fmtDate(s.session_date) }), el("a", { href: href(s), text: sessionPreview(s.title) })]))),
    sessions.length > 6 ? el("a", { class: "project-more", href: sessionHash({ project: r.path }), text: t("All {n} sessions", { n: sessions.length }) }) : null]);
}
function projectTodayLine(r) {
  const n = projectTodayCount(r);
  return n ? el("p", { class: "project-today" }, [projectTodayLink(r, pdT(n === 1 ? "1 open item is in Today" : "{n} open items are in Today", { n }))]) : null;
}
function projectLead(r) {
  const what = projectProse(r, "what it is", 1), stands = projectProse(r, "where it stands", 2);
  what.forEach(p => p.classList.add("project-what"));
  return [...what, stands.length ? projectPart("project-stands", "Where it stands", stands) : null, projectActivityPart(r),
    projectDecided(r), projectPeople(r), projectRecent(r), projectTodayLine(r)].filter(Boolean);
}
// The page's first line answers "what state is it in": the board's column, its last date, a late promise in red.
function projectStateLine(r) {
  const state = projectState(r), late = projectLate(r), kinds = paActivity(r).kinds, mapped = known(r).last;
  // "Last active" is said only of something counted (a message, a session, a mail); a date the map alone gave
  // stays a mapped session, never verified activity.
  const counted = (kinds.messages || 0) + (kinds.sessions || 0) + (kinds.mail || 0) > 0;
  return el("p", { class: "project-state", "data-state": state }, [
    el("span", { class: "project-state-word" }, [el("i", { class: "pd-state-dot " + state, "aria-hidden": "true" }), pdT(PD_STATES.find(([key]) => key === state)[1])]),
    counted ? el("span", { text: pdT("Last active") + " " + fmtDate(paActivity(r).last) })
      : mapped ? el("span", { text: t("Last mapped session") + " " + fmtDate(mapped) }) : null,
    late ? el("span", { class: "red", text: pdT("{n} days late", { n: late.days }) }) : null]);
}
function sessionSection(r, name) {
  return (r.text.split(/^## /m).find(part => part.startsWith(name + "\n")) || "").slice(name.length + 1).trim();
}
function sessionMessages(r) {
  return sessionSection(r, "What you typed").split(/^### /m).filter(part => /^\d/.test(part)).map((part, i) => {
    const [stamp, ...lines] = part.split("\n");
    // A turn's level is the page's structure, its own heading ("### 09:12 [sensitive]"), never a token the owner
    // typed inside the quote: the quote stays literal, and the level curtains it whole.
    const { text: time, level } = markedText(stamp);
    return { id: "session-message-" + (i + 1), time, level, text: sessionUnquote(lines.join("\n")) };
  });
}
// The owner's words a session may show as its preview: the first turn with no privacy level, by its heading or by a
// mark in its words (#3425 follow-up). The server already chose it (session_first); a page drawn from text alone
// chooses the same way. Empty when every turn is labelled.
function sessionOpen(message) { return !message.level && !hasPrivacy(message.text || "") && !hasPrivacy(message.time || ""); }
function sessionOpenText(r) {
  if (r.session_all_hidden) return "";
  return r.session_first || sessionMessages(r).find(sessionOpen)?.text || "";
}
function sessionUnquote(text) { return text.replace(/^> ?/gm, "").replace(/^\n+|\n+$/g, ""); }
function sessionJump(id) {
  const target = document.getElementById(id);
  if (!target || target.closest(".private") && document.documentElement.classList.contains("hide-private")) return;
  for (let parent = target.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === "DETAILS") parent.open = true;
  }
  target.classList.add("session-cited");
  target.scrollIntoView({ block: "center" });
}
function sessionMessageLink(r, message, text) {
  const link = el("a", { href: href(r) + "&h=" + message.id, text });
  link.onclick = event => { event.preventDefault(); sessionJump(message.id); };
  return link;
}
// The owner's words, literal. A level from the turn's heading makes the quote a labelled passage, which applyPrivacy
// curtains at 遮敏感 and removes at 只看公开; the words inside stay exactly as typed.
function sessionQuote(text, level = "") {
  return el("blockquote", { class: "session-quote" + (level || hasPrivacy(text) ? " private" : ""), ...(level ? { "data-level": level } : {}), text });
}
function sessionFinalReply(r) {
  const text = sessionUnquote(sessionSection(r, "Final reply"));
  if (!text) return null;
  const quote = sessionQuote(text);
  if (text.length > 1200) quote.textContent = text.slice(0, 600) + "…";
  quote.sessionFullText = text;
  const out = el("section", { class: "session-final", id: "session-final" }, [el("h3", { text: t("Final reply") }), quote]);
  if (text.length > 1200) {
    const button = sessionButton("Show all", () => {
      quote.textContent = text; quote.sessionExpanded = true; button.remove();
      out.dispatchEvent(new Event("session-reply-expanded", { bubbles: true }));
    }, { class: "session-show-all", "aria-expanded": "false" });
    out.appendChild(button);
  }
  return out;
}
// Only text nodes enter the attachment's find results.
function sessionMarkText(quote, text, needle) {
  text = String(text || "").replace(/<\/?artifact-content-authored-by-others\s*\/?>/gi, "").replace(/\*\*([^*]+)\*\*/g, "$1");
  const nodes = [], lower = text.toLowerCase();
  let start = 0, at = needle ? lower.indexOf(needle) : -1;
  while (at !== -1) {
    nodes.push(document.createTextNode(text.slice(start, at)), el("mark", { text: text.slice(at, at + needle.length) }));
    start = at + needle.length; at = lower.indexOf(needle, start);
  }
  nodes.push(document.createTextNode(text.slice(start)));
  quote.replaceChildren(...nodes);
}
function sessionFind(attachment, body, initial) {
  const input = el("input", { type: "search", placeholder: t("Find in this conversation"), "aria-label": t("Find in this conversation") });
  const status = el("span", { class: "session-find-status", role: "status", "aria-live": "polite" });
  const previous = sessionButton("↑", () => move(-1), { "aria-label": t("Previous match") });
  const next = sessionButton("↓", () => move(1), { "aria-label": t("Next match") });
  previous.disabled = next.disabled = true;
  const quotes = [...body.querySelectorAll(".session-quote")];
  for (const quote of quotes) quote.sessionFullText ??= quote.textContent;
  let matches = [], current = -1;
  function move(step) {
    if (!matches.length) return;
    matches[current]?.classList.remove("current");
    current = (current + step + matches.length) % matches.length;
    matches[current].classList.add("current");
    status.textContent = t("{n} of {m}", { n: current + 1, m: matches.length });
    matches[current].scrollIntoView({ block: "center" });
  }
  function find() {
    const needle = input.value.trim().toLowerCase();
    for (const quote of quotes) {
      const full = quote.sessionFullText;
      const hidden = hasPrivacy(full) && document.documentElement.classList.contains("hide-private");
      const clipped = quote.closest(".session-final") && full.length > 1200 && !quote.sessionExpanded && !needle;
      sessionMarkText(quote, clipped ? full.slice(0, 600) + "…" : full, hidden ? "" : needle);
    }
    matches = [...body.querySelectorAll("mark")]; current = -1;
    previous.disabled = next.disabled = !matches.length;
    status.textContent = needle ? t("{n} of {m}", { n: 0, m: matches.length }) : "";
    if (matches.length) move(1);
  }
  input.oninput = find;
  input.onkeydown = event => { if (event.key === "Enter") { event.preventDefault(); move(event.shiftKey ? -1 : 1); } };
  body.addEventListener("session-reply-expanded", find);
  const bar = el("div", { class: "session-find" }, [input, status, previous, next]);
  input.value = initial || "";
  bar.refreshSessionFind = find;
  return { node: bar, run: find };
}
function sessionAttachment(r, messages) {
  const reply = sessionFinalReply(r);
  const attachment = el("details", { class: "session-attachment", id: "original-conversation" }, [el("summary", {
    text: t("Original conversation · {n} messages", { n: messages.length }) + (reply ? t(" · final reply") : "") })]);
  const outline = el("nav", { class: "session-outline", "aria-label": t("Conversation outline") }, [
    el("span", { text: t("Messages") }), el("ol", {}, messages.map(message => el("li", {}, [sessionMessageLink(r, message,
      message.time + " · " + unlabelled(message.text).replace(/\s+/g, " ").slice(0, 60))])))]);
  const body = el("div", { class: "session-messages" }, messages.map(message => el("section", { class: "session-message", id: message.id }, [
    el("h3", { text: message.time }), sessionQuote(message.text)])));
  if (reply) body.appendChild(reply);
  const find = sessionFind(attachment, body, route().find || route().query);
  attachment.append(find.node, el("div", { class: "session-conversation-layout" }, [outline, body]));
  return { node: attachment, find };
}
function sessionDecisions(r, messages) {
  const text = unlabelled(sessionSection(r, "Decisions"));
  if (!text) return null;
  return el("section", { class: "session-structure session-decisions" }, [el("h2", { text: t("Decisions") }),
    el("ul", {}, listItems(text).map(line => {
      const match = /^(.*?)\s*\((\d{2}:\d{2})\)$/.exec(line), clock = match?.[2];
      const quote = (match?.[1] || line).replace(/^[“"「]|[”"」]$/g, "");
      const message = messages.find(m => m.time.endsWith(clock) && m.text.includes(quote)) || messages.find(m => m.time.endsWith(clock));
      return el("li", {}, [el("span", { class: "session-decision-quote", text: "“" + quote + "”" }),
        message ? sessionMessageLink(r, message, clock) : null]);
    }))]);
}
function sessionArtifact(line) {
  const match = /^([^:：]+)[:：]\s*(.*)$/.exec(line);
  if (!match) return el("li", { text: line });
  const [, name, value] = match;
  if (/^Files changed \(\d+\)$/.test(name) || name === "Commands") {
    const values = name === "Commands" ? [...value.matchAll(/`([^`]+)`/g)].map(m => m[1]) : value.split(/,\s*/);
    return el("li", {}, [el("details", {}, [el("summary", { text: t(name) + (name === "Commands" ? " · " + value.split(";")[0] : "") }),
      el("ul", {}, values.map(text => el("li", {}, [el("code", { text: text.replace(/^`|`$/g, "") })])))])]);
  }
  if (name === "Pull requests") return el("li", {}, [el("span", { class: "session-artifact-label", text: t("Pull requests") }),
    ...[...value.matchAll(/https?:\/\/[^\s,<>]+/g)].map(m => el("a", { href: m[0], target: "_blank", rel: "noopener", text: m[0] }))]);
  if (name === "Commits") {
    const commit = /^`([^`]+)`\s*(.*?)(?:\s+\(([^()]*)\))?$/.exec(value);
    if (commit) return el("li", {}, [el("code", { text: commit[1] }), " " + commit[2],
      commit[3] ? el("span", { class: "session-artifact-branch", text: " · " + commit[3] }) : null]);
  }
  return el("li", {}, [el("span", { class: "session-artifact-label", text: t(name) }), el(name === "Branches" ? "code" : "span", { text: value })]);
}
function sessionArtifacts(r) {
  const text = unlabelled(sessionSection(r, "Artifacts"));
  return text ? el("section", { class: "session-structure session-artifacts" }, [el("h2", { text: t("Artifacts") }),
    el("ul", {}, listItems(text).map(sessionArtifact))]) : null;
}
function sessionNeighbours(r) {
  const sessions = inCategory("sessions").filter(s => !r.session_project || s.session_project === r.session_project).sort(sessionOrder);
  const index = sessions.findIndex(s => s.path === r.path), older = sessions[index + 1], newer = sessions[index - 1];
  return el("nav", { class: "session-neighbours", "aria-label": t("Neighbouring sessions") }, [
    older ? el("a", { href: href(older), text: "← " + t("Older") + ": " + older.title }) : el("span"),
    newer ? el("a", { href: href(newer), text: t("Newer") + ": " + newer.title + " →" }) : null]);
}
function sessionFactsLine(r) {
  const project = byPath(r.session_project), folder = r.session_folder || "";
  const line = el("div", { class: "session-facts-line" }, [
    [fmtDate(r.session_date), r.session_time, r.session_agent].filter(Boolean).join(" · ") + " · ",
    project ? el("a", { href: href(project), text: project.title }) : el("span", { text: folder.split(/[\\/]/).filter(Boolean).pop() || t("No project"), title: folder }),
    " · " + t("{n} turns", { n: r.session_turns || 0 }) + (r.session_outcome ? " · " + t(SESSION_OUTCOMES[r.session_outcome] || r.session_outcome) : "")]);
  return line;
}
function sessionDetails(r) {
  const facts = parseFacts(r), source = section(r, "sources");
  return el("details", { class: "session-details" }, [el("summary", { text: t("Details") }),
    el("dl", {}, [el("dt", { text: t("Folder") }), el("dd", {}, [el("code", { text: r.session_folder || "" })]),
      el("dt", { text: t("Session id") }), el("dd", {}, [el("code", { text: facts.get("Session")?.[0]?.value || "" })])]),
    source ? el("section", {}, [el("h3", { text: t("Sources") }), sectionBody(r, source)]) : null]);
}
function sessionRecord(r, heading) {
  const main = document.getElementById("main"), project = byPath(r.session_project), messages = sessionMessages(r);
  const attachment = sessionFrame(r);
  CITES = { from: r.path, sources: Object.fromEntries(sourceList(r).map(s => [s.n, s.text])) };
  const summary = ownerAsYou(unlabelled(r.session_summary || sessionSection(r, "Summary"))), followups = sessionSection(r, "Follow-ups");
  const page = el("article", { class: "session-page" }, [
    el("div", { class: "eyebrow" }, [el("a", { href: lastSessionListHash, text: label("sessions") }),
      project ? el("span", { class: "sep", text: "/" }) : null, project ? el("a", { href: href(project), text: project.title }) : null]),
    el("header", { class: "page-head" }, [el("h1", { text: r.title }), sessionFactsLine(r),
      // The shared tag row when the session's tags are in the vocabulary; its own session filter links otherwise.
      pageTagRow(r) || el("div", { class: "session-tags" }, (r.session_tags || []).map(tag => el("a", { class: "tag-link", href: sessionHash({ tag }), text: tag })))]),
    el("section", { class: "session-summary" }, [summary ? el("h2", { text: t("Summary") }) : null,
      el("p", { class: "lede" + (summary ? "" : " session-unsummarised"), text: summary || (sessionOpenText(r) ? t("Not summarised yet") + " — " + unlabelled(sessionOpenText(r)).replace(/\s+/g, " ").slice(0, 160) : t("This session's content is hidden")) })]),
    attachment.node,
    sessionDecisions(r, messages),
    followups ? el("section", { class: "session-structure session-followups" }, [el("h2", { text: t("Follow-ups") }),
      el("ul", {}, listItems(followups).map(text => el("li", { html: inline(text, r.path) })))]) : null,
    sessionArtifacts(r), sessionNeighbours(r), sessionDetails(r)]);
  main.replaceChildren(page);
  if (route().find || route().query) {
    attachment.node.open = true;
    requestAnimationFrame(() => { if (page.isConnected) attachment.find.run(); });
  } else if (heading) requestAnimationFrame(() => {
    const source = /^src-/.test(heading) ? citationId(r, heading.slice(4)) : heading;
    const message = r.session_messages?.find(m => m.source === source);
    sessionJump(message?.id || heading);
  });
}

