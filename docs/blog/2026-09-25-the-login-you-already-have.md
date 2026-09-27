# The login you already have

The LinkedIn pipeline had been running unattended on the free engine for
weeks. Moving it to the paid WTF Browser was supposed to be a one-flag change:
`--engine wtf`. The first page it opened was LinkedIn's sign-in form.

Of course it was. The WTF Browser keeps its own profile, and that profile had
never seen LinkedIn. The obvious fix was to sign in once, by hand, inside it.
But this account had been force-logged-out for "unusual activity" a month
earlier, and a fresh sign-in from a browser LinkedIn has never seen, on a
fingerprint it has never seen, is the most unusual activity there is. The
session we wanted was already sitting in Chrome, on the same machine, signed
in and trusted. It just was not in the right browser.

So `co browser import` reads it from there. The interesting part was not the
decryption. Chrome on macOS encrypts each cookie with AES-128 under a key
derived from a Keychain item, and newer databases put a SHA-256 of the host in
front of every value; a few dozen lines, and a fake profile in the tests,
encrypted with a known password, keeps them honest. The interesting part was
the other end: how the cookies get *into* the paid browser.

The tempting answer is to write them into its cookie file. It is SQLite too;
open it, insert rows, done. That answer breaks the week the browser changes
how it stores cookies, and it was about to: the paid browser may move to a mock
keychain, so a row encrypted the way Chrome encrypts would be garbage there.
Every browser already has a way to accept a cookie and store it however it
likes. Playwright's `add_cookies` goes through it, and `co browser cookies
load` already used it. The import hands each site's cookies to that same path,
so where the bytes end up, and how they are encrypted, stays the target
browser's business.

Then the owner added a rule we had not thought of: an import must never
switch the account the paid browser is already signed in to. Overwriting a
working session with a different one is a quiet way to break a pipeline that
was fine. So before writing, the import asks the target which sites it already
holds cookies for, reads only their names, and leaves those sites alone
unless `--replace` says otherwise.

What this teaches is small and keeps coming back. When two systems both have
a front door, use the doors. Reading Chrome's files is unavoidable, because
Chrome offers no door for that, so the import reads a copy and never touches
the original. Writing into the other browser has a door, so it goes through
it. And every value stays out of the terminal: the report says how many
cookies landed per site and why the rest did not, never what they were.

It is a first version on purpose. macOS and Chrome only, cookies only, and a
site that binds its session to the device may still ask you to sign in.
`--dry-run` shows what would come across without touching the Keychain or the
browser, and the last line of every import names the one command that proves
it worked: open the site in the paid browser and see whether you are in.
