# co wechat help pages

Each section is printed verbatim by `--help` for the command it names (#3355),
the way `co rem` prints rem_help.md: plain in a pipe, the same words styled in
a terminal. A test holds every page to its command's real options.

## co wechat

```
co wechat — read your own WeChat for Mac chats on this Mac. Read-only; nothing is sent.

Run co wechat on its own: the first time it sets up what is missing (access to
the WeChat folder, the database keys), then it lists your recent chats, numbered.
macOS only.

Usage:    co wechat [--limit N]
          co wechat COMMAND
Example:  co wechat  |  co wechat read 1  |  co wechat search 合同  |  co wechat contacts --friends
          --limit   how many recent chats to list (default 20)

Read
  read          One chat's recent messages, oldest first.
  search        Messages that contain your words, across your chats, newest first.
  contacts      Count and find your contacts: friends, groups, accounts.
Set up and check
  doctor        Whether chats can be read: macOS, folder access, saved keys.
  key           The database keys: see them, capture them, or save one.
Raw access
  tables        Each database with its tables and row counts.
  decrypt       Plaintext SQLite copies of every database, into a folder.
  export        One table as JSON or Markdown.

Effects:  Read-only. The first run may ask for folder access and run co wechat key capture.
Coverage: the list ends with one line saying how many chat databases exist and how many
          a key opens; a database with no key (e.g. history migrated after the last
          capture) is named there, never skipped silently, with its fix.
Next:     co wechat read 1, or co wechat key capture when the coverage line names a missing key
Back:     co --help
```

## co wechat doctor

```
Check whether WeChat chats can be read on this Mac: macOS, access to the WeChat
data folder, and saved database keys. Read-only; exits 2 if something is missing
and names the step that fixes it.

Usage:    co wechat doctor
Example:  co wechat doctor
Effects:  Read-only.
Next:     co wechat
Back:     co wechat --help
```

## co wechat read

```
Show one chat's recent messages, oldest first. Read-only.

Usage:    co wechat read WHO [--limit N]
Example:  co wechat read 1  |  co wechat read 妈妈 --limit 50
          WHO       a number from the last co wechat list (for 15 minutes), or a name
          --limit   how many recent messages (default 30)
Effects:  Read-only. Reads the message databases that have a key; a database
          without one is skipped, so after migrating chat history run co wechat key capture.
Next:     co wechat search 合同
Back:     co wechat --help
```

## co wechat search

```
Find text messages that contain your words, across your chats, newest first. Read-only.

Usage:    co wechat search WORDS [--limit N]
Example:  co wechat search 合同  |  co wechat search invoice --limit 50
          WORDS     the text to look for
          --limit   how many results (default 20)
Effects:  Read-only. Searches the message databases that have a key; a database
          without one is skipped, so after migrating chat history run co wechat key capture.
Next:     co wechat read 1
Back:     co wechat --help
```

## co wechat contacts

```
Count your WeChat contacts and find one. Friends are the people you added; groups,
official accounts and people you only share a group with are counted apart. Read-only.

Usage:    co wechat contacts [--friends] [--search TEXT] [--limit N] [--json]
Example:  co wechat contacts  |  co wechat contacts --friends --search Mia  |  co wechat contacts --json
          --friends  list friends only (by default it prints the counts)
          --search   names, remarks, aliases or ids that contain TEXT
          --limit    how many to list (default 50)
          --json     one JSON object: the counts and the listed contacts
Effects:  Read-only. Reads contact.db; nothing is written.
Next:     co wechat read 1
Back:     co wechat --help
```

## co wechat tables

```
List each WeChat database with its tables and row counts, then how many chat
databases a key opens. Read-only.

Usage:    co wechat tables [--json]
Example:  co wechat tables  |  co wechat tables --json
          --json    only the chat-database coverage as JSON: found, read, skipped, missing_keys
Effects:  Read-only. A database without a key is named with its fix, never skipped silently.
Coverage: the last line says how many chat databases exist and how many a key opens.
Next:     co wechat export --db contact.db --table contact --format json, or
          co wechat key capture when the coverage line names a missing key
Back:     co wechat --help
```

## co wechat decrypt

```
Writes a plaintext SQLite copy of each WeChat database into a folder, openable by
any SQLite tool. Local only; WeChat's own files are never changed.

Usage:    co wechat decrypt [--out DIR]
Example:  co wechat decrypt --out ~/wechat-plain
          --out     the folder for the copies (default ./wechat-plain)
Effects:  Writes plaintext copies into --out. They hold your whole history unencrypted:
          delete them when you are done.
Next:     co wechat tables
Back:     co wechat --help
```

## co wechat export

```
Writes one table from a WeChat database as JSON or Markdown, to a file or the screen.
Reads WeChat only.

Usage:    co wechat export --db FILE --table NAME [--format json|md] [--out FILE]
Example:  co wechat export --db contact.db --table contact --format json --out contacts.json
          --db      a database file name, as co wechat tables shows it
          --table   a table in that database, as co wechat tables shows it
          --format  json or md (default json)
          --out     write here instead of printing
Effects:  Writes --out when given; otherwise prints. Read-only for WeChat.
Next:     co wechat tables
Back:     co wechat --help
```

## co wechat key

```
Check, capture or save the WeChat 4.1 database keys; with no command, says how many
are saved. WeChat encrypts each database with its own key, which exists only while
WeChat opens it. Read-only unless you run capture or set.

Usage:    co wechat key
          co wechat key COMMAND
Example:  co wechat key  |  co wechat key capture

Commands
  capture       Capture the key of every database on this Mac; merges with the saved ones.
  set           Save one key you already have.

Effects:  Read-only with no command.
Next:     co wechat key capture
Back:     co wechat --help
```

## co wechat key capture

```
Save the keys that let co read your WeChat messages: writes the key of every
database on this Mac to ~/.co/wechat/keys.json (owner-only), keeping the keys saved
before. Run it on first setup and whenever new databases appear. Quits and reopens WeChat.

Run it the first time, and again whenever WeChat has new databases: after you
migrate chat history from your phone, or when co wechat tables lists a database
as skipped. Without a key for a database, its messages can't be read.

What happens: it asks once, quits WeChat, and opens a re-signed copy of WeChat
under Apple's debugger. Log in to that copy (scan the QR code with your phone)
and click Allow when macOS asks to let it read your data. The copy opens each
database, its key is saved, the copy is deleted, and the real WeChat reopens:
log in there once more. Only macOS tools are used; nothing is installed.

Usage:    co wechat key capture [--yes] [--keep-copy]
Example:  co wechat key capture  |  co wechat key capture --yes
          --yes        skip the question; for a script you started yourself
          --keep-copy  keep the 1.4 GB re-signed copy for the next capture
Effects:  Writes ~/.co/wechat/keys.json (new keys added, saved keys kept) and says how
          many keys it found this time and how many databases now have one.
          Quits and reopens WeChat.
Next:     co wechat tables
Back:     co wechat key --help
```

## co wechat key set

```
Writes one database key you already have into ~/.co/keys.env (owner-only).
Most people want co wechat key capture instead.

Usage:    co wechat key set KEY
Example:  co wechat key set "x'0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0'"
          KEY       a SQLCipher raw key: x' and 64 hex characters '
Effects:  Writes one line in ~/.co/keys.env.
Next:     co wechat doctor
Back:     co wechat key --help
```
