# "Expired" was the wrong word

An hour after OneNote shipped in 1.8.9b19, the owner signed in with
`co auth microsoft`, accepted the new consent screen, and ran `co onenote ls`.
It said: "Microsoft authorization expired. Next: co auth microsoft." So they
signed in again. Same answer.

The token had not expired. With the same token, mail answered 200 and OneNote
answered 401, code 40001: "The request does not contain a valid
authentication token." The owner's account is an outlook.com one, a personal
Microsoft account. Microsoft's OneNote permissions list three scopes for
personal accounts, `Notes.Create`, `Notes.Read` and `Notes.ReadWrite`, and
two more, the `.All` ones, for work or school accounts only. We had asked for
`Notes.ReadWrite.All` alone. The consent screen accepted it, the token carried
it, and OneNote ignored it.

Two things were wrong. The consent asked for a scope that half our users can
never use, so it now asks for `Notes.ReadWrite` as well. And the CLI read
every 401 as "expired" and sent the person back to a sign-in that could not
fix it. Now a 401 to a sign-in without `Notes.ReadWrite` says that a personal
account needs it, and names the command that asks for it.

The lesson: an error message is a diagnosis. If the code does not know the
cause, "sign in again" is a guess, and a guess that loops is worse than
saying what was refused.
