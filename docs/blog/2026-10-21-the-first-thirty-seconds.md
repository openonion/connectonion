# The first thirty seconds

We opened the reader on a notebook straight after `co rem init`, the way a
new user would, once in English and once in Chinese. The first screen got
the first impression wrong in a few places.

It called the initial build "last night". The home page said "Last night:
read 5058 items · rewrote 14 pages", and then "Nothing about your people or
projects changed last night. 14 pages were reworded." There was no last
night. The reader now notices when every run in the log belongs to the
latest pass, and says "Built today: read 5058 items · wrote 14 pages". The
section that will later list overnight changes says the notebook was just
built, and, when the nightly schedule is off, how to turn it on. The quiz
card that asks what you remember about a page is hidden too. A brand-new
user has not read any of those pages yet.

The owner's own page appeared as if it were someone else. A thread recorded
on your page showed your full name as the counterpart. It now reads "Your
page".

In Chinese mode a fresh notebook has no translations yet, so the chrome was
Chinese and every page English, with nothing to say why. Home now says so in
one line and gives the `co rem translate --all` command to copy. A page that
has only been mapped no longer lists thirteen English section names it has
not written. It says how many it will write once investigated.

Two smaller fixes came from the project page. The writer's hedge about
which session sample it read sat as the page's second line; it now sits
inside Full memory and sources. "Connected context ▸ Text mentions" became
"Related pages ▸ Pages that mention it". Sections with nothing in them are
now left out, and the few that must stay ("Open threads") share one calm
"Nothing open." line.

Finally, an axe-core pass in Chrome over the main views in both themes. The
muted grey used for dates and labels was 3.3:1 against the light
background, under the 4.5:1 that WCAG AA asks for. It is darker now in
light mode and lighter in dark mode. Links inside sentences have an
underline, so colour is not the only cue. The status icons carry an image
role, and a "Skip to content" link comes first. The same audit went from 59
distinct findings to none.
