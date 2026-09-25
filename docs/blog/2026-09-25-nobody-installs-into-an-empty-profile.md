# Nobody installs into an empty profile

1.8.8 went stable this afternoon, and it had earned it. Over three rounds,
testers installed each preview into a fresh profile and walked through it
until a round found nothing. By the end, starting from nothing worked.

An hour later we upgraded the one notebook that had been in daily use since
20 September, and it didn't work at all. Its nightly update had failed every
night for four days. Its settings file still named a model the provider had
stopped accepting. Its owner page was an old contact card for one of the
owner's own addresses, because an earlier map hadn't known that address was
his. And when the first real update finally ran, it did all its work and then
failed at the very end, over an optional suggestion it had formatted wrong.

None of the three rounds could have caught this, because a fresh profile is
the one state no real user is in. People upgrade. Their notebooks carry
settings chosen by an older version, pages written by an older map, and
batches half done when a rule changed. Each clean round tests that the product
starts correctly. It doesn't test whether the product carries forward what a
real user already has.

So the next version, 1.8.9, is for exactly this. It will ship a preview each
time a few fixes land, found by using the product on real, lived-in data
rather than new profiles, and install each one from PyPI before calling it
ready. Its first preview fixes the owner page and the suggestion that failed
the update. The settings file comes next, and the notebook that started all
this will be the first to get it.
