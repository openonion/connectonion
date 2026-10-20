---
description: At sixteen workers, a page's source gathering went from 146 seconds to 38. The pages stopped waiting for the session scan, and stopped scrubbing notes that never named the person.
tags: [REM, Performance]
---

# The pages waited for the same scan

After the last fix, a page at sixteen workers still spent about two and a half
minutes gathering. Two things were left.

The first was a queue. The session scan runs once per run and every page needs
it. Sixteen pages started together, so fifteen of them waited for the first
one's scan and counted the wait as their own gathering. The scan now runs once,
before any page starts. It has the interpreter to itself, and each page finds
the result already in memory.

The second was a search. A person's page looks for their name in the owner's
project notes: 2,894 notes, 17.7 million characters on this machine. For every
person, every note was scrubbed for secret-shaped strings, split into lines and
searched line by line. That took 11.8 seconds a person. Now each note is first
searched once for the name, and only a note that contains it is scrubbed and
excerpted. The answer is the same, checked on five people. It takes 2 seconds.

We thought about a word index. It would be faster again, but it would answer a
different question. A name inside a longer word, or a Chinese name inside a run
of characters, would stop matching. Two seconds that keep the same answer were
enough.

Sixteen pages, with the model stubbed, interleaved with the previous build:
median gathering went from 147 and 139 seconds to 39 and 38. The whole batch
went from about 205 seconds to about 136.
