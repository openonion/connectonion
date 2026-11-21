# A write confirms the preview

A vault reader and a vault writer have different consequences. The read-only
Obsidian CLI in #3039 is the foundation; this follow-up proposes just `create`
and `append`, without REM integration or multi-vault subscriptions.

The first call describes a change. It does not save a receipt or touch the vault.
The next call carries `--yes --expect`, binding the confirmation to the operation,
selected scope, target, input bytes and original note version. If the note or
selection changed, the caller must preview again. A numbered listing may locate
an append preview, but the confirmation names the actual file.

We considered accepting `--yes` on its own, as many CLIs do. It is convenient for
scripts but loses the connection between what was inspected and what is written.
Requiring a preview hash adds one call while making stale confirmation explicit.
The token is a local consistency check, not proof that a human reviewed the text.

Create refuses an existing name. Append keeps the original Markdown and adds the
requested text, with a line separator when needed. Staging the complete result
before publication avoids truncating the original on an ordinary staging error.
It also replaces the inode on append: mode bits survive, but extended attributes,
ACLs and ownership are not promised. That tradeoff is documented rather than
presented as an invisible in-place edit.

Directory handles and a cooperative lock protect the local write path on macOS
and Linux. Content and scope are rechecked before publication. These checks do
not create a compare-and-swap transaction with Obsidian or a cloud sync client;
external edits should be paused during confirmation. Windows writes are refused
until an equivalent handle-based publication path is implemented.

Tests have been added for preview side effects, stale and reused confirmations,
scoped paths, newline preservation, stdin replay, row conversion and failed
staging. The author reports that the two new write test files, four reader/CLI
and shared-listing regression files, and `co audit co obsidian` passed locally
on macOS. A live walkthrough also exercised create/append previews, confirmed
writes, stale-confirmation refusal and refusal to overwrite an existing note;
the author confirmed that the final read retained the expected content. These
are local validation results, not a full-suite or upstream CI pass. This entry
describes a proposal, not a released feature.
