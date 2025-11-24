#!/usr/bin/env python3
"""Test the new inline @ autocomplete."""

from connectonion import input_with_at

print("=== Testing Inline @ Autocomplete ===\n")
print("Instructions:")
print("  1. Type some text, then press @")
print("  2. Inline dropdown appears below (max 5 items)")
print("  3. Continue typing to filter files")
print("  4. Arrow keys to navigate")
print("  5. Tab/Enter to accept, ESC to cancel")
print()

result = input_with_at("> ")
print(f"\nYou entered: {result}")
