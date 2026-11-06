---
title: Asking for credentials to say not supported
date: 2026-10-23
description: A CLI verb should refuse unsupported provider capabilities before demanding credentials for that provider.
---

An operator ran `co inbox edit` against a Discord message in a clean workspace
where Discord credentials had not been configured yet. Instead of learning that
message editing is not implemented for the Discord inbox adapter, the CLI exited
with code 3 (`EXIT_CONFIG`) and asked the operator to configure a Discord bot
token first.

Had the operator stopped what they were doing, generated and stored the token,
and re-ran the same command, the CLI would have reached the second gate and
refused with exit code 1 because the Discord provider does not implement `edit`.
The credential check was running ahead of the capability check, turning a static
fact about the adapter into a misleading setup errand.

In `listen_commands.py`, `handle_edit`, `handle_delete`, and `handle_react`
resolved the provider instance and immediately called `_configured(name,
sends=True, p=p)` before checking whether the provider exposed `edit`, `revoke`,
or `react`. That ordering made sense when every registered provider supported
the full verb surface, because a missing credential was the only thing standing
between the caller and the network call. Once providers with partial verb
support joined the table—Discord, Telegram, Feishu, and Lark—the assumption
broke.

We inverted the two checks so each handler inspects the provider's capability
(`getattr(p, "edit", None)`, `getattr(p, "revoke", None)`, and `getattr(p,
"react", None)`) before calling `_configured`. When a provider does not
implement the requested verb, the CLI immediately exits with code 1 and names
the upstream API endpoint and next action, whether or not credentials exist in
the environment.

Twelve parametrized unit tests across Discord, Telegram, Feishu, and Lark
(`test_unsupported_verbs_refuse_without_credentials_before_asking_for_them`)
verify that `edit`, `delete`, and `react` refuse with exit code 1 in an
unconfigured environment, and all 29 tests in
`tests/unit/test_inbox_edit_and_delete.py` pass.

Validating prerequisites in the wrong order wastes user trust when the first
check asks for secrets that the second check will never use. Capability checks
belong ahead of credential checks whenever capability is known statically.
