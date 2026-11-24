# The host is the agent now, not its parent

Someone stopped `co host` the ordinary way, with `kill` and the PID, and ran
it again. The second start said "Port 8000 is already in use". Nothing visible
was running. `lsof` showed what was: `python agent.py`, still listening, its
parent now PID 1. Stopping the host had stopped only half of it.

`co host` did not serve anything itself. Since 1.9.2b19 it has started
`./agent.py` with co's own Python, so the command works however co was
installed, and it did that as a child process with `subprocess.call`. A
parent and a child are two processes, and a signal sent to one PID reaches
one of them. SIGTERM and SIGHUP killed the `co host` wrapper and left the
agent running, holding the port, with nobody left to stop it. Ctrl-C in a
terminal happened to work, because the terminal signals the whole foreground
group. A SIGINT sent to the PID also stopped the agent, but only because
`subprocess.call` cleans up with SIGKILL, so the host never ran its own
shutdown.

There were two fixes on offer. One keeps the child and teaches the parent to
pass each signal on: handlers for TERM, INT and HUP, a wait, and still
nothing for SIGKILL, which no handler can catch. The other removes the
second process. On macOS and Linux, `co host` now calls `os.execve` and
becomes agent.py: same PID, same terminal, same environment. Whatever holds
that PID, whether a shell, `kill`, or launchd behind `co host --background`
and `--stop`, is holding the agent. There is nothing left to forward, and
nothing to outlive it. Listen channels from `.co/host.yaml` were already
threads inside agent.py, so they go down with it. Windows keeps the child
process, because exec there starts a new process and returns the prompt
early.

What we measured. On a throwaway project on a spare port, before the fix:
after SIGTERM the agent's parent went from the host's PID to 1 and the port
stayed taken, and SIGHUP did the same. After the fix the listener's PID is
the `co host` PID, and after SIGTERM, SIGHUP and SIGINT nothing is listening.
SIGINT now ends with exit code 0, a clean shutdown, where before it ended in
SIGKILL. The regression test stops `co host` with each of the three signals
and checks that agent.py is gone. On the old code it failed for SIGTERM and
SIGHUP ("agent.py outlived co host"), and with the fix it passes.

One side effect: the existing `co host` tests used to run the command inside
pytest. With exec, that would have replaced pytest itself, so they now run
`co host` as a real process.
