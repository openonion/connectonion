# The default nobody chose

We were fixing the docs site when it turned up a line that looked like a typo.
The models page said the default was `gemini-3.7-flash`. We went to the code to
check which number was right, expecting 3.8. The code said neither.
`DEFAULT_MODEL = "co/llama"`.

The owner's answer was immediate: no, our default is Gemini 3.8. There is just
a tip. When someone's credits are gone and `co status` shows zero, we tell them
they can keep going on the free Gemma, or on Ollama.

Both were true, one day apart. On 26 September a change titled "Make co/llama
the free managed default" had landed. The free models were real and worth
having: Llama 3.1 8B and Gemma on ConnectOnion's own GPU, zero-dollar tokens,
and an error message that points to them when credits run out. But the same
change also moved the default for every new `Agent()` and `llm_do()` to the
8B model. That model has a 4,096-token context and one shared inference slot.
It shipped in a preview, the docs were updated to match, and the test that
had guarded "the default is Gemini 3.8" was renamed to guard "the default is
Llama" instead. Everything agreed with everything else, except the owner.

A default is a product decision disguised as a constant. Changing it changes
what every person who never named a model gets, silently. Nobody sees it
happen: their agent just gets a little worse at calling tools, and nothing
they ran tells them why.

So this change restores Gemini 3.8 and keeps everything else the free models
brought: prices, context limits, their place on the free list. It moves them
to where the owner meant them to be. At a zero balance, `co status` now names
`co/gemma` and `ollama/<model>` beside the purchase page. The restored test
also checks the docs: a line that calls Llama the default fails the build.

The lesson: when a change moves a default, treat it as the decision it is.
Ask the person who owns the decision, even when the rest of the change is
obviously good.
