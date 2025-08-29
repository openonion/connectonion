# Design System Reference

This document outlines the standardized Tailwind CSS component classes for consistent UI across the documentation site.

## Typography Classes

### Headings
- `.heading-1` - Main page titles (responsive: 2xl → 3xl → 4xl)
- `.heading-2` - Section headers (responsive: xl → 2xl → 3xl)
- `.heading-3` - Subsection headers (responsive: lg → xl → 2xl)
- `.heading-4` - Minor headers (responsive: base → lg → xl)

### Body Text
- `.body-large` - Large body text with proper contrast
- `.body-base` - Standard body text
- `.body-small` - Small text for captions

## Interactive Components

### Buttons
All buttons have:
- Minimum height of 44px for mobile touch targets
- Proper focus states with ring
- Active scale animation
- Disabled states

```html
<!-- Primary button -->
<button class="btn-primary">Click me</button>

<!-- Secondary button -->
<button class="btn-secondary">Click me</button>

<!-- Ghost button -->
<button class="btn-ghost">Click me</button>
```

### Links
- `.link-primary` - Purple links with underline
- `.link-nav` - Navigation links without underline

### Cards
- `.card-interactive` - Cards with hover and focus states

## Navigation

### Current Page Indicator
- `.nav-current` - Highlights current page in sidebar
- Includes purple left border and background

### Navigation Items
- `.nav-item` - Standard navigation item with hover/focus states

## Loading States
- `.skeleton` - Animated pulse for loading content
- `.loading-spinner` - Spinning loading indicator

## Accessibility Features

1. **Color Contrast**: All text uses `text-gray-200` or better for WCAG compliance
2. **Focus States**: Every interactive element has visible focus rings
3. **Touch Targets**: Minimum 44px height/width on mobile
4. **Keyboard Navigation**: Full keyboard support with proper focus management
5. **ARIA Labels**: Proper aria-current, aria-expanded, etc.

## Usage Examples

### Typography
```jsx
<h1 className="heading-1">Page Title</h1>
<p className="body-base">Content text with proper contrast</p>
```

### Buttons with Loading State
```jsx
<button className="btn-primary" disabled={loading}>
  {loading ? (
    <span className="loading-spinner" />
  ) : (
    'Submit'
  )}
</button>
```

### Navigation with Current Page
```jsx
<Link 
  href="/docs" 
  className={pathname === '/docs' ? 'nav-current' : 'nav-item'}
>
  Documentation
</Link>
```

## Migration Guide

Replace old classes with new standardized ones:

| Old | New |
|-----|-----|
| `text-gray-400` | `text-gray-200` or `.body-base` |
| `hover:bg-gray-800` (inconsistent) | `.btn-ghost` or `.nav-item` |
| `text-4xl font-bold` | `.heading-1` |
| Random button styles | `.btn-primary`, `.btn-secondary`, or `.btn-ghost` |
| Missing focus states | All new classes include focus rings |

## Important Notes

1. **Don't mix**: Use either the component class OR individual utilities, not both
2. **Override carefully**: Use `!` modifier sparingly (e.g., `!bg-indigo-600`)
3. **Test on mobile**: All interactive elements must be easily tappable
4. **Check contrast**: Use browser DevTools to verify WCAG AA compliance