# The quotes were the point

REM's pages are mostly summary: who someone is, what is open, what changed.
The few words a person actually wrote are the part you can trust without
opening a source. In the reader they looked exactly like the summary around
them. "by Friday" sat in the same grey serif as the sentence that paraphrased
it.

We took screenshots of every view at 1440 and 390 pixels, light and dark, on
the invented Avery Lin notebook and on a copy of a real one. The real copy was
the more useful critic. An organisation page opened its full memory by default
and ran to 13,000 pixels. A person with nothing open still got a "Between you"
heading over the sentence "Nothing open between you". A Chinese contact's
history showed three dated rows with no text, because every word in them was
a hidden labelled passage. The sidebar ended in a schedule sentence and a
command that the sidebar itself clipped.

None of these were bugs a unit test would catch. Each was correct output that
nobody needed to see.

So the pass was mostly subtraction. Empty sections, blank rows and Unknown
fields no longer render; Full memory collapses on every kind of page; the
sidebar shows the theme and the snapshot time, and keeps the rest behind
"Reader settings". On a phone the brand and search share one row, which moved
a record's first heading from about 215 pixels down to about 140.

Then one addition: quoted words now carry their own warm colour and tint, and
block quotes a heavier bar. The search highlight stays yellow, so a match and
a quote never look alike.

Two accessibility faults from the issue list went with it. A citation with a
64-character source id could push its tooltip 106 pixels past a phone's edge;
tooltips are now clamped to the viewport. The source panel's focus loop could
land on a disabled "Next match" button; it now skips disabled and hidden
controls.

The screenshots also caught something the first round introduced. The new
sticky sidebar clipped a nav item in half on a 540-pixel-tall window. The
fix was to let the whole rail scroll instead of the list inside it, and a
browser test now holds that height.
