# The names only reached new pages

1.8.9b16 taught the Wiki's map to name people from the owner's greetings, and
on the owner's real mailbox it named 176 of 195 people. We installed it on the
owner's Mac. Before telling the owner to re-map, we checked what the re-map
would actually change on their notebook.

It would have changed nothing for those 176 people. Their pages already
existed, made by an older map and titled `larryleework7@gmail.com`, and the
map never rewrites a page that already exists. The new code worked in every
test, and every one of those tests started from an empty notebook.

Leaving existing pages alone is the right rule for a page someone has
investigated, because the title there is someone's work. A page nobody has
investigated holds only what an earlier map wrote, so this map may correct it.
It now retitles a page whose title is an address, when a name has been found
and the page has never been investigated.

The new test starts from a notebook with two address-titled pages, one
investigated and one not, and it failed on the released code. We also ran the
map on a copy of the owner's real notebook before shipping. A fix that only
reaches new data leaves the old data wrong, and old data is what the owner
looks at.
