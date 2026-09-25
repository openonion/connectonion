# The tick that meant nothing

An unattended agent wrote to a file three times in one day and got a green
tick each time. The file never changed. Nobody was watching, so nobody asked;
the agent carried on as though its notes were saved.

That report sat in the list for weeks, and when the 1.8.9 fix line looked at
the other bugs filed since 1.8.8 shipped, the same shape kept turning up. A
Teams invitation reported as created, and mailed to everyone, with no meeting
link in it. A mistyped API key reported as a problem on our side, to be
retried later — forever. `co create --key` accepting a key and quietly writing
nothing. A skills plugin that loaded every skill and never told the model they
existed. A deploy that copied a laptop's stale session history over the
server's, and called it a successful deploy.

None of these crashed. Each one produced an answer that was confident and
wrong about what had happened, which is worse than a crash for a program an
agent drives: an agent believes what the tool says, and so does a person
reading its log at the end of the day.

So the fixes in 1.8.9b3 are mostly about evidence. A write reads the file back
and compares bytes before it says so. The Teams command asks the account what
it can do before it sends anything. A rejected key is classified by who
rejected it — checked against the real service with a key that could not work.
The deploy rule for each file names which side owns it, and a real rsync run
proves it. The test for each one was written first, against the claim the tool
was making, and failed.
