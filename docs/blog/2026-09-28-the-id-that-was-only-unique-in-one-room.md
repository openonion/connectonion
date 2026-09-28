# The id that was only unique in one room

The weekend capstone groups talk in Slack, not Feishu or Discord. They wanted to try what the rest of `co`'s inbox does, an agent that listens in a channel and answers when someone asks it something, and on the day stable 1.8.9 was due the only honest answer was "not on your platform".

So `co slack` started as a copy. Discord already had the shape we wanted: dial out over a WebSocket, open no port, write every message to a directory, send replies over HTTPS. Slack's Socket Mode is the same idea, so the plan was to port the Discord provider line for line and change the URLs.

Reading Slack's docs against that plan is where it stopped being a copy, three times.

The first was the message id. Discord's is a snowflake, unique across the whole platform, and the inbox dedupes on it as it is. Slack's closest thing is `ts`, a timestamp like `1727500000.123456`, and it is unique only inside one channel. Two rooms can have a message with the same `ts`. Ported as-is, the inbox would have taken the second one for a duplicate of the first and dropped it without a word. So a Slack id is `<channel>:<ts>`. That also settled a smaller problem: an @mention arrives twice when a bot subscribes to both `app_mention` and `message.channels`, and with the channel in the id the two copies are exactly one message.

The second was replies. Discord threads are channels of their own, so "reply in the chat it came from" was enough. Slack threads hang off a parent, and its docs say to avoid a reply's own `ts` and use the parent's. An agent answering the third message in a thread would otherwise have aimed at the wrong thing. `co slack reply` now looks the message up and answers under the thread's root.

The third was length. Discord refuses a message over 2,000 characters, loudly. Slack advises 4,000 and truncates past 40,000 without refusing anything. A long agent answer would have posted, returned an id, and been cut off in the middle, with the sender told it succeeded. `co slack` refuses over 40,000 before anything is sent, because an error you can see is better than half an answer you can't.

None of this has met a live workspace yet. It was tested against fakes that play Slack's envelopes, which is why the help and the docs page both say Experimental, the way `co discord` did before it. The weekend groups are the first people who will connect it to a real app, and we would rather they find the fourth difference than hear later that we assumed there wasn't one.

The lesson: when you port a working thing to a new platform, the dangerous parts are the words that match. Both platforms have an "id" and a "reply", and they don't mean the same thing on each.
