> **Preview 1.9.3rc22.** This reference includes the send-budget and status behavior in this opt-in preview; stable remains 1.9.2. See [release notes](https://github.com/openonion/connectonion/releases/tag/v1.9.3rc22).

# OpenOnion email

`co email` and [OO Mail](https://mail.openonion.ai) use the same account, mailbox and server API. The global selected identity is the default; use `co --env-file PATH email ...` to select a project account explicitly. Help is the command reference: `co email --help`.

## Everyday mail

```sh
co email inbox --last 50
co email inbox --address you@mail.openonion.ai
co email read 123
co email sent
co email sent read 456
co email search "launch" --last 100 --offset 0 --json
```

`--address` narrows the inbox to one mailbox. An address this account does not own, and has not been granted read access to, exits with an error that lists this account's addresses. The received-mail API returns an empty page for an address it will not confirm, so the command checks the account's address list before calling that page "no mail".

To mark selected messages read:

```sh
co email mark-read 123 124
```

To mark one message unread:

```sh
co email mark-unread 123
```

A reply sends immediately:

```sh
co email reply 123 "Thanks for the update."
```

A forward also sends immediately:

```sh
co email forward 123 you@example.com "For your review."
```

Received and Sent reads retrieve one record by ID, including older messages outside the newest page. Reading alone does not change unread state. Received reads require the backend's `/email/received/{id}` endpoint; unread changes use `/email/s/mark-unread`. HTTP 404 and expired authentication have distinct recovery messages.

Search examines a bounded received-mail page: sender, recipient, subject and body. Its output names the number scanned and offset; use the next offset for older messages. It is not a server-wide search index. Replies and forwards call the existing idempotent send path with quoted plain text. They send immediately, include no attachments and add no RFC threading headers.

## Browser connection

```sh
co email open
co email open --qr
co email open --no-browser
co email connect <challenge-from-the-OO-Mail-dialog>
```

`co email open` opens the selected account on your computer and prints an **independent, unused phone link**. The automatic desktop visit cannot consume the phone ticket. Interactive terminals also show its QR. `co email open --qr` prints one phone QR/link and never opens the computer's browser. `--no-browser` prints only one unused URL on stdout for copying or automation; diagnostics stay on stderr.

Links work once and remain valid for up to ten minutes, bounded by the issuing credential's expiry. Open the printed link directly in Safari/Chrome on the phone, or scan with the phone's camera. It is already a sign-in link; no challenge needs to be copied back. An existing browser session may also create a fresh QR under **Settings → Open on phone**, without keeping the original CLI computer online.

The link contains an opaque random code in the URL fragment, not your API token or private key. The browser removes that fragment, exchanges the code once and keeps its session in an HttpOnly cookie. If a different account is already connected, it asks before switching. A replayed or expired link names the command to run again. The anonymous homepage is a connection page; `/demo` is an isolated sample mailbox even when a real account is logged in.

An older CLI with `open` can use `co email open --no-browser` for an unused phone link. The legacy signed-challenge flow remains under the homepage’s compatibility help. Generate the browser challenge, run the displayed `co email connect` command, and paste its output back into that browser. A downloaded helper remains available in the dialog. This compatibility flow also keeps the private key local.

## Monthly free sends, then PAYG

Every free account receives **100 included emails each calendar month (UTC)**. Unused allowance does not roll over. Existing purchased monthly allowances stay available. After the allowance, an accepted email costs **USD $0.003**, deducted from existing OpenOnion credits. There is no mandatory subscription, automatic renewal or automatic top-up. Reading and local drafts are unchanged.

```sh
co email tier
```

Use included sends only:

```sh
co email send you@example.com "Hello" "My message"
```

Alternatively, authorize up to USD $0.003 for one email; included sends still cost $0:

```sh
co email send you@example.com "Hello" "My message" --max-cost 0.003 --idempotency-key my-send-001
```

Check that send without resending:

```sh
co email status my-send-001 --json
```

`--max-cost` also works with `reply` and `forward`. A price change above that cap or insufficient credits refuses the send before dispatch. Retry an uncertain delivery with **the same send ID, recipient, subject, body, From address and budget**. Do not edit an uncertain send into another message. `status` checks without resending or creating another charge; it can release expired reservations. A definitive initial provider rejection refunds the hold. Unconfirmed sends expire after 24 hours; a background task normally releases the hold within the next minute, or a status check releases it, without automatically resending; check Sent and the recipient before composing again. Deleting or transferring mailbox history cannot erase the original payer's charge or free-allowance usage.

Replies use the original receiving address when it is still owned; an explicit `--from` wins. If that address is unavailable, the CLI names the default-sender fallback before sending.

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

These examples inspect or preview. Address creation/changes require `--buy` to charge credits. `co email quota --buy --idempotency-key <unique-key>` purchases exactly one plan-defined increment; reuse the key on retry. History deletion requires `--yes`; received history is the default scope and `--include-sent` also deletes sent logs; it does not reset the monthly allowance or remove send receipts. The address is retained.

Existing commands cover custom names, account default, sharing/revocation and tier upgrades. `co email setup` replaces no other address. `change` resolves the owned address record ID and previews the backend's current price; names/domains are normalized before pricing.

## Transfer one address

```sh
co email transfer prepare you@mail.openonion.ai --to <recipient-public-key> --out request.json
```

The named recipient runs this using their own selected identity:

```sh
co email transfer accept request.json --out approval.json
```

The original owner previews completion:

```sh
co email transfer complete approval.json
```

After reviewing that preview, the owner completes the transfer:

```sh
co email transfer complete approval.json --yes
```

Both keys sign the backend's exact five-minute transfer message, which names the address and its existing received/sent history. The first two commands write new mode-0600 files and refuse overwrites. Completion previews unless `--yes`; only then does it change ownership. The key-derived automatic address cannot be transferred. The backend verifies ownership and applies the address/history move atomically.

Server-synchronized archive, trash, stars, drafts, attachments and threading are not exposed by the existing email API. OO Mail's personal organization remains browser-local; this CLI does not invent server endpoints for those features.

## Validation

Protocol signatures, expiry, tampering, identity selection, direct reads, retry-key reuse, management previews, address pricing and partial bulk failures are covered by offline tests. An independent AI review checked user workflows, output fidelity, signature safety and permission boundaries. The real account was connected in OO Mail; CLI/web message IDs and body agreed, and one self-addressed UTF-8 web send appeared once in Sent and once in Inbox. Purchases, address transfers and history deletion were verified with mocks and local dummy identities, without executing them on the real account.
