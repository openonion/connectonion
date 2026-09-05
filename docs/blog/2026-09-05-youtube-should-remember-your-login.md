# YouTube should remember your login

*2026-09-05 — draft design journal; implementation under review, not released*

The request sounded familiar: give YouTube the same place in the terminal as
Gmail. Connect an account, run a short command, and see recent items. A video
number should work in the next command without copying an ID from a webpage.

Our first draft made that harder than it needed to be. It offered a browser
inspection command alongside API commands that expected a fresh access token
on stdin. The browser scanner could verify visible video titles, and the API
tests could verify request shapes. Neither result answered the practical
question: why did someone who already used `co gmail` have to manage tokens or
open a YouTube tab to use another `co` command? The user asked us to use the
same approach as Gmail.

Removing the browser command was straightforward. Making the remaining command
work exposed a dependency outside the CLI. The existing Google login requested
Gmail, Calendar and Drive permissions. It did not request YouTube access, and
refreshing that login could not create a permission the user had never granted.
Reusing a token alone would turn the first ordinary video listing into a
permission error.

The revised flow extends the existing login with `co auth google --youtube`.
After consent, `co youtube` uses the saved Google connection and the same refresh
broker as Gmail. The OAuth client secret stays on the backend. YouTube reads,
uploads and metadata edits go through the official API, so the user does not
need a YouTube tab for those operations.

That exposed another assumption in the backend. Its credentials response
reported a fixed list of requested capabilities. With optional YouTube consent,
the distinction between asking and receiving matters: a user can decline the
new permission. Both callbacks now record the scope string returned by Google,
and credential refresh reports that recorded grant. Old connections keep their
previous capabilities without acquiring an invented YouTube permission.

The tests now begin with saved synthetic Google credentials and exercise broker
refresh, including a second refresh on a cached client. They check that missing
scope stops before an API request and that read permission cannot authorize a
write. The focused client checks passed 538 tests, and the backend's complete
mocked suite passed 843. All seven creator command tips also survived a pipe
and the text-only next-command check. The larger client suite still has
documented baseline failures; those numbers are not a claim of live acceptance.

The remaining test needs an approved account after the companion backend is
deployed. No real upload or edit has been attempted. The change under review
does establish the part the original draft missed: once an account is connected,
the command should carry that connection into the next invocation. A scanner
that reads the right title cannot supply that continuity.
