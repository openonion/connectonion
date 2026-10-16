# 1.9.3rc5: handoffs, sealed

*2026-10-17*

This candidate carries one change: `co handoff` is end-to-end encrypted.

The sender's co seals the handoff before it leaves the machine and puts the key
after the `#` in the link, the one part of a URL a browser never sends. The page
decrypts in the reader's browser; `co handoff accept` decrypts on the
recipient's machine. Once the recipient's agent has accepted, every message
between the two agents is boxed to the other's key. The backend stores and
relays ciphertext.

Why it works this way, and what it does not cover, is in
[The key after the #](2026-10-16-the-key-after-the-hash.md).

The recipient's pasted line now installs 1.9.3rc5, since older co cannot read
the new `coh4` codes. Handoffs sent from 1.9.3rc4 or earlier still pick up.

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc5'
```
