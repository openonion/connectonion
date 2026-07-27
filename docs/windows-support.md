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

### Problem 4: Subprocess Encoding (GBK/cp936)

**Before:**
```
UnicodeDecodeError: 'gbk' codec can't decode byte 0x?? in position ...:
illegal multibyte sequence
```

**Why it failed:**
- Chinese/Japanese/Korean Windows uses a legacy locale codepage (GBK/cp936, cp932) as the default text encoding — **not UTF-8**
- `subprocess` with `text=True` but no explicit `encoding` decodes a child process's stdout/stderr with that codepage
- When `co ai` (or the `Shell`/background tools) ran a command that emitted UTF-8/emoji output, the reader crashed with `UnicodeDecodeError` — and a child printing emoji to a GBK console raised `UnicodeEncodeError`
- Note: v0.3.5 fixed **file** I/O; this was the remaining **subprocess pipe** gap (see issue #230)

**After:**
```python
# All subprocess calls pin UTF-8 and never crash on a stray byte
subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", ...)

# Command runners also force child processes to emit UTF-8 regardless of codepage
env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
```

**Fixed in:**
- `useful_tools/shell.py`, `useful_tools/bash.py`, `useful_tools/read_file.py`
- `cli/co_ai/tools/background.py` (the `co ai` background runner)
- `cli/co_ai/context.py`, `cli/co_ai/commands/undo.py` (git subprocess calls)

### Problem 5: Console Output Codepage

**Before:**
```
UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f680' ...
```

**Why it failed:**
- The `co` CLI prints emoji and box-drawing characters (Rich output). On a GBK/cp1252 console, `sys.stdout` uses that codepage, so any non-encodable character crashes the command — including when `co`/`co ai` is driven through a pipe by another tool.

**After:**
```python
# connectonion/cli/main.py — reconfigure the CLI's own streams before anything prints
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
```

`co ai` is a subcommand of the `co` app, so it inherits this reconfigure automatically.

### Comprehensive UTF-8 coverage

Beyond the specific traceback fixes above, a full audit now pins **every** text-mode
file read/write in the package to `encoding="utf-8"` (`open()`, `Path.read_text()`,
`Path.write_text()`) — CSV contact/email exports, `.env`/keys files, session storage,
memory JSON, eval YAML, skills manifests, prompt assembly, and browser-daemon
pid/lock files. Binary I/O (images, tarballs, raw fds) is intentionally left alone.
The three encoding directions — **file I/O**, **subprocess pipes**, and **console
output** — are now all UTF-8 regardless of the Windows locale codepage.

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
4. Creates config → `C:\Users\王小明\.co\host.yaml` (UTF-8)
5. Skips chmod (Windows doesn't support it)
6. Authenticates with OpenOnion API
7. Saves API token → `C:\Users\王小明\.co\keys.env` (UTF-8)

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
type %USERPROFILE%\.co\host.yaml

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
- `connectonion/network/trust/factory.py` - Trust policy handling
- `connectonion/network/trust/tools.py` - Trust verification

### Test Coverage

New tests in `tests/unit/test_windows_compat.py`:
- ✅ UTF-8 encoding with Chinese usernames
- ✅ UTF-8 encoding with Arabic usernames
- ✅ Paths with spaces (e.g., "John Smith")
- ✅ Console logging with UTF-8 characters and emojis
- ✅ chmod skipped on Windows, applied on Unix
- ✅ Path comparison with `.resolve()`
- ✅ Round-trip encoding (write → read → same content)
- ✅ Subprocess pipe decodes UTF-8/emoji even when the locale reports GBK/cp936
- ✅ Subprocess survives non-UTF-8 bytes (`errors="replace"`, no crash)

A real Windows E2E job (`.github/workflows/tests.yml` → `windows-e2e`) also runs the
shipped `Shell` + background runner under an actual `chcp 936` (GBK) console.

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

**A:** Python 2.7 is not supported. ConnectOnion requires Python 3.10+.

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
