# A citation kept its number and changed its destination

Candidate implementation, not included in public 1.9.3rc16.

A translation could retain every numbered citation while replacing the source
behind one number. The previous validator counted references globally. It could
also accept citations moved between claim lines. A cached translation needed the
original page's digest, but its own definitions were not checked again on read.
The language switch then let some source-routing consumers read translated text
while others read the original. One visible reference could acquire two meanings.

A stronger prompt alone cannot protect that boundary. Discarding every old cache
would also throw away valid work. The correction instead checks the existing
contract at write and read: exact supported source targets, per-line citations,
record identity, headings, quotations, privacy labels and reader markers. Unknown
source syntax remains literal. Mixed legacy session and numbered definitions
are refused because their effective numbers can collide; ordinary legacy session
references remain usable. Ambiguous definitions stop a translation before
execution. Paths, revisions, hashes, queries and fragments are not normalized or
resolved while comparing them.

The reader uses the canonical page to route an evidence action and to label the
selected original. A translated caption can explain that destination only when
its identity and privacy labels agree; otherwise the original caption remains.
Sources captions now use the existing privacy class. This does not certify all
identity, tooltip, popup or accessibility privacy behavior.

On a cache read, invalid content falls back to the original and stays on disk for
diagnosis. There is no automatic model execution or notebook rewrite. Valid
version-2 caches remain usable; an explicit translation may replace a bad cache
after validation. This is a conservative choice: unfamiliar source syntax cannot
freely translate, and line-preserving checks can refuse a fluent reformatted
answer. The existing prompt already requires each line's structure to stay.

Synthetic regressions demonstrated changed targets, swapped references, moved
citations and digest-matching invalid caches. Actual reader functions were
composed with logical element stubs to check routing and caption data flow.
Those are not browser screenshots or native acceptance. No fresh account, model,
mailbox, scheduler or real notebook trial was performed.

The check cannot tell whether a fluent translation reverses a claim while keeping
its citation on the same line. Source truth, translation meaning and current
phone, keyboard and screen-reader behavior still need their own evidence.
Revisit the literal definition policy when the canonical routing grammar changes;
expand the parser and regression evidence together before allowing new syntax.
