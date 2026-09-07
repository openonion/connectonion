# A tool result is not a final answer

RC6's release gate asked Claude Code to build and test a bounded C11 project. Claude finished the work, returned success, and left behind files that compiled and passed independently. Then the parent model returned no text.

That empty response exposed a seam between two kinds of completion. The provider invocation was complete, but the conversation was not. A remote coding client needs both: verified work and a usable handoff that restores the composer.

Treating the empty response as success would fabricate an answer the model never gave. Treating the provider result itself as the assistant answer would expose an internal envelope and collapse the distinction between evidence and explanation. Waiting forever was safer than inventing success, but still wrong for the user.

The repair is deliberately bounded. After real tool execution, an empty terminal model response gets one more call with a narrow instruction: summarize only what the recorded tool results prove. If that call is also empty, the turn fails explicitly. Empty assistant messages are never persisted.

This is the same principle Workrooms use elsewhere: internal state and user-facing state are related, not interchangeable. A tool can prove the work happened. The parent still owns the final answer, and the Host still owes the client exactly one terminal outcome.

RC7 must repeat the exact Claude parent and Workroom journey. The regression test proves the boundary in isolation; the release gate proves the composer recovers in the real client.
