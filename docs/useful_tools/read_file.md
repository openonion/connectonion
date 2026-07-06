# read_file

One copyable tool that reads **any** file — text, code, images, PDF, LaTeX, PowerPoint, Word, audio, video — and hands the extracted content to the agent. It dispatches by file extension and returns the raw content; the agent decides what to do with it.

This is a `co copy`-able tool (it is **not** imported from the package by default). It supersedes the lightweight built-in [`read_file`](file_tools.md) (text + line numbers) — copy this one in when you need the heavier formats. They share the tool name `read_file`, so pass one or the other, not both.

## Quick Start

```bash
co copy read_file        # → ./tools/read_file.py
```

```python
from connectonion import Agent
from connectonion.useful_plugins import image_result_formatter
from tools.read_file import read_file

agent = Agent(
    "assistant",
    tools=[read_file],
    plugins=[image_result_formatter],   # required so images reach the vision model
)

agent.input("What's in report.pdf?")
agent.input("Describe diagram.png")     # the model actually sees the image
```

## Supported formats

| Extension | Returns |
|-----------|---------|
| `.txt .md .csv .json .tex` + code | the file's text, as-is (UTF-8, or GB18030 for Chinese) |
| `.png .jpg .jpeg .gif .webp` | a `data:image/…;base64,…` URL the vision model sees ([how](#how-images-reach-the-vision-model)) |
| `.pdf` | extracted text, one section per page |
| `.pptx` | the text of each slide |
| `.docx` | the document's text |
| `.mp3 .wav .m4a …` (audio) | a transcript (via `transcribe()`) |
| `.mp4 .mov .mkv …` (video) | a transcript of the **audio** track (ffmpeg → `transcribe()`) |

Legacy binary `.ppt` / `.doc`, scanned (text-less) PDFs, and a missing `ffmpeg` return an actionable `Error: …` string. Video reads the audio only — a silent video (screen recording, etc.) has nothing to transcribe.

## How images reach the vision model

Reading an image is **not** the tool doing OCR or captioning. `read_file` only produces the image *data*; a separate plugin turns that into something the model can actually see. The call chain:

```
read_file("diagram.png")
      │  returns  "data:image/png;base64,iVBORw0KGgo…"      (raw image bytes, base64)
      ▼
tool result  →  a normal text tool-message in the conversation
      ▼
image_result_formatter plugin        (runs on the `after_tools` event)
      │  1. detects the  data:image/…;base64,…  URL in the result
      │  2. uploads the bytes to oo-api → gets back a short /img URL
      │  3. replaces the tool message with a short placeholder
      │  4. inserts a user message: { "type": "image_url", "image_url": {"url": "…/img/…"} }
      ▼
next LLM call  →  the model SEES the image (vision), not base64 text
```

Only the ~70-byte `/img` URL enters the message history — never the base64 — so screenshots don't bloat the replayed context or session logs. The upload needs `OPENONION_API_KEY` (set up by `co init`); oo-api stores the bytes in content-addressed storage and materializes them per provider at call time (e.g. inlines them for Gemini, which can't fetch URLs).

**Why a plugin, and not `read_file` itself?** A tool's return value can only become a *text* tool-message. Putting an image into the conversation means mutating the message list, which is only safe on the `after_tools` event — so a plugin does it. This is the exact path browser screenshots use. Keeping `read_file` to "return the image data" and letting the plugin handle presentation keeps each piece single-purpose.

**Consequence:** images only reach the model if the agent has the [`image_result_formatter`](../useful_plugins/image_result_formatter.md) plugin. The [`minimal`](../templates/minimal.md) template enables it by default; a bare `Agent(...)` does not — add `plugins=[image_result_formatter]`. Supported image types match the plugin: PNG, JPEG, GIF, WebP.

## Dependencies

Python packages (declared by connectonion, installed with it): `pypdf` (PDF), `python-pptx` (PPTX), `python-docx` (DOCX), `charset-normalizer` (text encoding detection). No lazy imports or "package missing" fallbacks — they're real dependencies.

System tool: **ffmpeg** on `PATH`, for video only (it is not a pip package — `brew install ffmpeg` / `apt install ffmpeg`). Audio and video transcription use the Gemini-based `transcribe()`, which needs `co auth` (a managed key); audio needs no ffmpeg.

## See Also

- [image_result_formatter](../useful_plugins/image_result_formatter.md) — turns the image data URL into a real image the vision model sees
- [FileTools](file_tools.md) — the built-in lightweight text `read_file` (line numbers, read-before-edit)
- [co copy](../cli/copy.md) — copying tools into your project to customize
