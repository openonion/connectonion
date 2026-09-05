# The fallback that nobody could vouch for

The first version of the You.com tools had a feature I was quietly proud of:
if the API key was missing or rejected, search would silently retry against
an unauthenticated "free" endpoint and still come back with results. Graceful
degradation — the agent never sees a dead end.

The review asked one question about it: *where is that documented?* Not in
code comments, not in a doc page — anywhere. What page at You.com says the
`profile=free` parameter exists on the REST API and permits this use? I went
looking for one to cite, and there wasn't one. The endpoint I was calling
undocumented-and-unauthenticated was one I could vouch for only by
observation.

That changes what the feature is. A fallback I can point to in a vendor's
terms is a feature; a fallback I can't is a liability that happens to work
today — for some definition of "works", since every retry hits a server that
never promised anything, with results nobody reviewed, going back to an agent
that believes it did a real search.

## The same answer from three tools

The fix was subtraction. The free-search path is gone. A missing or rejected
`YDC_API_KEY` now returns the same shape from all three tools:

```python
{"error": "auth_required", "message": "YDC_API_KEY is not set. ..."}
```

No retry, no second endpoint, no request leaving the machine. The agent, or
the human behind it, learns immediately that the tool needs a key — which is
the only honest thing to say, because it does.

Removing the fallback also removed the reason the code had state at all. The
old version was a class: constructor read the key, built a header dict, kept
a timeout and base URL, and carried them through every call. The free-search
retry was the main consumer of that state. As plain functions —
`youcom_search(query)`, `youcom_contents(urls)`, `youcom_research(query)`,
matching `send_telegram` and the rest of `useful_tools/` — each call reads
the key when it happens, so a key exported mid-session just works, and there
is nothing to construct and nothing to go stale.

The one piece I kept from the class version is the failure envelope: nothing
raises past the tool boundary. Every failure is a dict with an `error` key —
`auth_required`, `payment_required` (the x402 case an aware client settles
elsewhere), `network_error` named by exception class rather than exception
string, because the string can contain the request URL and the header has the
key in it.

## What it teaches

"Opt-in" is only opt-in if *off* does something safe and explicit. A tool
that quietly degrades to an undocumented path isn't off — it's on, in a mode
nobody chose and nobody can defend in review. The question "can you cite the
page that permits this?" is a good test of any fallback: if the answer is no,
the fallback isn't a feature, it's a deferred incident.
