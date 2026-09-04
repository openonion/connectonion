# A screenshot is not a string

*2026-09-01 · Design Journal*

The first Remote Browser prototype could execute the same command on another
machine. That made navigation look nearly finished. A screenshot exposed what
the command demo had hidden.

The local browser returned two things at once: it wrote a PNG into its own
`.tmp` directory, then returned a base64 data URL so an AI could see the image.
Both were convenient while the browser and caller shared one computer. Neither
defined what “take a screenshot” meant when the browser ran on a server. The
path named a file the caller could not read. The base64 value made the entire
file one oversized text reply.

We considered adding a second `get` command. The first command would return an
artifact ID and the caller would retrieve it next. That is a familiar API, but
it gives one user action two public methods and two independent outcomes. If the
second call never arrives, the server retains an abandoned file. If an Agent
retries the first call, it may repeat the browser action. Screenshot and
download would also drift into separate implementations.

We considered returning base64 everywhere. It would be simple for tiny images,
but it grows the bytes, buffers the complete file at both ends, and turns a
reasonable one-message memory guard into an arbitrary file-size limit. Removing
the guard would not solve that architecture; it would only remove the defense.

The decision is that Browser files are streams inside the command transaction.
The daemon sends one typed result followed by bounded binary chunks. The caller
writes a private partial file, checks every offset, verifies the final size and
SHA-256, atomically exposes it without overwriting, and commits the stream. Only then is the command
successful and only then can daemon staging disappear.

This produces a useful distinction: the chunk has a limit; the file does not
inherit it. Our first stream-data frame is capped at 256 KiB so a malicious peer
cannot demand a huge allocation. A screenshot or download may contain as many
frames as its authorized resource policy and available disk permit. File quotas
remain configurable operational policy rather than a hard-coded one-megabyte
protocol mistake.

The first implementation lands at the local BrowserDaemon boundary. Every new
local command and result now uses one Protocol Buffers envelope. Screenshots use
the Artifact Stream even when the browser is on the same machine, so local and
remote semantics cannot quietly diverge again. The daemon never receives the
caller's output path. The AI proxy receives a caller-owned filename instead of a
base64 blob; the existing image formatter reads that file normally.

We are deliberately not switching on remote artifact frames yet. Protocol
Buffers provide structure, not secrecy. Relay traffic needs the reviewed OIP
secure-channel protocol, authenticated identity binding, replay protection, and
shared conformance vectors. Sending plaintext first and “adding encryption
later” would make the preview easy and the migration dangerous. Until that
boundary is ready, remote screenshots fail closed instead of choosing a hidden
base64 or public-URL fallback.

Downloads will reuse exactly this stream. Chromium's `accept_downloads` switch
is not enough: Browser Core needs an explicit capture action, safe completed-file
registration, quotas, collision handling, quarantine policy, and no automatic
open. Those are product and security semantics around the stream, not a second
file-transfer method.

The lesson is the same one Remote Browser keeps teaching us: “send the old
command farther away” proves reachability, not equivalence. A command is remote
only when its result belongs to the caller, its authority survives the network
boundary, and partial failure has one unambiguous meaning.
