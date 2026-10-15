# A contact fact is the person's own or Unknown

Status: implemented on branch `rem/init-quality` (#2348, 2026-10-15), not yet released.

## The problem

A wrong phone number is worse than none: the user calls a stranger. Contact
facts were removed by a denylist (another sender's signature number went;
anything else stayed), and the contacts audit of the 1.9.2b3 notebook found:

- **P1** A facilities manager's mobile on Nina's page, from an estate notice
  she forwarded: "Thank you for your understanding as we continue…" was read as
  a sign-off, so the block under it became her signature.
- **P2, E2** "call Larry 0405…" on Ody's page, from a Luma host copy; Ody's
  Luma relay address had joined his page by display name and become his Email.
- **C1–C4** Company filled from any older domain: UNSW for Ziming, who had
  graduated and writes from Hotmail; UNSW for Sam, who writes from his own
  company; seven students got their university as employer; an agent's
  `mail.openonion.ai` address named ConnectOnion.
- **T2** Tamara's Last contact was a kitchen-etiquette note to about 30 startups.

## Decision

A contact fact stays only when the material shows it is the person's own.
Otherwise the field says `Unknown`.

- **Email**: one the page already carried (the map's, or the user's own
  `co rem stub`), or one the person is named at in a From, To or Cc. Never a
  relay (Luma, `lu.ma`, Airbnb's message relay); a relay keeps a map group of
  its own.
- **Phone**: a mail the person sent (or a relay message under their name, with
  their name on a line beside the number) shows the number, and nobody else is
  named to call beside it. A number cited to a published web page stays.
- **Extraction** reads no facts from relay, system or notice mail, takes a
  sign-off only as a line of its own, and opens a phone only in a block signed
  with the sender's name. Only rows the person wrote or signed are restored
  after the turn.
- **Company** from a domain uses only the newest address they write from, and
  never a mailbox provider, a relay, an agent address or a student address
  (`student.` / `ad.` subdomains, an ID as the local part).
- **Last contact** is the last human mail between the user and them: not a
  notice, and not a mail to more than five recipients.
- The same check runs on a sync's one-page turn as on an investigation, and
  `review.json` lists what went under `contacts_unverified` and what filled
  Company under `company_from_domain`.

## Why not let the model judge

The extractor handed the turn every number it found and promised to put back
any the page left off, so one bad read became certain: the facilities manager's
mobile came back onto Nina's page after the turn had dropped it. A turn cannot
see that the block it read came from a forwarded notice. Whether a
number is in a mail the person sent is a fact code can check, and checking it
costs nothing. Judgement stays where it belongs: which of the person's own
numbers is their mobile, and what their role is.

## Cost

Some true facts become `Unknown`: a number someone gives only inside a quoted
reply, or a work address they never wrote from. That is the intended trade.
The user can add one with `co rem stub`, and a page already carrying an Email
keeps it.
