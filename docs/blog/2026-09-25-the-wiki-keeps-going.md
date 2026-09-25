# The wiki keeps going

Four reports about the Personal Wiki came in together. They looked unrelated:
lost mail, a bill that kept arriving, a notebook that stopped opening, and a
dependency nobody asked for. Reading them side by side, they turned out to be
the same mistake four times. Each time, the Wiki met something it didn't
expect and either stopped or went on without saying so.

## The week with 250 emails

Mail is read one week at a time, and each listing call returns at most 200
messages. Beside that limit sat a comment: "a busier week continues on the
next pass." Nothing made that happen. The scan finished the week and went on
to the next one, and the other 50 mails were never looked at. The run
reported success and there was no error. The people in those mails just never
showed up in the notebook.

Our first fix was a cursor: keep going from the last mail the listing
returned. That works for Outlook, which fills the 200 from the oldest end.
Gmail fills them from the newest end, so for Gmail the lost 50 are before the
cursor, and the cursor never goes back for them. So a full listing is now
split in half, and each half is split again until it fits. That works however
a provider picks its 200. If a single second holds more than 200 mails, the
scan stops with an error. We'd rather stop than skip mail.

The test mailbox has 250 mails in one week, and it runs twice: once against a
fake that keeps the oldest 200 and once against one that keeps the newest.

## Paying twice for the same batch

A batch goes through extraction, then maintenance, and the maintainer writes
the pages. The source cursor only moved when the whole run succeeded. When a
maintainer wrote its pages and then failed on something small afterwards,
like saving the review questions or the result file, the run was recorded as
failed and the cursor stayed put. The next morning the schedule ran the same
batch through both paid passes again. The pages were already correct, so
nothing looked wrong. Only the bill grew.

The run now compares the notebook before and after. If pages changed, the
maintainer used the material, and the cursor moves on even though the run is
logged as failed. An interrupted run still doesn't move the cursor, because
Ctrl-C can land partway through a write. There was a second, quieter leak.
If extraction finished and the maintainer then failed without writing
anything, the retry ran extraction again on the same messages. Those notes
were already on disk, so the retry now reuses them.

## One stray file

When you copy a folder to a USB stick, macOS leaves a `._alice.md` file next
to each page. Emacs leaves `.#alice.md` lock links. Editors keep settings in
hidden folders. Every wiki command starts by listing the notebook, and the
listing treated any of these as a forbidden hidden path and refused the whole
notebook. So `co wiki show`, `search` and `sync` all failed because of one
file the user never made. A pasted log saved as a 3 MB page did the same
thing, and that included the commands you'd need to find and fix it.

A tester then found more of the same: a symlinked page, and a page saved in
Latin-1 instead of UTF-8. None of the errors said which file was the
problem. The listing now skips Finder and editor files without comment. It
also leaves out a symlink, an oversized page or a non-UTF-8 page, and prints
a warning on stderr that names the file and what to do about it. Every other
command keeps working. Asking for that one page directly is still refused,
but the refusal now names it.

## A dependency for a few users

`openpyxl` was installed for everyone, but the only thing that uses it is
the Wiki reading spreadsheet attachments. It's now the `wiki` extra. Without
it, an XLSX attachment is listed as unread, along with the exact command to
install it. The rest of the investigation goes ahead.

## What they had in common

In every case the code had one expected path and treated anything else as the
end of the run, whether that meant quietly dropping mail or refusing to open
the notebook. The fix in each case was to decide ahead of time what "keep
going" should mean, and to say what was skipped when we skip it.
