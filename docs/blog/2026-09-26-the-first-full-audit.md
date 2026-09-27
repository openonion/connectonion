# The first full audit

`co audit` had been built and tested on a few pages. Then we pointed it at
all of `co`, with the model review switched on, and it came back with 118
problems. Four were rules: `co wiki` pages with no example. The other 114 were
the model's: first lines a newcomer could not act on, examples nobody would
run, and words like "owner-bound", "OIP" and "self-descendant" that only make
sense if you wrote the code.

Four agents took a group each and worked through them with one instruction:
the model's suggestion is an opinion, so read the handler and apply it only
where it is true. That instruction mattered. Several suggestions would have
made a page wrong. The reviewer wanted `co youtube channel` to say it reads
public metadata, but by default it reads your own channel through your login.
It wanted `co schedule run` to say "right away", when it runs within the next
minute. It wanted full 40-character addresses in the trust examples, when our
addresses are 64 characters and a real-looking one in help is a privacy
problem. Those were declined, with the reason written down.

Reading handlers also found pages that were simply false. `co env rotate` said
it rewrote the env file, but it writes a separate secrets store and the value
does not change. `co trust remove` said it removed an address from every list,
but blocks and admins stay. `gmail draft attach --drive` described a row number
that only works together with a listing id.

The audit also improved itself. Our `private` rule looked for 40-character
addresses, which is Ethereum's length, not ours. A rule that sounds right is
not the same as one checked against our own data. And one gap the model kept
circling turned into a rule of its own: 113 options and arguments printed a
name and a type but no description at all. The model can notice that, but a
regular expression can prove it on every page, so now it does, for any CLI.
On `uv` it finds `--user` with no description, and on `gh` nothing.

After the fixes, all 281 pages pass every rule, and the review is down to 12
flags. Five of those are the address examples we declined on purpose. The
rest are single-word preferences a rerun may not repeat.
