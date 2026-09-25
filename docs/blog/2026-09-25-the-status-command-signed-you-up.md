# The status command signed you up

`co wiki init` has a recovery tip for when it cannot open a mailbox: "Check
mailbox access with co auth status." It is the kind of line you follow without
thinking. Status commands look; they do not change anything.

On a fresh machine, running it printed "Welcome", generated a master keypair,
created an OpenOnion account and wrote a token to `~/.co/keys.env`. On a
machine that was already signed in, it quietly authenticated again and
rewrote the file. And `co auth logout`, the one you would run to get out, did
exactly the same thing: it logged you in.

Nobody wrote a status command that signs people up. `co auth` takes one
optional word. The code checked that word against the services it knew,
google, microsoft, feishu and lark, and anything else fell to the `else`
branch, which was the bare `co auth` sign-in. `status` was not a service, so
it was "anything else". So were `logout`, `login`, and every typo. The `else`
was written for the case where no word was given, and it caught every word
nobody had thought of.

That is why a doc and a tip could point at a command that never existed and
nothing looked wrong. The command ran, printed a friendly screen and exited
0. The CLAUDE.md in the repo documented `co auth login`, `co auth status` and
`co auth logout` side by side, and all three did the same thing.

The fix makes the words mean what they say. `co auth status` reads the
identity, whether `keys.env` holds a token, and which Google, Microsoft,
Feishu and Lark connections exist. It creates nothing and makes no network
call. On an empty HOME it says "Not signed in" and names `co auth login`.
`co auth login` is today's bare `co auth`. `co auth logout` asks first, then
removes only the token. It never removes the keypair, because the keypair is
the account, and the next login should bring you back to the same address.
Any other word now exits 2 and lists the valid ones.

The tests run on the isolated HOME every test gets, with sign-in replaced by
a function that fails the test if it is called. A status that tried to sign
in would fail loudly there instead of passing by accident.

The lesson is about the fallback branch. An `else` that performs the most
powerful action in the command is a default nobody chose on purpose. When
the input is a word from a person, the safe fallback is to refuse and list
the words you know.
