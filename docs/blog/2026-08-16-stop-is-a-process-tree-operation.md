# Stop Is a Process-Tree Operation

The browser said the command had stopped. The Host disagreed.

In a real OIP test, an operator approved `sleep 120` and then pressed **Stop**.
O Chat promptly rendered an interrupted tool with `exit 1`. A process-tree check
afterward still found both `/bin/bash -c ...` and its `sleep 120` child. The UI
had cancelled ownership of the result, but the operating system was still doing
the work.

ConnectOnion's general interrupt boundary deliberately runs arbitrary blocking
Python on an abandonable daemon thread. Python cannot safely kill an arbitrary
thread, so the Agent revokes that worker's IO lease, ignores late output, and
continues. This protects conversation state, but it cannot undo external side
effects. Tools that own cancellable external work must cooperate.

The built-in `bash` tool did not. It used blocking `subprocess.run()` and had no
runtime Agent parameter, so it could not observe the revocable IO lease. Killing
only the shell would not have been enough either: shell commands routinely spawn
children, and those children can outlive their parent.

Hosted Bash runs now take the cooperative path. The tool receives the Agent as a
runtime-only parameter that is absent from the model-visible schema. It launches
the shell in a new process session, polls the lease while collecting output, and
terminates the entire process group on Stop or timeout. A short grace period uses
`SIGTERM`; a surviving group receives `SIGKILL`. Direct local calls keep the
existing `subprocess.run()` behavior.

The regression test does not stop at checking an `interrupted` trace. It launches
a real child process, records its PID, sends the same interrupt used by OIP, and
then proves that the PID no longer exists. That distinction matters: protocol
state can say “cancelled” while resource state says “running.”

Cancellation therefore has two separate contracts. The framework owns result
isolation: cancelled work cannot commit late Agent state or emit late UI events.
The tool owns resource termination: processes, sockets, browser jobs, and provider
sessions must expose a cooperative stop path when they can safely do so.

The practical rule is simple: if a tool starts an external resource, its Stop test
must inspect that resource, not just the card rendered in the browser.
