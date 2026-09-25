# The write that said yes

One morning in late August, an unattended `co ai` pipeline sent no digest
email. A freshness guard had refused to mail it: the HTML file it was about to
send was two days old. The run log said the agent had written that file an
hour earlier. Twice.

```
▸ write(content="<div s...", path="/Users/you/...")      ✓ 0.00s
```

Two more runs that day did the same thing to a file of DM drafts. Each time
the log showed a green tick, and each time the file's mtime had not moved. The
person who hit it searched the whole disk for a misplaced copy and found none.
They tested `write` directly with both argument orders, because the one call
that had worked that morning had put `path=` first and the failures had put
`content=` first. Both orders landed. They filed #1338 with everything they had
ruled out, and noted the one thing they could not see: the log cut off both the
path and whatever the tool had said back.

## What the tool actually said

The tick was not lying about the tool. It was lying about the answer.

In 1.7.0, `write()` refused to overwrite a file that already existed. It
returned `"Error: File '...' already exists. Use edit()..."`, as a plain
string. The executor had no way to know a plain string was a refusal, so it
recorded success and drew a tick. The 04:37 call that "worked" was the first
time that file was created; every later call to the same path was refused, in
0.00 seconds, which is about how long a refusal takes. The argument order was a
coincidence.

That part was fixed the same day, in 1.8.0: tools can now return a
`ToolFailure`, which is still a string to the model but is drawn as ✗ and
recorded as an error. So why keep the issue open?

## A claim, not a receipt

Because the fix answered the one path we found, and the report was really
about something bigger. The agent's only evidence that a file changed is the
sentence the tool hands back. `"Successfully wrote 16 bytes to 'digest.html'"`
was built from the arguments, not from the disk. It would have said the same
thing if a sync folder had put the old copy back, if the path had resolved
somewhere unexpected, or if the file had come out different from what was
asked. Even the byte count was the number of characters.

And the refusal was not the only way to say something that looks like yes.
`DiffWriter`, the approval-flow writer, returned plain strings for a rejected
change, for a client that disconnected mid-question, and for a plan-mode
preview that wrote nothing at all. Each of those would have been a tick.

## What changed

A write is now a success only once the tool has read the file back and found
the bytes it was asked to write. The message names the resolved absolute path,
the real UTF-8 size and the mtime, so a claimed write carries its own proof:

```
Successfully wrote 7 bytes to '/Users/you/notes/today.md' (verified on disk, mtime 2026-09-25T10:14:03)
```

If the bytes differ, or no file is there afterwards, the tool returns a
`ToolFailure` and says to treat the write as failed. `DiffWriter` does the
same check, and its rejection, closed-channel and plan-mode answers are now
failures too, each saying "Not written" in so many words.

The last change is the one the reporter asked for first. When a tool fails,
the log now prints what the model was told, in full, under the ✗ line. The
line that stopped this investigation, `path="/Users/you/..."`, is followed by the
path and the reason.

## The lesson

A tool's return value is a claim about the world, and the agent believes it
completely. If the claim is built from the request instead of the result, the
tool is reporting what it meant to do. The cheap fix is to go and look: one
read after one write. Before anyone treats a tick as proof, it should be proof
of something.
