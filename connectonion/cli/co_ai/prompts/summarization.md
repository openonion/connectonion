# Conversation Summarization

Your task is to create a detailed summary of the conversation so far, paying close attention to the user's explicit requests and your previous actions.

This summary should be thorough in capturing technical details, code patterns, and architectural decisions that would be essential for continuing development work without losing context.

## Summary Structure

Create a summary with these sections:

### 1. Primary Request and Intent
Capture all of the user's explicit requests and intents in detail. What are they trying to accomplish?

### 2. Key Technical Concepts
List all important technical concepts, technologies, and frameworks discussed.

### 3. Files and Code Sections
Enumerate specific files and code sections examined, modified, or created. Include:
- File paths
- Summary of why each file is important
- Key code snippets (verbatim)
- Changes made

### 4. Errors and Fixes
List all errors encountered and how they were fixed. Include:
- Error messages (verbatim)
- Root cause
- Solution applied
- User feedback if any

### 5. Problem Solving
Document problems solved and any ongoing troubleshooting efforts.

### 6. User Messages
List ALL significant user messages (not tool results). These capture feedback and changing intent.

### 7. Pending Tasks
Outline any tasks explicitly requested but not yet completed.

### 8. Current Work
Describe precisely what was being worked on immediately before this summary. Include:
- File names and code snippets
- The exact state of work

### 9. Next Step
What should happen next? Only include if directly aligned with user's most recent request.
Include direct quotes from recent conversation to prevent task drift.

## Guidelines

- Be thorough but concise
- Preserve technical precision (exact file paths, function names, error messages)
- Include verbatim code snippets for critical sections
- Focus on actionable information needed to continue work
- Capture user feedback and corrections
