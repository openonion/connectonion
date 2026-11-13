# Two more elements

*2026-11-13*

A month ago we wrote that Gemini 4 had one model, Argon, and no Flash. This
morning the model list on our key had three: Argon, Carbon and Hydrogen.

The names say nothing about the order, so we read the price page tab by tab.
The first pass gave us the same twelve numbers for all three models, which
would have meant Hydrogen costs exactly what Carbon does. It doesn't. Our
script had walked up to a container that held every section and kept reading
the first table in it. Scoped to each heading, the page says something more
useful: Carbon and Argon share a price, $2.00 in and $10.00 out per million
tokens until it doubles on 1 December, and Carbon is the one that thinks longer
per turn. Hydrogen is $1.50 and $7.50, flat, and it is the only Gemini 4 model
on Google's free tier.

So the question "which Gemini 4 is cheapest" has an answer that changes with
the calendar. Today Hydrogen costs twice what the default 3.8 Flash does. On 1
January, when 3.8 Flash's promotional rate ends, they cost the same. The
default stays where it is; all three are now one name away:

```python
Agent("researcher", model="co/gemini-4-hydrogen")
```

Both new models answered on a real key before we wrote a line: tool calls,
structured output, the sampling knobs that 3.8 Flash refuses, and
`reasoning_effort` at every level. The cached-rate test flagged them on the
first run, as it did Argon, because Google discounts their cache by 95% where
older Gemini rows get 75%. They join Argon in the list of pinned exceptions
rather than loosening the rule.
