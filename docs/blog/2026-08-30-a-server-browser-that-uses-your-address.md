# A browser on a server, using your address

The first test looked finished. A browser was running on a cloud server, its
traffic crossed a Laptop in Sydney, and the destination reported the Laptop's
public IP. That was the number we wanted to move.

Then we looked one step earlier than the destination.

The server had resolved the hostname before asking the Laptop to open the
numeric socket. The page arrived from the right address, but the server still
announced where it was going through DNS. We had moved the last packet and left
the first one behind.

That is a particularly dangerous kind of green test: the visible result is
right while the security boundary is wrong.

## Moving DNS changes who must be trusted

Sending the hostname to the Laptop sounds like a small correction. It is not.
DNS can return several addresses, change its answer, or point a public-looking
name at a private machine. If the server approves one lookup and the Laptop
performs another, neither side knows which socket the other side meant.

The path now makes one answer set cross the boundary:

```text
WTF Browser on server
        │ hostname
        ▼
Laptop resolves and checks every answer
        │ complete numeric answer set
        ▼
server checks it independently and chooses one address
        │ numeric CONNECT
        ▼
Laptop checks again and opens the public socket
```

The remote operating system never resolves the target. The Laptop cannot talk
the server into accepting a private answer, and the server cannot use the
Laptop as a tunnel into somebody's home network. A request for
`192.168.0.1:80` dies before any upstream socket opens.

The useful lesson was not “proxy DNS too.” It was that a proxy boundary is a
decision about an exact socket. Hostname checks are only evidence used to reach
that decision; they are not the decision itself.

## Truth has a lifecycle

Once DNS and the final socket belonged to the same Laptop, two older behaviors
became impossible to ignore. A shared session accepted the Laptop endpoint but
recorded itself as `direct`. Stopping a share removed a JSON entry but left the
listener alive.

Both bugs said the system was in a state it had never reached.

The WTF runtime now binds to one Direct or shared exit before the browser
starts. A second session cannot quietly change it. Stop authenticates to the
live service, waits for the listener to close, and only then removes the state.
If the Laptop disappears, the browser loses the network path; it does not find
the server's datacentre address as a convenient fallback.

## The negative test mattered most

We drove a visible Chromium through the two real proxy hops and served a page
from the fake Laptop exit. DNS and the numeric connection both appeared at the
Laptop boundary. Then we deliberately restored Chromium's localhost bypass.
The preflight failed.

That second run is the stronger result. A test that only proves the intended
path works can stay green while another path leaks. A test that introduces a
real leak and watches the boundary reject it tells us the alarm is connected.

The next acceptance is deliberately less tidy: two physical machines, observed
DNS on both sides, and a destination comparing the Laptop and server IPs. The
current listener also needs a trusted VPN or tunnel between networks; its Basic
credential is authentication, not transport encryption. Those are remaining
boundaries, not details to hide behind the successful local run.
