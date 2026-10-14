# 1.9.2b31: nobody gets more than the handoff

*2026-10-14*

Handing work to someone should not hand them your agent. We checked what each
side of a handoff could do to the other, and found the person who accepted
became a full contact of the sender's agent: able to send it instructions and
approve its own tool calls. Worse, "the person who accepted" meant whoever
opened the link first.

Now each side gets only what the handoff needs: messages about that one
handoff. Letting someone use your agent is a separate, deliberate step. The
rule behind it is simple: trust follows from what it would cost the other
person to abuse it, and for someone we know nothing about, we assume nothing.

```bash
python -m pip install --upgrade 'connectonion==1.9.2b31'
```

See the [release notes](../releases/1.9.2b31.md).
