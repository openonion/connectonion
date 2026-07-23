# browser-workflow-skill-builder

Build robust browser automation skills for logged-in web apps (LinkedIn, X/Twitter, YouTube, Stripe, …) — explore the real page first, then lock the flow into a repeatable, evidence-backed skill.

## Install

```bash
co copy browser-workflow-skill-builder
# → .co/skills/browser-workflow-skill-builder/SKILL.md
# → .co/skills/browser-workflow-skill-builder/scripts/extract-items-template.js
# → .co/skills/browser-workflow-skill-builder/scripts/verify-item-template.js
```

## Usage

```
/browser-workflow-skill-builder build a skill that comments on LinkedIn feed posts
```

## What the Skill Teaches

The core pattern: **save context → analyze DOM/CSS → write skill-local JS extraction → verify the same item by hash → click/type with generic browser tools → screenshot/context verify**.

1. **Explore first** — screenshot + `save_page_context`, inspect `elements.json`/`page.html`, find stable semantic selectors (aria-label, role, data-testid) before writing any automation
2. **Skill-local scripts** — site-specific DOM logic lives in the target skill's `scripts/*.js`, never in the browser core; extraction returns structured JSON with a deterministic `text_hash`
3. **Verify before acting** — the same item is re-verified by author/text/hash before every click, type, and submit; a mismatch stops the run and leaves evidence
4. **One-shot side effects** — final submit/post/publish is clicked exactly once; pre/post screenshots and saved context are mandatory evidence
5. **Dry run with new input** — a flow counts as locked only after it passes with a different input

Two starter templates ship with the skill: `extract-items-template.js` and `verify-item-template.js`.

For the underlying browser commands, see [co-browser](co-browser.md).
