# The picture was the answer

In July someone asked for a small thing: let an agent draw. A branch appeared the
same afternoon. It taught our LLM classes to read images out of a reply, added a
`generate_image` tool, and registered a handful of Gemini image models with
prices. Then it tried the real endpoints, and every one of them said no.

Google's OpenAI-compatible chat endpoint refused `gemini-2.5-flash-image` with a
sentence that was almost helpful: image generation is not supported here,
use `images.generate`. `gemini-3-pro-image-preview` failed differently. Google's
own compatibility layer could not serialise the JPEG the model had just made.
Our managed `co/` route forwarded to that same endpoint, so it failed in both
ways. The branch was patched to call the images API directly, a note about the
server went into a test docstring, and nobody opened a pull request. It sat for
two months while `llm.py` moved on underneath it.

Porting it this week was mostly a lesson in which parts of the old branch were
claims and which were facts. The error messages were facts: someone had seen
them. The rest was not. The branch had registered
`gemini-2.0-flash-preview-image-generation`, a model we had deliberately cut in
#603 along with everything else from before 2025. It had given
`gemini-2.5-flash-image` a price that appears nowhere in our tables, while a test
on main now insists that model shows `~` because we do not know what it costs.
And the tests for the managed route asserted success on a path that had only ever
been seen to fail.

So the port keeps the facts and drops the claims. Direct Gemini image models go
through the images API, which is what Google's own error told us to do. OpenRouter
asks for the image modality. The managed route is left alone. `generate_image`
refuses a `co/` model up front, with a sentence that says what to use instead,
rather than letting it fail as a 400 three layers down. No new price was added.

One real bug turned up only because the agent test used a fake that behaves like
the real thing. An image model's whole answer can be the picture, with no text
at all. The agent loop treats an empty final answer as a failure and raised
`RuntimeError` on a call that had worked. Now an image-only answer comes back as
"Generated 1 image.", and the image itself is on `agent.last_images`.

What we still do not know is the most important part: whether any of this
returns an image today. The real-API test is written, and it has not been run.
The pull request says so, and so does the tool's page, because the last version
of this feature failed by sounding more certain than it was.
