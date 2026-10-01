# The page was ready, but Windows could not open it

I had just checked REM's new morning page on a phone. The HTML rendered, the
People table worked, and the release checks were green. Then I followed the
last step of `co rem open`: it writes that HTML to a local file so the browser
can show it. The line that opened the file asked Python for `O_NOFOLLOW`.
Windows Python does not have that flag. The page could be perfect and still
never reach the browser.

At first the missing flag looked like a small compatibility edit. Replacing it
with zero would let the line run. But the filename is predictable, and the
flag had kept an existing symbolic link from pointing the write at somebody
else's file. Removing it would trade an obvious Windows failure for a quiet
overwrite risk.

The useful question became: why open the predictable name for writing at all?
I tried writing the page under a random private name first, then moving the
finished file into place. The old name is replaced as a directory entry; its
possible target is never opened for writing. A link visible before the move is
still refused. I checked a planted link and opened the page twice, then moved
the installed-wheel check outside the source checkout so Windows CI would test
the package people actually install.

The browser should only ever see a complete page, and the notebook should stay
untouched. That is now what the snapshot check asks on Windows. The detour was
a reminder that platform compatibility is not just making the exception go
away: the reason for the original guard has to survive the repair.
