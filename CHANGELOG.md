# Changelog

All notable changes to ConnectOnion will be documented in this file.

## [Unreleased]

### 🎉 Major Features

#### FileTools Refactor - Claude Code-style File Operations
- **NEW**: `FileTools` class with read-before-edit tracking and permission control
- **Read-Before-Edit Validation**: Prevents edits without prior file reads
- **Stale Read Detection**: MD5 hash snapshots detect external file changes
- **Permission Modes**: `write` (full access) and `read` (read-only) modes
- **Simplified write()**: Now a pure function for creating NEW files only

### 🔧 Improvements

#### File Operations Architecture
- **Organized Structure**: Moved to `useful_tools/file_tools/` folder (like `browser_tools` pattern)
- **Consistent Naming**: All files match function names (`read.py`, `edit.py`, `write.py`, `glob.py`, `grep.py`)
- **Simplified write()**: Removed DiffWriter dependency, reduced from 122 to 52 lines
- **write() Semantic**: Enforces new-file-only, returns error if file exists (guides agents to use `edit()`)
- **No agent Parameter**: write() no longer requires agent parameter

#### API Changes
```python
# Old way - separate tools
from connectonion.useful_tools import read_file, write_file, edit_file

# New way - unified class with state tracking
from connectonion.useful_tools import FileTools

ft = FileTools()  # Full access with read-before-edit
ft = FileTools(permission="read")  # Read-only mode
```

#### Safety Features
- **MD5 Snapshots**: More reliable than timestamps for detecting file changes
- **Atomic Multi-Edit**: All edits succeed or none applied
- **Auto Parent Dirs**: write() creates parent directories automatically
- **Clear Error Messages**: Helpful guidance when operations fail

### 🧪 Testing

#### Comprehensive Test Coverage
- **27 Tests**: Cover all file operations and edge cases
- **Test Coverage**:
  - ✅ Read offset/limit functionality
  - ✅ Edit uniqueness validation
  - ✅ Multi-edit atomic operations
  - ✅ Write preventing overwrites
  - ✅ Glob patterns and max results
  - ✅ Grep modes (files/content/count)
  - ✅ FileTools validation and stale reads
  - ✅ Permission enforcement
  - ✅ Integration scenarios

### 📚 Documentation

#### New Documentation
- **file_tools/README.md**: Comprehensive documentation of architecture
- **docs-site/file_tools.md**: User-facing documentation with examples
- **Updated useful-tools.md**: Added FileTools to tool reference

#### Usage Examples
- File editing agent with safety
- Read-only documentation agent
- Code generation agent (creates new files)

### 🗑️ Breaking Changes

#### Removed Features
- **Removed**: DiffWriter from write() function
- **Changed**: write() now returns error if file exists (instead of overwriting)
- **Migration**: Use `edit()` or `multi_edit()` to modify existing files

### 📁 File Structure

```
connectonion/useful_tools/file_tools/
├── __init__.py         → Exports FileTools class and functions
├── file_tools.py       → FileTools class (wrapper with state tracking)
├── read.py             → read_file() function
├── edit.py             → edit() function
├── multi_edit.py       → multi_edit() function
├── write.py            → write() function (simplified, no DiffWriter)
├── glob.py             → glob() function
├── grep.py             → grep() function
└── README.md           → Comprehensive documentation
```

### 🚀 Impact

- **Better Safety**: Read-before-edit validation prevents stale edits
- **Simpler API**: write() is now a pure function without DiffWriter complexity
- **Cleaner Semantics**: write() for new files, edit() for modifications
- **Agent-Friendly**: Clear error messages guide agents to correct operations
- **Backward Compatible**: Individual functions still available without FileTools wrapper

### 💭 Philosophy

> "Keep simple things simple, make complicated things possible"

This refactor embodies our core philosophy by:
- Making write() simpler (removed DiffWriter)
- Making file operations safer (read-before-edit, stale-read detection)
- Providing flexibility (permission modes, standalone functions)

---

## [0.1.9] - 2025-10-05

### 🎉 New Features

#### Simplified API Key Setup Flow
- **Reduced Options**: Streamlined from 4 to 3 choices for better UX
- **Universal Authentication**: All users now receive `OPENONION_API_KEY` automatically in `.env`
- **Default Free Tokens**: "Skip" option is now default, providing 10k free tokens ($0.1 credit)
- **Generous Onboarding**: Removed purchase complexity - everyone gets started with free tokens

#### Token Allocation
- **BYO Key**: Enter your own API key + get free OpenOnion tokens as bonus
- **Star GitHub**: $1 credit (100k tokens) for starring the repository
- **Skip (Default)**: $0.1 credit (10k tokens) automatically - no action required

### 🔧 Improvements

#### Developer Experience
- **Better Error Messages**: TUI-friendly formatting with clear command options
- **Improved `co auth` Errors**: Shows both `co init` and `co create` options side-by-side
- **Cleaner Flow**: Authenticate before `.env` creation to guarantee key inclusion
- **Scannable UI**: Rich markup for better terminal readability

### 🗑️ Removed

#### Removed Features
- **Managed Keys Purchase Flow**: Removed complex "ConnectOnion credits" purchase option
- **Result**: -85 lines of code (122 deleted, 37 added)

### 📁 File Changes

```
Modified Files:
├── connectonion/cli/commands/auth_commands.py (improved error messages)
├── connectonion/cli/commands/init.py (universal authentication)
├── connectonion/cli/commands/project_cmd_lib.py (simplified menu)
├── setup.py (version bump to 0.1.9)
└── connectonion/__init__.py (version bump to 0.1.9)
```

### 🚀 Impact

- **Better UX**: Default option is now "Skip" with free tokens
- **More Generous**: Everyone gets `OPENONION_API_KEY` automatically
- **Cleaner Codebase**: Removed 60+ lines of purchase flow complexity
- **Faster Onboarding**: Less decision fatigue, simpler choices

### 💭 Philosophy

> "Keep simple things simple, make complicated things possible"

This release embodies our core philosophy by removing unnecessary complexity while ensuring everyone has access to the platform.

---

## [0.0.4] - 2025-09-05

### 🎉 New Features

#### CLI Browser Integration  
- **NEW**: Browser automation commands via `-b` flag with natural language support
- **Screenshot Command**: Use `co -b "screenshot example.com save to screenshot.png"` for quick captures
- **Device Presets**: Built-in viewport sizes for iPhone, iPad, desktop testing
- **AI-Powered**: Natural language processing for intuitive command interpretation

#### Automatic Environment Loading
- **Auto .env Loading**: Agent class now automatically loads environment variables on initialization
- **Seamless Setup**: API keys from `co init` are automatically available to Agents
- **No Manual Loading**: Removed need for manual `load_dotenv()` calls in user code

### 🐛 Bug Fixes

#### Model Configuration
- **Fixed**: Corrected default model from invalid "gpt-5-mini" to "gpt-4o-mini"
- **Impact**: Prevents 404 errors when using default Agent configuration

### 📚 Documentation & Examples

#### New Documentation
- Browser CLI feature documentation in `/docs/cli-browser.md`
- Browser agent example with natural language processing
- Updated CLI documentation with browser commands

#### New Examples
- `examples/browser-agent/` - Browser automation with AI agent
- Simplified implementation removing over-engineering

### 🔧 Technical Improvements

#### Code Quality
- **Reduced Complexity**: Removed excessive try-catch blocks and if-else chains
- **AI-First Design**: Delegated command interpretation to AI instead of hard-coded logic
- **Cleaner Architecture**: Simplified browser_utils.py using Agent pattern

#### Testing
- Comprehensive test suite for CLI browser feature (28 tests)
- Updated test mocks for new Agent-based implementation

### 📁 File Changes

```
New Files:
├── connectonion/cli/browser_utils.py
├── connectonion/cli/prompts/browser_agent.md
├── docs/cli-browser.md
├── tests/test_cli_browser.py
└── examples/browser-agent/

Modified Files:
├── connectonion/agent.py (auto .env loading, model fix)
├── connectonion/cli/main.py (added -b flag)
└── setup.py (version bump)
```

## [0.2.0] - 2025-07-28

### 🎉 Major Features Added

#### Function-Based Tools
- **NEW**: Functions can now be used directly as tools without inheriting from Tool class
- **Automatic Conversion**: `create_tool_from_function()` converts regular Python functions to Agent-compatible tools
- **Smart Schema Generation**: Type hints automatically become OpenAI function calling schemas
- **Docstring Integration**: Function docstrings become tool descriptions
- **Parameter Handling**: Supports required and optional parameters with proper type mapping

#### System Prompts
- **NEW**: `system_prompt` parameter added to Agent constructor
- **Personality Control**: Define agent role, tone, and behavior through system prompts
- **Default Prompt**: Sensible default provided if no custom prompt specified
- **Examples**: Multiple personality examples showing different use cases

#### Enhanced Developer Experience
- **Simplified API**: Create agents with just functions - no class inheritance needed
- **Type Safety**: Better return type handling (automatic string conversion)
- **Error Handling**: More robust tool execution error management
- **Backwards Compatible**: Old Tool class approach still fully supported

### 📚 Documentation & Examples

#### New Examples
- `examples/quick_start.py` - Minimal setup example
- `examples/basic_example.py` - Comprehensive feature demonstration  
- `examples/advanced_example.py` - Production-ready patterns
- `examples/interactive_chat.py` - Terminal chat interface
- `examples/personality_examples.py` - Different agent personalities
- `examples/README.md` - Complete examples documentation

#### Enhanced Documentation
- Updated main README with function-based approach
- System prompt best practices
- Migration guide from class-based to function-based tools
- Complete API reference updates

### 🧪 Testing Improvements

#### New Test Coverage
- Function-to-tool conversion tests
- System prompt functionality tests
- Mixed tool usage tests (functions + classes)
- Error handling and type conversion tests

#### Test Infrastructure
- `tests/conftest.py` - Shared fixtures and configuration
- `tests/unit/test_tools_comprehensive.py` - Complete tool testing
- `tests/integration/test_agent_workflows.py` - End-to-end workflows
- `tests/performance/test_benchmarks.py` - Performance benchmarks
- `tests/utils/mock_helpers.py` - Testing utilities
- `pytest.ini` - Test configuration with markers

### 🔧 Technical Improvements

#### Agent Class Enhancements
- Added `system_prompt` parameter and storage
- Improved tool processing pipeline
- Better type conversion for tool results
- Enhanced error handling and reporting

#### Tool System Refactor
- `create_tool_from_function()` utility function
- Automatic type mapping (str→string, int→integer, etc.)
- Dynamic tool attribute attachment
- Preserved backwards compatibility with Tool classes

#### Code Quality
- Enhanced type hints throughout codebase
- Improved error messages and debugging
- Better separation of concerns
- More robust error handling

### 📁 File Structure Changes

```
New Files Added:
├── examples/
│   ├── README.md
│   ├── quick_start.py
│   ├── advanced_example.py  
│   ├── interactive_chat.py
│   ├── personality_examples.py
│   └── .env (copied for convenience)
├── tests/
│   ├── conftest.py
│   ├── pytest.ini
│   ├── unit/test_tools_comprehensive.py
│   ├── integration/test_agent_workflows.py
│   ├── performance/test_benchmarks.py
│   └── utils/mock_helpers.py
├── CHANGELOG.md (this file)
└── TESTING_SUMMARY.md

Modified Files:
├── connectonion/
│   ├── __init__.py (updated exports)
│   ├── agent.py (system_prompt support)
│   └── tools.py (function conversion utility)
├── tests/test_agent.py (updated tests)
├── requirements.txt (added python-dotenv)
└── README.md (comprehensive updates)
```

### 🚀 Usage Examples

#### Before (v0.1.0)
```python
from connectonion import Agent
from connectonion.tools import Calculator

agent = Agent("assistant", tools=[Calculator()])
result = agent.input("What is 2+2?")
```

#### After (v0.2.0)
```python
from connectonion import Agent

def calculate(expression: str) -> float:
    """Perform mathematical calculations."""
    return eval(expression)

agent = Agent(
    name="assistant",
    system_prompt="You are a helpful math tutor.",
    tools=[calculate]
)
result = agent.input("What is 2+2?")
```

### ⚡ Performance & Reliability

- **Faster Tool Loading**: Function-based tools load more efficiently
- **Better Error Recovery**: Enhanced error handling in tool execution
- **Type Safety**: Automatic type conversion prevents API errors
- **Memory Efficiency**: Reduced overhead from function-based approach

### 🔄 Migration Guide

#### From Tool Classes to Functions

**Old Way:**
```python
class MyTool(Tool):
    def __init__(self):
        super().__init__("my_tool", "Does something")
    
    def run(self, param: str) -> str:
        return f"Result: {param}"
    
    def get_parameters_schema(self):
        return {"type": "object", "properties": {"param": {"type": "string"}}}

agent = Agent("test", tools=[MyTool()])
```

**New Way:**
```python
def my_tool(param: str) -> str:
    """Does something."""
    return f"Result: {param}"

agent = Agent("test", tools=[my_tool])
```

### 📊 Statistics

- **Lines of Code**: ~500 lines added
- **Test Coverage**: 90%+ across all components  
- **Examples**: 5 comprehensive examples added
- **Documentation**: 400+ lines of new documentation
- **Backwards Compatibility**: 100% maintained

---

## [0.1.0] - 2025-07-28

### Initial Release

- Basic Agent functionality with OpenAI integration
- Tool class system with built-in Calculator, CurrentTime, and ReadFile tools  
- Automatic behavior tracking and JSON persistence
- History management and reporting
- Basic error handling and type validation