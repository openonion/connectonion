# Redirects are not authoring

An agent running a five-step pipeline spent all 100 iterations on each step and
still wrote zero bytes. The commands were not trying to author source files:
one appended a JSONL record, another redirected browser output, and a third used
`tee` to keep a log. The `prefer_write_tool` plugin treated all three spellings
as file creation, then told the agent to use `Write`, which cannot append safely
to a shared log without first reading and rewriting it.

The guard now keeps its narrow job: it blocks commands that visibly manufacture
content with `cat <<EOF`, `echo >`, or `printf >`. It allows append redirects,
`tee`, and redirects whose content comes from another command. That distinction
preserves the reviewable path for source authoring while leaving operational
state and command output to the shell tools that produce them.

The regression tests exercise both sides of the boundary. In particular, an
`echo` redirect remains blocked, while a browser-output redirect, an append, and
a `tee` pipeline are allowed. The change does not inspect the destination path:
the important signal is whether the command itself is generating the content.
