# A Download Can Partly Succeed

Draft for 1.8.4; publish after release acceptance.

The download regression starts with a file already on disk. It is named
`report.txt`, and its contents are `old`. The simulated Gmail message contains
two more files with that name. One even arrives as `../../report.txt`.
The test asks the CLI to download all attachments into the chosen directory.

A successful HTTP response cannot answer whether that operation was safe.
Opening the first destination for writing would replace the existing file.
Stripping the incoming path solves the directory escape but makes the two
attachment names collide again. We need all three sets of bytes at the end,
inside the selected directory, with the original file untouched.

That is why filename selection happens at publication. Each decoded attachment
is written to a private temporary file first. After the size check and fsync,
the client tries to place it under an unused name. If another file already owns
that name, it tries a numbered suffix. The collision check and placement must
be one operation; checking that a path does not exist and then opening it
would leave the same race in a smaller gap.

The next fixture makes the second attachment's base64 invalid. Now the first
file is safely saved, but the overall request has failed. Rolling the first
file back would conceal useful completed work. Printing only an error would
leave the operator unsure whether a retry would create another copy.

The result therefore retains both parts: the first has a destination and hash,
and the second has an error. The command exits 1. The test checks both the exit
behavior and the directory, including that no partial second file was published.
A separate symlink fixture checks that a colliding link cannot redirect the
write to its target.

These cases changed what counts as completion. The request was to save a set
of attachments, so the answer has to account for that set. A single success
sentence cannot describe the moment when one file is complete and the next
one never made it to disk.
