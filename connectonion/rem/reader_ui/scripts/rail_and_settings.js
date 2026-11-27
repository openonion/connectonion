// ---------- views ----------
function route() {
  const hash = typeof location !== "undefined" ? location.hash : "";
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  return { record: params.get("r"), category: params.get("c"), query: params.get("q"), related: params.get("related") || "", heading: params.get("h"),
    view: params.get("view"), project: params.get("project"), reviews: params.has("reviews"),
    ...Object.fromEntries(["find", "agent", "when", "from", "to", "person", "tag", "outcome", "src", "dir", "item"].map(key => [key, params.get(key) || ""])) };
}
function railActive() {
  const { record: r, category: c, query, view, reviews } = route();
  const kind = r && r.split("/")[0];
  // The calendar lives in Today (#3152): its old addresses light Today in the rail.
  if (c === "agenda" || view === "agenda") return "today";
  return reviews ? "reviews" : view === "graph" || c === "all" || c === "knowledge" ? "knowledge" : view || c || (r ? (ACTIVITY.has(kind) ? "activity" : kind) : (query ? "search" : "today"));
}
function scheduleState(s) {
  const state = s.state || "";
  if (/^(?:Not started|Stopped|Not scheduled here)/.test(state)) return "Background updates off";
  if (/^Running in background/.test(state)) return "Nightly updates are on";
  if (/^Background needs attention/.test(state)) return "Background needs attention";
  return state;
}
function nightlyUpdatesOff() {
  return scheduleState(REM.status || {}) === "Background updates off";
}
// Every picture is copied from a published set, never drawn by hand (owner, 2026-11-17: the phone, mail and GitHub
// pictures "are not very accurate"). Interface icons are Lucide 0.468.0 (ISC), the set the rail already used (D-132);
// keys the reader had before keep their names: project is Lucide's folder, more ellipsis, skip chevrons-right,
// agent sparkles, chat message-circle, pin map-pin, right/down chevron-right/-down, doc file-text, undo undo-2,
// ext external-link; at (new) is at-sign. phone is the handset, because the fact it marks is a number, not a device.
// Strokes come from .ic, never from here, and a Lucide rect is the same shape as a path, because the sheet owns
// every radius attribute. connectonion/_licenses/rem-reader-icons.txt lists each key's source.
const ICONS = {
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
  "message-square-reply": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="m10 7-3 3 3 3"/><path d="M17 13v-1a2 2 0 0 0-2-2H7"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  "building-2": '<path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/><path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/><path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/><path d="M10 6h4"/><path d="M10 10h4"/><path d="M10 14h4"/><path d="M10 18h4"/>',
  folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  key: '<path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4"/><path d="m21 2-9.6 9.6"/><circle cx="7.5" cy="15.5" r="5.5"/>',
  zap: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
  // Lucide draws the lid as a rect with rx="1"; it is the same lid as a path, because the sheet owns every radius attribute.
  archive: '<path d="M3 3h18a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>',
  ellipsis: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
  project: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  layers: '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z"/><path d="M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12"/><path d="M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17"/>',
  more: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  skip: '<path d="m6 17 5-5-5-5"/><path d="m13 17 5-5-5-5"/>',
  agent: '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/>',
  terminal: '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>',
  chat: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
  mail: '<path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-16a2 2 0 0 1 -2 -2v-12a2 2 0 0 1 2 -2z"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
  phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
  at: '<circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  quote: '<path d="M16 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z"/><path d="M5 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z"/>',
  pin: '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/>',
  right: '<path d="m9 18 6-6-6-6"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  activity: '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
  calendar: '<path d="M8 2v4"/><path d="M16 2v4"/><path d="M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2z"/><path d="M3 10h18"/>',
  scale: '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
  book: '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/>',
  doc: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  expand: '<path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="m21 3-7 7"/><path d="m3 21 7-7"/>',
  ext: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
  // Service marks are Simple Icons 16.34.0 (CC0), each the published path unchanged. .ic.solid fills them with the
  // page's ink, never the brand's colour. That set publishes no LinkedIn, Slack or Microsoft mark, so the reader
  // draws none: those handles are an @ with the service's name in words (HANDLE_MARKS).
  "brand-github": '<path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>',
  "brand-x": '<path d="M14.234 10.162 22.977 0h-2.072l-7.591 8.824L7.251 0H.258l9.168 13.343L.258 24H2.33l8.016-9.318L16.749 24h6.993zm-2.837 3.299-.929-1.329L3.076 1.56h3.182l5.965 8.532.929 1.329 7.754 11.09h-3.182z"/>',
  "brand-wechat": '<path d="M8.691 2.188C3.891 2.188 0 5.476 0 9.53c0 2.212 1.17 4.203 3.002 5.55a.59.59 0 0 1 .213.665l-.39 1.48c-.019.07-.048.141-.048.213 0 .163.13.295.29.295a.326.326 0 0 0 .167-.054l1.903-1.114a.864.864 0 0 1 .717-.098 10.16 10.16 0 0 0 2.837.403c.276 0 .543-.027.811-.05-.857-2.578.157-4.972 1.932-6.446 1.703-1.415 3.882-1.98 5.853-1.838-.576-3.583-4.196-6.348-8.596-6.348zM5.785 5.991c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 0 1-1.162 1.178A1.17 1.17 0 0 1 4.623 7.17c0-.651.52-1.18 1.162-1.18zm5.813 0c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 0 1-1.162 1.178 1.17 1.17 0 0 1-1.162-1.178c0-.651.52-1.18 1.162-1.18zm5.34 2.867c-1.797-.052-3.746.512-5.28 1.786-1.72 1.428-2.687 3.72-1.78 6.22.942 2.453 3.666 4.229 6.884 4.229.826 0 1.622-.12 2.361-.336a.722.722 0 0 1 .598.082l1.584.926a.272.272 0 0 0 .14.047c.134 0 .24-.111.24-.247 0-.06-.023-.12-.038-.177l-.327-1.233a.582.582 0 0 1-.023-.156.49.49 0 0 1 .201-.398C23.024 18.48 24 16.82 24 14.98c0-3.21-2.931-5.837-6.656-6.088V8.89c-.135-.01-.27-.027-.407-.03zm-2.53 3.274c.535 0 .969.44.969.982a.976.976 0 0 1-.969.983.976.976 0 0 1-.969-.983c0-.542.434-.982.97-.982zm4.844 0c.535 0 .969.44.969.982a.976.976 0 0 1-.969.983.976.976 0 0 1-.969-.983c0-.542.434-.982.969-.982z"/>',
  "brand-whatsapp": '<path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>',
  "brand-telegram": '<path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>',
  "brand-discord": '<path d="M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z"/>',
};
// A mark fills its whole 24 box where an outline icon keeps 2 units clear, so a mark is drawn in a 28 box
// to sit at the same optical size. Its class is solid, not brand: .brand is the header's REM mark. Callers name a
// picture and never say which kind it is.
function icon(name, cls = "") {
  const brand = name.startsWith("brand-");
  return el("span", { class: "icw", "aria-hidden": "true", html: '<svg class="ic' + (brand ? " solid" : "") + (cls ? " " + cls : "")
    + '" viewBox="' + (brand ? "-2 -2 28 28" : "0 0 24 24") + '">' + (ICONS[name] || "") + "</svg>" });
}
// The pictures of the places that are also record categories.
const CATEGORY_ICON = { devices: "layers", knowledge: "book", decisions: "scale", principles: "quote", agenda: "calendar", sessions: "terminal",
  opportunities: "activity", works: "doc" };
// The rail (D-132, #2953, #3091): ONE ordered list of places, each a picture with its word under it, settings and
// you at the foot. The order reads top to bottom as act, who and what, what the notebook concluded, then the raw
// material it was built from; a hairline parts the groups. The rail shows as many places as its height holds and
// only what does not fit goes under 更多 (fitRail), so 更多 is gone when everything fits. Each row is
// [key, picture, name, link, word, group]. The word is the name unless the English name is wider than the cell;
// then the name is one hover away and in the accessible name, which starts with the word you see (WCAG 2.5.3:
// saying "Orgs" finds Orgs · Organisations). The phone sheet reads data-name.
function railPlaces(active) {
  const category = (c, picture, group, word) => [c, picture, label(c), "#c=" + c, word, group];
  return [["today", "sun", t("Today"), "#", undefined, 0],
    ["open", "message-square-reply", t("Waiting on you"), "#view=open", t("Waiting on you, in the rail"), 0],
    category("people", "users", 1), category("orgs", "building-2", 1, t("Organisations, in the rail")), category("devices", CATEGORY_ICON.devices, 1), category("projects", "folder", 1),
    category("keys", "key", 1),
    // One Knowledge place, not Knowledge plus All records (#2996): the owner could not tell them apart. It holds
    // the wiki's entries and the graph All records drew; every record that list held is in its own category.
    category("knowledge", "book", 2), category("decisions", CATEGORY_ICON.decisions, 2), category("principles", CATEGORY_ICON.principles, 2),
    category("skills", "zap", 2),
    // Raw material last (the owner, #3091), then the places that are the first to fold in a lower window.
    category("sessions", CATEGORY_ICON.sessions, 3, t("Agent sessions, in the rail")),
    category("opportunities", CATEGORY_ICON.opportunities, 3, t("Opportunities, in the rail")), category("works", CATEGORY_ICON.works, 3),
    ["changes", "activity", t("Memory changes"), "#view=changes", t("Memory changes, in the rail"), 3]].filter(([key]) => railHas(key, active));
}
// One rule, the one 更多 always had: the eight places every notebook has, and Memory changes, always show; a
// record category that came later (Decisions, Principles, Agent sessions, Opportunities, Works) shows once it
// holds a page, or while you are on it. Sessions' pages arrive with the details, so it shows until they are in.
const RAIL_FILLED = ["devices", "decisions", "principles", "sessions", "opportunities", "works"];
function railHas(key, active) {
  if (!RAIL_FILLED.includes(key)) return true;
  return memoryCategories().includes(key) && ((!detailReady && key === "sessions") || inCategory(key).length > 0 || active === key);
}
function railCell(tag, attrs, picture, name, word = name, badge = null) {
  const spoken = name.startsWith(word) ? name : word + " · " + name;
  return el(tag, { ...attrs, "aria-label": spoken, "data-name": name, ...(word === name ? {} : { title: name }) },
    [icon(picture), el("span", { class: "w", "aria-hidden": "true", text: word }), badge]);
}
// 更多 holds the places the rail had no room for, in the rail's order; with none it is not there at all.
function railMore(rest, active) {
  const current = key => active === key ? { "aria-current": "page" } : {};
  const menu = el("div", { class: "menu rail-more", id: "rail-more", hidden: "" },
    rest.map(([key, picture, name, link]) => el("a", { href: link, class: "mi" + (active === key ? " active" : ""), ...current(key) }, [icon(picture), el("span", { text: name })])));
  const on = rest.some(([key]) => key === active);
  const button = railCell("button", { type: "button", class: "nav more" + (on ? " active" : ""), "aria-expanded": "false", "aria-controls": "rail-more",
    ...(rest.length ? {} : { hidden: "" }) }, "ellipsis", t("More"));
  button.onclick = event => {
    event.stopPropagation();
    menu.hidden = !menu.hidden;
    button.setAttribute("aria-expanded", String(!menu.hidden));
    if (!menu.hidden) placeBeside(menu, button);
  };
  return [button, menu];
}
// 更多 opens from where its button is now: its foot level with the button's, growing upward, and never above
// the window's top edge; its height is capped by the window in CSS.
function placeBeside(menu, button) {
  const foot = innerHeight - button.getBoundingClientRect().bottom;
  menu.style.bottom = Math.max(8, Math.min(foot, innerHeight - 8 - menu.offsetHeight)) + "px";
}
// The phone's sheet lists every place, so nothing folds there; on a desktop the places are too tall when they
// and 更多 need more than the rail has between the mark and Settings.
function railOverflows(nav) {
  if (matchMedia("(max-width: 640px)").matches) return false;
  return nav.offsetHeight > nav.parentNode.clientHeight - document.getElementById("rail-end").offsetHeight - 4;
}
// The height rule (#3091): show every place; while they do not fit, fold the last one shown under 更多.
let railDrawn = { places: [], active: "" };
function fitRail() {
  const nav = document.getElementById("nav"), { places, active } = railDrawn;
  const cells = [...nav.children].slice(0, places.length);
  const fold = shown => {
    cells.forEach((cell, i) => { cell.hidden = i >= shown; });
    nav.replaceChildren(...cells, ...railMore(places.slice(shown), active));
  };
  let shown = places.length;
  for (fold(shown); shown && railOverflows(nav);) fold(--shown);
}
function renderRail(active) {
  const nav = document.getElementById("nav"), places = railPlaces(active);
  const mine = threadCounts().mine;
  nav.replaceChildren(...places.map(([key, picture, name, link, word, group], i) =>
    railCell("a", { href: link, class: "nav" + (active === key ? " active" : "") + (i && group !== places[i - 1][5] ? " group" : ""),
      ...(active === key ? { "aria-current": "page" } : {}) }, picture, name, word,
      key === "open" && mine ? el("span", { class: "n waiting", text: String(mine) }) : null)));
  railDrawn = { places, active };
  fitRail();
  renderRailEnd(active);
  renderTabbar(active);
  renderLangToggle();
  renderPrivacyControl();
  renderDisplayMenu();
  renderSettings();
  const ownerPage = byPath(REM.owner);
  document.getElementById("brand-sub").textContent = ownerPage ? t("{name}'s memory", { name: ownerPage.title.split(/\s+/)[0] }) : (REM.root || "").split("/").filter(Boolean).slice(-1).join("");
}
function renderRailEnd(active) {
  const end = document.getElementById("rail-end"), owner = REM.owner && byPath(REM.owner);
  const settings = railCell("button", { type: "button", class: "nav settings-open", "aria-controls": "settings" }, "settings", t("Settings"));
  settings.onclick = openSettings;
  // Your face is its own picture and has no word under it, so its name shows beside it on hover and on keyboard
  // focus; fixed, so a rail that scrolls does not clip it.
  const you = owner && t("You") + " · " + owner.title;
  const link = owner && el("a", { href: href(owner), class: "nav you" + (route().record === owner.path ? " active" : ""), "aria-label": you, "data-name": you },
    [face(owner.title, "s"), el("span", { class: "you-name", "aria-hidden": "true", text: you })]);
  // Placed from the face when it shows, as 更多 is from its button (placeBeside).
  if (link) link.onfocus = link.onmouseenter = () => { const box = link.getBoundingClientRect(); link.lastChild.style.top = box.top + box.height / 2 + "px"; };
  end.replaceChildren(settings, link);
}
// Phone (D-123): the rail and the ⌘K bar give way to a floating tab bar: 今天 · 等你 · 人物 · 搜索 · 更多.
function renderTabbar(active) {
  const bar = document.getElementById("tabbar"), toggle = bar.querySelector(".nav-toggle");
  const tab = (key, iconName, title, link, badge) => el("a", { href: link, class: "tab" + (active === key ? " active" : "") }, [icon(iconName), badge, el("span", { text: title })]);
  const search = el("button", { type: "button", class: "tab tab-search" }, [icon("search"), el("span", { text: t("Search") })]);
  search.onclick = () => { document.body.classList.add("searching"); document.getElementById("q").focus(); };
  bar.setAttribute("aria-label", t("Tabs"));
  toggle.replaceChildren(icon("ellipsis"), el("span", { text: t("More") }));
  toggle.classList.add("tab");
  const mine = threadCounts().mine;
  bar.replaceChildren(tab("today", "sun", t("Today"), "#"), tab("open", "message-square-reply", t("Waiting"), "#view=open", mine ? el("span", { class: "n", text: String(mine) }) : null),
    tab("people", "users", label("people"), "#c=people"), search, toggle);
}
function openSettings() {
  askTranslateStatus();
  const sheet = document.getElementById("settings");
  if (!sheet.open) sheet.showModal();
}
// Settings (D-123): one sheet for language, theme, motion, labelled passages, the notebook's languages,
// REM's state and the release. #rendered-at stays in the page so a failed rebuild can say so.
function renderSettings() {
  const s = REM.status || {}, foot = document.getElementById("foot"), current = document.documentElement.dataset.theme || "auto";
  document.getElementById("settings-title").textContent = t("Settings");
  const close = document.querySelector("#settings .settings-close");
  close.replaceChildren(icon("x"));
  close.setAttribute("aria-label", t("Close"));
  close.onclick = () => document.getElementById("settings").close();
  const themeSwitch = el("div", { class: "theme-switch n3-seg", role: "radiogroup", "aria-label": t("Theme") });
  for (const mode of ["auto", "light", "dark"]) {
    const btn = el("button", { class: "theme-btn" + (current === mode ? " active" : ""), type: "button", role: "radio",
      "aria-checked": String(current === mode), text: t(mode[0].toUpperCase() + mode.slice(1)), title: t(mode + " theme") });
    btn.onclick = () => setTheme(mode);
    themeSwitch.appendChild(btn);
  }
  const currentSkin = document.documentElement.dataset.skin || "porcelain";
  const skinSwitch = el("div", { class: "skin-switch theme-switch n3-seg", role: "radiogroup", "aria-label": t("Skin") });
  for (const [skinKey, skinName] of REM_SKINS) {
    const btn = el("button", { class: "theme-btn" + (currentSkin === skinKey ? " active" : ""), type: "button", role: "radio",
      "aria-checked": String(currentSkin === skinKey), text: t(skinName), title: t(skinName + " skin") });
    btn.onclick = () => setSkin(skinKey);
    skinSwitch.appendChild(btn);
  }
  const languageSwitch = el("div", { class: "language-switch n3-seg", role: "group", "aria-label": t("Interface language") });
  for (const [tag, name] of [["en", "EN"], ["zh", "中文"]]) {
    const button = el("button", { type: "button", class: "theme-btn" + (uiLanguage === tag ? " active" : ""),
      "aria-pressed": String(uiLanguage === tag), lang: tag, text: name });
    button.onclick = () => setInterfaceLanguage(tag);
    languageSwitch.appendChild(button);
  }
  const calm = document.documentElement.classList.contains("calm");
  const motion = el("button", { id: "calm-toggle", class: "switch", type: "button", role: "switch", "aria-checked": String(calm), "aria-label": t("Reduce motion") });
  motion.onclick = toggleCalm;
  const asOf = calendarDay(REM.as_of) === calendarDay(new Date().toISOString()) ? fmtTime(REM.as_of).split(" · ").pop() : fmtTime(REM.as_of);
  const words = remStateWords(s);
  const translating = translateAll();
  const row = (title, control, note) => el("div", { class: "set-row" }, [el("div", {}, [el("div", { class: "set-k", text: t(title) }), note ? el("div", { class: "set-note", text: note }) : null]), control]);
  foot.replaceChildren(
    row("Interface language", languageSwitch), row("Skin", skinSwitch), row("Theme", themeSwitch), row("Reduce motion", motion),
    // replaceChildren writes a null as the word "null": the rows only the live page has are left out instead.
    notebookLanguages(), ...[translating && row("Translate pages", translating), ignoredSendersList()].filter(Boolean),
    el("div", { class: "set-rem" }, [icon("moon"), el("span", { class: "set-state", text: words })]),
    el("div", { class: "memory-legend" }, [el("span", { class: "memory-legend-dot", "aria-hidden": "true", text: "●" }), " " + t("updated last night") + "  ",
      el("span", { class: "uncertain-marker", "aria-hidden": "true", text: "◌" }), t("not confirmed by sources")]),
    el("div", { class: "foot-line" }, [el("span", { class: "foot-facts" }, [REM.version ? el("span", { class: "version", text: "co " + REM.version }) : null,
      el("span", { class: "as-of", id: "rendered-at", text: t("Updated") + " " + asOf })]), shortcutsLink()]));
  const state = document.getElementById("rem-state");
  state.replaceChildren(icon("moon"));
  state.setAttribute("aria-label", t("REM status") + " · " + words);
  state.classList.toggle("off", nightlyUpdatesOff());
  state.onclick = openSettings;
}
// Where an ignored sender is let back in: a quiet list, each with a worded button. Only the live page has one.
function ignoredSendersList() {
  const found = Object.entries(REM.ignored_senders || {});
  if (!found.length || !liveHere()) return null;
  return el("div", { class: "set-ignored" }, [el("div", { class: "set-k", text: t("Ignored senders") }),
    el("div", { class: "set-note", text: t("Their mail stays out of Today and gets no draft.") }),
    el("ul", {}, found.map(([address, day]) => {
      const back = el("button", { type: "button", class: "btn-quiet", text: t("Show again") });
      back.onclick = async () => {
        back.disabled = true;
        if (await saveIgnoredSender(address, false)) return;
        back.disabled = false;
        back.textContent = t("Not saved") + " · " + t("Try again");
      };
      return el("li", {}, [el("span", { text: shownAddress(address) }), el("span", { class: "set-note", text: t("Ignored {date}", { date: threadDate(day) }) }), back]);
    }))]);
}
// REM's state in words, never a command (D-60): off, needs attention, or when the next pass runs.
function remStateWords(s) {
  if (nightlyUpdatesOff()) return t("Nightly updates are off.");
  return /^Background needs attention/.test(s.state || "") ? t(scheduleState(s)).replace(/`/g, "")
    : s.next_run ? t("Next pass") + " " + fmtTime(s.next_run) : t(scheduleState(s) || "No pass scheduled").replace(/`/g, "");
}
function shortcutsLink() {
  const button = el("button", { type: "button", class: "btn-quiet shortcuts-open", text: t("Keyboard shortcuts") });
  button.onclick = () => { document.getElementById("settings").close(); openShortcuts(); };
  return button;
}
function toggleCalm() {
  const calm = document.documentElement.classList.toggle("calm");
  readerStorage("co-rem-calm", calm ? "calm" : "");
  renderSettings();
}

// One page as one row: its name, what it is to you, what is open, when.
function row(r, opts) {
  const k = known(r);
  const meta = (opts && opts.kind) ? singular(r.category) : r.category === "people" ? company(r) : "";
  const li = el("li", {}, [
    el("div", { class: "t" }, [
      el("span", {}, [el("a", { href: href(r), text: pageName(r) }), updatedMarker(r), meta ? el("span", { class: "meta", text: meta }) : null,
        r.category === "people" && restingFriends().has(r.path) ? el("span", { class: "meta", text: t("No chats yet") }) : null, statusPill(r)]),
      el("span", { class: "when", text: shortDate(k.last) })])]);
  // A page's Tags line is shown by its tag row, never as its summary (#3140: tag-page members read "Tags: pilot").
  const rawBase = /^\s*(?:\*\*)?(?:Tags|标签)(?:\*\*)?\s*[:：]/i.test(k.summary || "") ? "" : k.summary;
  const raw = r.category === "orgs" && typeof stripStaleOrgPeopleCount === "function" ? stripStaleOrgPeopleCount(rawBase) : rawBase;
  const summary = STATEMENT_CATEGORIES.includes(r.category) ? statementLead(summaryLine(raw)) : summaryLine(raw);
  const lead = summary.length > 220 ? summary.slice(0, 217) + "…" : summary;
  if (lead) li.appendChild(rowLine("hit", raw, lead, r.path));
  const open = threads(r).items[0];
  if (open) li.appendChild(el("div", { class: "hit open" }, [el("span", { class: "k", text: t(DIRECTION_LABEL[open.dir]) }), rowLine("", open.text, displayLine(open.text), r.path, "span")]));
  const u = r.category === "skills" ? skillUsage(r) : null;
  if (u && (u.count || !opts?.hideZeroUsage)) li.appendChild(el("div", { class: "meta usage" }, [t("{n} uses", { n: u.count }) + (u.last ? t(" · last {last}", { last: shortDate(u.last) }) : "")]));
  if (r.installations && r.installations.length > 1) li.appendChild(el("div", { class: "hit ui", text: t("{n} installed copies — open to compare sources", { n: r.installations.length }) }));
  return li;
}
// A list row's line: plain words, unless the line carries a privacy label. Then it goes through inline(), as on the
// page, so the level covers or removes its passage (#2840: no sensitive fact legible at the default, in any list).
function rowLine(cls, raw, plain, from, tag = "div") {
  const attrs = cls ? { class: cls } : {};
  return /[\[［](?:personal|sensitive)[\]］]/i.test(raw || "") ? el(tag, { ...attrs, html: inline(raw, from) }) : el(tag, { ...attrs, text: plain });
}
// A decision's lead is what was decided (#3159): not "这项选择作于 2026-11-08 的 10:20，所在会话开始于…", and a date reads once,
// in the reader's words, never as an ISO timestamp.
function statementLead(text) {
  const when = /(?:^|[，,。.;；]\s*)(?:这项(?:选择|决定)(?:作于|做于|是在|发生在)|所在会话开始于|This (?:choice|decision) was (?:made|taken)|The session (?:began|started))[^，,。.;；]*[，,。.;；]?/gi;
  const raw = String(text || "").replace(when, " ");
  const locale = /\p{Script=Han}/u.test(raw) ? "zh-CN" : "en-US";
  const iso = /\b(\d{4}-\d{2}-\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?(?:\s*的\s*\d{1,2}:\d{2})?/g;
  return raw.replace(iso, (_, day) => calendarDate(day, locale)).replace(/^[\s，,。.;；]+/, "").replace(/\s*[:：]\s*$/, "").replace(/\s{2,}/g, " ").trim();
}
function alsoOn(records = []) {
  if (!records.length) return null;
  return el("div", { class: "also-on" }, [t("Also on "), ...records.flatMap((r, i) =>
    [i ? ", " : "", el("a", { href: href(r), text: pageName(r) })])]);
}
function threadWho(r) {
  return r.path === REM.owner ? t("Your page") : r.title;
}
// #3158: a row is one line to read at a glance: dates in the reader's words, a long quote one level down (原话,
// one click), the sources on hover. The quote is kept, never cut.
function rowWords(text) {
  const quote = /\s*[:：—–-]?\s*[“"]([^”"]{24,})[”"](\.?)/.exec(text);
  const after = quote ? text.slice(quote.index + quote[0].length) : "";
  const joiner = quote && /^\s+[A-Z\p{Script=Han}]/u.test(after) ? "." : "";
  const rawLead = quote ? text.slice(0, quote.index) + joiner + after : text;
  const locale = /\p{Script=Han}/u.test(rawLead) ? "zh-CN" : uiLocale();
  const lead = rawLead
    .replace(/\b(\d{4}-\d{2}-\d{2})\b/g, day => calendarDate(day, locale))
    .replace(/\s*[,，]?\s*[:：—–-]+\s*\./g, ".")
    .replace(/,\./g, ".")
    .replace(/\s*[,，:：—–-]\s*$/, "")
    .replace(/\s{2,}/g, " ")
    .trim();
  const q = quote ? quote[1].trim() : "";
  return { lead: lead || q, quote: lead ? q : "" };
}
function threadRow(r, thread, withPage, also = [], grouped = false, strip = false) {
  const cites = (thread.text.match(/\[W?\d{1,3}\]/g) || []).join(" ");
  const { lead, quote } = rowWords(withoutDateClutter(thread.text, thread));
  const text = lead + " " + cites;
  return el("li", { class: "thread " + thread.dir + (grouped ? " grouped" : "") }, [
    grouped ? null : el("span", { class: "dir", text: t(DIRECTION_LABEL[thread.dir]) }),
    el("div", {}, [el("div", { class: "what", html: inline(text, r.path) }),
      withPage ? el("div", { class: "who" }, [el("a", { href: href(r), text: threadWho(r) }), r.path === REM.owner ? "" : " · " + singular(r.category)]) : null,
      quote ? el("details", { class: "row-quote" }, [el("summary", { text: t("Their words") }), el("q", { text: quote })]) : null,
      withPage ? alsoOn(also) : null, threadActions({ r, t: thread, also }, !withPage, strip), draftNote(threadDraft({ r, t: thread, also }))]),
    // A stale promise keeps its date but not the red (staleEntry): it is asked about, not burning.
    el("span", { class: "when" + (thread.due && thread.due < calendarDay(REM.as_of) && !staleEntry({ r, t: thread }) ? " overdue" : (!thread.due && daysSince(thread.since) === 0) ? " today" : ""), title: (thread.since ? t("since ") + threadDate(thread.since) : "") + (thread.due ? t(" · due ") + threadDate(thread.due) : "") }, [threadAge(thread), blockerTag(thread)])]);
}

function emptyLine(thread) {
  const calm = thread.calm ? withoutDateClutter(thread.calm) : "";
  return el("p", { class: "empty-line", text: !calm || /^Nothing\.?$/i.test(calm) ? t("Nothing open.") : calm });
}
function emptyState(lead, action = "Explore memory →", href = "#view=graph", clear = null) {
  const link = el("a", { href, text: t(action) });
  if (clear) link.onclick = event => { event.preventDefault(); clear(link); };
  return el("div", { class: "empty" }, [el("span", { class: "lead", text: t(lead) }), link]);
}
function sectionHead(title, note) {
  title = t(title);
  return el("h2", { class: "section" }, [el("span", { text: title }), note ? el("span", { class: "n" }, [t(note)]) : null]);
}
function capFirst(text) {
  const word = text.match(/^\p{L}+(?=\s|$)/u)?.[0];
  return word && word === word.toLowerCase() ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}
function newestStanding(r) {
  if (r.category !== "projects" || r.path === REM.owner) return "";
  const lines = (section(r, "where it stands")?.text || "").split("\n")
    .map(line => /^\s*-\s+(\d{4}-\d{2}-\d{2})\s*[:：—–-]\s*(.+)/.exec(line))
    .filter(line => line && !/^Unknown\b/i.test(line[2].trim()));
  lines.sort((a, b) => b[1].localeCompare(a[1]));
  return lines[0]?.[2] || "";
}
function memoryStatement(r) {
  const insight = section(r, "insight");
  const lines = insight ? listItems(insight.text) : [];
  // Lead project pages with the current finding; the full note preserves patterns.
  const preferred = r.path === REM.owner ? ["Changed", "Now"]
    : r.category === "projects" ? ["Now", "At stake", "Changed", "Pattern"] : ["Now", "Changed"];
  const line = preferred.map(kind => lines.find(item => new RegExp("^" + kind + "[:：]", "i").test(item))).find(Boolean)
    || lines.find(item => /^At stake[:：]/i.test(item)) || lines[0];
  const current = section(r, "where it stands");
  const statement = newestStanding(r) || (line ? line.replace(/^(?:Changed|Now|At stake|Pattern|现在|变化|利害|模式)[:：]\s*/i, "") : current?.text || known(r).summary);
  const first = statement.split("\n").find(line => plainLine(line, true)) || "";
  return plainLine(capFirst(listItems(first)[0] || ""), true);
}
function memoryConnection(records) {
  const visible = new Set(listedRecords().map(r => r.path));
  for (const r of records) {
    for (const match of r.text.matchAll(/\[[^\]]+\]\(([^)]+\.md)\)/g)) {
      const other = byPath(resolve(r.path, match[1]));
      if (!other || other.path === r.path || !visible.has(other.path)) continue;
      return el("div", { class: "memory-connection" }, [
        el("span", { class: "label", text: t("Related pages") }),
        el("a", { href: href(r), text: r.title }),
        el("span", { class: "relation", "aria-hidden": "true", text: "↔" }),
        el("a", { href: href(other), text: other.title }),
        el("span", { class: "basis", text: t("Linked in {name}'s page", { name: r.title }) })]);
    }
  }
  return null;
}
// A record page not yet in the reader's language shows its original quietly (D-103). The owner read the old
// 原文 chip above every name as jargon (sprint 15): a page simply in English with no translation on its way says
// nothing, and one on its way says so in words, one meta-size line under the header, by the body it describes.
// Opening the page only moves it up the nightly queue (translate.request); nothing translates it while it is
// open, so the line never says "translating". The title says what happens next.
function translationLine(r) {
  if (uiLanguage === "en" || (uiLanguage === "zh" ? hasChinese(r) : r.translations?.[uiLanguage]) || r.written_in?.toLowerCase().split("-")[0] === uiLanguage) return null;
  // Only when one can arrive: queued from this live page, or a nightly target with background updates on.
  const queued = translationQueued(r), nightly = REM.status?.worker?.enabled && REM.status?.translation_coverage?.[uiLanguage]?.requested;
  if (!queued && !nightly) return null;
  const go = translateAll();
  return el("p", { class: "translation-line", text: t("Not translated yet — showing the original"),
    title: t(REM.status?.worker?.enabled ? "Queued for the next translation pass" : "Translation pending — background updates off") }, go ? [go] : undefined);
}
// A current Chinese version of the page in any region: a zh-TW or zh-CN cache is read as 中文 too.
function hasChinese(r) {
  return Object.keys(r?.translations || {}).some(tag => /^zh(?:-|$)/i.test(tag));
}
function originalMark(lead = false) {
  return el("span", { class: "lang-status" + (lead ? " lead" : ""), text: t("Original"), title: t("No Chinese translation yet; showing original") });
}
// Today's and Maybe over's rows carry the page header's 原文 when their page has no current Chinese version
// (what translationLine reads), first, so a closed row's ellipsis never cuts it off. A row of Chinese words
// keeps no mark even then: names, codes and English terms inside it ("跟进 Jordan Lee 的 Q3 pricing proposal")
// would outvote the Han characters in a script count, and the row is already in the reader's language.
function rowMark(words, r) {
  if (uiLanguage !== "zh" || hasChinese(r) || /[\u4e00-\u9fff]{2}/.test(words)) return null;
  return originalMark(true);
}
function wordsLine(name, words, r, after, attrs = {}) {
  const mark = rowMark(words, r);
  return mark ? el("p", { class: name, ...attrs }, [mark, words, ...after]) : el("p", { class: name, text: words, ...attrs }, after);
}
// The language a text is written in, by script, as languages.language_of decides it: Han counts per
// character, other scripts per word, kana outrank shared Han, and under three it is too short to say.
function textLanguage(text) {
  const SCRIPT_WORDS = { ja: /[\u3040-\u30ff]/g, ko: /[\uac00-\ud7af]/g, zh: /[\u4e00-\u9fff]/g, ru: /[\u0400-\u04ff]+/g, ar: /[\u0600-\u06ff]+/g, en: /[A-Za-z]+/g };
  const words = Object.fromEntries(Object.entries(SCRIPT_WORDS).map(([tag, pattern]) => [tag, (String(text || "").match(pattern) || []).length]));
  if (Object.values(words).reduce((sum, n) => sum + n, 0) < 3) return null;
  if (words.ja) { words.ja += words.zh; delete words.zh; }
  return Object.entries(words).reduce((best, entry) => entry[1] > best[1] ? entry : best)[0];
}
// The draft's gist is a summary, not a translation, and the writer may miss the owner's language:
// the title names its language whenever that is not the reader's, so a Chinese-side label never sits over English.
function gistTitle(gist) {
  // A run of Han is Chinese however many English names sit in it (rowMark says why).
  const language = /[\u4e00-\u9fff]{2}/.test(gist) ? "zh" : textLanguage(gist);
  return t("Gist") + (language && language !== uiLanguage ? " · " + nativeName(language) : "");
}
function claimValue(claim, r, after, compact = false) {
  let value = after ? claim.after : claim.before, original = uiLanguage !== "en";
  if (after && original && r.translations?.[uiLanguage]
      && plainLine(factText({ ...r, readLanguage: "" }, claim.field)) === plainLine(claim.after)) {
    const translated = factText({ ...r, readLanguage: uiLanguage }, claim.field);
    if (translated) { value = translated; original = false; }
  }
  // The 原文 mark stays outside the strike-through: it labels the language, not the old value.
  value = localDates(compact ? plainLine(value) : value);  // the reader's dates, never 2026-11-18T14:00:00Z
  return el("span", {}, [el(after ? "span" : "del", { text: value }), original ? originalMark() : null]);
}
function changeCard(claim) {
  const r = byPath(claim.record);
  if (!r) return null;
  const card = el("article", { class: "claim-card" }, [
    el("span", { class: "claim-kind", text: claim.kind === "newly recorded" ? t("Newly recorded · supported") : t("Revised in memory · supported") }),
    el("h3", {}, [el("a", { href: href(r), text: r.title }), " / " + t(claim.field)]),
    claim.before ? el("p", { class: "before" }, [t("Before: "), claimValue(claim, r, false)]) : null,
    el("p", { class: "after" }, [t("Now: "), claimValue(claim, r, true)]),
    el("a", { href: href(r) + "&h=src-" + (claim.sources || [""])[0].toLowerCase(),
      text: t("Open the page and source →") })]);
  return card;
}
function firstMapBrief() {
  const counts = Object.values(REM.counts || {});
  const mapped = counts.reduce((n, row) => n + (row.mapped || 0), 0);
  const written = counts.reduce((n, row) => n + (row.written || 0), 0);
  if (lastPass() || !mapped || written) return null;
  const people = inCategory("people").length;
  const { held, service } = peopleExclusions();
  const preview = el("span", { text: t(REM.status?.worker?.enabled ? "Unwritten pages queued for tonight" : "Unwritten pages pending — background updates off") });
  const brief = el("section", { class: "morning first-map", "aria-label": t("Source map and next step") }, [
    el("div", { class: "morning-top" }, [el("div", {}, [
      el("span", { class: "morning-kicker", text: t("Source map") }),
      el("h2", { text: t("{n} records mapped", { n: mapped }) })]),
      el("span", { class: "morning-time", text: t("0 memories written") })]),
    el("p", { class: "memory-empty", text: t("People, projects, organisations and skills are ready to explore. These are metadata starting points, not investigated findings.") }),
    el("div", { class: "first-map-actions" }, [el("a", { href: "#c=people", text: t("Browse {n} people →", { n: people }) }), preview])]);
  if (held || service) brief.appendChild(el("p", { class: "first-map-held", text:
    (held ? t("{n} possible contacts are held for review and excluded from the People count.", { n: held }) : "") +
    (service ? (held ? " " : "") + t("{n} service or institutional senders are excluded from People.", { n: service }) : "") }));
  return brief;
}
function overnightChange(claim) {
  const r = byPath(claim.record);
  if (!r) return null;
  return el("li", { class: "overnight-change" }, [el("a", { href: href(r), text: r.title }),
    el("span", { class: "meta", text: " · " + t(claim.field) }),
    el("span", { class: "claim-values" }, [claim.before ? claimValue(claim, r, false, true) : null,
      claim.before ? " → " : "", claimValue(claim, r, true, true)]),
    el("a", { href: href(r) + "&h=src-" + (claim.sources || [""])[0].toLowerCase(), text: t("source"), title: t("Supported by the cited source") })]);
}
// What REM did overnight, one line per kind of work, each naming whom it was for.
const NIGHT_DONE = [["prepared", "1 thing has a reply drafted", "{n} things have a reply drafted"],
  ["task", "Prepared 1 task", "Prepared {n} tasks"], ["no_reply", "1 thing needs no reply", "{n} things need no reply"],
  ["already_handled", "1 thing was already handled", "{n} things were already handled"],
  ["could_not_prepare", "Could not draft for 1 person", "Could not draft for {n} people"]];
// One tally of what REM did with the open items it went through. The side line's number, the sheet's lines
// and the Overnight section's sentence all read it, so they cannot disagree: on real data the line gave a count
// while the section below spoke only of reworded pages. Every kind counts items, so the lines add up to the
// number; the people are named beside them. What REM could not draft is listed but is not "handled".
function nightTally() {
  const outcomes = [...new Map((REM.night_outcomes || []).map(o => [o.key, o])).values()].filter(o => byPath(o.record) && !byPath(o.record).private);
  const kinds = NIGHT_DONE.map(([kind, one, many]) => {
    const items = outcomes.filter(o => o.kind === kind), records = [...new Set(items.map(o => o.record))].filter(path => path !== REM.owner).map(byPath);
    return { kind, records, text: n => t(n === 1 ? one : many, { n }), n: kind === "could_not_prepare" ? records.length : items.length };
  });
  // Replies REM sent itself after the 10-minute hold (direct send).
  const sent = [...new Set((REM.sent_by_rem || []).map(row => row.title).filter(Boolean))];
  const n = kinds.filter(kind => kind.kind !== "could_not_prepare").reduce((sum, kind) => sum + kind.n, 0) + sent.length;
  return { kinds, sent, n };
}
function nightDone(tally = nightTally()) {
  const rows = tally.kinds.map(({ kind, records, text, n }) => n ? el("li", { "data-kind": kind }, [el("b", { text: text(n) }), nightNames(records)]) : null).filter(Boolean);
  const sent = tally.sent;
  if (sent.length) rows.unshift(el("li", { "data-kind": "sent" }, [el("b", { text: t(sent.length === 1 ? "Replied to 1 person for you" : "Replied to {n} people for you", { n: sent.length }) }),
    el("span", { class: "who", text: sent.join(uiLanguage === "zh" ? "、" : ", ") })]));
  if (!rows.length) return null;
  return el("section", { class: "night-done", "aria-label": t("What REM did overnight") }, [el("h2", { text: t("What REM did overnight") }), el("ul", {}, rows)]);
}
// The same tally as one sentence: "REM handled 6 things overnight: 3 things have a reply drafted; …".
function nightTallyLine(tally = nightTally()) {
  if (!tally.n) return null;
  const lower = text => uiLanguage === "zh" ? text : text[0].toLocaleLowerCase() + text.slice(1);
  const parts = [...(tally.sent.length ? [t(tally.sent.length === 1 ? "Replied to 1 person for you" : "Replied to {n} people for you", { n: tally.sent.length })] : []),
    ...tally.kinds.filter(kind => kind.kind !== "could_not_prepare" && kind.n).map(kind => kind.text(kind.n))].map(lower);
  const zh = uiLanguage === "zh";
  return el("p", { class: "night-tally" }, [t(tally.n === 1 ? "REM handled 1 thing overnight" : "REM handled {n} things overnight", { n: tally.n })
    + (zh ? "：" : ": ") + parts.join(zh ? "，" : "; ") + (zh ? "。" : ".")]);
}
function nightNames(records) {
  const shown = records.slice(0, 3);
  return el("span", { class: "who" }, [...shown.flatMap((r, i) => [i ? (uiLanguage === "zh" ? "、" : ", ") : "", el("a", { href: href(r), text: threadWho(r) })]),
    records.length > 3 ? " " + t("+{n} more", { n: records.length - 3 }) : ""]);
}
function morningBrief() {
  const pass = lastPass(), claims = pass?.claims || [];
  const first = firstBuild(), title = first ? "First build" : "Overnight";
  const brief = el("section", { class: "overnight", "aria-label": t(title) }, [sectionHead(title), nightTallyLine()].filter(Boolean));
  if (first) {
    if (pass.changed.length) brief.appendChild(el("p", { class: "quiet-line", text: t("Your notebook was just built. Overnight changes appear here after the next update.") }));
    if (!pass.failed.length && nightlyUpdatesOff()) brief.appendChild(el("div", { class: "translation-note" }, [
      el("p", { text: t("Nightly updates are off.") })]));
  } else if (claims.length) {
    brief.appendChild(el("ul", { class: "overnight-changes" }, claims.slice(0, 3).map(overnightChange).filter(Boolean)));
    if (claims.length > 3) brief.appendChild(el("a", { class: "brief-more", href: "#view=changes", text: t("All {n} changes →", { n: claims.length }) }));
  } else {
    brief.appendChild(el("p", { class: "quiet-line pages-line", text: pagesLine(pass) }));
  }
  if (pass?.failed?.length) brief.append(failureSummary(pass), el("a", { class: "brief-more", href: "#view=activity", text: t("Review failed runs →") }));
  return brief;
}
// The pages' half of the night, said as pages, so it never reads as "nothing happened" under the tally of
// what REM handled; a pass older than a day and a half names its date instead of calling itself last night.
function pagesLine(pass) {
  const runN = pass?.runChanged ? pass.runChanged.length : (pass?.changed?.length || 0);
  const stampN = pass?.stampChanged?.length || 0;
  const localPassDay = pass?.localDate || (pass ? (typeof localDay === "function" ? localDay(pass.latest) : calendarDay(new Date(pass.latest).toISOString())) : "");
  const values = { n: runN || stampN, date: localPassDay ? (typeof calendarDate === "function" ? calendarDate(localPassDay) : fmtDate(localPassDay)) : "" };
  const dated = pass && (pass.isLastNight === false || (Date.parse(REM.as_of) - pass.latest > 36 * HOUR));
  if (dated) {
    if (!runN && stampN) return t(stampN === 1 ? "Pages were last updated {date}: no content diffs; 1 page had a metadata update."
      : "Pages were last updated {date}: no content diffs; {n} pages had metadata updates.", values);
    return t(!runN ? "Pages were last updated {date}: nothing new about your people or projects."
      : runN === 1 ? "Pages were last updated {date}: nothing new about your people or projects; 1 page was only reworded."
      : "Pages were last updated {date}: nothing new about your people or projects; {n} pages were only reworded.", values);
  }
  if (!runN && stampN) return t(stampN === 1 ? "No page content changed last night; 1 page had a recent metadata update."
    : "No page content changed last night; {n} pages had recent metadata updates.", values);
  return t(!runN ? "Pages about your people and projects gained nothing new last night."
    : runN === 1 ? "Pages about your people and projects gained nothing new last night; 1 page was only reworded."
    : "Pages about your people and projects gained nothing new last night; {n} pages were only reworded.", values);
}
function failureSummary(pass) {
  // Name the recovery step without exposing private runner output.
  const errors = pass.failed.map(run => String(run.error || "")).join("\n"), reasons = [...new Set(pass.failed.flatMap(run => run.failure_reasons || []))];
  if (/authenticate|authentication|\b40[13]\b|request not allowed/i.test(errors)) reasons.push("Model access was refused. Restore access before retrying.");
  if (/timeout|timed out/i.test(errors)) reasons.push("A request timed out.");
  if (/quota|usage limit|rate limit|\b429\b/i.test(errors)) reasons.push("A model usage limit was reached.");
  if (!pass.changed.some(r => r.path !== REM.owner && known(r).status !== "Mapped")) reasons.push("No memory pages were written in the last pass.");
  return el("p", { class: "quiet-line", text: t(pass.failed.length === 1 ? "{n} investigation failed. " : "{n} investigations failed. ", { n: pass.failed.length }) + [...new Set(reasons)].map(reason => t(reason)).join(" ") });
}
// Remove presentation metadata only; commitments and quoted evidence keep their dates.
function withoutDateClutter(text, { since = "", due = "" } = {}) {
  const quotes = [];
  text = text.replace(/"(?:[^"\\]|\\.)*"|“[^”]*”|‘.*?’(?!\p{L})|「[^」]*」|『[^』]*』|(?<!\p{L})'.*?'(?!\p{L})/gu,
    quote => { quotes.push(quote); return "\u0005" + (quotes.length - 1) + "\u0005"; });
  let words = text.replace(/^\s*(\d{4}-\d{2}-\d{2})\s*[:：]\s*/, (clause, day) => since === day ? "" : clause)
    .replace(/(?:最近联系|Last contact)[:：]\s*\d{4}-\d{2}-\d{2}(?:[,，]\s*(?:邮件|mail|email))?\s*(?:[\[［]W?\d{1,3}[\]］]\s*)*(?:[.!?。！？]|$)/gi, "")
    .replace(/[;；]?\s*open as of\s*[:：]?\s*\d{4}-\d{2}-\d{2}/gi, "")
    .replace(/\s*(?:since\s*[:：]?\s*|(?:从|自)\s*)(\d{4}-\d{2}-\d{2})(?:\s*(?:起|开始))?/gi,
      (clause, day) => since && day === since ? "" : clause)
    .replace(/\s*[—–-]\s*\d+\s+days\b/gi, clause => since ? "" : clause)
    .replace(/\s*[—–-]?\s*[（(]\d{4}-\d{2}-\d{2}[)）]/g, (clause, at, all) =>
      /(?:\b(?:dated|on|by|until|before|after)|日期为|截止于|于)\s*$/i.test(all.slice(0, at)) ? clause : "")
    .replace(/\s*[—–;；,-]\s*due\s*[:：]?\s*(\d{4}-\d{2}-\d{2})(?:,\s*overdue)?/gi, (clause, day) => due === day ? "" : clause)
    .replace(/[,，]?\s*已过\s*\d+\s*天/g, clause => since ? "" : clause);
  const removedDate = words !== text;
  // Mark citation gaps so only punctuation joined by their removal is collapsed.
  words = words.replace(/(?:\s*[\[［]W?\d{1,3}[\]］])+/g, "\u0004")
    .replace(/([,;:—，；：])(?:\s*\u0004\s*[,;:—，；：])+/g, "$1").replace(/\u0004/g, "");
  if (removedDate) words = words.replace(/([,;:—，；：])(?:\s*[,;:—，；：])+/g, "$1").replace(/\s+([,;:，；：])/g, "$1");
  if (words !== text) words = words.replace(/^[\s,;:—，；：]+/, "")
    .replace(/^\p{Ll}/u, letter => letter.toLocaleUpperCase());
  return words
    .replace(/\s*[—–:：;,，；-]+\s*(?=[.!?。！？]|$)/g, "")
    .replace(/[;；]\s*with you(?=[.!?。！？]?$)/gi, "")
    .replace(/[;；]\s*(?=[.!?。！？]?$)/g, "")
    .replace(/,\./g, ".")
    .replace(/\boverdue and;/gi, "overdue;")
    .replace(/\s+([.!?。！？])/g, "$1").trim()
    .replace(/\u0005(\d+)\u0005/g, (_, i) => quotes[i]);
}
// A Today line whose every clause is labelled: at Cover sensitive, taking the passages out left only "— due 9 Dec."
// (rc44 hunt), so the row says what it is instead. At Show all the labels go and every word stays (owner,
// 2026-11-20: "全部显示的时候，应该把这些都显示出来").
function morningWords(text, r, thread = {}) {
  const labelled = hasPrivacy(text);
  text = privacyLevel === "all" ? String(text).replace(/\s*[\[［](?:personal|sensitive)[\]］]/gi, "") : unlabelled(text);
  const left = text.replace(/\[W?\d{1,3}\]|[\[［](?:personal|sensitive)[\]］]/gi, "").replace(/[—–-]?\s*due\s+\d{4}-\d{2}-\d{2}/gi, "").replace(/[\s—–\-.,;:。，；：]+/g, "");
  if (labelled && !/[\p{L}\p{N}]/u.test(left)) return { words: t("A sensitive item (covered)"), context: "", covered: true };
  const cites = [...new Set(text.match(/\[W?\d{1,3}\]/g) || [])].join(" ");
  const words = withoutDateClutter(plainLine(capFirst(threadWords(text, r))), thread);
  return { words, context: cites };
}
// A copied obligation belongs on its named counterpart's page, once per morning.
function morningEntries(entries) {
  return todayEntries(entries, "morning");
}

function threadDate(day) {
  return fmtDate(day);
}
function dueLabel(thread) {
  return t(thread.due < calendarDay(REM.as_of) ? "overdue · " : "due ") + threadDate(thread.due);
}

function taskResult(entry) {
  const task = rowTask(entry);
  if (!task || (!task.result && !REM.live)) return null;
  const pLevel = typeof privacyLevel === "string" ? privacyLevel : "all";
  const markRe = /[ \t]*[\[［](?:personal|sensitive)[\]］]/gi;
  const rawCtx = [entry?.t?.originalText || entry?.t?.text || "", task?.summary || "", task?.reason || "", task?.reply || "", task?.step?.summary || ""].join(" ");
  const level = /[\[［]sensitive[\]］]/i.test(rawCtx) ? "sensitive" : (/[\[［]personal[\]］]/i.test(rawCtx) || entry?.r?.private ? "personal" : "");
  if (level && pLevel === "public") return null;
  // A run shows on the row itself (handOff): here only a task that waits, and a finished one's reply to send.
  // Live, a finished run's next step is on its row (summary, 用这个回复起草, the report in the side card, #3147). A
  // snapshot (the phone) can neither open that card nor draft, so there a finished run shows its one-line summary,
  // and the reply it wrote, if any, to read and copy. Never a file path or a notice that REM did it.
  const snapshotDone = !liveHere() && task.result === "completed";
  if (handed(task) && !snapshotDone) return null;
  const labels = {ready: "Awaiting approval", waiting: task.wait === "budget" ? "Queued: budget used up" : "Queued: later tonight", completed: "Completed"};
  const cleanReason = task.reason ? String(task.reason).replace(markRe, "").trim() : "";
  const cleanSum = snapshotDone && summaryHere(task.summary) ? String(summaryHere(task.summary)).replace(markRe, "").trim() : "";
  const result = el("section", {class: "task-result" + (level ? " private" : ""), ...(level ? { "data-level": level } : {}), "aria-label": t("Task result")}, [
    el("strong", {role: "status", text: t(labels[task.result || "ready"] || "Task")}),
    cleanReason ? el("p", {text: cleanReason}) : null, cleanSum ? el("p", {text: cleanSum}) : null]);
  if (snapshotDone && task.reply && !(level === "sensitive" && pLevel === "cover")) {
    const replyText = String(task.reply).replace(markRe, "").trim();
    const reply = el("textarea", {readonly: "", "aria-label": t("Prepared reply")});
    reply.value = replyText;
    const copy = el("button", {type: "button", class: "btn-quiet", text: t("Copy prepared reply")});
    copy.onclick = () => copyToClipboard(replyText);
    result.append(reply, copy);
  }
  return result;
}

// #3364 Part A: One authoritative translation count shared across Today, Knowledge, Keys, People, Topic, Graph & Settings.
const TRANSLATABLE_CATEGORIES = ["people", "orgs", "projects", "decisions", "principles", "knowledge", "skills"];
function listedTranslatablePages() {
  return (REM.records || []).filter(r => r.written && TRANSLATABLE_CATEGORIES.includes(r.category)
    && !r.needs_review && !r.service && !r.catalog_parent);
}
function authoritativeTranslationCounts() {
  const job = typeof translateAllJob !== "undefined" && translateAllJob ? translateAllJob : {};
  const busy = ["starting", "running", "stopping"].includes(job.state);
  if (job.total != null && job.done != null) {
    const total = Math.max(0, Number(job.total) || 0);
    const done = Math.max(0, Math.min(total, Number(job.done) || 0));
    return { total, done, left: Math.max(0, total - done), busy, job, source: "job" };
  }
  const pre = (typeof detailReady === "undefined" || !detailReady) && Number.isFinite(REM.untranslated_count);
  if (pre) {
    const left = Math.max(0, Number(REM.untranslated_count) || 0);
    const total = Number.isFinite(REM.written_count) ? Math.max(left, Number(REM.written_count)) : left;
    return { total, done: Math.max(0, total - left), left, busy, job, source: "snapshot" };
  }
  const pages = listedTranslatablePages();
  const missing = pages.filter(r => !hasChinese(r) && !/^zh(?:-|$)/i.test(r.written_in || ""));
  return { total: pages.length, done: pages.length - missing.length, left: missing.length, busy, job, source: "records" };
}
if (typeof untranslatedPages === "function") {
  untranslatedPages = function() {
    return listedTranslatablePages().filter(r => !hasChinese(r) && !/^zh(?:-|$)/i.test(r.written_in || ""));
  };
}
if (typeof langParts === "function") {
  langParts = function() {
    const { total, done, left, busy, job } = authoritativeTranslationCounts();
    const parts = [];
    if (uiLanguage === "zh" && busy) {
      parts.push(el("span", { text: job.total != null ? t("Chinese {n} / {m}", { n: done, m: total }) : t("Getting the pages ready…") }));
      const stop = el("button", { type: "button", class: "lang-act", text: t("Stop") });
      stop.disabled = job.state === "stopping";
      stop.onclick = () => translateAllSend("stop");
      parts.push(stop);
    } else if (uiLanguage === "zh" && left) {
      const run = (REM.logs || REM.brief_logs || []).find(run => /translat/.test(run.phase || ""));
      const failed = run?.translation_failures ?? (run?.pages || []).filter(page => page.outcome === "failed").length;
      if (failed) parts.push(el("span", { class: "lang-failed", text: t(failed === 1 ? "{n} page could not be translated." : "{n} pages could not be translated.", { n: failed }) }));
      parts.push(el("span", { text: t("{n} pages not in Chinese yet", { n: left }), title: t("Chinese {n} / {m}", { n: total - left, m: total }) }));
      if (liveHere()) {
        const go = el("button", { type: "button", class: "lang-act", text: t("Translate") });
        go.onclick = () => translateAllSend("start");
        parts.push(go);
      } else parts.push(el("span", { class: "lang-when", text: t("tonight") }));
    }
    return { parts, busy, left, job };
  };
}
// #3438: Consistent local-time night window & clean separation of run rewrites vs metadata/date stamp updates.
function localNightDay(ms) {
  if (typeof localDay === "function") return localDay(ms);
  const d = new Date(ms);
  const pad = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
if (typeof lastPass === "function") {
  lastPass = function() {
    const logs = passRuns().filter(run => !isNaN(runTime(run)));
    if (!logs.length) return null;
    const asOf = Date.parse(REM.as_of || "") || (typeof clockNow === "function" ? clockNow() : Date.now());
    const latest = Math.max(...logs.map(runTime));
    const windowStart = latest - 18 * HOUR;
    const isLastNight = (asOf - latest) <= 36 * HOUR;
    const runs = logs.filter(run => runTime(run) >= windowStart);
    const runChangedSet = new Set();
    for (const run of runs) for (const path of run.changed || []) if (byPath(path) && path !== "skills/catalog/index.md") runChangedSet.add(path);
    const startDay = localNightDay(windowStart), endDay = localNightDay(latest);
    const stampChangedSet = new Set();
    for (const r of listedRecords()) {
      if (runChangedSet.has(r.path)) continue;
      const m = /\b(?:investigated|updated)\s+(\d{4}-\d{2}-\d{2})/.exec((STAMP.exec(r.text) || [""])[0]);
      if (m && m[1] >= startDay && m[1] <= endDay) stampChangedSet.add(r.path);
    }
    const runChanged = [...runChangedSet].map(byPath).sort(byActivity);
    const stampChanged = [...stampChangedSet].map(byPath).sort(byActivity);
    const changed = [...new Set([...runChangedSet, ...stampChangedSet])].map(byPath).sort(byActivity);
    const sources = [...new Set(runs.flatMap(run => Array.isArray(run.sources) ? run.sources.map(sourceName) : []).filter(Boolean))];
    const failed = runs.filter(run => FAILED.test(String(run.outcome || "")) && !/translat/.test(run.phase || ""));
    const items = runs.reduce((n, run) => n + (Number(run.items) || 0), 0);
    const claims = runs.flatMap(run => Array.isArray(run.claim_changes) ? run.claim_changes : [])
      .filter(claim => byPath(claim.record) && (claim.sources || []).length && !sameClaim(claim.before || "", claim.after || ""));
    return { latest, windowStart, isLastNight, localDate: endDay, runs, changed, runChanged, stampChanged, sources, failed, items, claims };
  };
}
if (typeof updatedMarker === "function") {
  updatedMarker = function(r, withLabel = false) {
    if (firstBuild(memoryPass) || !memoryPass || memoryPass.isLastNight === false) return null;
    const pool = memoryPass.runChanged || memoryPass.changed || [];
    if (!pool.some(page => page.path === r.path)) return null;
    if (!withLabel) return el("span", { class: "fresh-label", text: t("last night"), title: t("Updated in last night's pass") });
    const dot = el("span", { class: "fresh-dot", role: "img", text: "●", title: t("updated last night"), "aria-label": t("updated last night") });
    return el("span", { class: "updated-label" }, [dot, t("updated last night")]);
  };
}

