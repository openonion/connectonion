# OpenOnion email

`co email` and [OO Mail](https://mail.openonion.ai) use the same account, mailbox and server API. The global selected identity is the default; use `co --env-file PATH email ...` to select a project account explicitly. Help is the command reference: `co email --help`.

## Everyday mail

```sh
co email inbox --last 50
co email read 123
co email sent
co email sent read 456
co email search "launch" --last 100 --offset 0 --json
co email mark-read 123 124
co email mark-unread 123
co email reply 123 "Thanks for the update."
co email forward 123 you@example.com "For your review."
```

Received and Sent reads retrieve one record by ID, including older messages outside the newest page. Reading alone does not change unread state. Received reads require the backend's `/email/received/{id}` endpoint; unread changes use `/email/s/mark-unread`. HTTP 404 and expired authentication have distinct recovery messages.

Search examines a bounded received-mail page: sender, recipient, subject and body. Its output names the number scanned and offset; use the next offset for older messages. It is not a server-wide search index. Replies and forwards call the existing idempotent send path with quoted plain text. They send immediately, include no attachments and add no RFC threading headers.

## Browser connection

```sh
co email open
co email open --no-browser
co email connect <challenge-from-the-OO-Mail-dialog>
```

Generate the two-minute challenge in the browser, run the displayed connect command, and paste its output back into that same browser. The selected local identity signs only the OO Mail protocol. The private key remains local; no bearer token is put into a URL. The command prints only the short-lived proof on stdout. A downloaded helper remains available in the web dialog for older CLI versions.

## Addresses and allowance

```sh
co email tier --json
co email quota
co email domains
co email addresses
co email setup mailbox --domain steadmail.com
co email change you@mail.openonion.ai --domain steadmail.com
co email delete-history you@mail.openonion.ai
```

These examples inspect or preview. Address creation/changes require `--buy` to charge credits. `co email quota --buy --idempotency-key <unique-key>` purchases exactly one plan-defined increment; reuse the key on retry. History deletion requires `--yes`; received history is the default scope and `--include-sent` also deletes sent logs, which affect quota counts. The address is retained.

Existing commands cover custom names, account default, sharing/revocation and tier upgrades. `co email setup` replaces no other address. `change` resolves the owned address record ID and previews the backend's current price; names/domains are normalized before pricing.

## Transfer one address

```sh
co email transfer prepare you@mail.openonion.ai --to <recipient-public-key> --out request.json
# The named recipient runs this using their own selected identity:
co email transfer accept request.json --out approval.json
co email transfer complete approval.json
co email transfer complete approval.json --yes
```

Both keys sign the backend's exact five-minute transfer message, which names the address and its existing received/sent history. The first two commands write new mode-0600 files and refuse overwrites. Completion previews unless `--yes`; only then does it change ownership. The key-derived automatic address cannot be transferred. The backend verifies ownership and applies the address/history move atomically.

Server-synchronized archive, trash, stars, drafts, attachments and threading are not exposed by the existing email API. OO Mail's personal organization remains browser-local; this CLI does not invent server endpoints for those features.

## Validation

Protocol signatures, expiry, tampering, identity selection, direct reads, retry-key reuse, management previews, address pricing and partial bulk failures are covered by offline tests. An independent AI review checked user workflows, output fidelity, signature safety and permission boundaries. The real account was connected in OO Mail; CLI/web message IDs and body agreed, and one self-addressed UTF-8 web send appeared once in Sent and once in Inbox. Purchases, address transfers and history deletion were verified with mocks and local dummy identities, without executing them on the real account.
