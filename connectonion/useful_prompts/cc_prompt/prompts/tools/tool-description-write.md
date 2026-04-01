<!--
name: 'Tool Description: Write'
description: Tool for writing files to the local filesystem
ccVersion: 2.1.53
variables:
  - MUST_READ_FIRST_FN
-->
Writes a file to the local filesystem.

Usage:
- This tool will overwrite the existing file if there is one at the provided path.${MUST_READ_FIRST_FN()}
- Prefer the Edit tool for modifying existing files — it only sends the diff. Only use this tool to create new files or for complete rewrites.
- NEVER create documentation files (*.md) or README files unless explicitly requested by the User.
- Only use emojis if the user explicitly requests it. Avoid writing emojis to files unless asked.
