#!/usr/bin/env python3
"""Quick test of the browser CLI feature."""

import subprocess
import sys
from pathlib import Path

def run_command(cmd):
    """Run a CLI command and return output."""
    print(f"\n📋 Testing: {cmd}")
    result = subprocess.run(
        cmd, 
        shell=True, 
        capture_output=True, 
        text=True
    )
    print(f"   Exit code: {result.returncode}")
    if result.stdout:
        print(f"   Output: {result.stdout.strip()}")
    if result.stderr:
        print(f"   Error: {result.stderr.strip()}")
    return result

def main():
    """Test browser CLI functionality."""
    print("🧪 Testing ConnectOnion Browser CLI Feature")
    print("=" * 50)
    
    # Test 1: Help message
    print("\n1️⃣ Testing help/usage:")
    run_command("co --help | grep browser")
    
    # Test 2: Invalid command (no URL)
    print("\n2️⃣ Testing invalid command (no URL):")
    run_command('co -b "screenshot"')
    
    # Test 3: Valid command format (will fail if no server)
    print("\n3️⃣ Testing valid command format:")
    run_command('co -b "screenshot localhost:3000"')
    
    # Test 4: With output path
    print("\n4️⃣ Testing with output path:")
    run_command('co -b "screenshot example.com save to /tmp/test.png"')
    
    # Test 5: With device size
    print("\n5️⃣ Testing with device preset:")
    run_command('co -b "screenshot example.com size iphone"')
    
    # Test 6: Full command
    print("\n6️⃣ Testing full command:")
    run_command('co -b "screenshot example.com save to /tmp/test-iphone.png size iphone"')
    
    print("\n" + "=" * 50)
    print("✅ Test script complete!")
    print("\nNote: Commands may fail if:")
    print("  - Playwright is not installed")
    print("  - Target URLs are not reachable")
    print("  - Permission issues with output paths")

if __name__ == "__main__":
    main()