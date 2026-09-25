# An agent that cannot look things up

Most skills people write for Claude Code or Codex start the same way: "search
for the current version", "read the docs page", "check the changelog". Handed
to `co ai`, every one of them stopped at that line. `co ai` could edit files,
run shell commands and drive a browser, but it had no way to ask the web a
question. It would open `co browser`, type into a search box and screenshot
the results, a minute and a vision call to do what one HTTP request does.

So `co ai` now has `web_search` and `web_fetch` by default, and both are also
commands, `co search` and `co fetch`, for skills that shell out.

**Search needs a provider, and the obvious ones are gone.** Google's Custom
Search JSON API no longer takes new customers, and Bing's search API was
retired. The one search-capable key our backend already holds is Gemini's,
and Gemini can ground an answer in Google Search, but a grounded request
cannot also carry an agent's function tools. That ruled out switching it on
in the agent's own chat call. It did not rule out a second call. The backend
now asks Gemini one question with only the search tool attached, and returns
the short answer together with the pages it cited, their redirect links
resolved to the real URLs so the agent can go and read them. Google bills
per query the model runs, so we charge per query too, from the caller's
ConnectOnion credits, the way a model call is charged. It works the moment
you have logged in, with nothing to configure.

**Running out of money must not mean running out of search.** An agent in
the middle of a task that gets a 402 back has two bad options: stop, or
invent an answer. So the default engine, `auto`, falls through to DuckDuckGo,
which needs no key and costs nothing. It says so in the result: the credits
are used up, these results are from DuckDuckGo, here is how to get Google
back. It never swaps silently, because an agent comparing two runs should be
able to tell that the source changed. If you asked for `--engine co` by
name, you get the failure and one next step, `co search '…' --engine ddg`,
rather than a substitution you didn't choose. Your own Serper or Brave key,
when set, is spent before your credits.

**Fetch had to be safe before it could be default.** An agent follows URLs it
read on the web, and a web page is text anyone can write. "Now fetch
http://169.254.169.254/latest/meta-data/" is one sentence on a page away from
a cloud credential. So `web_fetch` resolves every host and refuses loopback,
private and link-local addresses on every redirect hop, because a public URL
can redirect inward. It also reports a redirect to another site instead of
following it. It returns Markdown rather than HTML: our older `WebFetch`
handed back raw markup, and most of a context window went on `<div>`.

What would make us revisit this: DuckDuckGo tightening its limits on
scripted use, which would take away the free floor, or Gemini grounding
becoming usable alongside function tools, which would let the model search
without the second call.
