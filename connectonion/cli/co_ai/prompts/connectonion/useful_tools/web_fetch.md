# WebFetch

Web fetching tool with single-responsibility functions.

## Installation

```python
from connectonion import WebFetch

web = WebFetch()
```

## Low-level APIs

Each function does ONE thing.

### fetch(url)

HTTP GET request, returns raw HTML.

```python
html = web.fetch("example.com")
# Returns: "<!DOCTYPE html>..."
```

### strip_tags(html)

Strip HTML tags, returns body text only.

```python
text = web.strip_tags(html)
# Returns clean text without HTML
```

### get_title(html)

Get page title.

```python
title = web.get_title(html)
# Returns: "Example Domain"
```

### get_links(html)

Extract all links from HTML.

```python
links = web.get_links(html)
# Returns: [{'text': 'Home', 'href': '/'}, {'text': 'About', 'href': '/about'}]
```

### get_emails(html)

Extract email addresses from HTML.

```python
emails = web.get_emails(html)
# Returns: ['support@example.com', 'sales@company.org']
```

### get_social_links(html)

Extract social media links.

```python
html = web.fetch("openai.com")
social = web.get_social_links(html)
# Returns: {'twitter': 'https://x.com/OpenAI', 'youtube': '...', 'github': '...'}
```

## High-level APIs

Uses LLM to analyze content.

### analyze_page(url)

Analyze what a webpage/company does.

```python
result = web.analyze_page("stripe.com")
# Returns: "Stripe is a technology company that builds economic infrastructure..."
```

### get_contact_info(url)

Extract contact information.

```python
result = web.get_contact_info("stripe.com/contact")
# Returns: "Email: support@stripe.com, Phone: ..."
```

## Composing Functions

```python
# Get clean text from a URL
text = web.strip_tags(web.fetch("example.com"))

# Get title and text
html = web.fetch("example.com")
title = web.get_title(html)
text = web.strip_tags(html)
```

## Use with Agent

```python
from connectonion import Agent, WebFetch

web = WebFetch()
agent = Agent("researcher", tools=[web])

agent.input("What does stripe.com do?")
```

## Customizing

Need to modify WebFetch's behavior? Copy the source to your project:

```bash
co copy web_fetch
```

Then import from your local copy:

```python
# from connectonion import WebFetch  # Before
from tools.web_fetch import WebFetch  # After - customize freely!
```
