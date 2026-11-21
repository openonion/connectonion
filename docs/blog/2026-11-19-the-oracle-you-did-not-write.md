# The oracle you didn't write

*2026-11-19*

`co wechat` reads your own WeChat for Mac history. The chat logs sit in SQLite
databases encrypted with SQLCipher 4, so the core of the feature is sixty lines
that decrypt a page: derive the HMAC key, check each page's HMAC-SHA512, run
AES-256-CBC, reassemble a normal SQLite file. Small, mechanical, easy to feel
confident about.

That confidence is the trap.

The obvious way to test a decryptor is a round trip: encrypt a known table with
your own code, decrypt it, assert you got the table back. It passes on the first
try, every time — because both halves share the same misreading of the format. If
you put the salt in the wrong place, you put it in the wrong place *consistently*,
and the test is green while the code cannot read a single byte WeChat ever wrote.
A round trip against yourself measures that your code is self-consistent, not that
it is correct. Those are different claims, and only one of them matters.

So we didn't write the oracle. We installed the real `sqlcipher` CLI — a different
implementation, by other people, years older than our sixty lines — and let *it*
encrypt the fixture. Our code decrypts what sqlcipher produced; plain `sqlite3`
reads the result back. The fixture is committed, so the test runs in CI with no
sqlcipher present. When it passes, it says something our own round trip never
could: a stranger's encoder and our decoder agree on the format. First run against
it, 202 rows came back, `PRAGMA integrity_check` returned `ok`, and the Chinese
text was intact. That is a measurement.

The second lesson came from the least interesting command. `co wechat doctor` just
checks whether WeChat's data folder is reachable. Reading that folder on macOS
trips a privacy prompt, and in a non-interactive shell the prompt never arrives and
never resolves — the probe blocks forever. A health check that can hang is worse
than no health check, because it fails in the one shape no one is watching for:
silence. The fix is to run the probe in a thread with a deadline, so an
unanswerable prompt becomes a prompt three-second "BLOCKED — grant Full Disk
Access" instead of a frozen terminal. "Can I read this?" has three answers, not
two: yes, no, and *I couldn't find out in time*. The third one has to be sayable.

What ships today is honest about its own edges. Obtaining the decryption key stays
a consented manual step; the tool stores a key you got, it doesn't reach into
WeChat for you. And WeChat's own table layout we haven't seen, so `co wechat chats`
shows you the tables it finds rather than pretending to know them, and `export`
works on any table without a schema. The parts we could prove, we proved against
something we didn't write. The parts we couldn't, we labelled.
