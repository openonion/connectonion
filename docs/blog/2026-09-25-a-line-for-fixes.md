# A line for fixes

1.8.8 went stable this afternoon, after three rounds of people installing
its previews into empty profiles. An hour later, upgrading one real notebook
turned up three problems no test had seen, because every test starts from an
empty notebook.

A release that only fixes things has usually been awkward to name. A patch
number suggests one or two fixes, and a minor version suggests new features,
when what we actually have is a steady flow of small fixes found by using the
product. So 1.8.9 is a fix line on purpose. It ships as many previews as the
fixes justify, each one released as soon as its fixes land and installed from
PyPI before anyone is told it is ready. It ends in one stable release that
closes a long list.

The list is public:
[#1722](https://github.com/openonion/connectonion/issues/1722). It holds the
Wiki problems found this week, the help audit that found 14 of 300 commands
meeting the help contract, deploy and remote-browser failures that give no
error, and a Write tool that reported success three times in one day without
changing the file. New features go to 1.9.

The first preview carries the two fixes from this afternoon's upgrade. One is
the owner's page, which a new map should rewrite when it was written by an
old map and nobody has touched it since. The other is a suggestion the model
added at the end of an update, which could fail the whole update.
