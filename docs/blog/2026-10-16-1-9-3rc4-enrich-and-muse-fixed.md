# 1.9.3rc4: the turn that ended too early

*2026-10-16*

1.9.3rc3 shipped `co rem enrich` and `co rem muse` the same day. Running them
again on a test project page showed two things wrong, and this candidate fixes
them.

The first was a turn that ended too early. When `co ai` delegates to Codex,
Codex reports its sub-agents' threads on the same connection as the main one.
Ours took any "turn completed" as the main turn's. So when the model sent a
reviewer sub-agent to check its work, the reviewer finishing ended the turn:
4 of muse's 7 turns stopped mid-sentence, and the reviewer's notes were printed
as the run's reply. Notifications from other threads are now ignored.

The second was a ledger that was too thin. For a project page, enrich's list
of what exists held only the coding-session messages that matched the
project's name. The model went and found the pull requests and the mail on
its own, cited them, and the review gate threw those citations out because it
could not identify them. The ledger now also lists the project's coding
sessions, its GitHub issues and pull requests with their comments, and the git
log as a reading guide; muse reads the same ledger; and the gate accepts what
the ledger lists.

Two smaller fixes came along. Enrich reads coding sessions within the same
730-day window investigate uses, which took gathering from 29 minutes to under
one on a machine with thousands of sessions. And token totals for a resumed
Codex thread are no longer counted twice.

On the same test page, enrich then muse now takes the page from 3 quotes to
15 (rc3: 6) and from 10 cited sources to 40 (rc3: 21). No quote was lost and
none differs from its source. Muse's turns went the way the skill describes:
the opening questions, three insights, one honest "no insight", and a final
reply in the skill's format.

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc4'
```
