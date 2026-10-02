---
description: A 58-second GitHub scan exposed the cost of finding reviews on old PRs. Why Co’s first listener reuses gh and keeps collection separate from task routing.
tags: [GitHub, Inbox, CLI]
---

# The first GitHub scan took almost a minute

The owner was reading a REM project page and noticed that GitHub was missing. An issue or a PR discussion had no route into the project's context; someone still had to notice it. He wanted the same first step as WhatsApp: a listener that puts messages in the inbox, then lets a consumer wake Codex or route the work.

The first real catch-up scan made that small request feel less small. I pointed the adapter at the landing-page repository, starting from September 25. It collected 61 PR and comment records and saved its checkpoint. The scan took 58.09 seconds. Our proposed polling interval was 60 seconds. A listener that spends nearly a minute catching up has very little room to pretend that polling is immediate.

The expensive part came from a question about reviews. Could the listener first find recently updated issues, then read only those PRs? That would keep a quiet repository cheap. I put an old closed PR into a test, left its issue update timestamp in 2020, and gave it a newly submitted review. A consumer still needed to see that review. Filtering candidates by the issue timestamp would discard the PR before asking for its reviews.

So the scan reads reviews for every PR, including closed ones. That is the uncomfortable boundary of this implementation: the case that prevents missed work also makes the collector expensive. The real scan gave us a number to attach to that tradeoff. I can call this an experimental listener for small repositories; I cannot claim it is ready to poll a large project's full review history every minute.

The owner had also asked whether Co could use GitHub's official CLI credentials. It can: the adapter calls `gh api`, leaving the login and credential store with gh. That solved setup, but it did not solve delivery. A successful API read is not yet work that another program can safely take. The listener records its first-start baseline before fetching, writes messages through the existing durable inbox, and advances the repository checkpoint only after the scan's pages and deliveries finish. Repeating the scan sees the same resource/version IDs instead of scheduling the same observation again.

That gave us a useful stopping point. The listener can recover still-existing activity after downtime, and a local consumer receives the repository, issue or PR number, original content and source link. It keeps its execution log local. It cannot recover a comment created and deleted between polls, or reconstruct every intermediate edit. Those are consequences of reading snapshots, not promises another retry loop can fix.

A webhook transport would change the collection side: precise actions could arrive without rereading every PR, but GitHub would need a reachable receiver, a separate signing secret and missed-delivery recovery. If larger-repository measurements make polling impractical, that is the next decision. The inbox and the program consuming it can stay where they are.

This PR prepares that boundary for a future preview. REM ingestion follows separately. The missing GitHub entry will also appear on the README, docs and landing-page walls, marked as upcoming; the sixty-second scan is why the label still matters.
