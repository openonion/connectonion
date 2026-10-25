# An allowance was not an execution log

Candidate implementation, not included in public 1.9.3rc16.

A saved translation failed its source-ID validation while its run record said
runner_attempts zero. Reading that as no model execution would be wrong: validation
happens after the harness returns. Manual investigations deliberately keep the same
field at zero to avoid charging the routine daily cap. Scheduled translation can
charge its parent instead. One counter had acquired two incompatible meanings.

Changing every zero to one would make the numbers look plausible while changing
budget policy and counting parents and children twice. Counting only successful
pages would hide failed work. We kept the allowance rule and observed a different
boundary: the attempt to execute the native co-ai subprocess.

Existing run records now hold that narrow observation, saved before execution and
updated after the wrapper returns or raises. A child links to its parent but owns
its direct attempts. Translation validation can reject a page after a successful
harness result without erasing the attempt or its returned usage. No prompt,
command, session ID or new copy of source material is stored by this observation.

A launch attempt is still not a provider API call. Authentication can fail before
inference; one harness can make multiple requests. Custom callbacks may bypass the
observed native boundary. Historic records cannot be reconstructed from allowance
or tokens alone. The interface says recorded attempts and leaves provider calls
unknown instead of manufacturing a precise count.

Four corrected native-boundary regressions failed on the unchanged base before
implementation. Additional controls cover cache hits, start/configuration failure,
parent-child accounting, interrupted wrappers, missing/corrupt/overflowing evidence
and both interface languages. These use isolated synthetic subprocess replies,
not a fresh account, model, mailbox, scheduler or real notebook trial. The reader
copy contracts are not current phone, keyboard or screen-reader acceptance.

Revisit this boundary if a harness exposes reliable per-request evidence; retain
explicit coverage and de-duplication rather than silently renaming attempts as
model calls. The broader memory product still needs useful, source-supported
corrections and current native acceptance.
