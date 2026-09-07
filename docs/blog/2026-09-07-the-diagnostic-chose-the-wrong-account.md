# The Diagnostic Chose the Wrong Account

Draft for 1.8.4; publish after release acceptance.

The identity guide was supposed to settle an argument between two addresses. A
configuration file named one account, while a running agent could answer as
another. Before changing either, the guide told the reader to inspect the token
that paid for model calls.

During the 1.8.4 review, that instruction became part of the problem. One command
decoded a token from the current directory's `.env`. The next used `$KEY`, which
the instructions had never defined, against a hardcoded production endpoint.
Neither step established that it was examining the environment of the process
whose bill the reader wanted to understand.

It was possible to make the shell example executable by assigning one variable.
That would have repaired the visible error while preserving the mistaken choice
of account. The release was deliberately removing implicit project-env loading.
Following the old guide from a project directory would still inspect that
project's file, even when the CLI itself had used global configuration.

The guide also described deployment as copying the operator's account wholesale.
The current implementation had moved on. It preserved a key already on the server,
authenticated that actual key, and supplied the server account's token and email.
Default deployment filtered personal credentials. A reader following the old
explanation could try to repair behavior the software was already preventing.

The correction began by separating three questions. Which address does the live
Host serve? Which account does the selected model token name? Which source supplied
that token? None can be answered safely by borrowing the answer to another.

The rewritten diagnostic uses the same env selector and backend resolver as the
application. It defines the token in the Python process, checks an existing account
with a read-only GET, refuses redirects, and prints account identifiers and balance
without printing the token. Decoding the JWT remains only an inspection step; the
backend lookup is what checks it against the configured service.

I exercised both copies of the example with an isolated env file and a mocked
custom backend. That made the important mistake observable without sending a real
credential anywhere: the request had to reach the configured test origin, and the
output had to omit the token. The guide and packaged skill now run the same
diagnostic rather than offering two almost-matching recipes.

The address mismatch itself does not always need a repair. A deploy can preserve
an older server key whose address differs from a newly derived candidate. Deleting
that key to make a note agree would create a different agent. The guide now tells
the reader to establish what is running before deciding what should change.

A diagnostic is another client of the system. If it selects credentials or an
endpoint differently, it can produce a convincing answer to the wrong question.
Making the example run was necessary. Making it inspect the same account was the
part that made it useful.
