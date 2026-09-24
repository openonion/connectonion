# It said it could not, and not where

During a two-machine test on 2 September, a laptop tried to lend its connection
to a rental host in Melbourne. The share said `reconnecting (the host is not
reachable directly; retrying in 60s)`, and `co proxy diagnose` said the same
thing in a longer sentence. Neither said *which* address it had tried.

Finding out took a manual query of the relay, which showed the host announcing
`http://34.129.161.131:8001` — no public domain configured, so it published its
IP and port — and a `curl` that timed out, because the cloud firewall for that
instance allowed 22, 80 and 443 and nothing else. The frustrating part was that
the code already knew. The function that picks an endpoint walks the relay's
list and tries each one; it just throws every failure away, which is exactly
right when you are connecting and exactly wrong when you are asking why you
could not.

So diagnose now does the same walk and keeps the answers. Against the real relay
today, with a host on this laptop:

```
The host announces:
  http://192.168.0.158:8611  → ok
  http://129.94.43.159:8611  → refused or unreachable
```

and when every endpoint times out, it says the thing a person would have said
after the curl: nothing answers there from this network, usually a firewall,
and a `co deploy --to` host answers on 443.

The same week, the same shape turned up in deploy. A project whose
`requirements.txt` pointed at a pre-release wheel — the whole point being to try
a build that was not on PyPI yet — was deployed, and `/info` said 1.7.0. The CLI
installs `connectonion==<its own version>` after the project's requirements, to
stop the index racing a fresh release, and that pin quietly replaced the wheel
the project had asked for. Nothing in the output mentioned it. Now a project that
names a build — an exact version, a wheel, a URL, an editable path — keeps it,
and every deploy says which connectonion ended up on the server and who chose it.

Both were cases of a tool that had the answer and printed a verdict instead.
