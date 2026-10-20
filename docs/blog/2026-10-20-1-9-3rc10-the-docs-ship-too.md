# 1.9.3rc10: the docs ship too

*2026-10-20*

connectonion's package carries the repository's `docs/` folder, so `co init`
can give an agent the full documentation offline. That includes the dev blog.

rc9 went out with a blog post that told a true story about a real person and
their own business, written the day before. We had removed the same story from
a code comment before tagging, and checked only the files the release itself
changed. The post was in the package anyway.

rc10 retells it with a fictional sender and a neutral task. Before a release
is tagged, the whole tree that gets packaged is now searched, not just the
release's own diff.

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc10'
```
