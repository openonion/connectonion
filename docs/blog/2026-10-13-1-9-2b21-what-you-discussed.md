# 1.9.2b21: a handoff that opens on what you discussed

*2026-10-13*

The person you hand work to now reads your session first. The mail says who
handed them what, then gives one line on the work: what you discussed, what you
concluded and what is still open. The block they paste into Codex or Claude
Code is three lines. Their agent runs `co handoff accept`, which fetches the
handoff and opens on a short report, with a diagram when there is something to
draw. Under it are your words and your AI's, quoted rather than summarised.

When they ask you something your session cannot answer, the question comes to
your inbox with the one line that answers it. Your agent answers on its own the
rest of the time, however you host it.

```bash
python -m pip install --upgrade 'connectonion==1.9.2b21'
```

See the [release notes](../releases/1.9.2b21.md).
