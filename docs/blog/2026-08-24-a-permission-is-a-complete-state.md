# A permission is a complete state

RC5 reached the part of the release gate that only a real remote coding session could exercise. Codex was running with a bounded outer Full Access grant. The browser showed seven turns left. A provider-only follow-up was stopped, the user returned to the parent conversation, and the control suddenly said Auto.

Nothing had actually lowered the Host permission. The provider still correctly retained Full Access. The browser and the authority had split.

The direct Work Room runner had copied the mode name into its isolated session but not the positive `turns_left` value that makes bounded Full Access valid. ConnectOnion's canonical reader did the safe thing with that incomplete pair: it treated it as Auto. The isolated runner then synchronized that degraded view to the browser, even though it did not own the durable outer permission transaction.

The tempting fixes were in the wrong layers. We could have made the UI ignore the Auto update, or weakened React's stale-revision protection so a later provider snapshot appeared to repair it. Both would teach a client to guess which server fact was real.

The fix stays at the boundary that created the isolated session. A direct Codex or Claude Code continuation copies the Host-validated mode and, only for Full Access, the same positive remaining budget. It does not renew the grant and it does not consume an outer COAI turn. An invalid or missing budget still degrades to Auto.

The broader rule is small: authority is often a tuple, not an enum. If one field makes another field valid, copying only the label creates a new state with different meaning. A remote client should display a complete authoritative state or no claim at all.

RC6 must prove this with the same sequence that found it: real Codex Full Access, a provider follow-up, Stop, return to the parent, an actual acknowledged outer downgrade, and immediate provider narrowing. Unit tests describe the invariant; the release gate proves the ownership boundary.
