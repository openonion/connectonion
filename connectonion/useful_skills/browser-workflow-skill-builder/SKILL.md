---
name: browser-workflow-skill-builder
description: Create robust browser automation skills for sites like LinkedIn, X/Twitter, YouTube, Stripe, or other logged-in web apps by saving page context, analyzing HTML/CSS, writing skill-local JS extract/verify scripts, and using CSS selector actions with screenshot verification.
tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
---

# Browser Workflow Skill Builder

Create or improve browser automation skills for logged-in web apps. Use this when building skills that read a page, choose the correct item, generate or prepare content, click/type/upload, or submit/post/publish.

The core pattern is: **save context -> analyze DOM/CSS -> write skill-local JS extraction -> verify same item by hash -> click/type with generic browser tools -> screenshot/context verify**.

## Architecture Rule

Do not add site-specific Python to the core browser tool.

Use generic browser primitives:

```text
save_page_context(name)
take_screenshot(path)
run_page_script(script_path, args_json)
run_frame_script(script_path, args_json, frame_url_contains, frame_name)
click_element_by_selector(selector, index, text)
type_text_by_selector(selector, text, index)
click_element_near_selector(anchor_selector, target_selector, target_text, ...)
upload_file_by_selector(selector, file_path, index, frame_url_contains, frame_name)
upload_file_after_click_by_selector(click_selector, file_path, index, text, frame_url_contains, frame_name)
```

Put site-specific selectors and DOM logic in the target skill:

```text
.co/skills/<target-skill>/
  SKILL.md
  scripts/
    extract-<items>.js
    verify-<item>.js
```

`run_page_script(...)` runs JS in the main document of the current browser page, so it shares the same browser context, login cookies, current tab, and DOM state.

`run_frame_script(...)` runs the same page-function script across matching frames and returns per-frame results. Use it when `elements.json` shows the target element has a non-main `frame`, when the UI is rendered through iframe/frame-like surfaces, or when main-document selectors cannot see a visible modal/composer.

## Build Workflow

1. Create or update `.co/skills/<target-skill>/SKILL.md`.
2. Start with safe read-only browser analysis:
   - navigate to the target page
   - take a screenshot
   - call `save_page_context("<target>_before")`
   - inspect saved `page.html`, `styles.css`, and `elements.json`
3. Identify stable selectors:
   - Prefer semantic selectors: `aria-label`, `role`, `contenteditable`, `placeholder`, `data-testid`, stable text.
   - Avoid generated class names unless there is no alternative.
   - For repeated items, identify the container selector, body/text selector, author/title selector, and primary action selector.
4. Write `scripts/extract-<items>.js`.
   - It must return structured JSON, not prose.
   - Include normalized text, a deterministic `text_hash`, action indexes, and visible bounds.
   - Filter ads/promoted/sidebar items in JS when possible.
5. Write `scripts/verify-<item>.js`.
   - It must accept expected author/title/text/hash from `args`.
   - It must rescan the current DOM and return `ok: true` only when the same item is still visible and actionable.
6. Update `SKILL.md` to make the scripts mandatory gates before clicks/submits.
   The target `SKILL.md` must also include a trust-the-scripts rule: during a live run, do not read, `ls`, or `glob` the skill's own script files, and do not run `node --check` or local tests. Live testing on 2026-06-12 showed an agent spending its first ~10 iterations reading every script before acting. Scripts are trusted by path; if one fails twice, save context and stop — fix it outside the live run.
7. Run a safe extraction test first: no click, no type, no submit.
8. Run a full workflow only after extraction and verification are proven.

If browser setup itself fails with profile locks, closed browser context, or Playwright sync/async errors, stop and report the browser failure. Do not write fallback browser runners, do not switch to ad hoc Python/Node Playwright scripts, and do not inspect browser tool source during a target skill run.

## Discovery Protocol

Before writing automation, gather evidence from the real page:

1. Open the target page in the browser workflow.
2. Take a normal viewport screenshot, not only a full-page screenshot.
3. Save context:

   ```text
   save_page_context("<site>_<workflow>_before")
   ```

4. Inspect `elements.json` first for clickable actions, aria labels, positions, text, button order, and the `frame` field.
5. If the target has a non-main `frame` or appears in a shadow/interop surface, plan to use `run_frame_script(...)` and shadow-aware JS traversal. Do not assume `document.querySelectorAll(...)` from the main page can see it.
6. Inspect `page.html` for stable DOM relationships around the target item and action button.
   - For frame/shadow UIs, `page.html` may not include the interactive internals. Treat `elements.json` plus screenshots as stronger evidence.
7. Inspect `styles.css` only when visibility, sticky layout, or hidden duplicate elements make DOM matching ambiguous.
8. Write down the exact selector set in the target skill:
   - item container selector
   - item text selector
   - author/title/channel selector
   - action selector and action text
   - editor/input selector
   - submit selector and submit text
   - frame name/url filter if `run_frame_script(...)` is required
   - whether scripts must traverse open shadow roots
   - upload trigger selector and file input selector if local file upload is part of the workflow
   - whether the editor is plain text or a rich text editor that preserves HTML

For feeds, modals, infinite scroll, and dashboards, the same visible label often appears many times. Treat button indexes as valid only when they come from the same extraction/verification script that selected the item.

## Selector Heuristics

Prefer selectors in this order:

1. `aria-label` with a meaningful stable phrase.
2. `role` plus text or nested semantic structure.
3. `contenteditable`, `placeholder`, `name`, `type`, `data-testid`.
4. Stable link URL patterns or form attributes.
5. Text filter passed separately to `click_element_by_selector(..., text='...')`.
6. Generated classes only as a last resort and only after screenshot/context evidence shows no semantic alternative.

Do not use CSS classes that look generated as the primary selector for social feeds. They usually change between sessions.

Do not assume a visible control is a `<button>`. Social apps often use `div[role="button"]` or frame-provided controls for labels such as `Start a post`. Match by semantic role and visible text before falling back to tag selectors.

Do not hardcode temporary context locators such as `[data-browser-agent-id="318"]` into a target skill. They are useful evidence for one saved context, not stable selectors.

When there are many matching buttons, prefer one of these patterns:

```text
extract JS returns action_index among all visible matching action buttons
click_element_by_selector('button', index=<action_index>, text='<Action>')
```

or:

```text
click_element_near_selector(
  anchor_selector='<editor/input selector>',
  target_selector='button',
  target_text='<Submit/Post/Comment>',
  container_selector='<item/form container selector>'
)
```

The first pattern is for opening the item editor/action. The second pattern is for final submit near an already active editor.

## Extraction Script Contract

The extraction script should look like:

```js
(args) => {
  const maxItems = args.maxItems || 3;
  // scan visible containers
  return {
    ok: true,
    items: [
      {
        item_index: 0,
        author: "Name or channel",
        text: "Exact visible content used for generation",
        text_hash: "stable hash of normalized text",
        action_index: 0,
        has_action: true,
        visible_bounds: { x: 0, y: 0, width: 0, height: 0 }
      }
    ],
    selected_item: null
  };
}
```

Rules:

- Normalize whitespace before hashing.
- Hash the exact text sent to the content-generation skill.
- Return the action index among the same selector/text set that `click_element_by_selector(...)` will use.
- Include enough identity to disambiguate repeated items: author/title/channel, timestamp if stable, URL/id if available, visible bounds.
- Return `ok: false` with a reason when no safe item is found.
- Do not click from JS.
- Filter things that should never be acted on: ads, promoted/sponsored items, sidebars, notifications, navigation, suggested people, unrelated cards.

The extractor should be conservative. It is better to return `ok: false` than to act on the wrong item.

## Verify Script Contract

The verify script should look like:

```js
(args) => {
  const expectedHash = args.expected_text_hash;
  const expectedText = args.expected_text;
  const expectedAuthor = args.expected_author;
  // rescan visible DOM
  return {
    ok: true,
    matched_item: {
      item_index: 0,
      author: expectedAuthor,
      text: expectedText,
      text_hash: expectedHash,
      action_index: 0,
      has_action: true
    }
  };
}
```

Rules:

- `ok: true` only when author/title and text/hash match.
- Include the current action index from the current DOM.
- If the feed moved, the modal changed, or the item is gone, return `ok: false`.
- The browser workflow must stop on `ok: false`.
- Return `scanned[]` on failure so the next debugging pass can see what the script did find.
- Do not accept fuzzy matches for final submit. Fuzzy matching is allowed only during discovery, not during action.

## Match Contract

For any workflow where content is generated for a page item, keep this state:

```text
verified_item_author_or_title
verified_item_text
verified_item_text_hash
generated_content
```

Required gates:

1. Extract JS returns the item text/hash.
2. Content generation receives exactly `verified_item_text`.
3. Verify JS confirms the same item before opening the editor/form/action.
4. Verify JS confirms the same item again before final submit/post/upload.

If any gate fails, stop before click/type/submit.

For generated replies/comments, the prompt to the writer skill must receive exactly `verified_item_text`, not a paraphrase, screenshot summary, or page-wide text. This prevents "good comment, wrong item" failures.

## Browser Action Pattern

After JS verification, use generic browser tools:

```text
click_element_by_selector('button', index=<matched_item.action_index>, text='Comment')
type_text_by_selector('<editor selector>', '<generated_content>')
click_element_near_selector(
  anchor_selector='<editor selector>',
  target_selector='button',
  target_text='<submit text>',
  anchor_index=-1,
  container_selector='<item container selector>',
  require_anchor_text=True,
  wait_ms=2500,
  verify_anchor_text_cleared=True
)
```

For uploads, use the equivalent stable input/button selectors and keep the same extraction/verification gates around the item or form being acted on.

Local file uploads cannot be completed by browser JavaScript alone. Browser-side JS cannot set a real local path on `<input type="file">`. Use generic browser upload primitives:

```text
upload_file_after_click_by_selector(
  click_selector='<upload button selector>',
  text='<Upload/Add file/Upload from computer>',
  file_path='<absolute local file path>',
  frame_name='<optional frame name>'
)
```

or, when a file input is directly available:

```text
upload_file_by_selector(
  selector='input[type="file"]',
  file_path='<absolute local file path>',
  frame_name='<optional frame name>'
)
```

Wrap uploads with skill-local JS scanners such as `verify-upload-controls.js` and `verify-upload-complete.js` that report visible upload triggers, `input[type=file]` metadata, media previews, and upload completion state. Save screenshot/context immediately after upload. If upload verification fails, stop before submit/publish.

For final side-effect actions in frame/shadow UIs, prefer a skill-local JS click script over generic CSS clicking:

```text
run_frame_script(
  script_path='.co/skills/<target-skill>/scripts/click-<action>.js',
  args_json='{"expected_text":"...","expected_text_hash":"..."}',
  frame_name='<optional frame name>'
)
```

The click script must verify the exact editor/composer content or item identity, find the enabled visible submit button near that verified context, click exactly once, and return `ok: true` only when it actually clicked. The workflow must require both `matched_frame.result.ok === true` and `matched_frame.result.clicked === true` before reporting success.

For multi-step publish flows, model every side-effect button as a separate one-shot gate. Example: article editor `Next` is not the same action as final `Publish`. Use `click-next.js` after exact editor verification, save the share/publish surface context, then use a separate `click-final-publish.js` that verifies the expected title/content is visible in that final surface before clicking `Publish`.

For testing multi-step publish flows without publishing, add an explicit debug flag such as `debug_next: true`: it may click the non-final `Next`, save context/screenshot of the final publish surface, report visible buttons, and stop before final `Publish`.

For reactions/likes, treat the reaction as the same pattern with no generated content:

```text
extract reaction targets -> verify same target by author/text/hash -> click verified reaction index -> verify the unreacted selector disappeared for that target
```

Example target skill:

```text
.co/skills/linkedin-thumbup/
  SKILL.md
  scripts/
    extract-like-targets.js
    verify-like-target.js
```

The reaction script is just another action variant. Do not add `like_linkedin_post()` to the browser core.

## Skill-Local JS Pattern

Each target skill should include scripts next to `SKILL.md`:

```text
.co/skills/<target-skill>/scripts/extract-items.js
.co/skills/<target-skill>/scripts/verify-item.js
```

Use the templates from this skill when starting:

```text
.co/skills/browser-workflow-skill-builder/scripts/extract-items-template.js
.co/skills/browser-workflow-skill-builder/scripts/verify-item-template.js
```

The scripts must be page functions:

```js
(args) => {
  return { ok: true };
}
```

They are run with:

```text
run_page_script(
  script_path='.co/skills/<target-skill>/scripts/extract-items.js',
  args_json='{"maxItems":3}'
)
```

For frame-aware workflows, run the same script with:

```text
run_frame_script(
  script_path='.co/skills/<target-skill>/scripts/verify-item.js',
  args_json='{"expected_text_hash":"..."}',
  frame_url_contains='',
  frame_name=''
)
```

Extraction and verification scripts should be deterministic and small. Avoid network requests, timers, mutation, clicks, typing, or localStorage writes. They should read DOM only and return JSON.

Final `click-<action>.js` scripts are the exception: they may click only after exact verification passes. They must never perform broad searches such as "first Post button" without checking the matching editor/item context.

If modals, editors, or submit buttons may live inside open shadow roots, include a small deep traversal helper in the script:

```js
const queryAllDeep = (root, selector) => {
  const out = [...root.querySelectorAll(selector)];
  for (const el of root.querySelectorAll('*')) {
    if (el.shadowRoot) out.push(...queryAllDeep(el.shadowRoot, selector));
  }
  return out;
};
```

Browser-side scripts run in the page, not Node. Do not use `require`, `fs`, `process`, or other Node APIs inside `.co/skills/<target-skill>/scripts/*.js`.

## Rich Text Editors

Do not assume a rich text editor renders Markdown when raw Markdown is typed or inserted. Live LinkedIn article testing showed raw Markdown stayed literal (`##`, `**bold**`, bullets, and Markdown links were displayed as text). For rich editors:

1. Parse source content outside the browser when needed.
2. Produce both rendered HTML and expected visible text.
3. Insert HTML through a paste-like path, `document.execCommand('insertHTML', ...)`, or direct `innerHTML` only inside a guarded fill script.
4. Verify against expected visible text, not the original Markdown syntax.
5. Return formatting evidence from verification: heading count, bold/italic count, link count, unordered/ordered list count, list item count, and code/pre count.

Example script contract:

```text
parse-markdown.js -> { title, raw_body, body_html, body_text, body_hash }
fill-editor.js(args: title, body_html, body_text) -> { ok, fill_method, formatting }
verify-editor.js(args: title, body_text) -> { ok, text_hash, formatting }
```

If formatting matters, the workflow must report `formatting` counts and use a screenshot to confirm rendered appearance. If visible text matches but formatting counts are zero for a Markdown-rich source, treat it as a draft-quality failure and stop before publishing.

When a screenshot, script result, or human report shows a Markdown render problem, always call `save_page_context("<workflow>_markdown_render_problem")` while the bad rendering is still visible, then call `take_screenshot("<workflow>_markdown_render_problem.png")`. Do not rely on screenshots alone. The saved context provides `page.html`, `styles.css`, and `elements.json` for frame/shadow/selector analysis before changing fill or verification logic.

## Run Efficiency

Agent runs have an iteration budget, and every tool call in its own turn costs a full LLM round trip. Live data from 2026-06-12: a sequential engagement run spent 20 of 100 iterations on bare `wait()` turns and hit the cap mid-run with no final report; after the rules below, the same workflow finished 4 items in 66 iterations with a clean report.

Write these rules into every sequential/multi-item target skill:

- Never spend a turn on a bare `wait()`. If the UI needs a settle pause, call `wait` and the next script in the same turn — multiple tool calls per turn are supported.
- While scanning for the next item, batch `scroll` + extract in one turn. Do not take unnamed screenshots during scanning; they feed images into model context and bloat it. The extract JSON is the source of truth while scanning.
- Screenshot only at evidence gates (before-submit, completed), with the item hash in the filename.
- Set an explicit per-run item budget (for example: stop after 4 successfully processed items unless the user asks for more). Repeat runs scroll past their own history, so an unbounded loop exhausts the budget hunting and loses the final report.
- End every run with a final report listing, per item: identity, hash, content, status, and the exact screenshot and saved-context paths.

For nested content-generation sub-calls (`co ai "/writer-skill ..."` from Bash):

- Pin the model explicitly with `-m <model>`. Nested calls use the CLI default model, not the parent run's model, and content quality tracks model quality.
- Sub-calls can stall; if one times out once, retry exactly once with an explicit timeout, then skip the item.
- Do not trust a sub-agent's own "complete" status for side-effect steps. Weak models quit multi-gate workflows after generating content and their self-evaluation still reports success; require the side-effect script's `ok`/`clicked` JSON and hash-named evidence instead.

## Testing Sequence

Use this order for every new browser workflow skill:

1. Script syntax:

   ```bash
   node --check .co/skills/<target-skill>/scripts/extract-items.js
   node --check .co/skills/<target-skill>/scripts/verify-item.js
   node --check .co/skills/<target-skill>/scripts/click-<action>.js
   ```

2. Local JS regression tests for non-trivial scripts:
   - Use `jsdom` or a simple DOM harness for hash matching, visibility guards, disabled button guards, and open shadow-root traversal.
   - Test that the final click script refuses wrong text/hash and clicks only the matching enabled button.
   - For rich text editors, test raw Markdown to HTML/text conversion, HTML fill behavior, visible-text verification, and formatting counts.
   - For uploads, test upload-control scanners and upload-complete verifiers with file input/media preview fixtures.

3. Safe browser extraction test:

   ```text
   Open <site>. Do not click, type, upload, post, submit, or publish anything.
   Take a screenshot, run extract-items.js, then run verify-item.js for selected_item.
   Report selected author/title, text_hash, action_index, and verify ok.
   ```

4. Editor-only test when safe:
   - Open the editor/input.
   - Type a harmless draft only if the user asked for it.
   - Screenshot and stop before submit.
   - For rich text editors, test with headings, bold, italic, links, unordered lists, ordered lists, and code. Verify whether raw typing stays literal or HTML insertion preserves formatting.

5. Full live workflow:
   - Only after extraction and verification both pass.
   - The final action must be one-shot.
   - Stop after screenshot/context, even if status is ambiguous.

Never skip the safe extraction test. It catches almost all wrong-container and wrong-button bugs before a live action happens.

## Page Context Analysis

Always save context during skill creation or debugging:

```text
save_page_context("<site>_<workflow>_before")
```

Use saved files this way:

- `page.html`: find semantic DOM structure and nearby stable attributes.
- `styles.css`: inspect visibility/layout clues only when DOM is ambiguous.
- `elements.json`: find clickable elements, text, aria labels, positions, frame names, and candidate selectors.
- screenshots: verify that extracted text matches the actual visible center workflow.

Do not rely only on screenshot OCR or raw page-wide `get_text` for fragile workflows.

Know where artifacts land so the final report can cite real paths: `take_screenshot(...)` writes under the working directory's `.tmp/`, and `save_page_context(...)` writes a timestamped folder under `~/.co/browser_context/<timestamp>_<name>/` containing `page.html`, `styles.css`, and `elements.json`. For sequential multi-item workflows, stamp the item's `text_hash` into evidence names (`<workflow>_before_submit_<hash>`, `<workflow>_completed_<hash>`) — hash-distinct evidence pairs are also how to prove the run processed different items rather than looping on one.

The skill scripts only resolve as `.co/skills/<skill>/scripts/...` when the working directory has a `.co/skills` symlink (or the skill is installed globally and run from a project with that layout). Verify the path resolves before a live run; a missing symlink makes the agent burn iterations rediscovering script paths with `ls`.

When a visible element exists in `elements.json` but cannot be found from `run_page_script(...)`, suspect a frame or shadow-root boundary before changing selectors.

For upload workflows, `elements.json` may show only the visible upload button while the actual `input[type=file]` is hidden. Use both saved context and a skill-local scanner to discover hidden file inputs, but use browser upload primitives for the actual local file selection.

## Debugging Wrong Matches

If the agent comments/posts/uploads to the wrong item, fix in this order:

1. Save context after the bad match.
2. Compare screenshot, `elements.json`, and extractor output.
3. Check whether the action index was computed among the same selector/text set used for clicking.
4. Check whether verification ran after any scroll, modal open, expansion, or content generation.
5. Check whether the target element lives in a non-main frame or open shadow root.
6. Add a stronger identity field to extraction: author/title, URL, timestamp, visible bounds, stable DOM id.
7. Add an exclusion rule for ads/sidebar/navigation if those appeared in `scanned[]`.

Do not solve wrong matches by telling the agent to "be careful". Make the script return better structured evidence.

For fragile submit failures, create a separate debug-capture skill that never publishes. It should open the relevant modal/editor, insert only harmless test content if needed, save context, take a screenshot, and run an analyzer script that reports button metadata, frames, visibility, disabled state, and nearby editor text.

For multi-step final actions, capture the intermediate surface before adding final submit. Example: after a verified `Next` click, save `<workflow>_share_before_publish` and report visible final buttons. Only add final publish after that surface has been captured and the final button can be verified semantically.

## Safety Rules

- Dry-run first: extraction + verification only, no click/type/submit.
- For social media or publishing actions, final submit is a one-shot action.
- After final submit click, never retry by clicking the same submit/post button again in the same run.
- Always take a pre-submit screenshot and post-submit screenshot.
- Save page context before submit and after submit when the skill needs debugging evidence. For new or fragile skills, make this mandatory.
- If a final JS click script fails or returns ambiguous evidence, immediately save context named `<workflow>_submit_js_failed`, take a screenshot, report the failure evidence, and stop. Do not try a different selector in the same live run.
- If the editor still shows the content after submit, report uncertain state instead of clicking again.
- For social, email, payment, upload, or publishing workflows, assume actions are externally visible and irreversible unless proven otherwise.
- If the user's request is only to test extraction or draft, do not click submit/post/upload even if the skill knows how.
- Do not navigate away from an already-open editor/composer that contains the intended content. Verify the existing composer first; navigation may discard the draft or open a different surface.
- If `open_browser`, navigation to the target editor, or browser context access fails, stop and report that setup failure. Do not write fallback Playwright runners or switch automation stacks inside the target skill.
- Do not create helper scripts during a live browser run. Add or edit skill-local scripts outside the live run, then run tests before the next live attempt.
- For uploads, verify the local file exists before opening the browser. If the upload fails or the uploaded media cannot be verified, stop before submit/publish.

## Skill Output Checklist

When creating the new target skill, make sure `SKILL.md` includes:

- exact page URL or navigation target
- required tools list
- script paths
- extraction JSON shape
- verification JSON shape
- stable selectors
- upload trigger/file input selectors if files are involved
- frame/shadow-DOM strategy
- rich-text strategy: raw text vs HTML insertion, expected visible text, and formatting evidence
- multi-step publish strategy: intermediate `Next`/preview/share gates and final submit gate
- match contract
- dry-run test command
- full-run test command
- one-shot submit rule
- screenshot/context save points with item hash in evidence names
- trust-the-scripts rule: no reading/`ls`/`glob` of skill scripts during live runs
- wait/batching rules: no bare `wait()` turns, scroll+extract batched while scanning
- per-run item budget for sequential workflows
- final report shape listing per-item evidence paths (`.tmp/` screenshots, `~/.co/browser_context/` contexts)
- pinned model (`-m`) for any nested content-generation sub-call
- exact stop conditions
- expected dry-run evidence
- expected full-run evidence

## Example Target Skill Skeleton

```markdown
---
name: <site-action>
description: <what this browser skill does and when to use it>
tools:
  - go_to
  - take_screenshot
  - save_page_context
  - run_page_script
  - run_frame_script
  - click_element_by_selector
  - type_text_by_selector
  - click_element_near_selector
  - upload_file_by_selector
  - upload_file_after_click_by_selector
---

# <Site Action>

Use scripts:
- `.co/skills/<site-action>/scripts/extract-items.js`
- `.co/skills/<site-action>/scripts/verify-item.js`
- `.co/skills/<site-action>/scripts/click-submit.js` when final submit lives in a frame/shadow UI or generic selectors are ambiguous
- `.co/skills/<site-action>/scripts/verify-upload.js` when local files are involved
- `.co/skills/<site-action>/scripts/fill-editor.js` when rich text or HTML insertion is involved

Workflow:
1. Navigate.
2. Screenshot and save context.
3. Run extract script.
4. Select item and set `verified_item_text_hash`.
5. Generate or prepare content from exactly `verified_item_text`.
6. Run verify script before click.
7. Click action by verified index.
8. Type/upload.
9. Screenshot and save context before submit.
10. Run verify script again.
11. Submit once.
12. Screenshot and save context after submit.
13. Report item identity, hash, content, and final status.
```

## Bad Patterns

Bad: adding `linkedin_extract_posts()` or `twitter_post_reply()` directly to core `browser.py`.

Good: generic `run_page_script(...)` in browser core, with `.co/skills/<skill>/scripts/*.js` holding site-specific DOM logic.

Bad: generate a comment from one post, then click the first visible Comment button.

Good: hash the exact extracted post text, verify the same hash before clicking, and use the current verified action index.

Bad: if submit is ambiguous, click again.

Good: screenshot/context, report uncertain state, and stop.

Bad: pass inline JavaScript as `script_text` or put JS source in the `script_path` argument.

Good: create a real skill-local file under `.co/skills/<skill>/scripts/*.js` and call it with `script_path`.

Bad: use Node APIs such as `require('fs')` inside browser-executed scripts.

Good: write browser page functions that use DOM APIs and return structured JSON.

Bad: keep retrying alternate submit selectors after a live final click fails.

Good: save `<workflow>_submit_js_failed` context plus screenshot, then analyze `elements.json` and the frame/shadow boundary before another live attempt.

Bad: type raw Markdown into a rich text editor and assume it renders.

Good: convert Markdown to HTML plus expected visible text, insert HTML through a guarded fill script, then verify visible text and formatting counts.

Bad: set a local file path from browser JS or write site-specific upload Python.

Good: use generic `upload_file_after_click_by_selector(...)` or `upload_file_by_selector(...)`, with skill-local JS only for discovering upload controls and verifying uploaded media.

Bad: after `Next` opens a publish/share dialog, immediately click the first visible `Publish`.

Good: treat `Next` and final `Publish` as separate one-shot gates; save the intermediate context and verify the final surface before the final click.

Bad: when `open_browser` or navigation fails, write fallback Playwright scripts inside the live skill run.

Good: stop, report the browser/profile failure, and fix the skill or browser tool outside the live run.

Bad: spend a whole turn on `wait(seconds=2)`, then another on extract, then another on an unnamed screenshot.

Good: batch the settle wait, the scroll, and the extract into one turn; screenshot only at hash-named evidence gates.

Bad: read every script in `scripts/` with `read_file` before acting, "to understand the workflow".

Good: trust the script paths listed in `SKILL.md` and run them; read scripts only outside live runs.

Bad: loop a sequential workflow until the iteration cap kills it mid-hunt with no final report.

Good: stop after the per-run item budget, then spend the remaining budget on the evidence-path report.

Bad: call a nested writer skill without `-m` and accept whatever the default model returns.

Good: pin a strong model, gate the returned content against concrete rejection rules, retry once with the rejection reason, and skip the item if it still fails.
