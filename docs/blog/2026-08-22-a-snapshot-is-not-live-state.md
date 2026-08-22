# A Snapshot Is Not Live State

The 1.7 beta opened with a reassuring Control Center. A green dot sat beside
“Ready,” followed by “Available for a new task.” Then we sent a real Rust job
through `co ai`, watched the agent create files, and stopped at a genuine shell
approval.

The Control Center still said Ready.

Nothing had failed to update. That was the problem. The starter dashboard is an
HTML snapshot sent when the client connects and after a turn changes the page.
It does not receive thinking, approval, input-wait, Stop, failure, or completion
frames. We had put a live claim on a surface with no live information.

The same end-to-end run found a second version of the mistake. O Chat showed
“live” under the composer after the final result had arrived. That word came
from the WebSocket being active, not the task still running. Two technically
correct implementation facts contradicted what the person saw happening.

The fix starts with ownership. Core's starter no longer invents a runtime state;
it points to Chat for current work, approvals, and results. O Chat derives one
authoritative phase from transport, pending decisions, and task activity, then
shows the same phase beside the composer and above the sandboxed Control Center:
Working, Approval needed, Input needed, Connected, or Disconnected.

The phone screenshot caught one more boundary error. A long Quick Action
description set the grid item's minimum width, so the iframe grew a horizontal
scrollbar and clipped its right edge. Explicit zero minimums now let the card
shrink to the pane instead of asking the pane to grow around its content.

Unit tests can prove that a template contains text and that a phase reducer has
the right precedence. Only the real Host → browser journey showed that the two
surfaces disagreed. The lesson is broader than dashboards: if a component does
not consume lifecycle events, it cannot truthfully describe lifecycle state.
