# The sentence that kept saying "framework"

We were asked a simple question: what is this, in one sentence? Three places
answered it differently.

The README said "a simple, elegant open-source framework for production-ready AI
agents". The PyPI summary said "a simple Python framework for creating AI agents
with behavior tracking". And the file AI crawlers read first on the website,
`llms.txt`, promised end-to-end encryption and migration tools. Neither exists:
the relay terminates TLS, and there has never been a migration tool.

The honest answer was sitting in `cli/main.py`. Count the top-level commands a
person can run without writing any Python: `co browser`, `co gmail`, `co outlook`,
`co gcalendar`, `co gdrive`, `co syno`, `co email`, `co sms`, `co telegram`,
`co whatsapp`, `co feishu`, `co call`, `co deploy`, and more — over thirty in
all. That is not a framework you adopt. It is a toolkit an agent uses. And
because every capability is a shell command, anything that can run a shell can
use it, including coding agents that have never imported our package.

So the sentence became: **ConnectOnion is the command-line toolkit for AI agents.**
It sits in `docs/PRODUCT.md` §0, and the README and PyPI summary now say the same.

The turn came while checking that sentence against the rest of `PRODUCT.md`.
The foundation document, the file that exists to stop us publishing false
claims, was publishing two of its own. It said "there is no `co calendar`, do not
claim calendar from the CLI", but `co gcalendar` and `co outlook calendar` both
shipped. Its list of things that are not true said `co deploy --to` "does not
exist", yet `co deploy --help` now offers exactly that. Both entries were right
when they were written. The CLI moved and the document did not.

That is the lesson worth keeping. A list of "things that are not true" goes
stale the same way a list of features does, and more quietly, because nobody
re-reads a prohibition. Each entry here was re-checked against the help text on
`main` before anything was reworded. Calendar is marked as reinstated in
`SELLING_POINTS.md` rather than deleted, so the history of why it was ever cut
stays readable.

Two words stayed out of the new sentence on purpose. "Best", because nothing we
can point to ranks us. And "framework", because it names the thing people are
relieved not to have to adopt.
