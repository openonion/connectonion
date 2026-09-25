# co search and co fetch

The `co ai` web tools as commands. Any skill that shells out to "search the
web" has something to run, and you can see exactly what the agent saw.

```bash
co search "python json module"                 # auto: your key, else credits, else free
co search "python json module" --engine ddg    # free, no key
co search "rust 2024 edition" -n 5 --json      # structured, for scripts
co fetch https://docs.python.org/3/library/json.html
co fetch https://docs.python.org/3/library/json.html --prompt "What does indent do?"
```

## co search QUERY

| Option | Meaning |
|---|---|
| `--engine, -e` | `auto` (default), `co`, `serper`, `brave`, `ddg` — see [web_search](../useful_tools/web_search.md#web_searchquery-engineauto-count10) |
| `--count, -n` | 1–20 results (default 10) |
| `--json` | `{"engine", "results": [{"title","url","snippet"}], "notes"}` on stdout |

Exit 0 with results; the tip on stderr names `co fetch <first result>`.
Exit 1 when the engine could not answer, with one next step. Out of credits:

```
$ co search "python docs" --engine co
Search failed (payment_required): Your ConnectOnion credits are used up. Add credits: co status. Free alternatives: ...
Next: co search 'python docs' --engine ddg
```

`co` charges each query to your ConnectOnion credits (`co status` shows the
balance). Your own `SERPER_API_KEY` or `BRAVE_API_KEY` in `.env` is used first
when set: `co env set SERPER_API_KEY <key>`.

## co fetch URL

| Option | Meaning |
|---|---|
| `--prompt, -p` | A question; a small model answers from the page instead of printing it |
| `--max-chars` | Longest page text printed (default 20000) |
| `--json` | `{"url","status","content_type","title","markdown","redirect"}` |

Private and local addresses are refused (exit 1, `Next: curl -sL <url>`). A
redirect to another site is printed, not followed, and the tip is
`co fetch <target>`. Pages that need JavaScript: `co browser`.
