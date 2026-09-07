# Google CLI output-only audit

2026-09-05: 36/36 command paths passed with `co/gemini-3.7-flash`.
Only synthetic command output and a goal were supplied to `llm_do`; returned
commands were graded as text and never executed. Test fixtures exercise pipe
rendering. This is discoverability evidence, not real-account API acceptance.

| Command | Printed tip | Goal | Model reply | Pass |
|---|---|---|---|---|
| `co gmail` | Read one with: co gmail read <#> | Read the first listed email | `co gmail read 1` | true |
| `co gmail inbox` | Read one with: co gmail read <#> | Read the first listed email | `co gmail read 1` | true |
| `co gmail search test` | Read one with: co gmail read <#> | Read the first matching email | `co gmail read 1` | true |
| `co gmail read msg-a` | Unread state unchanged. Reply with: co gmail reply msg-a <message> | Reply with body Thanks | `co gmail reply msg-a Thanks` | true |
| `co gmail reply msg-a Thanks` | Check sent mail: co gmail sent | Check sent mail | `co gmail sent` | true |
| `co gmail send a@example.invalid Test Hello` | Check sent mail: co gmail sent | Check sent mail | `co gmail sent` | true |
| `co gmail sent` | Find sent messages to read: co gmail search in:sent | Find sent messages to read | `co gmail search in:sent` | true |
| `co gmail draft list` | Preview one with: co gmail draft preview <# from this listing> | Preview the first listed draft | `co gmail draft preview 1` | true |
| `co gmail draft create a@example.invalid Test Hello` | Attach a local file: co gmail draft attach draft-a <path> | Attach report.pdf | `co gmail draft attach draft-a report.pdf` | true |
| `co gmail draft attach draft-a report.pdf` | Preview it: co gmail draft preview draft-a | Preview the staged draft | `co gmail draft preview draft-a` | true |
| `co gmail draft remove draft-a 1` | Preview it: co gmail draft preview draft-a | Preview the updated draft | `co gmail draft preview draft-a` | true |
| `co gmail draft replace draft-a 1 report.pdf` | Preview it: co gmail draft preview draft-a | Preview the updated draft | `co gmail draft preview draft-a` | true |
| `co gmail draft preview draft-a` | Send with confirmation: co gmail draft send draft-a | Proceed to the confirmation gate | `co gmail draft send draft-a` | true |
| `co gmail draft send draft-a` | Preview again: co gmail draft preview draft-a | Inspect the kept draft | `co gmail draft preview draft-a` | true |
| `co gdrive` | Download one with: co gdrive get <# from column 5> | Download the first listed file | `co gdrive get 1` | true |
| `co gdrive list` | Download one with: co gdrive get <# from column 5> | Download the first listed file | `co gdrive get 1` | true |
| `co gdrive search Report` | Download one with: co gdrive get <# from column 5> | Download the first matching file | `co gdrive get 1` | true |
| `co gdrive get file-a` | Show more files: co gdrive list | Show more files | `co gdrive list` | true |
| `co gdrive put report.pdf` | Check uploaded files: co gdrive list | Check uploaded files | `co gdrive list` | true |
| `co gdrive rm file-a` | Show remaining files: co gdrive list | Show remaining files | `co gdrive list` | true |
| `co gcalendar` | Next: co gcalendar read event-a | Read the first listed event | `co gcalendar read event-a` | true |
| `co gcalendar list` | Next: co gcalendar read event-a | Read the first listed event | `co gcalendar read event-a` | true |
| `co gcalendar today` | Next: co gcalendar list | List upcoming events | `co gcalendar list` | true |
| `co gcalendar read event-a` | Next: co gcalendar list | List upcoming events | `co gcalendar list` | true |
| `co gcalendar meetings` | Next: co gcalendar list | List upcoming events | `co gcalendar list` | true |
| `co gcalendar free 2026-09-05` | Next: co gcalendar list | List upcoming events | `co gcalendar list` | true |
| `co gcalendar create Demo 2026-09-05T10:00:00Z 2026-09-05T11:00:00Z` | No changes made. Next: co gcalendar create --help | Review the confirmation options | `co gcalendar create --help` | true |
| `co gcalendar meet Demo 2026-09-05T10:00:00Z 2026-09-05T11:00:00Z --attendees a@example.invalid` | No changes made. Next: co gcalendar meet --help | Review the confirmation options | `co gcalendar meet --help` | true |
| `co gcalendar update event-a --title Changed` | No changes made. Next: co gcalendar update --help | Review the confirmation options | `co gcalendar update --help` | true |
| `co gcalendar delete event-a` | No changes made. Next: co gcalendar delete --help | Review the confirmation options | `co gcalendar delete --help` | true |
| `co youtube` | Inspect one: co youtube video 1 | Inspect the first listed video | `co youtube video 1` | true |
| `co youtube list` | Inspect one: co youtube video 1 | Inspect the first listed video | `co youtube video 1` | true |
| `co youtube channel` | List this channel: co youtube list UCaaaaaaaaaaaaaaaaaaaaaa | List this channel | `co youtube list UCaaaaaaaaaaaaaaaaaaaaaa` | true |
| `co youtube video abcdefghijk` | See its channel: co youtube channel UCaaaaaaaaaaaaaaaaaaaaaa | Inspect its channel | `co youtube channel UCaaaaaaaaaaaaaaaaaaaaaa` | true |
| `co youtube put clip.mp4 --title Demo --channel UCaaaaaaaaaaaaaaaaaaaaaa` | Review confirmation options: co youtube put --help | Review the confirmation options | `co youtube put --help` | true |
| `co youtube update abcdefghijk --title Changed` | Next: co youtube update --help | Review the confirmation options | `co youtube update --help` | true |

## Exit-code reproductions

All operational-failure reproductions use mocked providers and synthetic data.

| Exit | Reproduction | Printed recovery |
|---|---|---|
| 0 | Every captured command above, except cancelled draft send | Next command shown above |
| 1 | Gmail draft send, decline confirmation | co gmail draft preview draft-a |
| 1 | Gmail/Drive/Calendar mock HTTP 403 | co auth google |
| 1 | YouTube auth_required fixture | co auth google |
| 2 | co gmail read / co gdrive get / co youtube video without argument | Corresponding command --help |
| 2 | co gcalendar update event-a without fields | co gcalendar update --help |

Help/skill parity is tested for Gmail, Gmail draft, Drive, Calendar and YouTube.
No TikTok group is registered. Remaining live acceptance requires interactive
Google consent and read-only queries; writes are only tested with mocks.
