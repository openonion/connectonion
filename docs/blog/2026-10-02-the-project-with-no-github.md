# The project with no GitHub

The owner was reading a REM project page when he noticed what was missing: GitHub. The conversations were there, but an issue somebody opened, a PR waiting for review, and the discussion underneath either one had no direct route into the project's context. Someone still had to notice them.

His proposed first step was smaller than another project-analysis feature: give GitHub a listener like WhatsApp, put its messages in the inbox, and let the next program decide what to do. That boundary already existed. The inbox keeps a record before handing it out, claims work for a consumer, and offers unfinished work again. GitHub needed a source adapter, not another queue.

The authentication question helped make the first version concrete. Could it use the same credentials as GitHub's official CLI? Calling `gh api` lets gh keep responsibility for the login, the credential store and environment tokens. Co only saves the repositories to watch. Nobody needs to paste a second copy of an access token into Co.

Receiving events was less straightforward. Webhooks offer precise actions, but a laptop needs an address GitHub can reach, a separate signing secret and recovery for missed deliveries. Notifications are easy to poll, but a person's subscriptions do not cover everything in a repository. This preview implementation polls the repository resources instead and preserves source links and original Markdown. It can catch up after a restart while the content still exists. It cannot recover a comment created and deleted between scans. That limit belongs in the command's documentation.

The existing consumer exposed another difference. In a chat, its stdout is the answer to send back. A Codex task runner may print a long execution log. Sending that log as a PR comment would be a surprising consequence of attaching the runner. GitHub's consumer therefore handles work locally, and chat consumers gain an explicit `--no-reply` option for the same purpose.

Tests exercise replay, equal timestamps, pagination, failed delivery and a review on an old closed PR whose issue timestamp never changed. That last case has a cost: this first implementation reads reviews for every PR. On a large repository, API usage may make polling too slow. A webhook transport is the next decision if measured scan time makes this adapter impractical; the inbox interface can stay the same.

The visible entry points matter too. The README, documentation homepage and landing page each have a command logo wall. A command missing from one of them is harder to discover even when its help is correct. All three are now part of the repository's CLI audit checklist, with the corresponding documentation link checked alongside the logo.

This is a PR for a future preview, not an announcement that the package has shipped. REM will gain a GitHub source after this listener boundary is reviewed and exercised on real repositories.
