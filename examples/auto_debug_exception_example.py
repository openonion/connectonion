"""
ConnectOnion Auto-Debug Exception Example

This example demonstrates how auto_debug_exception() automatically analyzes
uncaught exceptions with AI to help you understand and fix errors quickly.

Prerequisites:
- Set OPENAI_API_KEY in your .env file
- Install ConnectOnion: pip install -e .
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv()

from connectonion import auto_debug_exception, Agent

# Enable AI exception debugging - now any uncaught exception gets AI help!
auto_debug_exception()

print("🧅 ConnectOnion Auto-Debug Exception Example")
print("=" * 50)
print("This example will intentionally crash to show AI debugging.\n")

# Example 1: Simple NameError
print("Example 1: NameError")
print("-" * 20)
try:
    # This will crash with NameError
    result = undefined_variable
except NameError:
    print("(Caught the NameError, so auto_debug_exception won't trigger)")
    print("Let's try an uncaught one instead...\n")

# Example 2: KeyError that we don't catch
print("Example 2: KeyError (uncaught)")
print("-" * 20)

def process_config(config):
    """Process configuration data."""
    # This assumes 'database' key exists
    db_config = config['database']  # Will crash if missing!
    return f"Connected to {db_config}"

# Create incomplete config (missing 'database' key)
my_config = {
    'api_key': 'secret',
    'timeout': 30
}

print("Processing config:", my_config)
result = process_config(my_config)  # 💥 This will crash and trigger AI debug!
print("Result:", result)  # Never reached