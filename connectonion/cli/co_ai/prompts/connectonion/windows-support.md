# Windows Support

ConnectOnion v0.3.5+ fully supports Windows, including users with non-ASCII usernames (Chinese, Arabic, Russian, Korean, Japanese, etc.) and paths containing spaces.

## What Works on Windows

✅ **Non-ASCII usernames**: `C:\Users\王小明\.co\`
✅ **Arabic usernames**: `C:\Users\محمد\.co\`
✅ **Spaces in paths**: `C:\Users\John Smith\.co\`
✅ **All CLI commands**: `co init`, `co create`, `co auth`, `co reset`
✅ **Crypto key operations**: Ed25519 key generation, saving, and loading
✅ **Agent logging**: Console output with UTF-8 characters and emojis
✅ **File operations**: Config files, .env files, recovery phrases

## What Was Fixed (v0.3.5)

### Problem 1: UTF-8 Encoding Errors

**Before (v0.3.4 and earlier):**
```
Traceback (most recent call last):
  File "connectonion\address.py", line 159, in save
    recovery_file.write_text(address_data["seed_phrase"])
UnicodeEncodeError: 'charmap' codec can't encode characters in position 0-2:
character maps to <undefined>
```

**Why it failed:**
- Windows default encoding is NOT UTF-8 (usually `cp1252` or locale-specific)
- File paths like `C:\Users\王小明\.co\keys\recovery.txt` would fail
- Chinese, Arabic, Russian characters couldn't be written to files

**After (v0.3.5+):**
```python
# All file operations now explicitly use UTF-8
recovery_file.write_text(seed_phrase, encoding='utf-8')  # ✅ Works!
```

**Fixed in 16 locations:**
- `address.py` - Key and recovery file operations
- `console.py` - Log file writing
- `auth_commands.py` - .env and config file operations
- `init.py`, `create.py`, `trust.py`, `reset_commands.py` - All file I/O

### Problem 2: File Permission Errors

**Before (v0.3.4 and earlier):**
```
Traceback (most recent call last):
  File "connectonion\address.py", line 154, in save
    key_file.chmod(0o600)
NotImplementedError: chmod unavailable on this platform
```

**Why it failed:**
- Windows uses ACLs (Access Control Lists), not Unix file permissions
- `os.chmod(0o600)` doesn't work on Windows and raises errors

**After (v0.3.5+):**
```python
# Skip chmod on Windows, apply on Unix/Mac
if sys.platform != 'win32':
    key_file.chmod(0o600)  # ✅ Platform-aware!
```

**Fixed in 4 locations:**
- `address.py` - Key file permissions (2 locations)
- `auth_commands.py` - .env file permissions (2 locations)
- `init.py`, `create.py`, `reset_commands.py` - Keys.env creation

### Problem 3: Path Comparison Bugs

**Before (v0.3.4 and earlier):**
```python
is_global = co_dir == Path.home() / ".co"  # ❌ Fails on Windows!
# C:\Users\User\.co != C:/Users/User/.co (different separators)
```

**After (v0.3.5+):**
```python
is_global = co_dir.resolve() == (Path.home() / ".co").resolve()  # ✅ Works!
# Both normalize to same canonical path
```

## User Journey: Windows with Chinese Username

### Scenario: User "王小明" installing ConnectOnion

```powershell
# 1. Install
pip install connectonion

# 2. Initialize project
co init
```

**What happens internally:**
1. Creates `C:\Users\王小明\.co\` directory
2. Generates Ed25519 keys → Saves to `C:\Users\王小明\.co\keys\agent.key`
3. Writes recovery phrase → `C:\Users\王小明\.co\keys\recovery.txt` (UTF-8)
4. Creates global config → `C:\Users\王小明\.co\config.toml` (UTF-8)
5. Creates project config → `.co\host.yaml` (UTF-8)
6. Skips chmod (Windows doesn't support it)
7. Authenticates with OpenOnion API
8. Saves API token → `C:\Users\王小明\.co\keys.env` (UTF-8)

**Result:** ✅ Everything works perfectly!

## Testing Your Setup

### Verify UTF-8 Support

```python
from pathlib import Path
from connectonion import address

# Generate keys
addr = address.generate()

# Save to home directory
co_dir = Path.home() / ".co"
address.save(addr, co_dir)

# Load back
loaded = address.load(co_dir)

# Verify it matches
assert loaded["address"] == addr["address"]
print("✅ UTF-8 encoding works correctly!")
```

### Check File Contents

```powershell
# View recovery phrase (should show 12 English words)
type %USERPROFILE%\.co\keys\recovery.txt

# View config (should be valid TOML)
type %USERPROFILE%\.co\config.toml

# Check logs (should show UTF-8 characters correctly)
type .co\logs\agent_name.log
```

## Troubleshooting

### Issue: "UnicodeEncodeError" still appearing

**Cause:** Using old version of ConnectOnion
**Solution:**
```powershell
pip install --upgrade connectonion
pip show connectonion  # Should show v0.3.5 or higher
```

### Issue: "NotImplementedError: chmod unavailable"

**Cause:** Using old version of ConnectOnion
**Solution:** Upgrade to v0.3.5+ (same as above)

### Issue: Console shows garbled characters

**Cause:** Windows terminal not set to UTF-8
**Solution:**
```powershell
# Set terminal to UTF-8 (Windows 10+)
chcp 65001

# Or use Windows Terminal (recommended)
# Download from Microsoft Store
```

### Issue: Path comparison not working

**Cause:** Using old version or comparing paths without `.resolve()`
**Solution:** Upgrade to v0.3.5+ which handles path normalization automatically

## Technical Details

### What Changed

| Component | Fix | Impact |
|-----------|-----|--------|
| **File I/O** | Added `encoding='utf-8'` to all `open()`, `.read_text()`, `.write_text()` | Non-ASCII usernames work |
| **Permissions** | Added platform check `if sys.platform != 'win32':` before `chmod()` | No more Windows errors |
| **Path Comparison** | Use `.resolve()` for path equality checks | Handles different path separators |

### Files Modified

- `connectonion/address.py` - Crypto key operations
- `connectonion/console.py` - Logging system
- `connectonion/cli/commands/auth_commands.py` - Authentication
- `connectonion/cli/commands/init.py` - Project initialization
- `connectonion/cli/commands/create.py` - Project creation
- `connectonion/cli/commands/reset_commands.py` - Account reset
- `connectonion/trust.py` - Trust policy handling
- `connectonion/trust_functions.py` - Trust verification

### Test Coverage

New tests in `tests/unit/test_windows_compat.py`:
- ✅ UTF-8 encoding with Chinese usernames
- ✅ UTF-8 encoding with Arabic usernames
- ✅ Paths with spaces (e.g., "John Smith")
- ✅ Console logging with UTF-8 characters and emojis
- ✅ chmod skipped on Windows, applied on Unix
- ✅ Path comparison with `.resolve()`
- ✅ Round-trip encoding (write → read → same content)

## Supported Characters

ConnectOnion now supports ALL Unicode characters in usernames and file paths:

| Language | Example Username | Status |
|----------|------------------|--------|
| Chinese (Simplified) | 王小明 | ✅ |
| Chinese (Traditional) | 王小明 | ✅ |
| Arabic | محمد | ✅ |
| Russian | Иван | ✅ |
| Japanese | 田中 | ✅ |
| Korean | 김철수 | ✅ |
| Hebrew | דוד | ✅ |
| Thai | สมชาย | ✅ |
| Greek | Γιάννης | ✅ |
| Emoji | User🚀 | ✅ |
| Spaces | John Smith | ✅ |
| Mixed | 王User123 | ✅ |

## FAQ

### Q: Do I need to do anything special for non-ASCII usernames?

**A:** No! Just upgrade to v0.3.5+ and everything works automatically.

### Q: Will my existing installation still work after upgrading?

**A:** Yes! The changes are backward compatible. Existing configs and keys will work perfectly.

### Q: What if I'm using Python 2.7?

**A:** Python 2.7 is not supported. ConnectOnion requires Python 3.7+.

### Q: Does this work on Windows 7?

**A:** Yes, but Windows 10 or 11 is recommended for best Unicode support in the terminal.

## Version History

- **v0.3.5** - Full Windows support with UTF-8 encoding and platform-aware chmod
- **v0.3.4** - Partial Windows support (UTF-8 errors with non-ASCII usernames)
- **v0.3.0** - Initial Windows testing

## Contributing

Found a Windows-specific bug? Please report it:
1. Check your ConnectOnion version: `pip show connectonion`
2. Include your Windows version and username type (ASCII/non-ASCII)
3. Share the full error message and traceback
4. Submit an issue at: https://github.com/openonion/connectonion/issues
