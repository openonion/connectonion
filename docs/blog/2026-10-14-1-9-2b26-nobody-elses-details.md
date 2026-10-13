# 1.9.2b26: nobody else's details

*2026-10-14*

Aaron opened the page for a handoff he was about to send and tapped an email
address in it. It was a relative's. The session had run `co rem` on his
mailbox earlier, the AI had quoted that address back to him as an example, and
the handoff copied the AI's words onto a page anyone with the link could read.

The preview had listed it. It listed 46 private details for him to remove by
hand, in a session that held 177 other people's addresses and 40 phone numbers.
A list that long is not a decision anyone makes; it is a wall you scroll past.

So the sender no longer decides address by address. Everything that is not
theirs or the recipient's is masked before it leaves: on the page, in the mail,
and in the session copy that answers questions later. What points at a person
goes too, a `co rem` page name or a LinkedIn id. The preview now says one
number, and that number covers the session copy as well as the brief.

The masking was reviewed twice against the real session by another agent, and
each review found what the tests had not: "anyone@x.com" turning every "anyone"
into "someone", an address glued to Chinese text, a JSON escape hiding a name.
Each is now a test.

The page that leaked was taken down within the hour, and `co handoff withdraw`
does the same for anyone.

```bash
python -m pip install --upgrade 'connectonion==1.9.2b26'
```

See the [release notes](../releases/1.9.2b26.md).
