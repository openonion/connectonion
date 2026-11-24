# 1.9.3: REM does the work

*2026-11-09*

Until now co rem told you what you owed. 1.9.3 starts paying it. While Avery
sleeps, REM reads the day's mail, drafts the replies he owes in his own voice
and runs the tasks he approved, through his own Codex or Claude Code. Replies
to people he trusts, like his co-founder Fern, can go on their own after a
10-minute hold he can undo. In the morning one email says what was prepared,
what was sent, and at most three things only he can decide.

The rest he hands off from the page. Mara at Fernhill Labs is waiting on a
signed data-sharing addendum; her row says so, and beside it sit "Hand to
Codex", "Hand to Claude" and "Talk it over". He picks one and the row says
"Codex is working", with Stop and Undo next to it, then "See result" when it is
done. If the task needs a word first, Talk it over opens a conversation with
the agent in the page, and it resumes the agent's own session rather than
starting cold. Every unfinished row works this way, not only the ones REM
prepared overnight.

Two things had to be true before we called it stable. Work must be visible and
reversible: nothing an agent does hides behind a command to copy, and each row
keeps its Undo. And the page must open at once, on any machine, Windows
included, keeping the section you had open when a sync redraws it.

```bash
python -m pip install --upgrade 'connectonion==1.9.3'
```

See the [release notes](../releases/1.9.3.md).
