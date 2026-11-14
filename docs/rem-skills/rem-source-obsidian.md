# Why rem-source-obsidian says what it says

The rules live in `connectonion/useful_skills/rem-source-obsidian/SKILL.md`.
Like the Codex and WhatsApp source Skills, this file explains the design; it
is not loaded as runtime instructions. These rules are specification-derived,
not claims of observed improvements from a paid model evaluation.

## Reuse the existing composition

`rem/runner.py` already appends `rem-source-{kind}/SKILL.md` for the
source kind of a maintenance or extraction batch. Investigations
with Obsidian evidence include the same reading rules alongside the relevant
page Skill.

The stage determines the output and page boundaries. The source Skill explains
the evidence. This follows `rem-source-codex` and `rem-source-whatsapp`; it does
not copy their assumptions about session messages or identifiable chat speakers.
The `abstract` stage reads notebook pages and deliberately receives no source
Skill.

## A vault is a collection, not one speaker

The adapter supplies `role: note`, not `role: user`. A stored article, a quoted
statement and an adopted decision can all appear in a personal vault. Treating
them alike would turn reading material into the user's beliefs. Frontmatter,
titles and tags assist navigation but do not settle attribution or adoption.

Useful learning belongs in Knowledge when supported. Decisions need an actual
choice; standing principles need adoption or the stage's separate evidence for
inference. Open questions do not become decisions because a file is tagged
`decision`. Directly stated adoption in extraction/maintenance is distinct from
`rem-abstract` inferring a principle across multiple decisions; this Skill does
not change that stage's threshold.

## Links help find pages without proving their contents

A wikilink supplies a spelling, sometimes an alias or heading, rather than a
verified identity. Existing pages and surrounding prose can resolve the target;
an ambiguous person stays ambiguous. The subject owns the page, not the note's
filename. The stage still decides when there is enough material for a page and
whether this pass is allowed to change it.

When a task enumerates its input files, that list bounds file reads and existence
checks as well as writes to the designated candidate. Reading one fixture grants
no access to sibling filenames. A past withdrawal attempt guessed an extra file
to check whether it existed after reading the authorized inputs. The source Skill
now makes that boundary explicit: verify the candidate through its own read-back,
and retain uncertainty when evidence is missing. The benchmark's inputs and
expectations stay unchanged; completed page content alone does not verify access
behaviour.

Project investigation counts authorized note snapshots as supplied project
evidence. A note-only packet must not receive the repository-only empty-input
restriction merely because it has no coding session. Notes may support cited project constraints and
changes. Their presence
does not establish the vault owner's authorship, endorsement or commitments.

## Snapshots retain provenance and changes

Collection records immutable changes under `inbox/obsidian/<instance>`.
A maintenance batch can deliver several unconsumed revisions of one note. The Skill treats
an explicit correction as a correction, not several independent votes. Exact
`source` IDs identify versions; `note_id` groups them, and the reference points
to the committed record. Extraction must retain the exact supporting IDs.

`timestamp` represents collection, and file mtime is also not a claim date.
Neither can date a meeting or decision without evidence in the note.

A deletion is a withdrawal marker with no body. Other independent sources may
still support a claim, so deleting a whole Wiki page would be unsafe. Rules can
guide the current maintenance pass; they do not implement deterministic global
contribution retraction. Missing-from-batch is also not a deletion.

## Verification

The source Skill benchmark in `examples/rem-skill-evals` uses synthetic examples. The [Obsidian CLI guide](../cli/obsidian.md)
shows how to test a selected live vault through REM.
