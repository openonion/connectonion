# The preview that started as a question

This preview began with three questions about the scheduler: is it
documented, is the code sound, and could it have a control panel? The honest
answers were no, mostly, and not yet. Each "no" became an issue before it
became code, and 1.8.8b9 is where they meet.

The order mattered. The docs could not be written until the code was right,
because two of the things a page would have to say were false. "A slow job
does not hold up the others" was false: jobs ran one after another under a
lock. "Add a job and it runs" was false for an agent that had started with an
empty schedule. So the fixes went first, as their own pull request, and the
command and the page were written against the fixed behaviour.

The command also exposed something the docs had nearly promised. The page
said a pause survives a deploy, because deploy protects the agent's `.co/`
directory. Checking that sentence found that protection only stops deletion.
A local copy of the state file was still sent to the server on every deploy,
and it replaced the server's record of what had run. The sentence is true now
because a test runs real rsync and looks at the file afterwards.

This preview also carries work from other sessions since b8: unattended Wiki
runs lose their shell and network, headless Claude Code returns to safe mode,
one browser daemon per user, and a first run whose messages are true. The
control panel buttons for the schedule are the next step (#1683). They will
write the same two fields the command writes, so the command line and the page
cannot disagree about whether a job is paused.
