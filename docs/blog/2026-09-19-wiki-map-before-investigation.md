# Build the map before asking a model to investigate

The Wiki's map and investigation had drifted apart. Init ran a model to create
people and project skeletons, while newer page templates asked for sections an
older skeleton did not contain. Investigation then edited the old page directly.
A failed local experiment exposed repeated write-existing-file errors, mismatched
edits, duplicated sections and references without source definitions.

The revised init enumerates people, projects and installed skills in code and
records its scope. The model is no longer needed to create those skeletons.
Judgment remains in the Skill: an automated sender hint does not decide whether
a correspondent matters, and a request in a session does not establish delivery.

Investigation now writes one complete candidate file. The runner checks its
structure and citations before replacing the existing page. It retains rejected
candidates so a normal process exit cannot hide an unusable page. This is a file
validation step, not a semantic truth engine: citations can be structurally valid
while a claim is wrong, and model output still needs factual review.

The input also has two forms: exact JSON for machines and a paginatable rendering
whose long strings are split into reversible chunks. This avoids a file reader's
500-character line cap silently discarding most of a JSON document. Concrete
customer examples were removed from the person template; the prompt provides
shape and rules, while evidence supplies facts.

A single synthetic project is the acceptance unit before another batch. The
reader repairs remain in the same review, while the broader experience and
sharing design continue in #1580. Nothing here starts an overnight queue or
publishes a notebook.
