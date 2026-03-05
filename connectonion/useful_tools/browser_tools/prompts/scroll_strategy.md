# Scroll Strategy

Analyze this webpage and determine the BEST way to scroll "{description}".

## Scrollable Elements Found
{scrollable_elements}

## Simplified HTML (first 5000 chars)
{simplified_html}

## Instructions

Return:

1. **method**: "window" | "element" | "container"

2. **selector**: CSS selector (empty if method is "window")

3. **javascript**: Complete IIFE that scrolls ONE iteration:
```javascript
(() => {{
  const el = document.querySelector('.selector');
  if (el) el.scrollTop += 1000;
  return {{success: true}};
}})()
```

4. **explanation**: Brief reason

## Common Patterns

- Gmail/email lists: Scroll the container with overflow:auto, NOT window
- Social feeds (Twitter, LinkedIn): Often scroll the main feed container
- Regular pages: Use window.scrollBy(0, 1000)

User wants to scroll: "{description}"
