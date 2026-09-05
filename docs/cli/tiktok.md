# co tiktok

Prepare a local TikTok post plan and inspect the current browser page. This
slice does not upload a file, create a TikTok draft, or publish a post.

```bash
co tiktok post clip.mp4 --caption "Demo #example" --account @creator --dry-run --json
co tiktok inspect --tab creator-tiktok --json
co tiktok --help
```

`post` validates a regular, nonempty video-named local file, hashes its bytes,
and includes the exact caption and intended @handle in a reviewable plan. It
previews by default, with `--dry-run` available for explicit use. The current
local caption limit is 2,200 characters, a conservative preview limit rather
than a claim about every TikTok UI version. Privacy must be selected later in
the verified upload form. The @handle is supplied intent, not proof of login.

`--confirm <plan.confirmation>` validates the SHA-256 digest, then returns
`submit_unavailable` with exit 1. It never uploads or clicks. The switch makes
the boundary reproducible in tests; it is not a working publish adapter. Both
normal output and `--json` explicitly call this a local plan.

The preview's next command, `co browser tab ls`, lists available tabs. For
browser inspection, first use the `co-browser` skill to reserve your own
tab and open `https://www.tiktok.com/tiktokstudio/upload`. Set `CO_WHO` on every
command. The CLI captures a viewport screenshot and context before reading
anything; its skill-local script verifies the login heading by exact text/hash.
Login returns `ok: false, reason: login_required`, even when the heading
verification itself passes. Any other surface currently returns
`unverified_surface`; seeing a file input is not treated as readiness.

The actual page on 2026-09-05 redirected to login. A future implementation needs
a manually logged-in, consented test account, saved upload-form context,
verified account identity, semantic file-input and caption selectors, privacy
choices, upload-complete evidence and a one-shot final publish gate. No
credentials should be inspected or automated. Login alone never authorizes an
upload; even attaching a file is an external action requiring approved scope.

The [co-creator skill](../../connectonion/useful_skills/co-creator/SKILL.md) names
the exact scripts and evidence protocol. Keep raw screenshots and DOM captures
local; publish only sanitized test evidence. No TikTok-specific behavior was
added to browser core.

The browser approach follows [#262](https://github.com/openonion/connectonion/issues/262).
The official Content Posting API's audit and client restrictions still require
separate evaluation; this CLI does not call that API. It also does not implement
the approved-app Display API profile/video queries proposed in
[#1426](https://github.com/openonion/connectonion/issues/1426), platform-wide search,
comments, private messages, drafts, or analytics.

Exit 0 means a local preview; exit 1 means invalid input, unsupported submission,
login/unknown-page state or browser failure; exit 2 means CLI usage error. Each
operational output includes one literal next command, including when piped.
Usage errors print their cause and next command to stdout as plain text, even
when `--json` is requested.
