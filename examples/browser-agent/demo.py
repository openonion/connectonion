#!/usr/bin/env python3
"""Interactive demo of the browser agent"""

from agent import agent, browser
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check if API key is loaded
api_key = os.getenv('OPENAI_API_KEY')
if not api_key or api_key == 'sk-your-key-here':
    print("⚠️  Warning: OPENAI_API_KEY not properly configured!")
    print("Please set a valid API key in .env file")
    exit(1)

print("🌐 ConnectOnion Browser Agent Demo")
print("=" * 50)
print("This demo will navigate to docs.connectonion.com and perform various tasks")
print()

# Step 1: Start browser and navigate
print("Step 1: Starting browser and navigating to docs.connectonion.com...")
result = agent.input(
    "Start the browser, navigate to https://docs.connectonion.com, "
    "and tell me the page title"
)
print(f"✅ {result}\n")

# Step 2: Take screenshot
print("Step 2: Taking a screenshot...")
result = agent.input("Take a screenshot and save it as connectonion_docs.png")
print(f"✅ {result}\n")

# Step 3: Extract content
print("Step 3: Extracting page content...")
result = agent.input(
    "Scrape the main content from the page and tell me what the first "
    "section is about (just a brief summary)"
)
print(f"✅ {result}\n")

# Step 4: Extract links
print("Step 4: Finding documentation links...")
result = agent.input(
    "Extract all the links on the page and tell me how many documentation "
    "sections there are"
)
print(f"✅ {result}\n")

# Step 5: Navigate to Quick Start
print("Step 5: Navigating to Quick Start page...")
result = agent.input(
    "Navigate to the Quick Start page if there's a link for it, "
    "and tell me what you find there"
)
print(f"✅ {result}\n")

# Step 6: Take full page screenshot
print("Step 6: Taking a full-page screenshot...")
result = agent.input(
    "Take a full-page screenshot of the current page and save it as "
    "quickstart_fullpage.png"
)
print(f"✅ {result}\n")

print("=" * 50)
print("Demo complete! Screenshots saved:")
print("  - connectonion_docs.png")
print("  - quickstart_fullpage.png")

# Clean up
print("\nCleaning up...")
result = agent.input("Close the browser and clean up")
print(f"✅ {result}")
print("\nGoodbye!")