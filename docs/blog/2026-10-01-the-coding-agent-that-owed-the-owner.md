# The coding agent that owed the owner a status

The 1.9.0a6 acceptance run ended on the page that matters most: the owner's
own. Under Open threads it said "Claude Code owes the user a message-volume
check" and "Codex owes the user a status". The Last contact line pointed at a
Claude Code session. Nothing on the page was false, exactly. The owner had
asked Claude Code for that check, and the Codex run had not finished. But
nobody owed him anything. He had been talking to his own tools, and the page
had written them up as colleagues.

Our first guess was a missing rule, but the rule was there. The owner page's
Skill already asked for "what they are working on now, from the coding
sessions". So we looked at what the turn had actually done. It had been handed
1,477 session messages and cited three of them. It never got as far as his
projects. The few session messages it did read, it read the way a person's
page reads mail: someone asks for something, so someone owes an answer. A
person's page needs that habit, and here it made the owner's tools look like
people.

So the problem was in two places. The first was a question of framing. A
coding session is not a conversation between two parties. It is the owner
doing his work out loud, and what he asked for is what he was doing that day.
The Skill now says so plainly. Coding agents are the user's tools, not people.
They are never a counterparty in Open threads, never Last contact, and never a
correspondent. A prompt like "check the message volume" becomes a dated line
about the owner's own work.

The second place was a mistake in our method. We had asked the model to find
the owner's projects in the middle of fifteen hundred messages, when the map
had already counted them. It knows every project's sessions and their first
and last dates. The owner's turn now gets that list directly: the projects of
the four weeks before the map was made, newest first, each with its dates. The
lead has to name the busiest of them, dated. The model still reads the
sessions, but now to say what he did in each project, not to work out which
projects there were.

The lesson goes beyond this one page. When a model reads material as the wrong
kind of thing, a stricter instruction doesn't help much. It helps more to say
what the material is, and to hand over the facts the system already knows
instead of asking the model to rediscover them.
