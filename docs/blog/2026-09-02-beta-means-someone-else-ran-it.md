# Beta means someone else ran it

1.8 went through eight alphas. Each one shipped a piece: the egress gateway,
the destination policy, the private browser runtime, the paid engine, the
Laptop Proxy, the SMS inbox. Each was measured by the person who built it, on
the machines they built it on.

`1.8.0b1` is the first cut where the whole path was run as a user would run
it: a laptop behind a home router, a server in a data centre, `co proxy
share`, `co remote-browser start`, a page, a bill.

## What the beta line means here

The versioning policy says `X.Y.0` is earned, not reached. A beta is the
step before that: the feature set stops moving, and the release exists to be
exercised by people who did not write it. The 1.8 list is now fixed —

- the Remote Browser leaves the internet from your computer, from anywhere,
- the paid Onion engine can actually pay (Onionwright 0.0.13),
- `co init` defaults to global credentials,
- a phone can join an Agent's SMS inbox without holding its key.

What is left before `1.8.0` is not code. It is the second and third run of
the cross-NAT path on machines nobody in this repository set up, and the
first run of the paid engine by someone who had to top up first.

## The one number

```text
co proxy stop; reload → ERR_TUNNEL_CONNECTION_FAILED
```

Every earlier measurement of this feature was a success number: the site saw
the laptop's address. This is the first release where the failure number is
in the notes too. Stopping the share breaks the tab. It does not fall back to
the data centre's address while you believe the traffic is leaving from home.
That is the property the whole feature is for, and it is now something a beta
tester can check in one line.
