# A Jira CLI that stops at the selected scope

A Jira command is easy to make look useful by listing a project, then quietly reading more than the user chose. That is a poor fit for a private local notebook: the useful boundary is not merely read-only access, but a visible, bounded selection before any source record is written.

This change starts with the small path a person can inspect in a terminal. `co jira verify` confirms the account without displaying the token. `co jira projects` lists accessible project keys, and `co jira issues` requires explicit issue keys in one project. `co jira sync` then writes only those selected records to the local Jira source directory.

The earlier team implementation also contained incremental checkpoints, history collection, and shared lifecycle work for other providers. Those are deliberately not included here. The first Jira PR needs a command surface that is discoverable, reviewable, and honest about what it does before broader REM integration is proposed.

The implementation is covered by offline pagination, validation, authentication, and selected-scope tests. Final verification still needs an authorised Jira account, terminal screenshots, the CLI audit, and a normal-permission pytest run on the final candidate.
