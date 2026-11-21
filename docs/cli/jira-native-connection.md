# Jira native connection

In a local terminal, run `co rem sources connect jira` to select scope by number.
No YAML is needed; the schema below remains available for scripts with `--config`.

```yaml
project: DEMO
issues: [DEMO-1]
history: false
```

Omit `issues` to approve the whole named project. Setup checks account and project
metadata; selected issues are verified with only their project field requested,
not their body. A verified empty project is valid. A first selected-issue read
that omits selected keys is incomplete: valid records remain and the cursor does
not advance. Later incremental zero results mean no observed change, not project
completion or issue deletion. New people/projects are stub-mapped inside normal
sync without another init; authored pages and normal page protections remain.
The existing Jira transaction and output writer locks coordinate independent CLI
and REM use, even when CLI state directories differ.

See [shared setup, consent, maintenance and recovery](rem-native-sources.md).


For account setup or an invalid site URL, read `co jira verify --help`.
It gives the exact saved URL/email/key commands and a site-root example.
Use `co rem sources connect --help` for the REM connection workflow.
Local constructor configuration errors preserve their fixed repair instructions;
remote/provider failures remain sanitized.
