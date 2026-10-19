# The language was detected and never read

The reader got a Chinese interface last week. It was supposed to start in the
owner's language, which REM detects from the mail the owner sent and the turns
they typed into coding sessions. On a copy of a real notebook it started in
English, and the snapshot said the owner's languages were an empty list.

The detector worked. Run by hand on that copy, it read 1,199 of the owner's own
messages and returned English 72%, Chinese 28%. The result is stored on the owner
entry in `map.json`, but only at the end of a full map and in one branch of
the daily round that partial runs skip. This notebook had been mapped before
the detector existed, and its daily runs had not reached that branch since. So the
answer was computed nowhere and read everywhere.

The reader now detects on the fly when nothing is stored, without writing.
That takes about two seconds on this notebook. The interface default also
changed: a bilingual owner whose mail is mostly English, because work is in
English, but who writes Chinese more than a tenth of the time, is shown Chinese.
English is the tools' language, not necessarily the reader's. The EN | 中文
switch still wins once used.

The same pass gave memory two quiet visual states. A page the last pass
rewrote carries a small dawn dot and "updated last night" above its title, and
"last night" beside its name in lists. When the night's change names a field,
such as Mara's role, that value gets a faint dawn underline with the before and
after in its tooltip. We say "updated", not "new finding", unless the change
record says a claim was revised.

Claims that say they are unconfirmed ("whether the scope was sent is
unknown") get a small hollow circle just before their citation, the same mark
the "Uncertain points" chip uses. Uncited sentences get nothing. Marking every
missing source would have made the page louder than the memory.

The People table on a desktop now opens with four columns, Name, What's open,
Company and Last contact, and keeps the rest behind "More columns".
