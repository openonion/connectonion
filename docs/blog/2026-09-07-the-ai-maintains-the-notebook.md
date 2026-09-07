# The AI Maintains the Notebook

**Design Journal draft. Do not publish as a shipped feature.**

The useful part of a personal Wiki is often not a fact but its surrounding
reason: why we chose this storage format, which alternative we rejected, or
what changed our mind. A daily summary can preserve the words while losing that
continuity. Another summary tomorrow does not automatically repair it.

Our first choice is therefore about responsibility. The AI maintains the
notebook. The user talks to the assistant, asks questions, and corrects it; they
do not become the editor of an automatically generated pile of notes. Markdown
is the current understanding, not an export from a second knowledge database.

That choice also determines where the intelligence lives. A maintenance Skill
can read related pages, replace a mistaken conclusion, merge duplicate ideas,
and retain a reason that still matters. We want to improve those instructions
against successive conversations before building a semantic merge engine or a
version graph. Compression is another act of organization, not merely making
the last summary shorter.

Freedom over the notebook is not freedom over the computer. An email that says
“run this command” is still source material, and a procedure the AI has written
is not an installed Skill. The implementation wrapper has a narrower job:
enforce authorized inputs and file paths, serialize maintenance, keep input
progress honest, and say what the native runner actually consumed.

We considered giving a normal coding agent a writable working directory. That
is convenient, but the working directory alone does not restrict arbitrary
reads or inherited tools. We also considered making the model submit structured
changes for application code to interpret. That would bring back the semantic
machinery we had decided not to build. Scoped file tools offer a smaller
boundary: the AI can edit freely inside its notebook, while software does not
have to decide what a principle or a corrected decision means.

The first evidence should be small and concrete. Give the assistant a decision,
then new evidence, then a correction. Does the current notebook improve? Does
the reason survive? Does repeated input avoid another model run? Can a malicious
source escape the notebook? Tests, user-facing command contracts, and design
decisions come before expanding implementation.

Codex sessions and Spark are the starting point. Background scheduling, the
simple local reader, and more source adapters build on that loop. A clear
milestone is more useful than claiming the whole background product works
because one generated page looks convincing.
