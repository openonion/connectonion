# A parameter that decided one thing

"Not Feishu. Give me Lark. Lark is ours, Feishu isn't."

I had run `co auth feishu` to create an application for a release test, and the
owner's correction was about product identity, not code. But it turned into a
code finding within a minute, because the obvious next move — run `co auth lark`
instead — produced the same `open.feishu.cn` link.

## The brand was known and not used

`handle_feishu_auth(brand=...)` had a `brand` parameter. `co auth lark` passed
`"lark"`, `co auth feishu` passed `"feishu"`. So far so good.

Then I read what `brand` actually did. It decided which prefix to write to the
env file — `LARK_APP_ID` or `FEISHU_APP_ID` — and that was all. Everything
around it was hardcoded to Feishu:

- the accounts domain the SDK was started on
- "Creating a Feishu application"
- the remedy when a registration came back half-empty: `Next: co auth feishu`
- the reuse command offered from lark-cli's config: `co auth feishu --app-id …`

Two of those are instructions a person is told to run. A Lark user who followed
them would run the wrong command, which would print the same wrong link, which
would tell them to run the wrong command.

## Why it worked anyway, which is why nobody noticed

The SDK's flow begins on Feishu regardless, then polls. When the poll sees the
scanner's tenant is Lark, it quietly switches domains and issues a new link.
So a Lark user who scanned the Feishu link *did* end up with a Lark application.

That is what made this survive. A bug that produced a failure would have been
filed the first day. This one produced a success with the wrong name on it, and
"it says Feishu but it works" is exactly the kind of thing people stop mentioning
after the second time.

The fix is one keyword argument: `domain="https://accounts.larksuite.com"` when
the brand is Lark. `co auth feishu` still passes nothing, on purpose — the SDK's
own Feishu-to-Lark switch is what makes a Feishu link work for a Lark scanner,
and a test now holds that in place so nobody "simplifies" it away.

## The offered command uses better evidence than the typed one

The reuse hint reads lark-cli's config and offers `--app-id` for an application
that already exists. It said `co auth feishu --app-id …` unconditionally.

The right verb is not what the person typed. lark-cli recorded each app's brand
when they logged in there, and that record is better evidence than the word they
chose just now. So the hint takes its verb from the app: `co auth feishu` on a
machine whose lark-cli only knows Lark apps still prints a command that works.

## The question this answered

The owner then asked the question I had been circling: if lark-cli is already
authenticated, can we just copy its AppID and secret into our env file?

Half of that already happens — `co auth lark` reads the ids and offers them. The
other half is refused on purpose. lark-cli keeps the secret in the macOS
keychain and its config holds only a reference to it. Copying a keychain entry
into a plaintext env file is a downgrade wearing the word "import" (#1497). One
scan with `--app-id` obtains the same credential with the platform's consent
instead of the operating system's, keeps the app's groups and permissions, and
takes ten seconds.

So the answer is yes — and the mechanism is a scan, not a copy, because the
thing being protected is worth ten seconds.

## The pattern

A parameter that decides exactly one thing, surrounded by constants that should
have been decided by it, is a refactor that stopped halfway. It looks complete
because the parameter exists. The tell is a `brand` — or a `mode`, or a
`channel` — that appears in the signature and in one `if`, and nowhere else.
