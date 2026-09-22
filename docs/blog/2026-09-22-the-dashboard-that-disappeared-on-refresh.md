# The dashboard that disappeared on refresh

The rental operator could still chat with the agent. The agent was online, its
health endpoint answered, and the dashboard file was sitting on disk. Yet a
refresh removed Control Center from the chat interface.

An older connection made the failure harder to understand: it still had a cached
copy of the page. The fresh connection received nothing. The missing piece was a
2 MiB check in the Host, before the file ever reached the network. Our real page
was 2,307,298 bytes. The warning stayed in the server console while the person
looking at chat lost the entire entry point.

Shrinking the page restored it, but that was the wrong product answer. A richer
calendar should not require deleting useful content to fit an arbitrary small
snapshot budget. We traced the check to the original dashboard implementation:
it had reserved generous headroom below Uvicorn's default 16 MiB message limit.
Removing Cloudflare from the proxy path had never removed either check.

The patch raises the HTML allowance to 128 MiB and matches it with a 256 MiB
transport envelope. That second number matters. JSON escaping and encrypted
base64 wrappers can make a message larger than its source file. UTF-8 encoding
avoids inflating ordinary Chinese text into ASCII escapes, and an explicit
encoded-size check catches unusually expansion-heavy content before sending.
The relay needs the same receive budget; changing one SDK constant alone would
only move the failure to the next socket.

We exercised an exact 128 MiB page containing Chinese text and emoji through an
encrypted WebSocket round-trip. Its SHA-256 matched after decoding. That is local
transport evidence, not a claim that production rollout has already finished.
The production relay configuration and installed-package acceptance are separate
release gates.

A load failure now sends a small explanatory page instead of making Home vanish.
The most useful change is that distinction: an unavailable dashboard is still a
place where the operator can learn what went wrong.
