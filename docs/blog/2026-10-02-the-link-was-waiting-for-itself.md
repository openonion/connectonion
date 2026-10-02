# The link was waiting for itself

We were moving a listening station to an office Mac while its owner was
across town. `co lark check` said the credentials were missing and pointed
at `co auth lark`. That command needed the Feishu SDK, which nothing had
installed. pyproject.toml did not mention it at all, and `check` had stopped
at the first problem, so the second one only appeared after the first fix
failed.

With the SDK installed, `co auth lark` said "scan this, or open the link". We
ran it in the background so we could send the link to the owner's phone. The
log stopped at 8,059 bytes, partway through a row of the QR, and had no
link in it. Off a terminal, Python buffers stdout. The QR alone filled the
buffer, and the link sat behind it until the process exited. The process
would only exit once someone approved, and approving needed the link.

On a terminal none of this happens, which is why it went unseen. 1.9.0a21
ships the SDK with connectonion and prints the link first, flushed. A test
now reads the output through a buffered pipe while the scan is waiting and
expects to find the link there.
