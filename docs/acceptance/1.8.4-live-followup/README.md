# Local acceptance after the public 1.8.4a1 preview

Tested 8 September 2026. These results cover an **unpublished local Gmail recovery
fix**, installed as a wheel in a separate virtual environment. They do not change
the public `1.8.4a1` wheel or constitute final stable acceptance. Exact local wheel
hash and sanitized results are in `results.json`.

The real Gmail/Drive journey passed source preservation across fresh CLI
processes, attachment replace/remove/reload, review invalidation, one self-send,
provider-stored body/attachment equality, consumed draft and saved receipt,
recovery after simulated receipt loss with actual resubmission forbidden,
frozen-list reads, label changes, archive and two private collision-safe downloads.
The inbox label was observed; Gmail rewrote Message-ID but retained the new
attempt marker. The test email and both Drive fixtures were moved to Trash.

Three earlier, small synthetic self-send probes isolated provider normalization:
a shorter ID and an account-domain ID were still rewritten; the dedicated marker
survived. Each probe was cleaned. An initial full journey then exposed a test-only
macOS path assertion error (`/var` versus `/private/var`); hashes were correct,
and the final run passed after resolving the expected temporary directory.

The local production O Chat build passed 26 browser scenarios covering Control
Center actions, conversation selection, reconnection, mobile layout and app
revision controls. Desktop and phone screenshots here were visually inspected.
These browser scenarios use a scripted Host; they are not a new live-model
application-authoring result. The bundled SDK remains published `0.4.4-rc.2`.

The loopback-only in-memory GCS emulator passed concurrent reservation/idempotency,
static response/byte checks and refusal to serve corrupted objects. Synthetic
objects were cleaned. No cloud bucket, identity policy or DNS was created.

Physical Synology acceptance still needs the operator's reachable NAS/profile
and disposable directory. Existing Gmail authorization worked throughout; no
new OAuth consent or phone interaction was required for those tests.

The fix and follow-up remain tracked by Core issue #1460. The public preview's
known issue remains applicable until a new reviewed artifact is published.

The public preview also passed fresh read-only checks for Gmail, Drive, Google
Calendar, YouTube, Outlook and Microsoft Calendar from an unrelated directory.
No account identifiers or provider contents are retained in this report.

The complete Core regression run passed **8,568 tests**, skipped 22 and deselected
184 in 291.12 seconds. It used the repository test venv on PATH, `PYTHONPATH=.`,
and CI's `OPENONION_API_KEY=test-key` placeholder for non-network Agent
construction. These counts are separate from the real Gmail/Drive journey.

The new technical article remains local. Automatic approval rejected its model
export twice and requested explicit approval for this specific article/destination;
no model check or remote publication of this follow-up has occurred.
