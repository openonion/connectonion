# Sleep Was the Global Lock

*2026-08-26*

The selector was known. The coordinates were known. The click worked. Yet one
agent typing into tab A could still freeze an unrelated agent reading tab B.

The lock was not in our session manager. It was `time.sleep()`.

## Human behavior is a sequence, not one call

ConnectOnion does not teleport a pointer to the center of every element. It moves
along a curved path, pauses, presses, pauses again, and releases. Text arrives one
character at a time. CJK text may temporarily use the operating-system clipboard.
Those details are observable behavior: replacing them with `locator.click()` and
`fill()` would make the async method faster by silently changing the product.

Copying the synchronous humanization helper was equally wrong. Every tiny
`time.sleep()` would block the sole asyncio event loop. Per-tab locks would be
correct on paper while all tabs still stopped together in practice.

The 1.8 input layer therefore keeps the existing geometry, timing distributions,
device personas, text segmentation, and clipboard policy as pure rules. A new
async executor awaits every mouse, keyboard, wheel, CDP, and pause operation. A
native test starts a humanized coordinate click on one tab, then requires another
tab to read its DOM before the first click finishes. That is the behavior we need,
not merely an `async def` label.

## The clipboard is shared even when tabs are not

CJK paste has a different concurrency boundary. The clipboard belongs to the
desktop, so tab A and tab B cannot safely save, replace, paste, and restore it at
the same time. The async runtime owns one clipboard lock while retaining one
operation lock per tab. Blocking clipboard commands run in worker threads, and
restoration completes before cancellation is allowed to escape.

This is deliberately a narrow #498 boundary. It ports known-selector clicks,
anchor-relative clicks, selector typing, and coordinate clicks. Model-selected
elements, AI scrolling, and form helpers remain separate because each carries a
different parity contract. Concurrency improves only when the old behavior is
made awaitable without being erased.
