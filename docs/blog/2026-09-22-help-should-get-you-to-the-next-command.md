# Help should get you to the next command

The user ran `co wiki investigate` and received a missing-argument error. Help offered `people/emma.md` as an example. They tried that path and another person's name. Neither file existed. Every response described a valid piece of the interface, but none supplied the missing connection: where to find a page that belonged to this notebook.

We could have written a longer Skill telling the agent to list pages first. That would help an agent that loaded the Skill, while leaving the terminal user with the same problem. It would also create another copy of the command's usage rules. Our decision was to put the workflow in help and share its definition with the no-argument overview. The Skill routes to that guide and adds evidence judgment.

The resulting help starts with a task. It explains when to initialize, how to discover inputs, which command performs the work, and what to inspect afterward. Calling `investigate` without arguments lists actual local pages without running a model. A unique exact title or email can identify a page; several matches produce choices. The next command carries the selected notebook directory, including shell quoting for spaces.

The interface also has to say what success means. Initialization builds a map, with source coverage and unknowns; it does not establish that a person or project has been researched. Investigation can finish while evidence remains incomplete. A source preview reads metadata, while a later sync may call a model. Current source authorization uses `start`, which also installs a background schedule. That coupling is visible in the help rather than hidden behind an instruction to retry.

We tested the guide as input to a fresh text-only model. Seven goals, each paired only with the relevant help page, produced seven correct command choices. A separate output-tip test initially exposed an invented `--paths` option. We clarified that the printed next command already lists paths; the final sixteen cases passed. Suggested commands were graded as text and never executed against an account.

Those results establish a narrow property: the guide can support the tested choices. They do not prove that an agent can complete every workflow or verify generated facts. The next evaluation should give an agent synthetic fixtures, help and command outputs, then check whether it discovers real inputs, finishes the work, verifies the result and stops correctly.

The change ships in the opt-in [1.8.7b4 preview](/releases/1.8.7b4.md). The [Wiki guide](/cli/wiki.md) describes the command sequence. If help grows too large to choose from, we should split detailed workflows into command-specific pages while keeping the group guide focused on routing. One source of usage knowledge still needs several levels of detail.

## Release-line correction

After the b4 preview, the release plan reserved 1.8.7 for a dashboard patch and moved Wiki to 1.8.8. The next Wiki preview is 1.8.8b1. Earlier preview links and measurements above describe their original artifacts; they are not renamed. This separates the feature trial from the smaller patch without changing the workflow described here.

A release audit also found that combining the documented dry-run option with backfill dropped the inspection flag in a recursive call. We reproduced it with a fake collector that failed if body collection began, then moved inspection ahead of execution-mode dispatch. The example matters beyond help text: a command described as a preview must remain one when its options are combined.
