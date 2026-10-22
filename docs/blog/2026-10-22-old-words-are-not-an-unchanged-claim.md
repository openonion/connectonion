# Old words are not an unchanged claim

Candidate repair for #2639. Not released.

REM protects accepted content while new evidence is added: a small source packet
cannot re-prove the whole relationship on every turn. But the source audit used
an unsafe shortcut. It removed every space and citation, then checked whether a
refuted sentence appeared somewhere in the previous Markdown. That could turn a
FAIL into PASS after a condition disappeared, a citation changed originals or a
historical statement moved into the current state. Even `now here` and `nowhere`
looked identical. A heading or code example could supply the matching characters.

Word boundaries alone would leave the conditions and evidence problems. Another
prompt would leave the code that overrides the model's verdict untouched. Whole
page equality would prevent small updates. The selected boundary is complete
unchanged prose context: preserve word separation, title and section placement,
and each numbered citation's original identity and relative location. Every
candidate occurrence must be covered. Removing or reordering an old neighbouring
paragraph or bullet invalidates the section's exemption; qualifications may live
outside the same sentence. A whole old block can remain before a new sentence
when the earlier context and evidence still match.

Independent AI source review caught two holes in the first implementation. We
kept source order but discarded the recorded citation positions, allowing a
citation to move to another sentence. We also excluded the main title, allowing
a pronoun assertion to inherit protection after the page subject changed. Two
review-level tests reproduced these before the correction. They join the initial
nine failing controls and the later adjacent-qualification cases.

Protection is not verification. An unchanged finding retained under the existing
policy now leaves an insufficient report and a visible deferred count in the
promotion record. It does not become a factual pass. Active new failures still
reach the ordinary repair and refusal path. Missing or ambiguous source bindings
cannot establish continuity. A conservative unmatched rewrite receives ordinary
review; there is no fuzzy claim-equivalence model in this change.

These tests exercise report classification and synthetic notebook promotion,
not a real model's ability to discover every source error. Syntactic continuity
also cannot prove that added surrounding prose has the same meaning or that an
old accepted statement is correct. No real notebook was rewritten, no new model
or provider run performed, and current native product acceptance remains open.
