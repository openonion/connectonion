# CLI Browser Feature

Quick browser screenshots for debugging web applications.

## Overview

The `-b` flag provides instant browser screenshots without writing code. Perfect for debugging, testing, and sharing visual proof of issues.

## Basic Usage

```bash
co -b "screenshot localhost:3000"
```

This command:
1. Opens a headless browser
2. Navigates to http://localhost:3000
3. Takes a screenshot
4. Saves as `screenshot_[timestamp].png`

## Command Format

```bash
co -b "screenshot [URL] [save to PATH] [size SIZE]"
```

All parts except URL are optional.

## Examples

### Basic Screenshot

```bash
# Screenshot local development
co -b "screenshot localhost:3000"

# With specific port
co -b "screenshot localhost:8080"

# External site
co -b "screenshot example.com"
```

### Save to Specific Path

```bash
# Save to temp directory
co -b "screenshot localhost:3000 save to /tmp/debug.png"

# Save to current directory with name
co -b "screenshot localhost:3000 save to homepage.png"

# Save to subdirectory
co -b "screenshot localhost:3000 save to screenshots/test.png"
```

### Device Sizes

```bash
# iPhone viewport
co -b "screenshot localhost:3000 size iphone"

# Custom dimensions
co -b "screenshot localhost:3000 size 390x844"

# Common presets
co -b "screenshot localhost:3000 size ipad"
co -b "screenshot localhost:3000 size desktop"
```

### Complete Examples

```bash
# Debug mobile checkout flow
co -b "screenshot localhost:3000/checkout save to /tmp/checkout-mobile.png size iphone"

# Document bug on specific page
co -b "screenshot localhost:3000/xray save to bug-report.png size 1920x1080"

# Test responsive design
co -b "screenshot localhost:3000 save to mobile.png size 390x844"
co -b "screenshot localhost:3000 save to tablet.png size 768x1024"
co -b "screenshot localhost:3000 save to desktop.png size 1920x1080"
```

## Device Presets

| Preset | Dimensions | Device |
|--------|------------|--------|
| `iphone` | 390x844 | iPhone 14/15 |
| `android` | 360x800 | Common Android |
| `ipad` | 768x1024 | iPad |
| `desktop` | 1920x1080 | Full HD Desktop |

## URL Handling

The command intelligently handles URLs:

- `localhost` → `http://localhost`
- `localhost:3000` → `http://localhost:3000`
- `example.com` → `https://example.com`
- `http://example.com` → `http://example.com` (unchanged)

## Output Files

If no path specified:
- Saves in current directory
- Named `screenshot_YYYYMMDD_HHMMSS.png`
- Example: `screenshot_20240115_143022.png`

## Installation

Browser features require Playwright:

```bash
pip install playwright
playwright install chromium
```

Or install ConnectOnion with browser support:

```bash
pip install connectonion[browser]
```

## Use Cases

### 1. Debug Local Development

```bash
# Quick check of homepage
co -b "screenshot localhost:3000"

# Debug specific route
co -b "screenshot localhost:3000/api/status"
```

### 2. Document Bugs

```bash
# Capture error state
co -b "screenshot localhost:3000/error save to bug.png"

# Mobile-specific issue
co -b "screenshot localhost:3000/mobile-bug save to mobile-issue.png size iphone"
```

### 3. Test Responsive Design

```bash
# Test different viewports
for size in iphone android ipad desktop; do
  co -b "screenshot localhost:3000 save to view-$size.png size $size"
done
```

### 4. CI/CD Integration

```bash
# In GitHub Actions or similar
co -b "screenshot $DEPLOY_URL save to artifacts/deployed.png"
```

## Error Messages

```bash
# Missing URL
co -b "screenshot"
❌ Usage: co -b "screenshot [URL] [save to PATH] [size SIZE]"

# Playwright not installed  
co -b "screenshot localhost:3000"
❌ Browser tools not installed
   Run: pip install playwright && playwright install chromium

# Cannot reach URL
co -b "screenshot localhost:3000"
❌ Cannot reach http://localhost:3000
   Is your server running?

# Permission denied
co -b "screenshot localhost:3000 save to /root/test.png"
❌ Cannot save to /root/test.png (permission denied)
```

## Tips

1. **Quick Debug**: Just `co -b "screenshot localhost:3000"` for instant feedback
2. **Organize Screenshots**: Use descriptive paths like `save to bugs/issue-123.png`
3. **Test Viewports**: Use device names (`iphone`, `ipad`) for common sizes
4. **Timestamps**: Default filenames include timestamp for versioning

## Limitations

- Screenshots only (no interaction, clicking, forms)
- Single page at a time
- Headless browser only
- PNG format only

For complex browser automation, use the full ConnectOnion browser agent or Playwright directly.

## Examples for Common Frameworks

### Next.js
```bash
co -b "screenshot localhost:3000"
co -b "screenshot localhost:3000/_error save to error.png"
```

### FastAPI
```bash
co -b "screenshot localhost:8000"
co -b "screenshot localhost:8000/docs save to api-docs.png"
```

### Django
```bash
co -b "screenshot localhost:8000"
co -b "screenshot localhost:8000/admin save to admin.png"
```

### React Dev Server
```bash
co -b "screenshot localhost:3000"
co -b "screenshot localhost:3000 size iphone"
```

## Summary

The `-b` flag provides dead-simple browser screenshots. No setup, no complexity - just describe what screenshot you want and where to save it. Perfect for debugging during development.