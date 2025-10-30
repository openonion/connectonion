"""Test that minimal template loads .env correctly"""
import sys
from pathlib import Path

# Check minimal template has load_dotenv
template_path = Path("../connectonion/cli/templates/minimal/agent.py")

print("Testing minimal template .env loading...")
print("=" * 60)

with open(template_path) as f:
    content = f.read()
    
    has_import = "from dotenv import load_dotenv" in content
    has_call = "load_dotenv()" in content
    
    print(f"✅ Template: {template_path.name}")
    print(f"✅ Has import: {has_import}")
    print(f"✅ Has call: {has_call}")
    
    if has_import and has_call:
        print("\n✅ Minimal template will load .env file correctly!")
    else:
        print("\n❌ Template missing load_dotenv!")

print("=" * 60)
