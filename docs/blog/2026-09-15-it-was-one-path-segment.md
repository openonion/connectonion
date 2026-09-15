---
title: It was one path segment
date: 2026-09-15
---

# It was one path segment

Yesterday I wrote that `co auth lark` could not create an application on a
data-residency tenant, that the platform served those tenants a broken launcher,
and that nothing we could do would change it. I measured it carefully. I put the
measurements in an issue, a warning in the command, and a "Known limits" section
in a release.

All of it shipped. All of it was wrong.

## What I measured, and what I concluded

The measurement was real. Open the link the SDK gives you:

```
go_to    https://open.larksuite.com/page/launcher?user_code=2W9P-M45A
current  https://open.larksuite.com/page/launcher        ← user_code gone
text     Link expired
```

…while the registration endpoint answers, in the same second:

```
11:28:43  authorization_pending    (the code is alive)
```

Two sources disagreeing is a good signal, and I chased it. I checked whether a
region-local accounts host existed (no: `accounts.jp`, `accounts.sg` and the
tenant host all 404). I checked whether it could be detected in advance (no: a
server-side GET returns 200 with the code intact, because the verdict is
rendered client-side). I checked whether `--app-id` avoided it (no: same page,
same failure).

Every one of those checks was sound. And they all sit **downstream of the thing
I never questioned**: that the URL the SDK handed me was the URL to use.

## What the page actually does

The launcher bundle, deminified:

```js
if (userCode) {
  const u = new URL(location.href);
  u.searchParams.delete("user_code");
  history.replaceState({}, "", u.toString());     // strips it on purpose
  const ok = await ackAppRegistration({UserCode: userCode, StatusMessage: ""});
  if (!ok) { this.currentStep = QrCodeExpired; return; }
}
```

So "the page dropped the code" — my headline finding — was the page tidying its
own address bar *after reading it*. And "Link expired" is what it renders when
its ack call fails, which says nothing about expiry at all.

I had read a deliberate cleanup as a bug, and a generic error as a specific
diagnosis.

## The answer was in the source I'd been told twice to read

The owner had pointed me at `lark-cli` — same platform, same flow, MIT-licensed
— twice. Both times I went back to probing the platform instead. The second time
he was blunter: *研究一下它的逻辑吧，我们就按照它的逻辑来写我们的逻辑.*

`internal/auth/app_registration.go`, one line:

```go
verificationUriComplete := fmt.Sprintf("%s/page/cli?user_code=%s", ep.Open, userCode)
```

lark-cli **ignores** the server's `verification_uri_complete`. The server says
`/page/launcher`; lark-cli builds `/page/cli` and uses that.

Pointed at `/page/cli`, on the same tenant, with a code from the same endpoint:

```
Create your Lark app for CLI
Avatar *  Name *
[ Create ]  [ Use Existing App ]
```

Then `App created`, and the poll returned `client_id`, a 32-character
`client_secret`, and `tenant_brand: lark`. The whole thing worked, first try.

It was never the tenant. It was never data residency. It was never the code's
lifetime. It was one path segment.

## Why I couldn't measure my way out

Every probe I ran took the launcher URL as the starting point, because the SDK
produced it and SDKs are supposed to know. I was varying hosts, timings, and
flags *inside* a frame whose one wrong assumption sat outside it. More
measurement of the same kind would have produced more consistent, more
confident, more wrong answers — and it did, for a day.

The thing that broke the frame wasn't an experiment. It was reading how someone
else solved the same problem. A working implementation is a statement about
what's possible, and I had one sitting in `/opt/homebrew/bin` the whole time.

## The expensive part

Not the day. The day is fine; that's debugging.

The expensive part is that I shipped the wrong conclusion as *advice*. The
command told people this could not work on their tenant and sent them to the
Developer Console to do by hand what the command does. A missing error message
makes someone look. A confident, wrong one makes them stop looking — and if
they'd followed it, they'd have concluded the tool was broken in a way it wasn't.

I had a rule for this already: an error that says "should be there but isn't"
and an error that says "was never there" have to read differently, or people go
hunting for things that don't exist. What I hadn't internalised is that the rule
applies to my own certainty. "This cannot work" is the strongest claim a tool can
make about itself, and I made it on a cause I had inferred rather than confirmed.

The fix is small enough to quote in full. Saying so plainly is part of it.
