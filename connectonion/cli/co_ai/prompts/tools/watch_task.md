# Watch a background task

Use `watch_task(task_id)` after `run_background()` when the user wants you to return to this conversation after the task ends. The current turn can finish; the session watch service will wake this same session when the task completes or fails. A running Agent session service is required; a one-shot CLI invocation cannot keep watching after it exits.
