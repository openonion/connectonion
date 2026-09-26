# The skill that stayed after its publisher withdrew it

A publisher removed a skill and a subscriber ran `co sub sync` again. The
command finished, but the skill was still on the subscriber's machine. Its old
`SKILL.md` remained in the mirror and its link remained visible to a coding
agent. The publisher's current profile no longer promised that body, yet the
agent could still read yesterday's instructions.

I reproduced that with two signed revisions: one with two public skills, then
one withholding the second body. The original sync wrote new files into the
existing directory but never asked which old files should leave. A publisher
rename produced a similar trace: the refreshed profile supplied a new alias,
so the old local path was left behind. Those failures made it clear that a
subscription was being treated as a one-time copy, even though users expect a
continuing relationship.

While tracing removal, I found a more serious problem. The cleanup code
treated the `<alias>-<skill>` prefix as proof that a path belonged to the
subscription. I put hand-written notes in a same-name Codex skill directory;
the old install path could replace that directory with a link. A name can be
chosen by a publisher or a subscriber. It cannot tell us who owns the files
under it.

The turning point was to make the local alias stable and check the destination
of each link before touching it. A refresh now builds a complete verified
bundle off to the side, swaps it into place, and reconciles only the links and
marked copies it installed. The hand-written directory stays. The withdrawn
skill leaves. When I forced an error during staging, the previous mirror and
its Codex link still read the old body, so an interrupted download did not
turn a working installation into half a new one.

That test exposed one last false success. A skill that said “run
`scripts/run.js`” arrived with only `SKILL.md`; its script was absent. We made
the companion file part of the publisher's signed profile and checked it again
before writing the subscriber's mirror. Changing one byte in the relay reply
now rejects the sync. This also dictates the rollout order: the relay must
serve those signed bytes before the SDK preview can publish them.

The lesson is that a successful subscription needs two answers: what the
publisher currently signed, and which local paths this subscriber actually
owns. `co sub list` now reports listed, mirrored, and installed counts so the
operator can see when those answers differ.
