<!--
name: 'Tool Description: Config'
description: Tool for getting and setting Claude Code configuration settings, with usage instructions and a list of configurable settings
ccVersion: 2.1.88
variables:
  - GLOBAL_SETTINGS_LIST
  - PROJECT_SETTINGS_LIST
  - ADDITIONAL_SETTINGS_NOTE
-->
Get or set Claude Code configuration settings.

  View or change Claude Code settings. Use when the user requests configuration changes, asks about current settings, or when adjusting a setting would benefit them.


## Usage
- **Get current value:** Omit the "value" parameter
- **Set new value:** Include the "value" parameter

## Configurable settings list
The following settings are available for you to change:

### Global Settings (stored in ~/.claude.json)
${GLOBAL_SETTINGS_LIST.join(`
`)}

### Project Settings (stored in settings.json)
${PROJECT_SETTINGS_LIST.join(`
`)}

${ADDITIONAL_SETTINGS_NOTE}
## Examples
- Get theme: { "setting": "theme" }
- Set dark theme: { "setting": "theme", "value": "dark" }
- Enable vim mode: { "setting": "editorMode", "value": "vim" }
- Enable verbose: { "setting": "verbose", "value": true }
- Change model: { "setting": "model", "value": "opus" }
- Change permission mode: { "setting": "permissions.defaultMode", "value": "plan" }
