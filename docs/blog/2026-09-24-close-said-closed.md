# Close said closed

A crawl on a schedule finished its work in two hours. Its wrapper's `trap`
ran `co browser close`, the wrapper exited 0, the collector exited 0, the rows
landed. The paid browser kept running for another three hours, renewing every
fifteen minutes, because `close` had hung and then left eleven Chrome processes
behind. Every check a scheduler could run was green. That was #1496.

The obvious fix was to kill the daemon when `close` takes too long. We had
already been doing that by hand — `pkill -f browser_agent.daemon` — and it did
not work either: the reporter needed a second `pkill` for the runtime. Playwright
starts Chrome in its *own* process group, so ending the daemon, or its group,
orphans the browser. By the time anyone looks, the parent links that said which
Chrome belonged to which daemon are gone.

So `close` now takes a snapshot of the daemon's whole process tree before it
asks the daemon to shut down, while those links still exist. It waits at most
a minute for an answer. Afterwards, whatever in the snapshot is still the same
process — checked by creation time, never by name — is stopped, named, and the
close exits 1. We tried it for real: a frozen daemon, a live page, and `close`
stopped nine processes (Chrome, its GPU and renderer helpers, Playwright's
`node`, the daemon) and left none. A clean close still exits 0 in a second; the
check waits for Chrome's helpers to finish on their own before calling anything
a survivor, which the first version of this did not, and would have reported
every normal close as forced.

Once we looked for that shape, it was all over the same command. `status` said
the browser was open after its paid session had ended, because it asked whether
the context answered rather than whether the session was alive. A scheduled job
could not find the daemon a login shell had started, because each worked out
the address from environment variables the other did not have — on this Mac,
`/var/folders/…/T/` from a shell and `/tmp` with no environment at all. And a
tab note that said "leave it alone" was read as the whole browser being busy,
so an agent put a user's task off for forty minutes over a tab it never needed.

The close told the truth about the daemon's reply and nothing about the
processes. The others told the truth about something nearby. None of them was
lying, which is why none of them looked like a bug until someone paid for it.
