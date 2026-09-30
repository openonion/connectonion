# Material

Each item below starts with its source id. The page as it stands is source `investigation:page`, and the coverage note is source `investigation:coverage`.

### investigation:coverage
13 messages the user typed in claude-code sessions in this project's folders, 2026-08-30 to 2026-09-24. The last activity is 2026-09-24. Only the user's own messages: no assistant replies, no tool output, no repository files.

### claude-code:sessions-side-feature:1 · 2026-08-30 — user (claude-code, /Users/alex/code/ledgerline)
ledgerline is my CLI for sole traders: point it at a bank CSV export and it writes the quarterly GST report (BAS worksheet) as a PDF.

### claude-code:sessions-side-feature:2 · 2026-09-01 — user (claude-code, /Users/alex/code/ledgerline)
Categorise transactions by payee rules in rules.yaml before the GST totals.

### claude-code:sessions-side-feature:3 · 2026-09-03 — user (claude-code, /Users/alex/code/ledgerline)
Side thing: I want a Telegram bot that reminds me when BAS is due. Start a bot/ folder.

### claude-code:sessions-side-feature:4 · 2026-09-04 — user (claude-code, /Users/alex/code/ledgerline)
The Telegram bot should use long polling, not a webhook, I don't have a server.

### claude-code:sessions-side-feature:5 · 2026-09-05 — user (claude-code, /Users/alex/code/ledgerline)
Bot: add /next to show the next due date.

### claude-code:sessions-side-feature:6 · 2026-09-07 — user (claude-code, /Users/alex/code/ledgerline)
Bot: store chat ids in a JSON file.

### claude-code:sessions-side-feature:7 · 2026-09-09 — user (claude-code, /Users/alex/code/ledgerline)
Bot keeps sending the reminder twice. Fix the duplicate.

### claude-code:sessions-side-feature:8 · 2026-09-10 — user (claude-code, /Users/alex/code/ledgerline)
Bot: the duplicate is gone, I got one message this morning.

### claude-code:sessions-side-feature:9 · 2026-09-12 — user (claude-code, /Users/alex/code/ledgerline)
Bot: add /snooze 3d.

### claude-code:sessions-side-feature:10 · 2026-09-14 — user (claude-code, /Users/alex/code/ledgerline)
Bot: make the reminder text say how much GST is owed if the last report exists.

### claude-code:sessions-side-feature:11 · 2026-09-16 — user (claude-code, /Users/alex/code/ledgerline)
Bot: timezone is wrong, use Australia/Sydney.

### claude-code:sessions-side-feature:12 · 2026-09-19 — user (claude-code, /Users/alex/code/ledgerline)
Back to the report itself: the Q1 PDF totals match my accountant's numbers now, 1,842.50 GST payable.

### claude-code:sessions-side-feature:13 · 2026-09-24 — user (claude-code, /Users/alex/code/ledgerline)
Bot: add a /help message.
