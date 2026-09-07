# When “Download” Quietly Meant “Replace”

The dangerous version of this bug looked ordinary. An agent downloaded an email, saved the first `cover.jpg`, then saved another attachment with the same sender-chosen name. The command reported both downloads, but the second write replaced the first. The same thing happened when a local file already had that name.

The downloader already treated attachment names as untrusted input: it stripped directory components and kept writes inside the selected destination. The missing piece was treating an existing filename as occupied data rather than an invitation to overwrite it. The fix keeps the first `cover.jpg`, then selects `cover-1.jpg`, `cover-2.jpg`, and so on, preserving the extension and returning the paths that were actually written.

The useful lesson is that safe path handling is more than preventing `../../` escapes. A path can stay inside the right directory and still destroy the wrong file. Regression tests now download duplicate names with different payloads and start with an existing local file; both original payloads remain readable, and the returned paths expose the disambiguation.
