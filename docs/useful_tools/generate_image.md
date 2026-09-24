# generate_image

> A prompt goes in, an image file comes out. Uses a Gemini image model with your own key.

## Usage

```python
from connectonion import generate_image

path = generate_image("a watercolor fox in snow", save_to="fox.png")
print(path)  # fox.png
```

As an agent tool:

```python
from connectonion import Agent, generate_image

agent = Agent("artist", tools=[generate_image])
agent.input("Draw a watercolor fox and save it as fox.png")
```

## Setup

Set `GEMINI_API_KEY` (or `GOOGLE_API_KEY`). The tool calls Google directly.

## Parameters

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `prompt` | required | What to draw |
| `save_to` | `""` | Output path. Empty means `generated_image_<timestamp>.<ext>` in the current directory, where the extension follows the format the model returned (`.png`, `.jpg`, ...) |
| `model` | `gemini-2.5-flash-image` | Any Gemini image model, e.g. `gemini-3-pro-image-preview`, or `openrouter/google/gemini-2.5-flash-image` with `OPENROUTER_API_KEY` |

Returns the saved path as a string. Parent directories are created.

## What it refuses

- **`co/` models.** Managed-key image output has never been shown to work:
  the backend forwarded image models to Google's chat endpoint, which refuses
  them. `generate_image("...", model="co/...")` raises `ValueError` before
  making a request, and the message tells you to use a direct model.
- **A reply with no image.** Raises `ValueError` carrying whatever text the
  model sent instead, so a refusal is readable.

## Using an image model without the tool

The same models work through `create_llm` and `Agent`. Generated images come
back as data URLs:

```python
from connectonion import Agent
from connectonion.core.llm import create_llm

llm = create_llm("gemini-2.5-flash-image")
response = llm.complete([{"role": "user", "content": "a watercolor fox"}])
response.images  # ["data:image/png;base64,..."]

agent = Agent("artist", model="gemini-2.5-flash-image")
agent.input("Draw a fox")    # "Generated 1 image."
agent.last_images            # ["data:image/png;base64,..."]
```

When the agent is hosted, each image is also sent to the connected client
with `io.send_image`.

## Limits worth knowing

- **One prompt, no history.** Direct Gemini image models go through Google's
  images API, which takes a single prompt. Only the last user message is sent.
- **Tools and image models do not mix.** Given tools, an image model goes to
  the chat endpoint instead, where Google has refused image models.
- **Cost is not tracked.** The images API returns no token counts, so the call
  adds nothing to `agent.total_cost`. `gemini-2.5-flash-image` has no price in
  ConnectOnion's table; check Google's pricing page.
- **Not yet verified live.** The code follows the error messages Google
  returned in July 2026. `tests/e2e/real_api/test_real_gemini_image.py` is the
  test that would confirm it and has not been run against this version.
