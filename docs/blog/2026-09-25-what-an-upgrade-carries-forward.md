# What an upgrade carries forward

The Wiki on the author's own laptop had been set to update itself every
night since 22 September. It had never succeeded once. The first failures
were a 400 from the model endpoint. After that the log read "model not
available to a ChatGPT login" every morning, and once the daily limit of
attempts was spent on failures, the log repeated a limit message every five
minutes.

The fixes were already written. The default model had been changed three
days earlier, and the turn timeout and digest size a day after that. None of
it reached this notebook. `init` had copied every default into the notebook's
`config.yaml` on 20 September, and a saved value always wins. The notebook
still ran with the settings it was created with (#1714).

Upgrading and re-mapping turned up two more cases of the same kind. The old
map hadn't known that `aaron@mail.openonion.ai` was the owner, so it had made
that address a correspondent page, titled with the address and showing one
mail. The new map recognised the owner and reused that page, but only filled
sections still marked Unknown, so the owner's page stayed a one-mail stub.
Then the first real update ran for five minutes and wrote its pages. It also
proposed a follow-up question, "is this the same person?", with one person
where two were needed, and that single malformed proposal failed the batch.
A failed batch doesn't advance, so the same forty messages would have been
reworked every night.

None of this showed up in tests, because every test starts from an empty
notebook. A real notebook has history: settings chosen by a previous version,
pages written by a previous map, output that is correct except for one
optional line. So a page the map wrote and nobody has investigated can now be
rewritten by the map. A bad proposal is dropped on its own instead of failing
the batch. The next change is to let defaults stay defaults, so a notebook
picks up the values the current release ships with.

That night's run, on the upgraded notebook, completed.
