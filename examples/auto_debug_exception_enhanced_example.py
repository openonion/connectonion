"""
ConnectOnion Auto-Debug Exception - Runtime Inspection Example

This example demonstrates how auto_debug_exception() uses runtime inspection
tools to provide deep analysis of exceptions with access to the actual crashed state.

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

from connectonion import auto_debug_exception

print("🧅 ConnectOnion Auto-Debug Exception - Runtime Inspection Example")
print("=" * 60)
print("This example shows runtime inspection debugging.\n")

# Enable AI exception debugging with runtime inspection tools (always enabled)
auto_debug_exception()

print("Runtime inspection tools available to AI:")
print("  • execute_in_frame() - Run code in the crashed context")
print("  • inspect_object() - Deep dive into any object")
print("  • test_fix() - Test potential fixes with actual data")
print("  • validate_assumption() - Test hypotheses about the crash")
print("  • trace_variable() - See variable values through the stack\n")

# Example: Complex nested data structure error
print("Simulating a complex data access error...")
print("-" * 40)

def process_user_data(user_data):
    """Process user data from API response."""
    # Extract nested data - but structure might be wrong!
    profile = user_data['profile']
    settings = profile['preferences']['notifications']

    # Process notification settings
    email_enabled = settings['email']['enabled']

    return f"Email notifications: {email_enabled}"

# API response with different structure than expected
api_response = {
    'profile': {
        'name': 'Alice',
        'preferences': {
            # Missing 'notifications' key - only has 'privacy'
            'privacy': {
                'public': False
            }
        }
    },
    'metadata': {
        'last_updated': '2024-01-15'
    }
}

print("Processing API response:", api_response)
print()

# This will crash and trigger AI debugging with runtime inspection tools
result = process_user_data(api_response)
print("Result:", result)  # Never reached