"""
Debug script to list available Gemini models and their supported methods.
"""

"""
LLM-Note: Debug script for Gemini model discovery

What it tests:
- Manual debug script (not pytest) to list available Gemini models
- Uses google.generativeai API to enumerate models and their capabilities
- Loads API key from tests/.env

Components under test:
- Google Gemini API model discovery
"""
import os
import google.generativeai as genai
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from tests/.env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY or GOOGLE_API_KEY not found in environment.")
else:
    genai.configure(api_key=api_key)
    print("--- Available Gemini Models ---")
    for m in genai.list_models():
        print(f"- Model: {m.name}")
        print(f"  Supported Methods: {m.supported_generation_methods}")
        print("-" * 10)
