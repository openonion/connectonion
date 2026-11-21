# A code you can send

Kim wanted an agent's WhatsApp listener on the office PC. The phone that would
link it was across town with its owner. `co whatsapp listen` shows a QR code,
and a QR code has to be seen. It also changes about every twenty seconds.

The workaround was to screenshot the terminal and send the picture over chat.
The first two arrived after the code they showed had already rotated.

## The phone already has another way

Under Linked devices, WhatsApp offers **Link with phone number instead**. The
person holding the phone types an eight-character code there. The code lasts
minutes, not seconds, and it is just text, so it survives any channel.

```bash
co whatsapp listen --phone +61412345678
```

```text
Pairing code: H7J4-6CTZ
On the phone with +61412345678: WhatsApp > Settings > Linked devices > Link a device > Link with phone number instead, then type the code. It lasts a few minutes.
```

The listener asks for the code at the first QR, which is the moment the socket
is up and the device is known to be unlinked. It asks only once, however many
QRs go by. If WhatsApp will not issue a code, for example because the number
has no account, the listener stops with exit 3 and gives WhatsApp's reason.
Retrying would not help in that case.

The QR still works when you are sitting at the screen. The messages that tell
someone a device is not linked now mention both ways. See #2161.
