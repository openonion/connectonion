# CLI Integration Tests

Integration tests for ConnectOnion CLI commands to verify bug fixes for issues #28 and #29.

## Setup

Make all test scripts executable (already done):
```bash
chmod +x tests/cli/*.sh
```

## Available Tests

### 1. BYO API Key Flow (Issue #29) ✅ AUTOMATED

Tests the "Bring Your Own API Key" initialization flow using CLI parameters.

**Usage:**
```bash
./tests/cli/test_byo_api_key.sh <YOUR_OPENAI_API_KEY>
```

**Example:**
```bash
./tests/cli/test_byo_api_key.sh sk-proj-xxxxx
```

**What it tests:**
- `co init --key <API_KEY> --template minimal`
- Verifies no `agent_email referenced before assignment` error
- Checks authentication completes successfully

### 2. Auth Command ✅ AUTOMATED

Tests the `co auth` command after initialization.

**Usage:**
```bash
./tests/cli/test_auth.sh
```

**What it tests:**
- `co init --yes --template minimal` (creates ~/.co)
- `co auth` (authenticates with backend)
- Verifies no `agent_email referenced before assignment` error
- Checks AGENT_EMAIL is saved to .env

### 3. Star for Credits Flow (Issue #28) ⚠️ MANUAL

Tests the "Star for $1 credit" initialization flow (requires user interaction).

**Usage:**
```bash
./tests/cli/test_star_credits.sh
```

**What it tests:**
- `co init` with interactive star for credits option
- User must manually select star option and confirm
- Verifies no `agent_email referenced before assignment` error
- Checks AGENT_EMAIL and OPENONION_API_KEY in .env

## Cleanup

Clean up test environment (removes ~/.co and /tmp/connectonion-test):

```bash
./tests/cli/cleanup.sh
```

**Note:** Each test automatically runs cleanup before starting.

## Test Environment

- All tests run in `/tmp/connectonion-test` directory
- Global ~/.co folder is removed before each test
- Tests are isolated and won't affect your working directory

## Quick Test Run

To quickly test the bug fix, use the BYO API key test:

```bash
# Export your API key (won't be logged)
export TEST_API_KEY="sk-proj-xxxxx"

# Run the automated test
./tests/cli/test_byo_api_key.sh "$TEST_API_KEY"
```

## Expected Behavior

**Before Fix (v0.1.10):**
```
Traceback (most recent call last):
  ...
  File ".../auth_commands.py", line 130, in authenticate
    env_lines.append(f"AGENT_EMAIL={agent_email}\n")
UnboundLocalError: local variable 'agent_email' referenced before assignment
```

**After Fix (v0.1.11+):**
```
✅ Authentication successful!
✓ AGENT_EMAIL found in .env
✓ OPENONION_API_KEY found in .env
Test PASSED!
```

## Test Results Format

Each test outputs:
- ✅ Test PASSED - No errors, authentication successful
- ❌ Test FAILED - Error occurred, check output
- ⚠️ Warning - Test passed but some checks failed
