"""Test that .env file loads correctly for Gemini API"""
import os
import sys
from pathlib import Path

# Add parent to path to test local code
sys.path.insert(0, str(Path(__file__).parent.parent))

print("Testing .env file loading for Gemini API...")
print("=" * 60)

# Test 1: Check if dotenv is imported in core modules
print("\n1. Checking if core modules have load_dotenv():")
with open("../connectonion/agent.py") as f:
    agent_content = f.read()
    has_dotenv = "load_dotenv()" in agent_content
    print(f"   agent.py: {'✅' if has_dotenv else '❌'}")

with open("../connectonion/llm_do.py") as f:
    llm_do_content = f.read()
    has_dotenv = "load_dotenv()" in llm_do_content
    print(f"   llm_do.py: {'✅' if has_dotenv else '❌'}")

# Test 2: Check .env file exists and has API key
print("\n2. Checking .env file:")
env_file = Path(".env")
if env_file.exists():
    print(f"   .env exists: ✅")
    with open(env_file) as f:
        env_content = f.read()
        has_gemini = "GEMINI_API_KEY" in env_content
        has_google = "GOOGLE_API_KEY" in env_content
        print(f"   Has GEMINI_API_KEY: {'✅' if has_gemini else '❌'}")
        print(f"   Has GOOGLE_API_KEY (backward compat): {'✅' if has_google else '❌'}")
else:
    print(f"   .env exists: ❌")

# Test 3: Import and check environment variables are loaded
print("\n3. Testing environment variable loading:")
from dotenv import load_dotenv
load_dotenv()

gemini_key = os.getenv("GEMINI_API_KEY")
google_key = os.getenv("GOOGLE_API_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

print(f"   GEMINI_API_KEY: {'✅ Found' if gemini_key else '❌ Not found'}")
print(f"   GOOGLE_API_KEY (backward compat): {'✅ Found' if google_key else '❌ Not found'}")
print(f"   OPENAI_API_KEY: {'✅ Found' if openai_key else '❌ Not found'}")

# Test 4: Test Agent creation with gemini model  
print("\n4. Testing Agent creation with Gemini model (without calling agent.input()):")
try:
    from connectonion import Agent
    
    # This should work if .env is loaded correctly
    agent = Agent(
        name="gemini_test",
        model="gemini-1.5-flash"
    )
    print("   Agent created: ✅")
    print(f"   Model: {agent.llm.model}")
    
except ValueError as e:
    error_msg = str(e)
    if "API key required" in error_msg:
        print(f"   Agent created: ❌ - {error_msg}")
        print("   → This means .env file is not being loaded!")
    else:
        print(f"   Agent created: ❌ - {error_msg}")
except Exception as e:
    print(f"   Agent created: ⚠️  - {type(e).__name__}: {e}")

print("\n" + "=" * 60)
print("Test complete!")
