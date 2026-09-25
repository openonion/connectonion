# A label in one place is not a label

On 24 September we marked `co discord` and `co tiktok` experimental in
`co --help`, with a test to keep the label there. The next morning a tester
with a fresh profile went looking for it and found it exactly once. `co
discord --help` said "Discord bot as an inbox". `co commands`, the register
agents read to find a command, said the same. The docs page never used the
word. Only the one listing we had tested carried it.

The cause was a Typer detail: `co --help` prints a group's `short_help`, while
the group's own page and `co commands` print its `help`. We had set the first.
A person who went straight to `co discord --help` — the natural thing after
reading about it in the release notes — saw a finished product.

The same tester found the second half of the problem one level down. Every
inbox group has the same verbs, and their help was shared too: `co discord
edit` promised "Prints the edit's id". It prints that the verb is not
implemented. Only WhatsApp can edit, delete or react; on Discord, Telegram,
Feishu and Lark a user would set up a bot and a token to find that out.

So the label now lives in the group's own help, which every surface reads,
and the three verbs say "Not implemented for this provider yet" wherever the
provider class has no method behind them. The test does not list providers:
it asks each provider class whether it has `edit`, `revoke` and `react`, and
checks the help against the answer, so a provider that gains the method gains
the honest description with it. The docs pages for Discord, Telegram and
TikTok now open with the same status line the CLI shows.
