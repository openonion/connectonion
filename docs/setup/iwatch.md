# Set up this Mac for OpenOnion Sense

**Candidate instructions, not yet released.** Intended stable URL:
`https://docs.connectonion.com/setup/iwatch.md`. Do not advertise that URL as live
until this guide and a matching tested package have been published. The current
candidate does not include the released Watch connector; report that dependency
instead of claiming complete device setup.

Give this page to Codex on the Mac. Codex should perform the steps, explain only
the next unavoidable user action, and finish with actual observed status.

1. Inspect `co --version`, `co commands`, `co init --help` and `co host --help`.
   Reuse a compatible installation. If installation/upgrade is needed, select a
   genuinely published official version containing these capabilities, using its
   verified release instructions. Never downgrade a working co or install a
   private development branch as though it were a public release.
2. When `co init --background` and native Codex hosting exist in that release,
   run `co init --background`. This performs standard identity/skill setup,
   prepares a dedicated private Mac Host profile and REM storage, and starts the
   macOS user service. It does not authorize mailbox investigation or cloud
   processing of saved recordings.
3. Inspect the returned profile and real service/process status. From that actual
   profile, use `co host --status`. A plist alone is not a running service. Codex
   login preflight is not a completed AI request. If Codex needs installation or
   login, use the returned recovery command and let the user complete any real
   account confirmation, then rerun initialization.
4. Check the actual supported Watch connection group/help. The target is
   `co iwatch connect`; an older `co sense connect` is usable only if that exact
   supported release includes a compatible native bridge. If no published release
   supplies the connector, say “Mac prepared; Watch connector not released” and
   stop at that truthful boundary. Do not create a demonstration QR or tell the
   user to find a helper path.
5. With a real supported connector, start it, display the live QR, and tell the
   user to open Sense's Mac connection entry on the phone. Both ends confirm the
   actual identity and selected data scope. The phone bridges the paired Watch;
   sharing an Apple account is not data access authorization.
6. Report separately: installed co version, native Codex login preflight, running
   Mac service, REM storage prepared, Watch connector available, paired permission,
   source online and any remaining next action. Do not call all-ready when one
   is missing. Retain recordings, identity and memory on every retry.

Expected later use: explicit record/ask requests reach the authorized Mac, which
can transcribe long recordings, invoke Codex and manage REM according to enabled
source permissions. Setup itself does not record, upload audio or infer health.
Mac sleep/logout/offline and missing device permissions remain visible states.
