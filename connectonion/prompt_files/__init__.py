"""
Purpose: Prompt files namespace for built-in plugin markdown prompts (empty module)
LLM-Note:
  Dependencies: none | imported by [prompts.py via load_system_prompt] | contains markdown files (reflect.md, etc.)
  Data flow: namespace only (contains .md files, no code)
  State/Effects: no state
  Integration: directory contains prompt files loaded by plugins (e.g., useful_events_handlers/reflect.py loads prompt_files/reflect.md)
  Performance: trivial
  Errors: none
Prompts module for ConnectOnion built-in plugins.
"""
