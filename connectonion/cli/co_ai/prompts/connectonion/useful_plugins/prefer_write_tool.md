# prefer_write_tool

Stop the agent creating files through bash, and remind it to read them with
`read_file`.

## Why block it

`bash("cat > config.py <<EOF ...")` writes a file with no diff, no approval
prompt, and nothing for the user to review. The `write` tool does the same job
through `DiffWriter`, which shows the change and — depending on mode — asks
first. The two are not equivalent, and the model reaches for bash out of habit.

File **creation** through bash is blocked outright. Reading gets a soft reminder
rather than a block, because `cat` in the middle of a pipeline is legitimate and
refusing it would break real commands.

## What is still allowed

Everything bash is actually for: git, builds, package managers, pipelines. This
plugin narrows one path, it does not police the shell.

## If you hit the block

You wanted `write`. That is the whole message.
