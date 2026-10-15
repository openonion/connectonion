# co rem: the live reader and pages in several languages

Owner's request (2026-10-15): `co rem open` should start the Host, and the REM
page should be able to call co ai to translate or switch language, end to end.
The same page should be readable in several languages.

## How you use it

```bash
co rem config set language zh      # new pages are written in Chinese (rem/q-language)
co rem open                        # live reader on this computer; starts co ai if needed
co rem translate "Alice Chen" --to zh    # the same from the terminal
co rem open --local                # offline snapshot, starts nothing
co rem open --live                 # O Chat view, for another device
```

In the reader, open a page. Under its title is **Read in [As written ▾]**.
Pick a language. A cached translation shows at once. Otherwise the menu entry
says "translate with co ai": picking it shows "Translating with co ai…", and
the page switches when the translation is ready, usually after a minute or two.
If it fails, the reason and the fix (for example `codex login`) appear next to
the menu. "As written" switches back.

## What `co rem open` does

| Situation | Opens | Says |
|---|---|---|
| Default notebook, co ai identity, Host answers on 127.0.0.1 (the port co rem started, or 8000) | `http://127.0.0.1:<port>/rem?token=…` | "the live reader, served by co ai on this computer" |
| No Host running | starts `co ai --port <free> --no-listen --no-launch` in the background, waits up to 20 s, then as above | same |
| co ai cannot start, or no network and no local Host | snapshot `file://…` | `Live: Live reader unavailable: <reason, log path>; showing a snapshot`, exit 1 |
| Custom `--root`, or no co ai identity | snapshot | why there is no live reader |
| co ai already runs on another, unknown port | snapshot | use `co rem open --live`, or stop that co ai |
| `--local` | snapshot | starts nothing |
| `--live` | O Chat `/{address}/rem` (unchanged, #1637) | |

The Host started by `co rem open` is reused by the next open (`.co/rem-live-host.json`
records its pid and port). Its log is `.co/rem-live-host.log`.

## How the page asks the Host for actions

The Host already serves HTTP on its port. Two routes are added
(`connectonion/network/host/rem_http.py`):

- `GET /rem`: the reader, rendered fresh from the notebook with `live: true`.
- `POST /rem/translate {page, language}`: returns `{state: "ready", text}` when
  a current translation is cached. Otherwise it starts one translation in a
  worker thread and returns `{state: "running"}`. The page polls the same call
  every 2 s until it gets `ready` or `{state: "failed", error}`. A failure is
  reported once; the next request starts a new attempt.

The reader's change (`reader.html`) is one line in `record()` that adds the
language bar, and a separate "Languages" block at the end of the script:
`languageBar`, `readIn`, `askHost`, `showLanguage`. Switching swaps the record's
text for the translation and re-renders. Headings, Facts labels and source ids
stay English, so every structured view (facts, threads, sources) still parses.

## Security: owner only

The existing model is "the Host's owner (admin) can read co rem". O Chat proves
it with a signed WIKI_READ from an admin browser key. The local page has no
browser key, so it proves ownership through the file system:

- `co rem open` reads `.co/rem-reader-token` (created once, mode 600, next to
  the Host's key) and puts it in the URL. Anyone who can read that file can
  already read the Host's private key and the notebook.
- The first `GET /rem?token=…` swaps the token for an `HttpOnly; SameSite=Strict;
  Path=/rem` cookie and redirects to `/rem`, so the token leaves the address bar
  and history.
- Every /rem request must come from a loopback client and carry a loopback
  `Host` header, so other machines on the LAN and DNS-rebinding pages get 404.
- `POST /rem/translate` requires `content-type: application/json`, so a
  cross-site form cannot send it. SameSite=Strict keeps the cookie off
  cross-site requests. Responses are `no-store`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`.
- `page` must be a listed notebook record and `language` must be a language tag,
  so neither can name another path. `/rem` is a reserved prefix that publisher
  routes cannot take.

## How translations are stored

`.state/translations/<language>/<record>`, for example
`.state/translations/zh/people/alice-chen.md`. The first line is
`<!-- co rem translation of people/alice-chen.md sha256:<hash of the page> -->`.

- **Canonical page untouched.** The Markdown page is still the record. Upkeep,
  investigation and search never read translations.
- **Stale = hash mismatch.** When the page changes, its translation stops
  matching. The reader stops offering it as cached, and the next request makes
  it again. Nothing has to watch for changes.
- **Made by co ai on the notebook's runner.** One `co ai --json --harness <runner>`
  turn (`runner.run_task`, stage `abstract`, Codex `workspace-write`) in a
  private `.state/tasks/translate-*` folder, from `page.md` to `translation.md`.
  The rules are the same `language_rules()` the page writers use: headings,
  Facts labels, source ids and markers stay as given, names stay as written, and
  a quote keeps its original language.
- **Checked before caching.** If the heading lines, the source ids (counted) or
  the English markers the reader parses (`Nothing open as of`, `Unknown`, `Now:`…)
  differ from the page, nothing is cached and the error says to try again. The
  `Investigation:` stamp line is never sent to the model and is put back as
  written. In the live check, Codex first translated `Nothing open as of`, which
  turned a closed conversation into an open thread, and later translated the
  stamp's label, which turned the status from "Investigated" into "Some findings".
  Both are now prevented.
- **Every snapshot carries current translations** (`record.translations`). The
  offline snapshot and the O Chat view can switch to any cached language. Only
  the live reader can make new ones.

## Not done (next steps)

- **Translating from O Chat.** O Chat already shows cached translations. To
  generate one from there, the iframe would `postMessage` to oo-chat, which would
  send a signed admin-only frame (`REM_TRANSLATE`, the same gate as WIKI_READ)
  through `@connectonion/react`. That needs an SDK method, so it waits until
  someone asks for it.
- **Ask.** "Ask about this page" would use the same route shape
  (`POST /rem/ask`, polled the same way).
- **Remembering the language across pages.** Each page is switched on its own
  for now.
