# agent-identity

Verify the address a Host actually serves and the account that pays for its model
calls. Use this skill before sharing an agent link, after a confusing deployment,
or when two hosts report the same address.

```bash
co copy agent-identity
```

Then invoke `/agent-identity` in your agent. The skill queries `/info`, resolves
the selected global or explicit env file, and checks the existing token against
the configured backend. It explains why a preserved server key can differ from
a newly derived candidate and why duplicate hosts can repeat work.

It never asks you to print secrets or delete a key to make an address agree.
Default `co init` is global; selecting a project env file requires `--env-file`.
Default deployment strips personal credentials and uses the live server account.

See [Agent identity and the account that pays](../agent-identity.md) for the complete
read-only diagnostic and migration details.
