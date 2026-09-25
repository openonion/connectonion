# Watch a background task

Use `watch_task(task_id)` after `run_background()` when the user wants you to return to this conversation after the task ends. The current turn can finish; the Host will wake this same session when the task completes or fails. Watches require the long-lived `co ai` Host. Do not claim that a one-shot CLI invocation can keep watching after it exits.
