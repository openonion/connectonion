# The second package in the gate

Candidate repair for #2631; not released.

We were waiting on a Pillow compatibility decision when another REM change hit
the dependency gate. It was tempting to describe the failure as the same blocker
again. Reading the actual job log changed the next step: this run named two
packages, and the second was the PDF parser that reads attachments into memory.

The lock held pypdf 6.19.0. The audit reported five advisories, with the last fix
listed in 6.21.1. That raised a familiar question: would repairing it quietly
exclude users on Python 3.10? Official package metadata says 6.21.1 still supports
Python 3.9 and newer. This repair could proceed independently of Pillow's higher
minimum Python requirement.

We raised the pypdf floor and asked the pinned resolver to regenerate that package's
lock entry. Then we ran existing tests with the actual patched library: reading
PDF text, an empty page, annotations, and the boundary where a stamp's appearance
has not been verified. Passing imports would have been a weaker check than the
attachment behavior REM depends on.

The strict audit still failed. This time pypdf had no reported advisories and
Pillow remained. Calling the entire gate green would hide that distinction just
as surely as calling the earlier failure only a Pillow problem hid useful work.
A blocked release can contain an independently repairable cause; the log decides
which cause is present now.

No preview is published by this patch. Real notebook and native page acceptance
are still separate work. The useful result is a smaller, accurately described
release blocker without weakening the compatibility promise or the audit.
