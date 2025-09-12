# Design Decision: CLI Create Flow Optimization

## Date
2024-09-12

## Status
Implemented

## Context
The original `co create` command flow asked users for the project name first, then template selection, then AI configuration. This created a poor user experience where users had to name something before they knew what they were building.

## Problem Statement
Users were experiencing decision paralysis and confusion because:
1. They had to name their project before choosing what type of project it would be
2. The template selection showed too much information in a verbose format
3. Users had to type template names instead of using simple numeric selection
4. The flow didn't align with natural decision-making process

## Decision
We restructured the `co create` flow to follow a more intuitive order:

### New Flow Order:
1. **Template Selection** (first) - What are you building?
2. **AI/API Configuration** (if needed) - How will it work?
3. **Custom Description** (if custom template) - What specifically?
4. **Project Name** (last) - What will you call it?

### UI Improvements:
- Replaced verbose template descriptions with clean numbered list
- Users press 1-6 instead of typing template names
- Removed excessive file tree information from initial view
- Added confirmation message after selection

## Implementation

### Before:
```
Project name [my-agent]: ???
[... then template selection with verbose output ...]
Template (minimal, web-research, email-agent, ...) [minimal]: minimal
```

### After:
```
Choose a template:

  1. 📦 Minimal - Simple starting point
  2. 🔍 Web Research - Data analysis & web scraping
  3. 📧 Email Agent - Professional email assistant
  4. 🤖 Meta-Agent - ConnectOnion development assistant
  5. 🎭 Playwright - Browser automation
  6. ✨ Custom - AI generates based on your needs

Select template [1-6] [1]: 3
✓ Selected: 📧 Email Agent

[... configuration ...]

Project name [my-agent]: email-assistant
```

## Rationale

### Why Template First?
- **Natural decision flow**: Users first decide WHAT they want to build, then HOW to configure it, and finally WHAT to name it
- **Reduces cognitive load**: Naming is easier after understanding the project scope
- **Better defaults**: We can suggest better default names based on template choice (future enhancement)

### Why Numeric Selection?
- **Faster**: Pressing "3" is faster than typing "email-agent"
- **Less error-prone**: No typos or case sensitivity issues
- **More accessible**: Better for users with mobility constraints
- **Industry standard**: Common pattern in CLI tools (npm init, create-react-app, etc.)

### Why Minimal Display?
- **Reduces overwhelm**: Users see essential information only
- **Faster scanning**: Clean list is easier to parse than verbose trees
- **Mobile-friendly**: Works better in small terminal windows
- **Progressive disclosure**: Details available after selection if needed

## Consequences

### Positive
- Improved user experience with more intuitive flow
- Faster project creation (fewer keystrokes)
- Reduced decision paralysis
- Better alignment with user mental models
- More professional CLI experience

### Negative
- Breaking change for users expecting old flow
- Scripts using the old flow need updating
- Less information upfront (though this is intentional)

### Mitigations
- The `-y` flag still works for automated/scripted usage
- Template can still be specified via `-t` flag
- Verbose information still available via `--help`

## Alternatives Considered

1. **Interactive menu with arrow keys**: More complex to implement, requires additional dependencies
2. **Keep name first but make optional**: Would complicate the flow with conditional logic
3. **Show all information but paginated**: Would slow down the process
4. **GUI/TUI interface**: Outside scope of simple CLI tool

## References
- User feedback: "I think user are lazy, should let them to choose from template"
- Similar patterns: npm init, cargo new, create-react-app
- UX principle: Progressive disclosure
- ConnectOnion philosophy: "Keep simple things simple"

## Future Enhancements
- Smart default names based on template (e.g., "my-email-agent" for email template)
- Remember user preferences for next time
- Template preview on hover/selection (if terminal supports it)
- Custom template gallery from community