# A Server Quota Is Not a Ceiling

`co server new` had exactly one region. It said so in the pricing response —
`"region": "australia-southeast1"` — as a fact, not a choice. That was fine
until the fourth server: the fifth request came back refunded, with GCE naming
the exact wall it hit — `Quota 'IN_USE_ADDRESSES' exceeded. Limit: 4.0 in
region australia-southeast1` — and nothing in the product to do about it. Not
another region, not a smaller machine. The only moves left were outside the
CLI entirely: raise the quota by hand, or destroy a server still in use.

The honest fix wasn't a bigger number. A quota that size is a routine ceiling
on one region, not a statement about how many servers an operator should ever
have. What was missing was a second place to stand.

`REGIONS` is now a dict of region name to its zones, not a single fixed pair.
Sydney stays the default — an Australian company keeps a customer's machine
and data in the country unless they ask otherwise — but it is a default now,
not the only value that exists. Zones within a region are still tried in
order, because capacity was always a per-zone accident, never a regional
verdict; that logic didn't change, it just runs inside whichever region was
asked for.

The part worth noticing is what *didn't* need to change: a server's region.
It's read off the `zone` column it already had — `"australia-southeast1-a"`
split on its last hyphen — rather than stored a second time next to it. Two
copies of the same fact drift; one, derived, cannot.

```bash
co server new backup --region asia-southeast1
```

`co server new` validates `--region` against a list the backend actually
publishes, the same way `--machine` is checked against real machine types —
never a value hardcoded on the client side of a line that used to have only
one value to be right about.
