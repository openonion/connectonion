---
description: An agent served by co host had one access policy, and the same agent answering on WhatsApp had none, so a deployment kept a second file of phone numbers and roles. WhatsApp people and groups are now entries in the same trust lists, checked by the same host.yaml trust, with per-level tools in restricted.
tags: [Trust, WhatsApp, Host]
---

# One policy for web and WhatsApp

A support agent answers customers on WhatsApp and staff on the web. The
customer wanted admins to tell the bot a contact's details in chat and have it
write them to the helpdesk, while everyone else stays read-only.

On the web, that is one policy: `host.yaml` trust plus the `.co/` lists, keyed
by agent address. On WhatsApp there was none. The deployment kept its own
`contacts.lst` of phone numbers and roles, and the handler script read it. That
meant two policy files for one agent, and nothing in the framework could answer
"may this person do X".

Now a WhatsApp person is an entry in the same lists:

```bash
co trust admin add whatsapp:+61400000000
co trust add whatsapp:+61400000001 --whitelist
co trust add whatsapp:120363000000000000@g.us      # a group: its members are contacts
```

What changes:

- **The phone number comes from the linked-device session,** not the message.
  A LID is resolved through the session's own map. A sender with no single
  known phone is a stranger, and that holds even in an admitted group, so a
  group's level never stands in for someone we could not identify.
- **`co whatsapp consume` and a Host's `listen:` channel check the sender**
  against `trust:` before anything runs:
  - `strict` answers admins and the whitelist;
  - `careful` adds contacts;
  - `open` answers everyone not blocked.

  The command then gets `CO_CALLER_ADDRESS` and `CO_CALLER_TRUST`, the same two
  variables a restricted web turn gets. Inherited values are cleared first, so
  a stray `CO_CALLER_TRUST=admin` in the environment never reaches a stranger's
  turn.
- **`restricted:` can give a level more tools:**

  ```yaml
  restricted:
    allowed_tools: ["Bash(python read_ticket.py:*)"]
    admin:
      allowed_tools: ["Bash(python write_contact.py:*)"]
  ```

  A level can only add tools. It cannot change the prompt or the environment.

One thing to know when upgrading: a project with a `.co/host.yaml` that uses
`consume` now stops answering WhatsApp senders its trust does not admit. On
`careful`, the default, that means strangers. `consume` says so when it
starts, and names the command that admits someone.
