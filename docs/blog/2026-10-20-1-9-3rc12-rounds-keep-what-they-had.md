# 1.9.3rc12: rounds keep what they had

*2026-10-20*

A REM round rewrites part of a page from the mail behind it. On the owner's
page, half of those rounds were being thrown away. The writer had been told to
delete what a part superseded, so it swapped old quotes for new ones, and the
check that guards quotes refused the round. Now every quote already on a page
stays word for word. A dropped quote is put back, then repaired, before a round
is refused. The details are in
[The writer swapped the quotes](2026-10-20-the-writer-swapped-the-quotes.md).

Open threads now say who owes whom, and a promise past its due date stays open
as overdue instead of quietly closing. See
[The audit closed every thread](2026-10-20-the-audit-closed-every-thread.md).

The first run no longer stops on one dropped mail connection. Its estimate now
matches the release check, which took 93.5 minutes against the 95 it announced
([The estimate was half](2026-10-20-the-estimate-was-half.md)). The reader's
home is a morning brief
([A morning brief, not a contents page](2026-10-20-a-morning-brief-not-a-contents-page.md)).

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc12'
```
