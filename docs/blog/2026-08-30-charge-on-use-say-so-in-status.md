# Charge on use, say so in status

The question was whether the paid browser should ask before it charges. The
answer is no — it charges the way tokens do. Use it, and it bills; there is no
prompt, because a prompt in front of every command that a script or an agent
runs is friction with no payer confused about what they clicked.

What was actually wrong was quieter: it charged and did not say so where you
would look. The open message names the price once, at launch. But a paid
browser is a long-lived thing — a daemon serving commands over minutes — and the
place you go to ask "what is this browser doing right now" is `status`. The
Engine line there reported the engine and the artifact and said nothing about
money.

Now it carries both the price and the live session:

```
Engine: requested=auto · resolved=onion · reason=onion_ready ·
        artifact=chrome/151/linux-x86_64.tar.zst · $0.025/interval ·
        paid session sess-123
```

Read defensively — a resolution with no price (a free or system engine, or an
upstream that reports none) produces the old line, not a `$0.000`. The test that
matters asserts the cost is *in* the rendered status, not merely computed;
dropping the string from the Engine line reddens it.

That is the whole change. The billing model is not a decision the client gets to
make — it is charge-on-use, like the rest of the platform. The client's job is
to make sure the number is never a surprise, and the surprise was never the
charge, it was that status stayed silent about it.
