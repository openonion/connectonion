# The Wiki opened in the wrong place

A user typed `co wiki open` and got a browser page. At first that sounded like the command had done its job. The page contained the notebook, the CSS was bundled, and even the JavaScript was there. But its address began with `file://`. It belonged to the machine that ran the command. A second device could not open it, and the first browser kept showing the same snapshot after the notebook changed.

The initial discussion wandered toward fixing CSS and designing three product pages: Chat, Control Center, and Wiki. Neither was the request. The user wanted one action: type the command and arrive in a full-page Wiki. Adding navigation among three surfaces would make that action harder.

The existing reader already supplied the page. `reader.py` turns Markdown into a self-contained document and escapes note text before embedding it as data. Rewriting that interface as another Web app would duplicate its navigation and rendering rules. The missing piece was a private way to carry the current document to a browser away from the local filesystem.

The Host already has an authenticated OIP session. The new `WIKI_READ` request uses that session and answers only for the Host owner. `co ai` binds its default Wiki directory, `~/.co/wiki`; the Host renders the document when asked and returns it to that request. A 16 MiB bound keeps an unexpectedly large notebook from becoming an unbounded WebSocket response. Nothing from the notebook enters the public Agent profile or a static app bundle.

`co wiki open` now opens the Agent's Wiki address when the default Wiki has an identity. The browser shows the reader in a full-page, opaque-origin iframe. The old local snapshot remains reachable with `--local`, and an explicitly selected `--root` still opens locally. That compatibility matters: a custom notebook should not silently become the default Host's notebook because its owner ran the same command.

There is still a boundary to remember. An OIP address is not a public document URL. The page can be opened remotely only while its Host is available, and the content is delivered only after the client passes the Host's owner check. The URL gets the reader to the right Agent; the authenticated session gets that reader the private notebook.
