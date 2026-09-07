# Gmail and Drive CLI audit — 2026-09-05

Scope: all Gmail commands, its draft group, and all Drive commands. Outlook and
agent-mail are not included. Method: `cli-skill-design`, with the `co-browser`
worked example. Providers are mocked for all mutations in this audit.

The audit adds missing terminal/piped tips, clears stale numbers on empty
listings, uses resolved IDs in reply tips, and sanitizes provider/network errors.
Drive TSV gains a fifth row-number column; existing column positions remain.
Connection failures after writes point to inspection rather than repeat writes.

## Reproduce

```bash
python -m pytest tests/unit/test_google_cli_design.py tests/unit/test_gmail.py tests/unit/test_gmail_commands.py tests/unit/test_gdrive.py tests/unit/test_gdrive_commands.py tests/e2e/cli/test_cli_gmail.py tests/e2e/cli/test_cli_gdrive.py -q
PYTHONPATH=. python tests/unit/test_google_cli_design.py | cat
PYTHONPATH=. python tests/unit/test_google_cli_design.py --tip-test
```

Focused suite: **277 passed**. The pipe run prints each command's captured CLI
output, including its next-step tip. Provider methods are mocked; Gmail listing
formatting uses the real formatter. Cache files live in a temporary directory.

## Help / SKILL parity

The automated check compares actual visible command registrations with every
command mentioned in the matching skill, and verifies each appears in help.

| Group | CLI and SKILL set | Difference |
|---|---|---|
| Gmail | draft, inbox, read, reply, search, send, sent | none |
| Gmail draft | attach, create, list, preview, remove, replace, send | none |
| Drive | get, list, put, rm, search | none |

## Output-only tip tests

Fresh text-only `llm_do` calls, pinned to `co/gemini-3.7-flash`. Input is captured
command output and the goal only. Model replies are graded, never executed.
All 20 command paths passed; quotes around `Thanks` are equivalent shell syntax.

| Command | Tip command | Goal | Reply | Pass |
|---|---|---|---|---|
| gmail | `co gmail read <#>` | read first email | `co gmail read 1` | yes |
| gmail inbox | `co gmail read <#>` | read first email | `co gmail read 1` | yes |
| gmail search | `co gmail read <#>` | read first match | `co gmail read 1` | yes |
| gmail read | `co gmail reply msg-a <message>` | reply Thanks | `co gmail reply msg-a "Thanks"` | yes |
| gmail reply | `co gmail sent` | check sent mail | `co gmail sent` | yes |
| gmail send | `co gmail sent` | check sent mail | `co gmail sent` | yes |
| gmail sent | `co gmail search in:sent` | find sent messages to read | `co gmail search in:sent` | yes |
| gmail draft list | `co gmail draft preview <# from this listing>` | preview first draft | `co gmail draft preview 1` | yes |
| gmail draft create | `co gmail draft attach draft-a <path>` | attach report.pdf | `co gmail draft attach draft-a report.pdf` | yes |
| gmail draft attach | `co gmail draft preview draft-a` | preview staged draft | `co gmail draft preview draft-a` | yes |
| gmail draft remove | `co gmail draft preview draft-a` | preview updated draft | `co gmail draft preview draft-a` | yes |
| gmail draft replace | `co gmail draft preview draft-a` | preview updated draft | `co gmail draft preview draft-a` | yes |
| gmail draft preview | `co gmail draft send draft-a` | proceed to confirmation gate | `co gmail draft send draft-a` | yes |
| gmail draft send (declined) | `co gmail draft preview draft-a` | inspect kept draft | `co gmail draft preview draft-a` | yes |
| gdrive | `co gdrive get <# from column 5>` | download first file | `co gdrive get 1` | yes |
| gdrive list | `co gdrive get <# from column 5>` | download first file | `co gdrive get 1` | yes |
| gdrive search | `co gdrive get <# from column 5>` | download first match | `co gdrive get 1` | yes |
| gdrive get | `co gdrive list` | show more files | `co gdrive list` | yes |
| gdrive put | `co gdrive list` | check uploads | `co gdrive list` | yes |
| gdrive rm | `co gdrive list` | show remaining files | `co gdrive list` | yes |

## Exit reproductions

All rows use the same isolated CLI runner, with mocked provider outcomes.
The usage errors come from the real command parser.

| Exit | Provoked by | Cause printed | Next command |
|---|---|---|---|
| 0 | gmail inbox | one numbered message | `co gmail read <#>` |
| 0 | gdrive list | one TSV row with row number | `co gdrive get <# from column 5>` |
| 1 | gmail inbox, injected HTTP 403 | Google request failed (HTTP 403) | `co auth google` |
| 1 | gdrive list, injected OSError | local I/O or Google connection failed | `co gdrive list` |
| 1 | gmail draft send, answer n | not sent, draft kept | `co gmail draft preview draft-a` |
| 2 | gmail read, missing ID | Missing argument email_id | `co gmail read --help` |
| 2 | gdrive get, missing ID | Missing argument file_id | `co gdrive get --help` |

The regression suite also injects lost responses into Gmail send/reply and
Drive upload and verifies the recovery command inspects provider state.
No live send, upload, trash, or download was performed by this expanded audit.
The earlier disposable-draft acceptance is described separately in the PR.
