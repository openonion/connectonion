# Two writers, one notebook

An hour after the new release went on the owner's machine, the nightly update
ran early. We had just raised its daily limit from 6 calls to 30, and the
scheduler saw that the morning's run had never gone through, so it started
it. At that moment the map was being rebuilt. The rebuild was clearing out
pages an older map had left behind.

The update picked a page to work on, and the rebuild moved that same page
into the archive. The update failed. Then a second rule made it worse. When an
update fails after pages have changed, we had taught the Wiki to assume the
model finished its work and move on, so it wouldn't pay twice for the same
batch. Pages had changed, but the rebuild had changed them, not the update.
So forty messages were marked as done, and none of them went into any page.

Both rules had been sensible when they were written. The map never used to
move pages, so it never needed the lock the updates share, and "pages changed"
was good evidence that the model had finished. What broke them was the change
earlier the same day that made the map move pages. Each rule assumed it was
the only writer.

Now the map takes the same lock. If an update's timer fires during a rebuild,
it finds the Wiki busy and tries again five minutes later. The forty messages
are gone from the queue, but not from the sessions: the next investigation of
those pages will read them.
