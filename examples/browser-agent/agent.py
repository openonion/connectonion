"""
Purpose: Main entry point for natural language browser automation agent
LLM-Note:
  Dependencies: imports from [pathlib, dotenv, connectonion.Agent, web_automation.WebAutomation] | imported by [README.md examples] | tested by [tests/test_all.py]
  Data flow: receives natural language command string from __main__ → agent.input() routes to LLM (gemini-2.5-flash) → LLM calls web.* tools → returns execution result string
  State/Effects: creates global web=WebAutomation() instance | loads .env with OPENONION_API_KEY | reads prompt.md system instructions | web tools mutate browser state (open/navigate/click/close)
  Integration: exposes agent.input(str) → str API | uses ConnectOnion Agent with tools=web (all WebAutomation methods become callable tools) | max_iterations=20 for complex multi-step workflows
  Performance: agent orchestrates sequential tool calls based on LLM decisions | browser operations are synchronous (blocking) | screenshot I/O writes to screenshots/ folder
  Errors: raises if .env missing OPENONION_API_KEY | playwright install required or import fails | web tools return error strings (not exceptions) for LLM to handle
"""

from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from connectonion import Agent
from connectonion.useful_plugins import image_result_formatter, ui_stream
from web_automation import WebAutomation

# Create the web automation instance
# Cloud deployment: use_chrome_profile=False (no persistent profile in cloud)
# Local development: set use_chrome_profile=True to use Chrome cookies/sessions
web = WebAutomation(use_chrome_profile=True)

# Create the agent with browser tools and streaming plugins
# image_result_formatter converts base64 screenshots to vision format for LLM to see
# ui_stream sends real-time activity events to connected UI clients via WebSocket
agent = Agent(
    name="browser_agent",
    model="co/gemini-3-flash-preview",
    system_prompt=Path(__file__).parent / "prompts" / "agent.md",
    tools=web,
    plugins=[image_result_formatter, ui_stream],  # Vision + real-time streaming
    max_iterations=50  # Increased for scrolling through all emails
)

if __name__ == "__main__":
    # Gmail analysis task - Get ALL emails and extract contacts
    result = agent.input("""
    1. hacknews and summary the newest news  
    """)
    print(f"\n✅ Task completed: {result}")
 
