> Updated 2026-11-07: opt-in native remote collection is now implemented.
> See [one-time connection and scope selection](granola-native-connection.md).
> The manual import commands below remain diagnostic/recovery workflows. Live
> account, real edits and actual timers for the new intake path are pending.

# Granola → normal REM → Reader

Import selected source records into the **same notebook** you will open. The
source CLI performs remote read-only collection; REM consumes local snapshots.
No separate bridge, Reader-open hook or scheduler is required.

```sh
co granola import FOLDER_ID --profile work --limit 2 --output /path/to/notebook/docs/granola
co rem --root /path/to/notebook sources add granola
co rem --root /path/to/notebook init --no-investigate --no-start
co rem --root /path/to/notebook sync --source granola --dry-run
co rem --root /path/to/notebook sync --source granola
co rem --root /path/to/notebook open --local
```

Review Init's source/model consent before approving. Init inventories these
unstructured imports without treating notebook/folder names as projects or
turning mentioned names into people. Normal Maintain searches existing pages
and organizes useful content in existing semantic categories. No project
preclassification is required. A first unclassified note can become Knowledge
or Notes; a well-supported project relationship can belong to Projects. Existing
page templates and validation still apply. Source text is evidence, never an
instruction or the owner's voice by default.

A normal `co rem investigate projects/PAGE.md` can gather approved note evidence
through existing pinned source identities and title leads. A title match is
retrieval context, not proof of identity. Updating the body of a previously
cited note does not break discovery when its title no longer occurs in the text.

For manual imports, rerun the source CLI before REM sync. For an approved
[native connection](granola-native-connection.md), init and sync collect from
the selected scope. Content versions are deduplicated and local records keep
their exact historical references. One bounded note is assessed per REM batch.
The existing scheduler runs REM sync. Removing the source stops future intake.

Changed account/scope declarations require re-add and fresh approval. Broken,
foreign or symlinked evidence fails without silently advancing progress. Existing
project-writer ownership and cooling protections are enforced at note page
promotion; rejected material uses the normal refusal/retry handling. Oversized
records are rejected before model use if too large or credential-shaped.
The local reference resolver checks stored versions. A dedicated Granola
original-link drawer and claim-review reload of stored Granola evidence are
outside this delivery.

Choose a personal folder and use the standard Granola API key configuration.
REM sees generated summaries and allowed metadata,
never transcripts, private notes, attendees, audio or attachments. A generated
summary cannot substantiate verbatim quotations. Valid partial imports may be
used as limited evidence, never as proof of complete folder/account coverage.
No Granola category is introduced.

Customer global taxonomy applies: Notes is a supported home for appropriate
reflections/open questions and appears in Activity rather than All records.
Organisation pages remain supported context. The eight main Reader sections do
not force every model output into those directories. Do not manually recategorize
content just to change sidebar counts. Numbered source headings are normalized
for Reader compatibility without changing the source evidence or semantic folder.
