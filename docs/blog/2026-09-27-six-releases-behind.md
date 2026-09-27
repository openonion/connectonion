# Six releases behind, and reporting healthy

On 22 September we shipped a fix for WhatsApp photos: download the file the
moment it arrives, because the keys to fetch it later are gone. Five days
later we counted what had arrived in the owner's inbox. There were six photos
and one document, the latest from that morning, and not one file on disk.
There was no `media/` folder at all.

The fix worked. It just never ran. The owner's listener had started on
21 September and was still running: the same process, the same code it
loaded that afternoon, through six releases of `pip install -U`. Upgrading a
package changes the files on disk. It does not change what a running process
has already loaded. And `co whatsapp check` said everything was fine. It was
connected and listening, which was true, and it was also running code from
last week, which it had no way to say.

The same count found a quieter version of the problem. Five of the owner's
seven failed sends were "No listener answered in 30s". `receive` starts a
listener when there is none; `send` and `reply` never did. So a script that
only sends, or an agent replying later, waited half a minute and gave up.

Both fixes are about the gap between "installed" and "running". A listener
now writes down the version it started with. Once a minute it compares that
with what is installed. After an upgrade, when no send is in flight, it
replaces itself in place with the new code, keeping the same pid and the same
linked device. `check` names both versions while they differ. `send` starts
a listener the way `receive` always did. A listener from before any of this
cannot restart itself, so `listen --restart` does it with one command.

The lesson: a health check that cannot tell "running" from "running the
code you think" will report healthy for as long as nobody looks.
