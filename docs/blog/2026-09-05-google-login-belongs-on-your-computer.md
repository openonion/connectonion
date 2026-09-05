# The refresh token we already had

“Why does YouTube need a database migration?”

That question stopped the release work. We had added a column to remember which
Google permissions a user granted. It looked like a small extension to the
existing login. But the user remembered something else: the refresh token was
already saved on their computer. Why was a server column necessary to use it?

Following the refresh request answered the wrong question first. The backend
could find a Google login by the OpenOnion account and renew it. That path worked
on its own terms. Looking at the caller showed the mismatch: the CLI had a local
refresh token, yet the request did not send it. The server renewed its own copy.
We had been treating two copies as one login.

Adding a scope column would have continued that assumption. Deleting the local
file would not have removed the server's ability to refresh; inspecting the local
grant would not have explained which credential the server used.

The Microsoft flow in the same codebase offered a way out. It already sealed
credentials to an ephemeral key created by the CLI and returned them to a local
callback. We reused that handoff for Google, then changed refresh to carry the
token the caller actually held. In a regression test, every credential-table
function was replaced with a failure. Consent and refresh still completed with
synthetic tokens.

The question was not whether a scope fits in a database column. It was which
copy of a login has authority. Once that was explicit, the new column had no job.
Old clients still need an upgrade, and real Google consent still needs its own
acceptance run. Neither is a reason to keep an invisible second login.

Preparing 1.8.3 made that distinction concrete again. The package installed in
a clean environment, and its commands and bundled documentation were present.
The deployed backend could issue the new consent URL. None of those checks
meant that a person had granted YouTube access. The release checklist keeps
that next action separate: the user consents in Google, then a fresh CLI process
reads through the four services using the local grant. An authorization screen
is not an authorization result, just as a local refresh token was never proof
that the server was using it.
