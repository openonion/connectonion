# A card, not a catalogue

The owner installed 1.8.9 on someone else's laptop and ran `co ai`. Two
things were wrong. The person couldn't connect a client, because the invite
code wasn't on the screen, only a hint to run `co keys --reveal`. And
somewhere they could see our internal Airbnb agents, with a list of what
each one does.

The second one came from the public directory. Every hosted agent published
a profile so that its own clients could check skill names, and the directory
listed every profile it had. Anyone could read the skill list of our
guest-messaging agent and our rental CRM. The skill contents stayed private,
but the names and one-line descriptions said a lot. The server now lists an
agent only when it asks to be listed, and even then it shows a card: a name,
an address and one line about what the agent does.

The agent's own Home page had the same habit on a smaller scale. It opened
on its name and then a row of skill buttons. It now opens on the same card,
with the skills folded under Capabilities for anyone who wants them.

The invite code needed more care. It is a password: on a deployed host,
startup output goes into the system log, which anyone on the machine can
read. So `co ai` now shows the code when you run it yourself in a terminal,
next to the address and the link to open the agent. When the output is not a
terminal it still says where to find the code, not what it is.
