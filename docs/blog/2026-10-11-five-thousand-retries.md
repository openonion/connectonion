---
description: A Feishu listener without a history scope retried every 60 seconds for three and a half days. A missing scope is now said once, with what to grant, and not retried.
tags: [Inbox, Feishu]
---

# Five thousand retries

The Feishu listener on one of our production agents looked healthy. People
@-mentioned it in a group, and it answered. Its log was 1.2 MB, though, and
nearly every line was the same:

```
history recovery incomplete; checkpoint retained: Feishu error 230027:
Lack of necessary permissions, ext=need scope: im:message.group_msg.
Check bot history permissions and network; retrying in 60 seconds
```

There were 5,404 of them over three and a half days.

History recovery is the listener's second path for messages. When the
WebSocket drops, it reads back through chat history so nothing sent during
the gap is lost. Reading group history needs `im:message.group_msg`. Since
#1544, `co auth feishu` asks for that scope when it creates an app. This app
had been brought in with `--app-id`, so it never got the scope. On a customer
tenant, it is a sensitive scope that only an admin can approve.

## Retrying something that can't change

The recovery worker treated every failure the same way: write the error,
wait 60 seconds, try again. For a dropped connection or a 502 that is right.
For a missing permission it is wrong in a way that is easy to miss: the
answer will be the same in 60 seconds, and in 60 hours, until a person
changes something in a console. The log line even said "check ... network",
which sent you to look in the wrong place.

## Said once

Feishu error 230027 is now its own exception, `MissingScope`. When the
recovery worker gets it, it writes the error once:

```
history recovery stopped: Feishu error 230027: ... need scope: im:message.group_msg.
Grant that scope to the app in the developer console (a tenant admin may need
to approve it), then restart the listener. Live messages still arrive.
```

Then the worker stops. Other failures still retry every 60 seconds, as they
should. The test drives the real `_data` parser with a 230027 response. It
checks that the worker thread ends on its own, that the code appears in
exactly one log line, and that the line names the scope. On main, the thread
was still alive and waiting to try again.
