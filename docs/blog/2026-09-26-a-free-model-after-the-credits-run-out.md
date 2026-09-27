# A model that still answers after the credits run out

The first time a new agent used up its managed credits, its next message ended
at a billing error. The error knew the balance and the shortfall, but offered
only a purchase link. For someone trying ConnectOnion, that made a temporary
limit feel like the end of the session.

We already had a GPU machine in Melbourne. It had Gemma 4 12B downloaded, but
the public inference proxy still forced every request to a different model.
We made `co/gemma` an explicit free route and sent a real completion through
the production API: the response said `cost_usd: 0.0` and the server recorded
the local provider. Then we loaded Llama 3.1 8B on the same GPU. It answered a
short prompt and called a test tool, so `co/llama` can serve as the default text
model rather than merely appearing in a model picker.

The GPU is small: 12 GB of available video memory, one request admitted at a
time, 4,096 tokens of context, and 1,024 output tokens per response. This is a
way to keep an agent going, not a claim that a local 8B model is interchangeable
with a large paid model. Audio transcription keeps Gemini because this Llama
model takes text. When credits run out, the SDK now names `co/gemma` as a free
next step instead of leaving the user with only a payment link.

We then exercised the whole path through oo-api v0.1.22: a newly authenticated
account omitted `model` and received `co/llama`, `OK`, and a zero-dollar usage
record, while its five-dollar balance stayed intact. A second request asked
`co/llama` to call `get_weather` for Sydney and received the named tool call.
The SDK's default `llm_do()` also returned `OK` through that production API.
Those checks prove the route and billing path that this preview uses; they do
not measure how many simultaneous users the one-request GPU proxy can serve.
