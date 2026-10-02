---
title: Small integrations, direct feedback
description: How ConnectOnion is expanding experimental CLI integrations while giving users a direct feedback channel and making validation status visible.
tags: [CLI, Integrations, Product]
---

# Small integrations, direct feedback

A Google Drive download can export a spreadsheet, but an agent preparing a customer list also needs to append rows and update cells. Reading a Google document is useful; creating a document and appending a report makes another everyday workflow possible. Those small operations are the starting point for a broader ConnectOnion logo wall.

The owner chose to build more experimental integrations now and improve them according to what people use and where they report problems. The first development branch implements 23 service groups. Google Docs, Sheets, Slides and Forms come first, followed by Microsoft files, workbooks and tasks, notes, project management, CRM, billing reads, design reads and two official CLI adapters. The [umbrella issue](https://github.com/openonion/connectonion/issues/2153) records the remaining queue.

The scope of each experiment is deliberately small. Sheets reads ranges and writes rows using RAW values. Docs appends plain text to the first tab. Slides replaces placeholders in an existing presentation. Forms accepts the provider's question-update request. Stripe only reads billing objects, and Figma only reads designs. GitHub reuses gh's login and DingTalk reuses dws's profile. A universal connector framework and complete provider coverage would delay those useful first workflows.

Each API command returns provider JSON, including pagination fields. Writes show their proposed body without authenticating; the caller must repeat the command with --yes to make one request. We avoid automatic mutation retries because a timeout can leave the caller uncertain whether the service applied a write. The caller should inspect the service before repeating it. This makes the current boundary visible in --help and in the [integration guide](/cli/experimental-integrations).

Account setup remains part of the experience. Microsoft's workbook API requires Files.ReadWrite even for a range read, so the broker needs another delegated permission and existing users must consent again. Google native document APIs must be enabled in the OAuth project's Google Cloud configuration. Other connectors need provider tokens with access to the target workspace or records. Those requirements are written beside the experimental commands.

The first branch passed request-contract and CLI regression checks locally, built an installable wheel, and built the expanded website wall. The agent mailbox was read successfully and the GitHub adapter returned valid JSON. Every provider has not been checked with a live account: the current CLI environment has no connected Google account, and DingTalk's live read could not succeed in its current profile. This branch has not been released on PyPI. The experimental wall links the branch's installation and setup instructions instead of implying availability in the stable package.

Feedback accompanies the experiment. Every CLI invocation includes a GitHub issue link, the Discord invitation and aaron.xie@mail.openonion.ai on stderr. Report links include version context without uploading environment values or logs. The maintainer's mailbox collector stores matching feedback messages, preserves unread state and deduplicates receipts before advancing its cursor. It does not send replies or turn email instructions into actions.

We will deepen the workflows people use and fix the errors they report. Repeated demand for token renewal, deeper document editing or additional pagination can justify extending an individual connector. The guide, command help and logo wall should continue to state the exact workflow that exists and the validation it has received.
