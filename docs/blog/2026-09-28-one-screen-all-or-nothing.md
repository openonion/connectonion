# One screen, all or nothing

A student wanted to build a backend on their OneNote notebooks, and
`co auth microsoft` could not give them OneNote. Our first design asked for it
politely: an opt-in flag, `--add onenote`, so nobody saw a permission they did
not need.

The owner rejected that in one line. Ask for everything worth having in one
sign-in, and if someone does not want to give a permission, that is fine
too. More sources make the Wiki more complete. Commands should stay short.

The second half of that ran straight into a fact about Microsoft. Its consent
screen has no checkboxes. You get Accept or Cancel for the whole list. So
"they can decline the one they don't want" cannot happen on Microsoft's side.
It can only happen on ours.

There was a sharper version of the same fact. If even one requested
permission needs an administrator's approval, most school and company
accounts cannot sign in at all, and the student's university is exactly that
kind of account. So we did not guess. We read Microsoft's own permissions
reference and kept only scopes a user can grant alone: OneNote including
Class Notebooks, OneDrive, SharePoint, Teams chats, the people you work with,
To Do. Channel posts and meeting transcripts stayed out, because each needs
an administrator.

Then we built the checkbox Microsoft does not have. `co auth microsoft` asks
for the full set. If it comes back refused, the server now says why in
Microsoft's own codes, and the CLI explains it and offers the core set (mail,
calendar, contacts), which is what worked yesterday. A script gets the exact
command instead of a prompt.

Reading the server code turned up a quiet bug. The permissions it reported
back to the CLI were the ones it had asked for, not the ones Microsoft
granted. A user could be told they had access they did not have. It now
reports what the token actually carries.

The lesson: when the platform will not offer a choice, make the choice
yourself, and check its rules first. It said yes to more than we asked for.
