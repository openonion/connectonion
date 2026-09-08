# The preview had to be a package

The test summary was green, but the NAS test had nowhere to connect. That was
where preparation for ConnectOnion 1.8.4 stopped being a question about the code
and became a question about what the version number would claim.

The combined local suite had passed 8,562 tests. The browser suite had passed
220. We had also built a wheel, installed it outside the checkout, copied its
Control Center starter and exercised approval, rejection and rollback. Those
results were real. So was the missing Synology profile. A simulated transport
could prove our handling of an interrupted copy; it could not prove that an
actual DSM installation accepted the negotiated request.

Gmail had a similar unfinished journey. The tests could change a draft during
review and inspect the exact bytes submitted afterward. They could lose a send
response and prove that a second command did not blindly send again. The live
journey still needed to create disposable Drive attachments, send once to the
same account and inspect what Google delivered. A successful mock assertion
was not a delivery receipt.

The owner asked for a preview first, then more local testing. That changed the
next action without changing what remained untested. The intended stable release
was still 1.8.4. The package we could publish for this next round was 1.8.4a1,
an explicit opt-in version while ordinary installation stayed on 1.8.3.

There was a trap in taking that shortcut. If the next tests imported our checkout,
we would learn little about the preview someone else could install. An editable
installation had already made source selection something we had to check
explicitly. The acceptance process therefore needs to start again from the
published artifact, in a fresh target and an unrelated working directory. Its
version and import path are assertions, not assumptions about which interpreter
happened to run the command.

That also determines how the package leaves the repository. The reviewed tag
runs the protected build and publishing workflow. Its final checks download the
public wheel and source archive and compare them with the preserved build
artifacts. Rebuilding a different wheel on a workstation and uploading it would
break the connection between the package exercised by CI and the package the
next test installs.

The preview does not make the missing NAS appear. It does not turn the pending
mail journey into a pass. It gives those tests an exact, obtainable input. The
release notes keep the completed local checks and the remaining provider checks
separate, and the GitHub release must be a prerelease rather than Latest.

This entry records the preview decision before publication is confirmed. The
next useful result will be a test of that public package, with the same remaining
questions still written down. Publishing an alpha is useful here because it
makes the next experiment reproducible; calling the work stable would hide why
that experiment is still needed.
