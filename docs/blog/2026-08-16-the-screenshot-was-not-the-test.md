# The Screenshot Was Not the Test

Alpha 12 began with a request to look at the screenshot.

The screenshot showed a credible product. Claude Code had a completed card and
an **Open Work Room** button. The invite flow appeared once. The approval card
offered Allow once, session trust, rejection, Stop, and explanation. A cancelled
Bash card turned red and reported `exit 1`.

Two production blockers were still hiding behind those correct pixels.

After pressing Stop on `sleep 120`, the chat said the tool was interrupted. A
process-tree check found both the shell and its child still running. The Agent had
correctly revoked the abandoned worker's result, so no late output could enter the
conversation, but the operating system had not stopped doing the work. The fix
needed an isolated process group and cooperative cancellation inside the Bash
tool, not another frontend state.

The image attachment preview was equally convincing. The thumbnail rendered in
the composer and OIP delivered an image to the Host. Only after Send did the
skills plugin call `.startswith('/')` on a multimodal content list and crash the
turn before the model ran. The fix needed the plugin to locate and replace only
the text part while preserving image parts, not an upload-card adjustment.

The same discipline caught a subtler Work Room defect. Claude's real provider
session resumed successfully, but the room displayed the resumed result before
the initial result. Looking at one completed card proved the adapter worked;
reading the entire chronological room proved whether it remained understandable.

Alpha 12 therefore pairs each visible assertion with an owner-side assertion:

- an invite dialog count with signed onboarding frame counts;
- a completed card with the exact provider session ID;
- a Stop state with an operating-system process query;
- an attachment preview with Host input counts and a completed model turn;
- a reconnect screen with the same session restored by an older exact client;
- a rollback claim with the same stored session resumed by an older exact Host.

The exact rollback tests were deliberately asymmetric. React alpha.10 created a
session that alpha.9 resumed on the public alpha.11 Host. Then the alpha.11 Host
created a session, the process was replaced by public alpha.10 using the same
address and storage, and the client continued that exact session. Both returned
distinct before/after markers rather than merely reconnecting to an empty chat.

Screenshots remain valuable. They catch the hierarchy, wording, duplication,
mobile layout, and ordering users actually experience. They become dangerous
only when “looks stopped,” “looks attached,” or “looks resumed” is treated as
proof that the owning system did the same thing.

The release lesson is a compact one: test the pixel, the protocol, and the owner.
For external work, test the resource too.
