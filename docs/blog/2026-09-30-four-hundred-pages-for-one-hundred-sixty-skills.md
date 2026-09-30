# Four hundred pages for a hundred and sixty skills

We ran co rem 1.9.0a2 on the owner's real notebook and opened the skills
catalog to answer a plain question: what is `ship-feature`, and does he actually
use it? The catalog had 420 pages. The owner has about 160 skills.

`ship-feature` alone had six pages. One for the copy in `~/.claude/skills`, one
for `~/.codex/skills`, one for `~/.agents/skills`, one for an old copy under a
different folder name, and two more from worktrees that no longer existed. Each
page opened with the same one-line description, then pasted the whole
`SKILL.md` below it. The median page was 198 lines, and the longest was 1,530.
None of them said whether he had ever run it. To find out, you would have had
to read six copies of the instructions and still come away without an answer.

The map had done exactly what it was built to do. It made a page per source
file, because two files with the same name might be two different skills, and
it pasted the source so the page would still say something if the file moved.
Both rules were careful. Together, on a machine where every skill is installed
for three harnesses and every agent session gets its own worktree, they produced
a catalog nobody could use.

The projects had the same problem. connectonion had two pages: one built from
agent worktrees and one from the main checkout. The browser repository was
split the same way. A Codex chat named after its first prompt,
"create-a-scheduled-task-called-weekday", had become a project. So had two
folders Codex made while installing plugins.

The fix was not to be less careful. It was to be careful about the right thing.
Two copies of a skill are the same skill when they have the same name, and a
content hash tells you whether they have drifted. The catalog now has one page
per name. It links to the source file instead of pasting it, and its `Source`
section lists every copy and marks each one identical or different. On his
machine that section shows `ship-feature` installed six times in three
versions. A copy inside a temporary worktree or `site-packages` is listed but
never gets a page of its own, because it will be gone or different after the
next checkout.

The question we started with now has an answer on the page. A script with no
model reads the session transcripts and counts invocations: Skill tool calls and
`/name` commands in Claude Code, `$name` mentions and `SKILL.md` loads in Codex,
once per turn. `ship-feature` was invoked 135 times in 180 days, most recently
two days before the run. The page calls these invocations, not successful runs,
because a transcript does not record whether the task worked.

For projects, a worktree folds into its repository, and `Paths` now reads
`~/projects/connectonion` and `Worktrees: 63` instead of listing each worktree.
A folder with no repository and a single session of three turns or fewer is a
chat, not a project. A folder the owner returned to, or talked in at length,
stays a project.

The part we were most careful about was the notebook that already existed.
Nothing is deleted. The next map merges the old pages into one. It keeps the
page with the most written content and adds the other page's written lines to
the matching sections, renumbering their citations. The old page goes to
`.state/archived/`, and its name becomes an alias, so links to it and commands
that use the old name still work. On a copy of the owner's notebook this turned
419 skill pages into 153, with a median of 57 lines, and 29 project pages into
21. Three split project pages were merged, and five chat folders were
archived.

What we took from it: a rule that is careful about one kind of mistake can
still produce a mess when the setup around it changes. Here, three harnesses
and a worktree per agent turned a careful rule into four hundred pages. When
that happens, what needs checking is whether the rule is being careful about
the right thing.
