# The number stayed; the source changed

The translated sentence still ended in `[3]`. That looked reassuring until
the cached page's Sources sent `[3]` to a different original. In a synthetic
reproduction, the page hash matched and every citation number survived, so
the cache was accepted. The hash identified the input; it did not check
what the translation had kept.

Current main already takes Sources out of the model's input and puts them
back verbatim afterward. That narrowed the repair: apply the same rule to
cached translations before offering them to the reader. A changed reader-visible
Sources section or a header naming another record now makes the cache unavailable.
The original page and cached bytes stay untouched. Reading does not call a
model; an explicit translation request can replace the rejected cache.

Thirteen regression cases failed before the fix, including changed mail,
session, file revision, hash and URL targets, swapped definitions and reader
snapshots that exposed them. Independent AI review then found that the reader
accepted heading variants the generation helper did not. Three more failing
tests caught earlier sections hidden behind those variants or HTML comments;
the cache check now follows the reader's section boundaries. All sixteen pass
alongside the existing translation tests. Valid caches with unchanged Sources
remain usable without a prompt version bump. Older caches with translated
captions must be translated again:
the small fix compares the preserved section instead of interpreting individual
routing IDs. This checks citation destinations, not translation meaning.
