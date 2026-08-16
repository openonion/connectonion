# A Work Room Is a Summary, Not a Transcript

The first time we let a Codex run stay alive for more than a reply or two, the
card looked impressively busy. It had provider detail, a tiny text preview,
approval controls, and a growing list of steps. It also made a simple question
surprisingly hard to answer: *what is happening now, and do I need to decide
anything?*

That became obvious during a deliberately ordinary C sorting task. Codex wrote
the files, paused to ask before compiling, paused again before testing, and
then carried on. Nothing was wrong with the agent. The problem was the
container around it: the conversation showed every bit of machinery at the
same volume, while the approval that needed a human sat in the middle of the
noise. A user should not have to read an execution log to decide whether one
scoped request is acceptable.

Our first instinct was to make the card richer: a terminal-like transcript,
separate file and activity panes, perhaps a thumbnail for each run. That would
have made the example look more like an IDE, but it would not have answered the
question that failed in the sort run. It would also have encouraged us to
pretend that text output was an image, or that a raw path from a provider was
safe presentation data. We stepped back instead.

The resulting Work Room begins with a much smaller promise. In the surrounding
conversation, a compact card says which provider is working, the safe category
of task, its current state, and how to enter. Inside, Overview answers the
current question first; Activity is the one place to look back. A verified file
name may appear as evidence, but there is no invented screenshot, terminal
transcript, second scroll region, or parallel chat to compete for attention.

Getting there meant drawing a line between native tools and the interface.
Codex and Claude Code remain native; their adapters translate private protocol
details into a finite lifecycle, semantic activities, and a verified approval
presentation. The React client accepts that limited vocabulary rather than
trusting arbitrary provider text. O Chat then renders the normalized state
without attempting to parse a server frame or promote a raw command into a UI
instruction.

The same distinction matters when the run pauses. A request says what action is
being considered, where it applies, and why it needs a decision. **Allow once**
and **Reject this request** answer that request. They are not disguised process
controls. Conversely, Stop is available only while a provider is starting or
running, and addresses that exact invocation. Keeping those verbs separate
turned out to be more calming than adding another mode or menu.

We checked the lesson with the same sort task that exposed the problem. A
disposable localhost Host ran real native Codex through two one-time approvals,
then independently rebuilt the resulting source with strict C11 flags and ran
its tests. A separate run sent a scoped Stop and reached the cancelled state
without ending the enclosing turn. Browser scenarios covered the compact desktop
card, long activity history, approval placement, stopped and failed states, and
375px/320px layouts.

There is still more to build, but it has to earn its place. A real visual
artifact can later arrive through its own typed contract. Model-reviewed Auto
approval and continuation chat remain separate fail-closed work. The lesson
from this release is simpler: a Work Room earns trust by answering the next
human question, not by replaying every machine detail that led to it.
