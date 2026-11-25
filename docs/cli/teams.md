# Microsoft Teams: `co teams`

Read your Microsoft Teams 1:1, group and meeting chats from the terminal, send
plain-text chat messages with a preview step, and list joined teams and their
channels — using the same work or school sign-in from `co auth microsoft`
(#1907). Agents get the same access through `Teams()`.

`check`, `chats`, `ls`, `read`, `teams` and `channels` are read-only. `send`
prints a preview by default and sends nothing until you pass `--yes`.

## Setup

Connect a **work or school** Microsoft account (Entra ID):

```bash
co auth microsoft
co teams check
```

`co teams check` inspects the saved token, reports the tenant kind
(`work_or_school` or `personal`) and shows which of the four delegated Teams
scopes were granted (`Chat.Read`, `ChatMessage.Send`, `Team.ReadBasic.All`,
`Channel.ReadBasic.All`). If your organisation blocks the full consent set and
you signed in with `co auth microsoft --core`, `Chat.Read` will show `✗` until
your tenant allows the full sign-in.

## Terminal usage

```bash
co teams                                       # recent chats, numbered 1, 2, ...
co teams chats --unread --since 7d             # unread chats active in the last 7 days
co teams ls --ids                              # alias for chats, with full chat IDs
co teams read 1                                # read chat 1 as plain text, oldest first
co teams send 1 "RC27 is green"                # preview target chat ID and message text
co teams send 1 "RC27 is green" --yes          # actually post the message
co teams teams                                 # joined Teams, numbered 1, 2, ...
co teams channels 1                            # channels in team 1
```

Every subcommand supports `--json` for structured output (IDs included, `Next:`
sent to `stderr` so `stdout` stays valid JSON):

```bash
co teams check --json
co teams chats --limit 20 --json
co teams read 19:abc@thread.v2 --json
co teams send 19:abc@thread.v2 "On my way" --json
co teams teams --json
co teams channels <team-id> --json
```

## Row numbers, IDs and safety

- `chats` (`ls`), `teams` and `channels` number their rows `1, 2, …` and hide
  long Graph IDs unless `--ids` is passed.
- Row numbers are saved for 15 minutes under `~/.co/teams-listings` (IDs only,
  never message text or topics) and bound to the selected Microsoft account.
  Switching accounts or running an empty relist invalidates older row numbers.
  Pass `--listing <id>` from the `Listing:` line to pin a specific list across
  commands, or pass the full Graph chat/team ID directly.
- `chats` requests `GET /me/chats?$expand=lastMessagePreview&$orderby=lastMessagePreview/createdDateTime desc`
  and marks `[UNREAD]` whenever `lastMessagePreview.createdDateTime` is newer
  than `viewpoint.lastMessageReadDateTime` (or when a chat with a message has
  not been opened yet).
- `read` fetches `GET /chats/{id}/messages?$top={limit}`, strips HTML tags,
  resolves `@mentions` and attachment names into clean plain text, and prints
  messages in chronological order (oldest first).
- `send` requires `ChatMessage.Send`. Without `--yes` it prints the target chat
  and message text and exits `0` without calling `POST /chats/{id}/messages`.
  Pass `-` (or pipe standard input) to read the message body from `stdin`.
- If `send --yes` hits a transport timeout or upstream gateway timeout after
  submitting the request, `co teams` never suggests a blind retry: the message
  may already have been delivered, so it points you to `co teams read` first.

## For agents

```python
from connectonion import Agent, Teams

agent = Agent("teams-assistant", tools=[Teams()])
agent.input("Check my unread Teams chats from today and summarize them.")
```

`Teams()` composes `Outlook`'s credential record, token refresh and throttling
retries without exposing `Outlook`'s mail methods. Its public methods are
`check`, `list_chats`, `chat_items`, `read_chat`, `message_items`,
`send_message`, `list_teams`, `team_items`, `list_channels` and
`channel_items`.

In tool approval policy, `Teams.send_message` (and `co teams send` in `bash`)
is classified as an external side effect requiring human approval (`ask`) and
an `as_owner` action — an unattended non-owner chat turn cannot post messages
as you.

## What it does not do

- **Personal Microsoft accounts (`outlook.com`, `hotmail.com`, `live.com`):**
  Microsoft Graph's Teams chat and team APIs only work on work or school Entra
  ID tenants. Personal accounts carry consumer MSA tenant
  `9188040d-6c67-4c5b-b112-36a304b66dad` (or an MSA compact ticket) and are
  refused immediately before calling Graph, rather than sending you round a
  re-authentication loop that cannot succeed.
- **Reading channel messages without tenant admin consent:**
  `co teams channels` lists a team's channels via `Channel.ReadBasic.All`,
  which a user can grant alone. Reading channel posts and replies
  (`GET /teams/{id}/channels/{id}/messages`) requires `ChannelMessage.Read.All`,
  which Microsoft restricts to tenant administrator consent, so `co teams` does
  not pretend to read channel threads on a standard user sign-in.
- **No polling `co teams listen` loop:**
  Microsoft's APIs Terms of Use and Graph Teams polling policy prohibit polling
  Teams resources more than **once per day** to check for changes; continuous
  polling loops risk throttling or suspension of API access, and Graph change
  notifications require a public webhook endpoint. Use `co teams chats` and
  `co teams read` on demand instead.

## When it refuses

| Message | What to do |
|---------|------------|
| `Microsoft Teams Graph APIs require a work or school Microsoft account … (tenant 9188040d-6c67-4c5b-b112-36a304b66dad)` | Sign in with an organizational work or school account via `co auth microsoft`; personal `outlook.com` accounts are not supported by Graph Teams APIs |
| `Missing Microsoft Chat.Read scope` / `Missing Microsoft ChatMessage.Send scope` | Run `co auth microsoft` without `--core` so Teams scopes are included |
| `No recent Teams chats list` / `Listing unavailable, expired, or for another account` | Run `co teams chats` (or `co teams teams`) for fresh row numbers, or pass the full Graph ID |
| `Microsoft Teams did not confirm whether the message was sent` | Run `co teams read <chat>` before sending again — the message may already be in the chat |
