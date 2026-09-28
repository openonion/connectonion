# A Retina Mac with no menu bar

We moved the paid browser to Chromium 154 because 151 had a tell: a headless
session announced itself as HeadlessChrome in its user agent. The browser
team fixed that in 154, and artifact keys never change for a revision, so the
only way to ship the fix was to move the pin.

The end-to-end run on an Intel MacBook looked fine at first. httpbin saw
`Chrome/154.0.0.0`, the Client Hints named Google Chrome and macOS, and
`navigator.webdriver` was false. Then we asked the page for its screen. It
said 1920 by 1200, at 1x, with `availHeight` equal to the height. That is a
Mac with no Retina display and no menu bar, which is not a Mac anyone owns.
The laptop was a 1512 by 982 screen at 2x.

The browser was not lying. We were. Every new tab called
`set_viewport_size(1920x1200)`, and in Playwright that is a device-metrics
override: it rewrites `screen.*` and `devicePixelRatio` along with the
layout. We set that size so pages would lay out the same for
every agent, and for the free browser that is still the right trade. For the
paid browser, whose whole job is to be indistinguishable, it painted the same
impossible screen over every real machine.

So the paid browser now leaves the screen alone, and the same run reports
1512 by 982 at 2x with an `availHeight` of 945. The free browser keeps its
fixed layout. The lesson we are keeping: a setting that makes one product
predictable can be the exact fingerprint the other product exists to remove,
so check what the page sees, not only what the request headers say.
