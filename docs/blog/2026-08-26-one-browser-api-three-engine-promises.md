# The command we had to send before the command

The paid browser integration looked finished. `co browser --engine onion`
carried `"engine": "onion"` in its JSON envelope, the new daemon pinned that
choice, and the launch seam refused to fall back after billing. Then one
question spoiled the neat picture: what if the daemon was already running?

That is normal for `co browser`. The daemon survives between shell commands so
the window, cookies, and tabs survive too. It may also survive a package
upgrade. A 1.8 client can therefore spend its first request talking to a 1.7
daemon.

The old daemon accepts the JSON envelope. It simply ignores fields it does not
know. That is usually a pleasant kind of compatibility, but here it changed the
meaning of a strict request. A user could type `--engine onion`, the client
could send exactly that, and the old daemon could drive system Chrome before
anyone noticed. Nothing crashed. The dangerous part was that everything looked
successful.

The obvious repair was to probe the daemon before every command. I added a new
`engine_status` verb and made the client call it first. The real socket suite
immediately exposed the cost of that shortcut: ordinary default commands now
made an extra round trip, and compatibility stubs without the new verb were
rejected even though their system-browser behavior was still correct. Worse,
the supposedly harmless probe went through normal dispatch, so it claimed the
main tab and replaced the recorded last command. A diagnostic check had become
a browser action in everything but name.

That failure clarified which promise actually needed protection. Only explicit
`onion` is unsafe against an old daemon. `system` already means system Chrome;
an old daemon honors the intent. `auto` is allowed to resolve to system before
billing, so the same old behavior is a safe fallback. There was no reason to
tax or reject those paths.

The final handshake is consequently narrow. Before sending an explicit Onion
page command to a warm daemon, the client sends `engine_status`. The daemon
handles it before tab registration and before last-command bookkeeping. If the
verb is unknown, the client refuses the original request and tells the user to
restart the daemon. The page command never crosses the socket. Default and
system commands keep their old one-request behavior.

Two small tests now describe the boundary better than the implementation does.
One gives the client an old daemon reply and asserts that the bytes containing
`go_to` were never sent. The other lets the probe succeed and asserts that the
real command follows with `engine=onion`. A daemon-side test proves the probe
leaves both the tab board and last command untouched. The complete real-socket
daemon regression suite passes 106 tests after the change.

The lesson was not “version your protocol”; the envelope was already versioned.
Compatibility has to preserve intent before the first irreversible effect. An
unknown field is safe only when ignoring it cannot turn one product promise
into another. Sometimes the most important browser command is the one that
proves it is safe to send the browser command at all.
