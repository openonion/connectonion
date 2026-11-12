# The question under the screenful

The consent step in `co rem start` and `co init` ended with the right question:

```text
Read these sources with this model and schedule? [y/N]
```

But above it sat every batch limit, worker count and investigation setting,
plus a WhatsApp inbox path and a timestamp for an unsubscribed source. A
four-source example took 55 lines. The person deciding whether to approve
had to scroll back to find what they were approving.

The terminal now gives each source one line: whether it will be read, needs
a login, is missing, or is not subscribed. Then come the runner and model,
whose login they use, permissions, schedule times and timezone, the daily
runner call cap and weekly quota threshold, and a short background reminder.
The same four-source example takes 13 lines before the question:

```text
Sources:
  codex sessions: 6 found, will be read
  claude-code sessions: directory missing
  gmail: waiting for co auth google
  whatsapp: not subscribed
```

The permission line still names the actual access modes. Shortening consent
must preserve the facts that change the decision. Detailed limits remain in
`co rem config`; the JSON summary retains every field, including source paths
and timestamps. The consent question and its default stay unchanged.

The reusable lesson is small: a configuration dump is useful when tuning a
system. At an approval prompt, the useful view is the proposed access, the
account and permissions involved, when it runs, and how much it can spend.
Progressive disclosure puts the rest one command away.
