# The secret you cannot ask for

Connecting a Feishu bot took eleven steps, and step four was the one that
decided whether anyone finished. Open the developer console. Create a
self-built application. Find the permissions page, add three scopes whose names
you have to get exactly right. Find the events page, choose long connection,
subscribe to one event. Publish. Then go to the credentials page, copy a string
that starts with `cli_`, copy a second string that is a password, and paste both
into a file in your home directory.

The eleven steps are not the problem. The problem is that nothing tells you when
you have got one of them wrong. A missing scope is not an error at setup time.
It is an error an hour later, in a log, when someone in a group @-mentions the
bot and nothing happens.

So we started designing the smallest thing that could fix that: a command that
opens the right console page, takes the secret on stdin so it never reaches
shell history, and then verifies — fetches a token, names the bot back to you,
checks the scopes against the list, and says which one is missing before you
walk away. One paste, then certainty.

The paste seemed irreducible. We checked. `application/v6` has an API that
returns an application's information, and its response has app_id, name, avatar,
owner, scopes, status — and no secret, which is correct; an API that hands out
credentials for an app you name is not an API, it is a vulnerability. It also
requires a `tenant_access_token`, which you can only get if you already have the
secret. There is no way in. We wrote that down as a constraint and moved on.

## The tool we were copying had already solved it

Feishu's own CLI does the setup in one step. We assumed it was privileged — an
official tool with an official back door. There was even a string in the binary
that supported the theory: `/open-apis/application/v6/larksuite_cli_app/probe`,
an endpoint named after the CLI itself.

It is MIT licensed. The endpoint turned out to be a best-effort telemetry ping
fired after the credentials are already saved, whose result the code explicitly
discards. The actual flow is forty lines above it, and it is this:

```
POST /oauth/v1/app/registration
  action=begin  archetype=PersonalAgent  auth_method=client_secret
→ device_code, user_code, verification_uri

person scans, approves

POST /oauth/v1/app/registration
  action=poll  device_code=…
→ client_id, client_secret
```

The begin request carries no client id, no key, no signature, nothing that says
which program is asking. It is OAuth 2.0's device authorization grant pointed at
app creation instead of login: the application is created by the person
scanning, in their own tenant, and the credentials are handed to whoever started
the flow. It is documented on the platform, under a heading we had not read, and
wrapped in all three official SDKs — including the Python one this project
already depends on, as `lark_oapi.register_app`.

So `co auth feishu` is a QR code in the terminal, and then two names in
`keys.env`. No console, no copy, no paste. We had spent a day designing a good
way to survive a constraint that was not there.

## What the mistake was

Not "we missed a feature". We concluded from a name. `larksuite_cli_app` reads
like a private channel, and that reading was consistent with everything else we
knew: no API returns a secret, the console is the only place the secret exists,
the official CLI does something we cannot. Three true facts and one inference,
and the inference felt like a fourth fact.

The correction was cheap — the source was public, MIT, and one command away. It
was cheap the whole time we were not doing it. What made us not do it was that
the conclusion already fit.

There is a smaller lesson under it about what verification means. We had
verified the API surface exhaustively: every endpoint under `application/v6`,
every documented response field, twice. That work was correct and it answered
the wrong question. The question was not "does an API return the secret" but
"how does the tool that does this get it", and those have different answers
because the mechanism is not an API at all — it is an authorization flow.
Checking harder in the place you are already looking does not find the thing
that is somewhere else.

## What one scan still does not do

It creates an application; it cannot list the ones you already have, because no
API does. So `co auth feishu` always makes a new one, and choosing between them
happens on Feishu's own confirmation page, which is the right place for it.

The preset it creates comes with more permissions than a message bot needs, and
the SDK's `addons` parameter only adds — there is no way to narrow it. In a
company tenant an administrator may have to approve those. We have not tested
that, and we are not going to claim it works until someone has.

The manual path is still documented, one collapsed section down, for anyone
with an application already. It is the same eleven steps. They are just no
longer the first thing a new person sees.
