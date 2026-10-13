# The session, not the manual

*2026-10-13*

Aaron opened one of our test handoffs in the Codex app the way a recipient
would. The first thing on the screen was an install guide: check the version,
run this curl line, on Windows run that one instead, save the text below as a
file, accept with this 110-character code. After that came the rules, and only
then the handoff itself. His verdict was that he couldn't follow it, and that
none of it was about the thing he cared about, the session someone had handed
him. Nothing said what the other person had discussed that day or what they
had concluded.

He was right, and the reason was structural. Everything rode in the mail,
because a first-time recipient has no agent address until co is installed, so
there was nowhere else to put it. The mail was the delivery truck, and whatever
it carried became the first message of their thread.

Now the mail is only a reminder. It says who handed you what and gives one line
on the work: what was discussed, what was concluded and what is still open.
Then come three lines to paste: install co if you need it, run
`co handoff accept <code>`, and tell the person what it is about. The handoff
itself waits on our backend under an id the code carries. `accept` fetches it,
refuses it unless it matches what the sender approved, and prints the report
first.

The report is what a person reads on a phone. It names who worked on what,
with which AI and on what day, then Discussed, Concluded, Still open, and, when
there is something to draw, a small diagram. Below it come the AI's own words,
quoted. We used to summarise them, but a summary drops whatever its writer
thought unimportant, and the reader cannot tell what is missing.

The last gap was on the sender's side. A question the sender left open cannot
be answered by any copy of their session. Every hosted agent now watches for
questions, and each new one is mailed to the sender with the one line that
answers it.
