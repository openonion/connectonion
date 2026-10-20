# The translation kept the quotes and lost a label

The reader's Chinese mode translated the interface and left every page in
English. The owner asked why. The pieces to fix it already existed:
`co rem translate` made one cached translation of a page, keyed by the page's
hash, and the snapshot already carried any cached translations. Nobody had
made translations in bulk, and the reader only showed one when you picked it
from a menu on that page.

Now `co rem translate --all` fills the cache one page at a time, and the daily
run translates the pages it changed, up to ten a day. In 中文 mode every view
reads the cached Chinese. A page with no translation shows its English and a
small "原文".

Quotes are evidence, so they stay in the language they were written in. The
prompt said so, and the model still turned “zero-risk things” into
“零风险事情”. The check that runs before a translation is cached caught it.
The prompt now lists each quoted passage by name, and the next run kept them. The
check compares a quote's words, not its punctuation, because “Hi Mara,”
legitimately comes back as “Hi Mara”, with the comma outside the quote.

The serious find came from the first real translated pages. A sentence the
owner had labelled private ended "…联系 [personal]。" in Chinese. The
reader recognised the label before an English full stop, not before a
Chinese one. With labelled passages hidden, which is the default, that sentence
appeared in plain text in Waiting on you. The reader now treats 。！？ like
.!? when it looks for labelled passages. The translation check rejects any page whose labels
moved or changed count. Our first fix also split "Dr." and "e.g." mid-sentence. A
browser test caught that, and English segmentation is back to what it was.

One more correction came from reading the result. The pages say "the user",
which the model translated as 用户, so the owner read about himself as a
third party. Translations now address him as 你, like the rest of the
interface, and a prompt version in the cache key retires the old ones.
