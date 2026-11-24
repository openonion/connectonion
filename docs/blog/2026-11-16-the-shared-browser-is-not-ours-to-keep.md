# The shared browser is not ours to keep

*2026-11-16*

`co auth asana` used to do everything in the co browser. It copied your
Chrome cookies for asana.com into it, opened Asana's developer console, opened
the new-token form and named the token. You accepted Asana's API terms and
pressed Create, and it read the token back and saved it encrypted. It worked
on a real account the first time, and it was the wrong default.

Review of the first Asana pull request put it plainly: the co browser is
shared. Every agent and every later `co browser` command uses the same
profile. After `co auth asana` finished, that profile was signed in to Asana
as you, with no end date, and nothing had said so. If the run failed after you
pressed Create, the new token was still on screen in that profile's tab.

So the default is now the one that touches nothing else. `co auth asana` opens
the developer console in your own browser and asks for the token, hidden, the
way `co env set ASANA_ACCESS_TOKEN <pat> --secret` would; it checks the token
with Asana before saving it. The browser path is still there, as
`co auth asana --browser`, and `co auth --help` now says what it does: it
copies your Chrome cookies for asana.com.

What `--browser` promises is that it puts the profile back. Before it copies
anything it asks the co browser which asana.com cookies it already holds. If
there were none, every asana.com cookie is cleared again at the end, whether
they were copied from Chrome or typed in its window. If there were some, they
were yours before this run, and they stay. If the co browser cannot say
which cookies it holds, the run copies and clears nothing and asks for the
paste instead: unknown is never read as "none". However the run ends, success,
a refused token, Ctrl-C, the console tab is replaced by one line, so the token
is not left on screen.

Clearing needed more care than it looks. `co browser cookies clear` clears
the cookies of whatever page the tab is on: sent while the tab sits on another
site, it signs you out of that site instead. So each Asana site is opened
first, the address it landed on is checked, and only a page on asana.com is
cleared. A redirect to anywhere else clears nothing and is reported instead.

The rest is smaller. How far a run got used to live in a module-level dict,
which a second run in the same process could inherit; it is now one object per
run. Five broad `except Exception` handlers became the errors each step can
actually raise.

Measured on this branch: 53 tests of `co auth asana` pass, seven of them fail
on the old module, and `co audit co auth` passes every rule. What we have not
tried is the browser path off macOS: `co browser import` reads a Mac's Chrome
profile, so elsewhere you sign in in the window, or paste.
