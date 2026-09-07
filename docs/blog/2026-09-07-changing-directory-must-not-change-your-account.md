# Changing Directory Must Not Change Your Account

Draft for 1.8.4; publish after release acceptance.

A mailbox command worked in one directory and asked for authorization in
another. Both commands used the same computer and the same intended account.
The difference was a project `.env`: package startup loaded it before the global
credential file. By the time Gmail or Outlook ran, an old token already looked
like a deliberate process override.

Changing the order inside one mail command would leave the startup problem in
place. It would also miss Drive, both calendar clients, YouTube and the auth
writers. The implementation instead gives them one selected env source. Global
`keys.env` is the default; `co --env-file PATH ...` explicitly selects another
file. That rule covers application settings as well as OAuth credentials.

The next problem was less visible. Picking each field independently could join
one account's token with another account's email and scopes. The resolver now
chooses complete account records. Missing scope metadata stays unknown until
the provider supplies evidence. It does not turn into an invented grant or an
automatic permission denial.

Refresh is a read-and-write operation. Two CLI processes can start with the same
refresh token, and Microsoft can rotate it after use. A file lock now covers the
refresh and atomic save. A waiting process can reuse a newer credential for the
same account; an account change stops the old writer. A process-only override
stays in memory, preserving credentials stored for another account.

This changes a documented behavior from 1.8.3. Existing project files remain,
but callers that want them must select them. The migration is visible in the
command line, where the account choice can be reviewed and repeated.
