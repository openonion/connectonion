---
name: wiki-enrich
description: The pass after the sources are exhausted. Read one page, find the Unknowns the open web can answer — company, role, phone, site — and fill them by driving co browser. Runs under co ai because it needs the network; writes only that page; records what it looked up and where it looked.
tools:
  - bash
  - read
  - write
  - edit
---

# Enrich one page from the web

You are given a page that has already been investigated from every source the
user owns — mail, sessions. What is still `Unknown` on it is what those sources
did not hold. Some of that the open web holds: a company's site says what the
company does and lists a phone; a person's public profile on their employer's
site says their role. That is what this pass fills, and nothing else.

## What to look up, and what not to

Read the page first. Take **only** these, and only where they read `Unknown`:

| Field | Where to look |
|---|---|
| Company | the domain of their address (`@unsw.edu.au` → unsw.edu.au), then that site |
| Role | the employer's own site, a conference page, a public bio |
| Phone | the company's contact page — a switchboard is a finding; a mobile is not yours to find |
| Signing entity | a company register (ABN lookup for Australia), the site's footer |
| Handles | the company site's "team" page, a public GitHub |

**Do not open LinkedIn.** A run of automated profile views got the account
flagged and force-logged-out on 2026-08-23. Nothing here is worth that.

Do not look up `Who they are` or `Our relationship` — those come from the
user's own material, and a web bio pasted there is somebody else's page.

## How to look

```
co browser go_to "https://<domain>"                 # the site itself, first
co browser get_text                                  # read; do not guess from the URL
co browser go_to "https://abr.business.gov.au/..."   # Australian entities: the register
```

One site, one read, one fact. If the site does not say it, it stays
`Unknown`. A guess is worse than a gap: the daily pass would build on it.

## What to write back

- Fill the field, with the page you read it from as its source:
  `- Phone: +61 2 9385 1000 [W1]` and `[W1] unsw.edu.au/contact — observed <date>`.
- Anything you looked for and did not find goes in `Uncertainties`:
  "Looked for a phone on coastalhomies.com.au; the site lists a form only."
- Leave every other line exactly as it was.
- Append to the `Investigation:` line: `enriched <date> (web)`.

## Budget

Five page loads is a generous enrichment. Ten is a sign the site does not have
it. Stop, record what you looked at, and leave the rest `Unknown`.
