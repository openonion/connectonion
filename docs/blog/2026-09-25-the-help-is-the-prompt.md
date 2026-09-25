# The help is the prompt

1.8.9b2 is a release about text. No command gained a feature. What changed is
what 264 help pages say, and a test that keeps them saying it.

The reason is who reads them. A person skims `--help` and fills the gaps from
experience. An agent has only the page. If `co status` does not mention your
balance, an agent looking for the balance moves on, even when the command
would have printed it. We measured this before touching anything: a model
given only the help pages it asked for found the right command for 9 of 14
everyday goals. In each failure it had already opened the right page.

So the preview makes each page answer three questions: what is this for, what
will it change, and how do I run it. The third has a test that reads every
example and checks that its flags exist. A fourth line, the way back to the
parent page, is generated from the command tree, so nobody has to remember it.

Writing "what it changes" from the code, rather than from memory, is where the
real bugs turned up. `co auth feishu` creates an application in your Feishu
tenant, and its help never mentioned that. `co keys --write` wrote to a
directory its help did not name. Neither is a large bug. Both are the kind an
agent would repeat to a user with confidence, because the help said so.
