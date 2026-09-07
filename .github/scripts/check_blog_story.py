"""blog-gate's second door: the post must read like a story.

The existence check proves a post shipped; this proves someone would want
to read it. A changelog wearing prose — "we added X, we fixed Y" — fails.
A story has a problem someone actually hit, a turn, and a lesson.
"""

import sys
from pathlib import Path

from connectonion import llm_do

RUBRIC = (
    "You are the quality gate for a team's dev blog. Judge ONLY whether this "
    "post reads like a story a person would want to read: it has a narrative "
    "arc (a problem someone actually hit, a turn or complication, a "
    "resolution or lesson), it flows, and it is not a changelog, commit "
    "list, or feature enumeration wearing prose. Imperfect grammar is fine; "
    "honesty about mistakes is a virtue. Reply with exactly one line:\n"
    "  STORY: <what makes it work, one clause>\n"
    "or\n"
    "  NOT_STORY: <the single biggest fix, one sentence, concrete>\n"
)


def main() -> int:
    failed = False
    for name in sys.argv[1:]:
        path = Path(name)
        if not path.is_file():  # deleted in this PR
            continue
        verdict = llm_do(
            RUBRIC + "\n---\n" + path.read_text(),
            model="co/gemini-3.7-flash",
        ).strip()
        print(f"{name}: {verdict}")
        if not verdict.startswith("STORY"):
            fix = verdict.split(":", 1)[-1].strip()
            print(
                "::error::The dev-blog post does not read as a story yet. "
                "It needs a problem someone hit, a turn, and a lesson — not "
                f"a list of changes. Model's one fix: {fix}"
            )
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
