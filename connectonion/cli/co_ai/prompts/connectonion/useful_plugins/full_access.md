# full_access

Full access skips routine tool approvals under a positive, bounded
`turns_left` budget. Each completed user-driven Agent turn consumes one unit;
zero returns the session to Auto.

It does not create a prompt, start another turn, extend itself, or decide that
an objective is unfinished. Only the exact public mode ID `full-access` is
accepted. Provider-private permission values are translated at their adapters.
