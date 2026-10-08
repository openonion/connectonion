---
description: co rem 1.9.1rc1: when a first run got four times more parallel, two locks that had always been fast enough were not.
tags: [REM, Reliability]
---

# Sixteen workers and one lock

The 1.9.1b5 first run wrote all 280 pages in 82 minutes, half the time of the
morning's preview, then went back over 55 people with two more years of mail
and drew five decisions and a principle from what it had written.

It also lost two pages, and neither to the model. Both waited for a lock and
gave up: one for the notebook, while another page's review held it; one for
the credential file, while twenty mail workers refreshed the same token. Thirty
seconds had always been enough, because nothing used to run at the same time.

The candidate waits as long as the work deserves: up to ten minutes to save
something already paid for, two minutes for a token refresh. Making a system
faster moves its slowest wait somewhere new; the only way to find it is to run
the whole thing.
