# Tidy ran before the mess was made

The morning after tidying shipped, we ran 1.9.0a5 on a copy of the owner's
notebook and read what it left. The services it had archived stayed archived,
and his own addresses stayed folded. But the fresh map had just made new ones.
Telnyx's `discover@` and `portal@`, Workday's one-time-password sender,
Singapore Airlines' booking desk and Lebara's `mylebara@` were all people
pages. Tidy had run and reported nothing, which was accurate: it runs before
the map, so these pages did not exist yet when it looked.

Three smaller things were wrong on the same pages. The owner's page asked
"possibly yours?" nine times about three addresses, and two of those were
already his. Its History said "in the 90 days to 2026-09-25" after that day's
map. `yahoo.com.hk` and `luma-mail.com` were organisation pages. And one daily
update took the connectonion project page from 13,421 characters to 25,255.

These all had one cause. Each rule was written for the first time something
happens, and nothing checked it the second time. The map wrote its lines on
the owner's page only where the page said "not investigated yet". A later map
never touched a line the first one had written, so every map added its own
lines and the old ones stayed. The size limit was in the upkeep instructions,
and a daily update is an investigation, which had no size rule. The service
rule only knew display names that start with the brand, and "Team Telnyx" ends
with it.

So tidy now runs again when the map finishes, and the map and tidy use the
same service rule. That rule now covers booking, OTP and portal desks, Workday
as a sender, a mailbox with its brand in the local part, and a brand at the end
of a display name. A mail provider under any country code is never an
organisation, and neither is an event platform's relay. The map replaces its
own lines on the owner's page each time instead of adding more. The runner
refuses any page over 20,000 characters that has grown, at every stage.

We picked 20,000 from the copy, not from a guess. 696 of its 698 pages were
under 15,000. The largest page built from read material was 18,910. Both
problem updates ended above 20,000. A page that is already over the limit can
still be saved when it gets shorter, so it is never stuck.

On the same copy, the new tidy archived eight more services and both
organisation pages, and cut the owner's nine "possibly yours" lines to the
zero the map still asks about. A second pass changed nothing.

The lesson: a rule that runs once is only tested once. Run it again on its own
output, and check that the second run changes nothing.
