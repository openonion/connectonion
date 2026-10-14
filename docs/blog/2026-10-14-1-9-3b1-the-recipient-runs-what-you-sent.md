# 1.9.3b1: the recipient runs the release you sent from

*2026-10-14*

When you hand a session to someone, the line they paste also tells their agent
which ConnectOnion to install. We fixed the permission defaults in 1.9.2, and
then found, by handing a session over for real, that the line still installed
an older beta. The person on the other end never got the fix.

Now they install the release you sent from, and a test stops any release from
pinning anything else.

```bash
python -m pip install --upgrade 'connectonion==1.9.3b1'
```

See the [release notes](../releases/1.9.3b1.md).
