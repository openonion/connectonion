# Source-context modal: eligible keyboard controls

## Scope and evidence

- Task: inspect a long archived source, use its search field, and return to the citation by keyboard.
- Baseline: published 1.9.3rc6 reader, identical to main `32dd0782a3ac22f33f5c5b02dc06ac2b6c42cf08` before editing.
- State: invented project/source; excerpt over 2000 characters, no external-file link; Next match initially disabled.
- Browser verification: **blocked**. The available browser tool rejected local `file://` navigation by its security policy. No alternate protocol, browser or renderer workaround was attempted.
- Before/after screenshots: **not produced**; comparable actual viewports, zoom and scroll are unverified.
- References: the actual published reader source is the behavior baseline; no visual reference image was inspected.

## Finding and fix

The narrow modal's focus handler included every visible native control, even a disabled last button. Shift+Tab from Close therefore selected an unfocusable target; Tab from the search field did not trigger the expected wrap. The patch filters disabled/inherited-disabled and negative-tabindex elements before choosing the loop endpoints. If no control is eligible, it retains focus on the panel. Escape and the desktop nonmodal path are unchanged.

## Three comparison answers

| Question | Verdict | Evidence |
| --- | --- | --- |
| Intended effect achieved? | partial | The unmodified production handler failed the isolated wrap regression; patched handler passes. Actual browser focus remains unobserved. |
| Relevant craft comparable? | unknown | No implementation/reference screenshots or visible-focus observation. |
| Largest remaining gap? | browser acceptance | Native keyboard order, visible focus, modal inertness and screen-reader behavior need manual verification. |

## Functional checks

Twelve pure Node regressions execute only the production key handler with test doubles. They cover disabled Next, Shift+Tab, inherited-disabled/hidden/negative-tabindex candidates, enabled Next, empty candidates, Escape, and width arguments on both sides of the 1100px modal boundary. These are **not actual viewport or browser tests**. Node v26.7.0 was used locally; CI skips these tests if Node is unavailable.

```sh
python -m pytest tests/unit/test_rem_evidence_focus.py -q
```

No real sources, notebook, model, network page or live scheduler were used. Contrast, touch, overflow, reduced motion and assistive technology were not tested.

## Independent review

A separate AI reviewer inspected the source and isolated logic only, and found no remaining code blocker. It confirmed that current panel controls use native zero-order keyboard elements and the existing panel is programmatically focusable. It explicitly did not verify native focus, mobile rendering, inert behavior or screen readers. Independent **visual** review remains pending.

## Manual acceptance still required

At 390×844 and 768×1024, open an invented long source with no file link: Tab should cycle Close → search → Close while Next match is disabled; Shift+Tab from Close should reach search. A query with multiple matches should make Next reachable and include it in the cycle. Escape should close the panel and restore citation focus. At 1440×900, the nonmodal panel must not trap Tab. Capture matching before/after focus screenshots and inspect visible focus, overflow and accessible names.

## Final status

- Isolated handler regressions: pass, 12 cases.
- Native/browser functional verification: pending due to tool security restriction.
- Reference comparison and independent visual review: pending.
- Merge/release: **draft only**, pending required CI and manual browser evidence. Do not treat this as product maturity acceptance.
