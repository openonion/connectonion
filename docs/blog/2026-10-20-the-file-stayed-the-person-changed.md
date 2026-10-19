# The file stayed. The person changed.

A memory can acknowledge an identity mistake in one paragraph and quietly preserve it in a structured field.

During a read-only review of an existing notebook, one saved person page distinguished its intended subject from the person in older correspondence. Its contact-date field still referred to that earlier material. We have not established which historical writing step created the inconsistency. We did find a current mechanism that could undo a later correction.

REM preserves contact dates when a writer replaces them with Unknown. That helps an ordinary update avoid losing an extracted fact. But the restoration used the page path as continuity: a candidate could change the subject's title, leave the date Unknown, and receive the previous subject's date and citation anyway. Another promotion step could refill fields from an extraction packet gathered for the old subject.

An invented reproduction made this visible without another model call. Four contact-date cases failed, and the actual candidate-promotion path reintroduced an old source. The proposed repair leaves the candidate's Unknown intact after a subject-title change when no explicit routing anchor survives, and skips automatic refill from that prior packet. Case-only title edits keep ordinary restoration; explicitly supplied candidate facts remain.

This deliberately does less than entity resolution. A normal email/domain-to-name first write keeps recovery when its explicit address/domain is retained. A rename without that anchor needs its facts retained or reestablished explicitly. A shared filename cannot establish that the same person is being described. Same-title collisions and already-written mistakes still require review.

The two relevant suites now pass 204 tests. The installed CLI and scheduled runtime were upgraded to public 1.9.3rc7 before this audit; the proposed correction is not yet published. No private notebook was rewritten, no fresh init or model investigation ran, and no browser or visual acceptance is claimed. Reading 251 issue bodies helped separate this source-truth repair from the conflicting dashboard proposals. Source ownership is part of the page design: it determines which structured facts the reader can trust.
