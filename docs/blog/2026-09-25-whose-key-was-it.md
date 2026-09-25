# Whose key was it

Someone adding error handling to a candidate-search job wanted to see what a
bad key looks like, so they passed one on purpose:

```python
llm_do("say hi", api_key="bad-key")
```

```
LLMAuthenticationError: The managed provider credential for co/gemini-3.8-flash
was rejected. This is a service-side configuration problem; retry later or
contact OpenOnion support.
```

The key was theirs, and it was wrong. The message told them the opposite: that
the fault was ours and that waiting would fix it. Someone who had not typed the
bad key deliberately — a server re-provisioned with a stale `.env`, say — would
have waited, then opened a support ticket, for a problem one `co auth` solves.

The message was written for a real case. oo-api holds the upstream provider
keys, and when Anthropic or Google rejects one of those, nothing on the
caller's machine can help. The mistake was assuming every 401 on a `co/` model
was that case. oo-api sends 401 for two different reasons: its auth check
rejecting the caller's own token ("Invalid token", "Token expired. ..."), and
a provider rejecting its key, which it passes through with a label
("Anthropic API error: 401 - ..."). Same status, opposite advice. The client
had been reading the number and ignoring the sentence next to it.

Now it reads the sentence. A labelled upstream failure still says
service-side. Anything else says "Your OpenOnion API key was rejected", keeps
oo-api's short reason — an expired token and a moved account need different
next steps — and names `co auth` and `OPENONION_API_KEY`.

A second key problem turned up in the same afternoon. OpenRouter keys start
`sk-or-`, which also starts `sk-`, and the OpenAI check used to claim them.
That order was fixed a month ago and `co init --key` has had a test ever since.
`co create --key` never did, and writing one showed something worse than a
wrong variable name: once `~/.co/keys.env` had anything in it, which it does
after the first `co auth`, create copied that file and dropped the key the
user had just typed. It now writes the key under the provider's name,
replacing any global value of that name, since it is the one the user asked for.

Both bugs are the same lesson from two directions. An error, or a config file,
is advice about whose move it is next. When two causes share a symptom — one
status code, one `sk-` prefix — the code has to look one step further before it
tells anyone what to do, and the test has to fake the response exactly as the
server sends it, or it will happily confirm the guess.
