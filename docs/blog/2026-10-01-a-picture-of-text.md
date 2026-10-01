# A picture of text

The README opened with every service `co` connects to: Gmail, Outlook,
WhatsApp, your browser, the models, about forty tiles, each with a logo and
the command that reaches it. It was drawn well, too. It came from the same
data as the homepage, in vector, with real brand marks.

It still looked like a screenshot, because on GitHub it was one. The README
showed the whole wall as a single `<img>`. Nothing inside it could be selected
or found with the browser's search. On a phone it shrank to fit the column,
so the part that mattered, `co gmail` under the Gmail logo, came out at about
six pixels. Being vector didn't help: GitHub shows an SVG as an image, so its
text never reaches the page.

The fix keeps the drawing and moves the text out of it. The website now serves
each mark as its own small SVG, `connectonion.com/icons/gmail.svg`, built from
the same react-icons data as the homepage wall. The README lays those out in a
plain HTML table. The logos are still images; the names and commands are now
text that GitHub renders itself. They can be copied, they wrap on a narrow
screen, and they show up when someone searches the page for "slack".

The table also had to stay current, which the old image did for free.
Writing it by hand would have drifted the first time someone added a
connection to the site and forgot the README. So the site prints it as well:
`curl -s https://www.connectonion.com/connections.md` returns the table
exactly as the README needs it, and the README marks where to paste it. Each
service is still listed in one place, and the README copies from that place.

Slack is on the wall now, in chat apps. It was the first thing we checked the
new table with.
