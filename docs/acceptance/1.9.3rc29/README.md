# rc28/rc29 acceptance on the owner's real notebook — 2026-11-03

A dated record of what was run on the owner's own machine and notebook, not a
claim about every notebook. The installed package went from published
`1.9.3rc28` to published `1.9.3rc29` (`uv tool install 'connectonion==1.9.3rc29'
--with onionwright`) during the session.

Notebook: 985 pages (93 people, 24 organisations, 34 projects, 158 skills,
504 agent sessions), Gmail and Outlook subscribed, native schedule in Codex,
weeks of daily runs (33 runs on the day of this check). Machine load average
was 10–117 during the session, so absolute timings below are inflated; the
before/after comparisons were taken under similar load.

## What was checked, and what it found

| Check | Result |
|---|---|
| `co rem status` on rc28 | Reproduced #2711: a Gmail read that dropped 9 deleted queued messages showed `✗` and `→ co rem logs`. |
| `co rem status` on rc29 | Fixed by #2714: `✓ Gmail  last read 2026-11-03: 9 queued messages dropped as missing`. |
| Native schedule wake job (rc28, #2707) | `ai.openonion.co-rem.<id>.wake` loaded in launchd with six daily times, last exit 0; status shows `last triggered 2026-11-03T06:04+11:00 · wake job loaded`. The "Codex closed" path was **not** exercised: closing the owner's running Codex desktop would have interrupted other sessions. |
| `co rem open` (live reader) | First attempt fell back to a snapshot: the Host did not answer within 20 s at load average ~94. A direct timing at load ~58 answered in 9 s; the retry succeeded in 18.8 s. |
| Live reader home `GET /rem` | **91 s, then 122 s**, 16.6 MB. Profile: 76 of 127 s in `cited_context`, which re-read a whole project JSONL per cited session line (6,452 citations). Fixed in #2716. |
| Morning brief | A weeks-old notebook opened on **"First build — your notebook was just built"**: the page carries 20 runs and the day had 33. Fixed in #2716. |
| Source panel (desktop and phone) | Opens, shows the claim and source label, but **every mail citation (0 of 960) had its original**: the excerpt budget was spent in id order on 8,000+ session lines. Fixed in #2716 (933 of 960 present, page 16.5 → 11.8 MB). |
| People list, person page | 93/93 written; two-way open items, changes, pattern and dated history render with source chips. |
| Phone width (390 px) | Home, person page and source sheet: no horizontal overflow; navigation becomes a menu; the source panel is a bottom sheet. |
| Owner page | Last investigated 2026-10-10 and never refreshed by daily rounds; the reader shows it as 24 days old. Filed #2720. |

## Not proved here

Overnight correctness of individual claims (only spot-read), recall over the
whole history, translation quality, and the wake job starting a closed Codex.
Two cold-build costs remain after #2716: name mentions across sessions (~15 s)
and the hashed mail-id fallback query (~18 s under heavy load).
