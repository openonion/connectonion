# The environment before the agent

The old Quick Start opened with `co create`, `python agent.py`, and a tiny
word-count tool. That is a valid SDK exercise, but it was a poor first answer
to the question most people bring to ConnectOnion: “How does my agent reach my
Outlook, Gmail, browser and files?” A reader could finish the tutorial with a
working Python function and still not know which account `co outlook` would
use.

We considered adding another integration example below the Python tutorial.
That would preserve the original order, but the first screen would still imply
that writing an agent is required before using the CLI. We instead made the
main Quick Start follow the operator's actual sequence: `co init` creates the
global identity, `co env` shows the selected configuration without revealing
values, `co auth microsoft` connects an account, and `co outlook` uses it.
Other integrations follow the same discover, connect, use pattern.

The distinction between `co init ./` and `co --env-file ./.env …` belongs near
the top, not buried in a reference page. Initializing a project does not make
its `.env` the implicit source for future CLI commands; an explicit selector
replaces the global file, with no per-key fallback. Saying that early prevents
an agent from silently reading the wrong account. We also show that numbered
mail rows require the listing ID printed by the inbox.

The tradeoff is less room in the first guide for Python APIs. Those examples
remain in the Agent and Tools guides, linked as an optional next step. We
would revisit the ordering if the product's default first task becomes
writing a custom agent rather than operating an existing environment. For
now, the first command should help a person see where the agent is standing.

The demonstration needed the same care. A wide terminal GIF was readable on
the landing page but shrank to tiny type in GitHub's narrow mobile README.
Repeating a screenshot would preserve the text only by losing the sequence.
The README now uses a `<picture>` with a portrait GIF for narrow screens and
static posters for readers who prefer reduced motion. The run itself is a
read-only `co search ConnectOnion` result, shortened for the frame; Telegram,
remote agent and email steps remain an explicitly illustrative workflow.
