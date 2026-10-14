# Experimental integrations (#2153)

23 small connectors, implemented against the linked provider APIs or official CLIs. These are experiments: their request contracts are tested offline, but we have not verified every provider with a live account. Help, setup requirements and supported operations describe the current scope. Report the workflows you use and the problems you find; that feedback determines where we invest next.

Tracking: [umbrella issue #2153](https://github.com/openonion/connectonion/issues/2153).

## Install the preview

These commands are on the `feat/experimental-connectors-2153` branch. They are not in the current stable PyPI release. In a separate virtual environment:

```sh
python -m venv .venv
source .venv/bin/activate
pip install 'connectonion @ git+https://github.com/openonion/connectonion.git@feat/experimental-connectors-2153'
co commands
co gsheets --help
co feedback report --command 'co gsheets read'
```

Read commands print the provider's JSON to stdout, including its pagination fields. `Next:` and feedback channels go to stderr, so redirecting stdout still produces valid JSON. A listing reads one page unless noted below: pass its returned cursor to the corresponding next-page option. IDs stay complete. Text and JSON writes accept `--input-file file` or `--input-file -` for stdin.

Writes **preview locally by default**, without authenticating or making a request. Repeat with `--yes` to apply once. There are no automatic mutation retries. If a write times out, inspect the service before repeating it. OneDrive download writes a local file, leaves cloud data unchanged and refuses existing destinations.

Google and Microsoft reuse the selected local OAuth account, including refresh. Other API connectors use token settings from `co env` (global `~/.co/keys.env` by default, or `co --env-file file …`). Store secrets using `co env set NAME value --secret`. `gh` and `dws` manage their own login and account/profile selection.

## Google setup

Run `co auth google --scopes drive`. Enable the Drive, Docs, Sheets, Slides and Forms APIs in the broker's Google Cloud project. Users of ConnectOnion's hosted OAuth broker cannot enable its APIs themselves; maintainers must enable them before live rollout. Drive access is accepted by the native document APIs; an old read-only grant cannot write. Listing uses the Drive API and filters by document type. Use `--page-token` with `nextPageToken`. Accepts document IDs and edit URLs, including Sheets ranges; published Forms `/d/e/` URLs are not API form IDs.

### gdocs

`co gdocs list`, `read ID`, `create TITLE`, `append ID --input-file body.txt`. Read includes all document tabs; append writes plain text to the first tab. It does not replace or style the entire document.

[Docs get/create/batchUpdate](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents).

### gsheets

`co gsheets list`, `info ID`, `read ID 'Sheet1!A1:D20'`, `create TITLE`, `append ID RANGE --input-file rows.json`, `update ID RANGE --input-file rows.json`.

Rows are a JSON array of arrays, e.g. `[["Name","Count"],["Alice",10]]`. Writes use `RAW`: strings beginning with `=` remain strings. Append adds rows at the end of the detected table; update overwrites the given range.

[Sheets values API](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values).

### gslides

`co gslides list`, `read ID`, `create TITLE`, `replace ID '{{NAME}}' Alice`. Create makes an empty presentation; replace edits matching text in an existing presentation, case-sensitively. It does not generate slide layouts.

[Slides API](https://developers.google.com/workspace/slides/api/reference/rest/v1/presentations).

### gforms

`co gforms list`, `read ID`, `responses ID`, `create TITLE`, `update ID --input-file questions.json`. Forms are created unpublished; update accepts the official batchUpdate body. For example:

```json
{"requests":[{"createItem":{"item":{"title":"How was your experience?","questionItem":{"question":{"textQuestion":{}}}},"location":{"index":0}}}]}
```

[Forms API](https://developers.google.com/workspace/forms/api/reference/rest/v1/forms). Publishing and respondent access need explicit provider settings outside this experiment.

## Microsoft setup

Run `co auth microsoft` with full consent, rather than `--core`. Existing users must consent again after the broker adds `Files.ReadWrite`; refreshing an existing token does not grant new permissions. OneDrive needs file access, SharePoint site access, and To Do `Tasks.ReadWrite`. Tenant policy may require an administrator's approval. Excel's range API needs **Files.ReadWrite even for reads**. The broker scope change is a companion PR to #2153.

### onedrive

`co onedrive list [--folder ID]`, `info ID`, `download ID --to local.pdf`. Lists include `@odata.nextLink`; extract its `$skiptoken` and pass `--skip-token`. Downloads do not send Graph credentials to the pre-authenticated content URL. Interrupted downloads can leave a partial local file; choose another destination or remove that partial file before retrying.

[DriveItem API](https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0).

### sharepoint

`co sharepoint sites 'Project'`, `drives SITE_ID`, `files DRIVE_ID [--folder ID]`. Document-library paging uses `--skip-token` from `@odata.nextLink`. Site and drive discovery print Graph's paging information; this first experiment does not follow every discovery page automatically.

[Site API](https://learn.microsoft.com/en-us/graph/api/resources/site?view=graph-rest-1.0).

### excel

`co excel sheets FILE_ID`, `read FILE_ID Sheet1 'A1:D20'`, `update FILE_ID Sheet1 'A1:B2' --input-file rows.json`. Optional `--drive DRIVE_ID` selects a business drive or SharePoint library. Requires a supported `.xlsx` workbook in OneDrive for Business or SharePoint; personal OneDrive workbooks are unsupported. Excel interprets its `values` according to the workbook API; Sheets' `RAW` mode does not apply here.

[Excel overview](https://learn.microsoft.com/en-us/graph/api/resources/excel?view=graph-rest-1.0), [range permissions](https://learn.microsoft.com/en-us/graph/api/worksheet-range?view=graph-rest-1.0).

### todo

`co todo lists`, `tasks LIST_ID`, `create LIST_ID TITLE`, `complete LIST_ID TASK_ID`. Task paging supports `--skip` and `--limit`; lists return Graph's pagination metadata.

[Microsoft To Do API](https://learn.microsoft.com/en-us/graph/api/resources/todo-overview?view=graph-rest-1.0).

## Token-based integrations

### notion

Set `NOTION_TOKEN` and share the target pages with the integration. `search TITLE`, `info PAGE_ID`, `read PAGE_OR_BLOCK_ID`, `create PARENT_PAGE_ID TITLE --input-file body.txt`, `append PAGE_ID --input-file body.txt`. Search is by title; read returns immediate children, not an automatically flattened page. Use `--cursor` with `next_cursor`, and read child blocks whose `has_children` is true. Text is split into paragraphs of at most 2,000 characters; a single write is limited by Notion to 100 blocks. API version is pinned to `2025-09-03`.

[Notion API](https://developers.notion.com/reference/intro).

### airtable

Set `AIRTABLE_TOKEN` with access to the chosen base and the required record/schema scopes. `bases`, `tables BASE_ID`, `records BASE_ID TABLE_ID`, `create BASE_ID TABLE_ID --input-file records.json`, `update BASE_ID TABLE_ID --input-file records.json`. Paging uses `--offset`; records accept `--formula`. Write bodies are provider JSON, e.g. `{"records":[{"fields":{"Name":"Alice"}}]}`. Updates require record IDs. Airtable permits up to 10 records per write.

[Airtable Web API](https://airtable.com/developers/web/api/introduction).

### todoist

Set `TODOIST_TOKEN`. `projects`, `tasks [--project ID]`, `create TITLE [--project ID]`, `complete TASK_ID`. Uses current `/api/v1`, with `--cursor` from `next_cursor`.

[Todoist API](https://developer.todoist.com/api/v1/).

### trello

Set `TRELLO_API_KEY` and `TRELLO_TOKEN`. `boards`, `lists BOARD_ID`, `cards LIST_ID`, `create LIST_ID TITLE`, `move CARD_ID LIST_ID`. Lists/cards read the provider's collection response; this experiment does not support historical card paging or attachments.

[Trello REST API](https://developer.atlassian.com/cloud/trello/rest/api-group-cards/).

### asana

Set `ASANA_TOKEN`. `workspaces`, `projects WORKSPACE_ID`, `tasks PROJECT_ID`, `create PROJECT_ID TITLE`, `complete TASK_ID`. Project/task paging uses `--offset` from `next_page.offset`; workspace discovery returns its raw provider response.

[Asana API](https://developers.asana.com/reference/gettasks).

### hubspot

Set `HUBSPOT_TOKEN` from an app with contacts/deals access. `contacts`, `contact ID`, `deals`, `create --input-file contact.json`. Paging uses `--after` from `paging.next.after`. Create takes the provider body, e.g. `{"properties":{"email":"alice@example.com","firstname":"Alice"}}`.

[HubSpot CRM contacts](https://developers.hubspot.com/docs/api-reference/crm-contacts-v3/guide).

### stripe

Set `STRIPE_API_KEY`, preferably a restricted read key. `customers`, `invoices`, `subscriptions`, with `--limit` and `--after LAST_OBJECT_ID` when `has_more` is true. Read-only: this experiment cannot charge, refund or change subscriptions. The account's API version applies.

[Stripe API](https://docs.stripe.com/api).

### jira

Set `ATLASSIAN_URL=https://example.atlassian.net`, `ATLASSIAN_EMAIL` and `ATLASSIAN_TOKEN`. This preview uses an unscoped API token with site Basic Auth; scoped tokens requiring the `api.atlassian.com` gateway are unsupported. `search JQL`, `read ISSUE`, `transitions ISSUE`, `transition ISSUE TRANSITION_ID`, `comment ISSUE --input-file comment.txt`. Search uses the enhanced `/rest/api/3/search/jql`, with `--page-token`. Comments use plain text in Atlassian Document Format.

[Jira search API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/).

### confluence

Uses the same `ATLASSIAN_*` settings as Jira, and the same site-token limitation. `spaces`, `pages SPACE_ID`, `read PAGE_ID`, `create SPACE_ID TITLE --input-file body.html`. Paging uses `--cursor` from `_links.next`. Create publishes a page in Confluence storage-format HTML. This experiment does not edit existing pages.

[Confluence v2 API](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/).

### zendesk

Set `ZENDESK_URL=https://example.zendesk.com`, `ZENDESK_EMAIL` and `ZENDESK_TOKEN`; enable API token access. `tickets`, `read TICKET_ID`, `comments TICKET_ID`, `reply TICKET_ID --input-file reply.txt`. Cursor paging uses `--after` from `meta.after_cursor`. Reply defaults to an **internal note**. `--public --yes` posts a customer-visible reply.

[Zendesk ticket API](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/).

### dropbox

Set a valid `DROPBOX_TOKEN` with file metadata access. `list [--path /Reports]`, `info /Reports/file.pdf`. Use `--cursor` while `has_more` is true. Token renewal is manual in this experiment; there is no daemon or automatic token refresh.

[Dropbox HTTP API](https://www.dropbox.com/developers/documentation/http/documentation).

### figma

Set `FIGMA_TOKEN` with file-content/comments/library read scopes as needed. `read FILE_KEY [--depth 2]`, `comments FILE_KEY`, `components FILE_KEY`. The key is from the Figma file URL. This experiment reads designs; it does not edit the canvas.

[Figma REST API](https://developers.figma.com/docs/rest-api/).

### shopify

Set `SHOPIFY_URL=https://store.myshopify.com` and `SHOPIFY_TOKEN` with product/order read access. `products`, `orders`, with `--limit` and `--after` from `pageInfo.endCursor` when `hasNextPage` is true. Uses Admin GraphQL `2026-07`. Order history and protected customer data depend on the app's approved access; the query reads IDs and status, without customer fields. Token renewal is manual.

[Shopify Admin GraphQL](https://shopify.dev/docs/api/admin-graphql/2026-07).

## Official CLI adapters

### github

Install `gh`, then `gh auth login`. `co github issues OWNER/REPO`, `pulls OWNER/REPO`, `issue OWNER/REPO NUMBER`. Read-only; returns `gh` JSON and honors its active account. The list limit is a cap, not a next-page cursor.

[GitHub CLI](https://cli.github.com/manual/).

### dingtalk

Install and sign in to the official `dws` CLI. `co dingtalk whoami`, `people NAME`, with optional `--profile NAME`. Uses the installed CLI's `--format json`, returns its result unchanged, and neither selects recipients nor sends messages.

[dws official source](https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli). Consult the installed `dws --help` for authentication and profile support.

## Feedback and validation

[Feedback commands and mailbox listener](feedback.md). Public contact: [GitHub issues](https://github.com/openonion/connectonion/issues/new), [Discord](https://discord.gg/4xfD9k8AUF), or `aaron.xie@mail.openonion.ai` with subject `[ConnectOnion feedback]`.

Offline tests cover one request from each HTTP connector, every write's preview/confirmation boundary, raw responses, representative pagination, host restrictions, URL/range encoding, empty completion responses, official CLI arguments and durable mailbox collection. They are not a claim that all APIs were tested with live accounts. Live Google checks need a connected Google account; this development environment currently has none. Follow the umbrella issue for provider-specific live verification and fixes.
