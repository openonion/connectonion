# Build the map before asking a model to investigate

The local Wiki experiment was supposed to fill in an existing project page. Instead, the run produced write-existing-file errors and edits that did not match the file. The page could end up with repeated sections or references whose source definitions were missing. A normal process exit did not tell us whether the notebook was usable.

The mismatch began before the investigation. Initialization had asked a model to create a skeleton, while the investigation was now using a newer template. The two steps disagreed about the page they were working on. Asking for an edit meant asking the model to reconcile that disagreement while it was also trying to understand the evidence.

That made the first useful change surprisingly plain: create the map in code. Enumerate the available people, projects and installed skills, build their skeletons from the same templates, and record the scope. The model still has decisions to make later. A sender that looks automated might matter; a requested feature might never have been delivered. Creating a place for those questions does not require answering them.

We then changed how an investigation hands back its work. It writes a complete candidate file, which the runner can inspect before replacing the current page. Repeated headings and references without definitions become reasons to retain the candidate for diagnosis rather than promote it. The old page remains available when that check fails. The experiment no longer has to treat a successful process exit as evidence that the write succeeded.

There was another limit in the same path: the file reader capped long lines at 500 characters. A JSON document could be valid on disk while most of its content never reached the model. Keeping the exact source alongside a paginatable rendering made that loss visible and gave the reader a way through it. The lesson applied to both ends of the run: inspect what the model can actually read and what the notebook actually receives.

A single synthetic project became the acceptance unit before trying another batch. Structural checks still cannot decide whether a cited claim is true. They give factual review a coherent page and explicit evidence to examine. The map's job is to make that next step possible; it cannot stand in for the investigation itself.
