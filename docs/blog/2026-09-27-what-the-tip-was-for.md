# What the tip was for

The free models arrived with a good idea attached. ConnectOnion's own GPU runs
Llama and Gemma at zero cost per token, so a person whose credits run out does
not have to stop. The error they get says so. That is a tip: it appears at the
moment someone needs it and names the way forward.

Then the tip became the default. For seven previews, every agent that did not
name a model ran on an 8B Llama with a 4,096-token context, whether its owner
had credits or not. The person who owns the product found out while we were
fixing a docs page. Their first reaction was that they remembered it the
other way: the default is Gemini 3.8, and there is a tip.

They were describing the design. The code had drifted from it, one reasonable
change at a time, with tests and docs updated to match at every step.

1.8.9b17 puts the two back in their places. The default is Gemini 3.8. The tip
is where the owner said it lives: in `co status`, once the balance reaches
zero, beside the purchase page. It names `co/gemma` and a local `ollama/` model,
the two ways to keep going without paying. A test now fails if any doc calls
Llama the default, so a later change has to argue with the test before it can
move the default again.

The lesson: a fallback and a default solve different problems. Keep a fallback
where the need appears, and change a default only on purpose.
