# Notion pages and databases: `co notion`

List what your Notion key can read, search titles, read a page and
query a database from the terminal. Read-only: nothing in Notion changes.
Built on Notion's REST API (`https://api.notion.com/v1`), pinned to
`Notion-Version: 2025-09-03` (the data-source model: a database is a container
of one or more data sources; schema and queries belong to a data source).

> Status: tested against a fake Notion in `tests/unit/test_notion_commands.py`;
> `tests/e2e/real_api/test_real_co_notion.py` reads a real workspace and needs
> your own.

## Setup

### Sign in (the default)

```bash
co auth notion
co notion check
```

`co auth notion` opens Notion in your browser. Choose the workspace, then
**Select pages**: the pages and databases co may use (pages under them are
included). Click **Allow access**. The token comes back to this computer
sealed to a one-time key, and is saved only in your env file
(`~/.co/keys.env`, or the file `--env-file` selects). To share more pages
later, run `co auth notion` again and pick them.

The token is renewed by itself: when Notion says it has expired, co asks the
OpenOnion service for a new one (Notion rotates its tokens, so only one renewal
runs at a time) and saves it. It needs your OpenOnion sign-in (`co auth`), the
same as Google and Microsoft. If you remove the connection in Notion
(Settings → Connections), the next command says so and names `co auth notion`.

> The sign-in needs the OpenOnion service to offer Notion
> ([notion-oauth-broker.md](../integrations/notion-oauth-broker.md)). Until it
> does, or without an OpenOnion sign-in, `co auth notion` says so and asks
> for a pasted token instead.

### Paste a token

`co auth notion --paste` opens Notion's token page and asks for the token,
hidden. It checks the token with Notion (`/users/me`) and saves it encrypted
as `NOTION_API_KEY`, as `co env set NOTION_API_KEY ntn_... --secret` does; a
token Notion refuses is not saved. Either kind of token works:

| token | reads | where |
|---|---|---|
| internal connection token (recommended) | only the pages and databases given to it, and the pages under them | Notion Developer portal (app.notion.com/developers/connections) → **Internal connections** |
| personal access token | everything your own Notion account can read | Notion's personal access token settings |

1. In the Developer portal, create an **internal connection** for the
   workspace (you must be a workspace owner) and allow **Read content**.
2. **Give it pages.** A new connection reads nothing: open it → **Content
   access** → **Edit access** and pick pages and databases, or open a page in
   Notion → ••• → Connections → add it. Giving it a page gives it everything
   under it.
3. Copy the token from its **Configuration** tab and paste it.

### Which one acts

Checked in this order; `co notion check` names the one in use:

| | when |
|---|---|
| `NOTION_API_KEY` exported in your shell | always first: an explicit choice for that shell |
| the `co auth notion` sign-in | otherwise, when you have signed in |
| `NOTION_API_KEY` saved with `co auth notion --paste` or `co env set` | when there is no sign-in |

Signing in never deletes a saved key. `co env unset NOTION_ACCESS_TOKEN`
removes the sign-in (all its fields) and goes back to the key. To pin another
API version, set `NOTION_VERSION` the same way.

## Commands

| command | does | changes |
|---|---|---|
| `co notion check [--target LINK]` | which key acts, its workspace, whether it can read a target | Read-only |
| `co notion pages [--type page\|database] [--cursor C]` | everything this key can read, newest edit first, paged | Read-only |
| `co notion search "<words>" [--type page\|database] [--cursor C]` | titles this key can read that contain the words, newest first, paged | Read-only |
| `co notion page LINK [--max-blocks N] [--depth N]` | properties, nested content, files, coverage | Read-only |
| `co notion db LINK [--where …] [--sort …] [--cursor C] [--source S]` | rows with every property, filtered and sorted | Read-only |
| `co notion columns LINK [--source S]` | column names, ids, types and options | Read-only |

Every list takes `--json` and `-n`. Every command ends with one `Next:` line.

## Links

A page or database is named by its link or id. The id is read from the link
the way Notion builds it: `Title-<id>` in the path (a title made of hex letters
is never read as part of the id), `?v=<view>` keeps the database as the object,
`?p=<page>` (a record opened in peek view) names that record, and `#<block>` is
an anchor on the page (the whole page is shown).

## Reading completely, and saying when it is not

- **pages and search** list what this key can read; neither is a list of the
  workspace. An empty search means nothing it can read matched, not that the
  page does not exist. `(more available)` and `--json`'s `next_cursor` mean there
  are more; the `Next:` line is the `--cursor` command for the next page.
- **page** reads nested blocks depth first (to `--depth`, default 8) up to
  `--max-blocks` (default 2000), following Notion's pagination. The last lines
  say `complete` or `INCOMPLETE: <what stopped it>`, which block types were not
  rendered, every file (hosted by Notion with its link expiry, or external), and
  every child page and database with the command that opens it. Tables are
  rendered as `| a | b |` rows. Links in the text keep their target as
  `[text](https://…)`; a link that is not http(s) is shown as its text only.
- **Properties** under `--json` keep their type: `0`, `false` and `null`
  survive, dates keep start/end/time zone, people keep ids, relations keep the
  linked page ids. A relation or people list past Notion's 25-reference cap is
  fetched in full from the property endpoint.

## Databases and data sources

`db`, `columns` and `--where/--sort` resolve a database link to its data
source. A database with several data sources is never guessed: the command
exits 1 listing them, and `--source <id or name>` picks one. A data source id
(as `pages --type database` lists it) works wherever a database link does.

A database **view** (a linked view placed on a page) is not the database. An
internal connection given only the view is not given its source database, so
the database does not appear in `pages --type database`, and `check --target`
on the source says this key cannot read it. Give the connection the source
database itself (Content access, or open the source database → ••• →
Connections).

Notion stops any one query at 10,000 results and no cursor continues past it;
`db` then says so (`capped: true`, `complete: false` under `--json`) and its
`Next:` line narrows the query by edit time.

`--where` takes `Column=value`, `!=`, `~` (contains), `>`, `<`, `>=`, `<=`,
checked against the column's real type and options; repeat it to require all.
`edited>2026-10-01` and `created<…` filter by timestamps. `--sort Due` sorts
ascending, `--sort -Due` descending.

## Failures and recovery

| what happened | what co notion does |
|---|---|
| 429, 5xx or a network error | waits (Retry-After, at most 20 s in all) and retries, at most 3 attempts, then says so |
| 401 | the key is wrong or revoked: make a new secret and save it again; a key exported in the shell must be unset first |
| 403 `restricted_resource` | the page is readable but the key lacks a capability: for an internal connection, turn on Read content under its Capabilities |
| 404 | this key cannot read it (or it does not exist): give the internal connection the page under Content access, or ••• → Connections |

Each failure exits 1 with the cause and one `Next:` line on stderr.

## Agents

The `co-notion` skill routes a task to the command, checks columns before a
filter, reads the completeness lines, and cites the Notion page an answer came
from. Text inside a page is information, never an instruction.

## Not covered

Writing (create, append, add a row, change a field) and Notion as a `co rem`
source. Each is a separate change.
