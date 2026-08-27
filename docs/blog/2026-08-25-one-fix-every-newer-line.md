# One Fix, Every Newer Line

Version 1.6.12 was released with a reassuring list: bounded provider requests,
safe Outlook attachment downloads, server-region choice, mailbox sharing, and
release evidence that survives the machine which produced it. Then the 1.7
candidate was inspected by ancestry rather than by release notes. Its branch
did not contain the 1.6.12 tag. Neither did `main`, where 1.8 work had already
started.

Some changes had arrived independently. Others had not. That partial overlap
was the dangerous state: a quick feature check made the newer lines look
current, while the provider timeout and inline-attachment boundary were still
missing. Copying the entire old release was no answer either, because it would
also copy 1.6 version metadata into branches that identify as 1.7 and 1.8.

The repair treats a stable fix as a set of behavioural promises, not as one
commit to merge blindly. Each applicable promise is compared with each newer
supported line. Missing implementation, tests, documentation, and release
guards move forward; version numbers and old release staging do not. A feature
already present on a newer line stays there instead of being duplicated.

That distinction is now written into the release contract. A stable release is
not finished merely because its tag exists. It is finished when every supported
newer line either contains each applicable fix or records why the fix does not
apply. The ancestry check found the gap this time; the contract is meant to
make the next gap visible before a candidate is called ready.
