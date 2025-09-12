# Authentication & Managed Keys

Zero-configuration LLM access with ConnectOnion's managed keys. Use any LLM model without managing API keys.

## Quick Start (2 minutes)

Get started with managed keys in three simple steps:

### 1. Authenticate Once

```bash
$ co auth
Opening browser for authentication...
✅ Authenticated successfully! Token saved to ~/.co/auth.json
📧 Your email: 0x1234abcd@mail.openonion.ai (activated)
```

### 2. Use Any Model with `co/` Prefix

```python
from connectonion import llm_do

# No API keys needed!
response = llm_do("Hello world!", model="co/gpt-4o")
print(response)  # Works immediately!
```

### 3. That's It!

You now have access to all major LLM models without managing any API keys.

## Your Keys vs Managed Keys

| Aspect | Your Own Keys | Managed Keys (co/) |
|--------|--------------|-------------------|
| **Setup** | Get keys from each provider | One-time `co auth` |
| **Usage** | `model="gpt-4o"` | `model="co/gpt-4o"` |
| **Config** | Set environment variables | None needed |
| **Models** | Limited to your keys | All models instantly |
| **Cost** | Direct provider billing | Usage-based pricing |
| **Team** | Share keys manually | Built-in collaboration |

## How It Works

### The Magic of `co/` Prefix

```python
# Using your own OpenAI key (traditional way)
llm_do("Hello", model="gpt-4o")  # Requires OPENAI_API_KEY

# Using ConnectOnion managed keys (new way)
llm_do("Hello", model="co/gpt-4o")  # Just works!
```

The `co/` prefix tells ConnectOnion to use managed keys from the platform instead of looking for environment variables.

### Behind the Scenes

1. **Authentication**: `co auth` gets a secure token from OpenOnion.ai
2. **Token Storage**: Token saved to `~/.co/auth.json` (encrypted)
3. **Email Activation**: Your agent's email address is activated for sending/receiving
4. **Request Flow**: When you use `co/` prefix, requests go through OpenOnion's proxy
5. **Automatic Refresh**: Tokens refresh automatically when needed

## Available Commands

### Currently Available

#### `co auth` - Authenticate with OpenOnion
```bash
$ co auth

# What happens:
# 1. Opens browser to https://openonion.ai/auth
# 2. You log in with GitHub/Google/Email
# 3. Token is saved locally
# 4. You're ready to use co/ models
```

### Coming Soon

```bash
# Check authentication status and usage
$ co status
✅ Authenticated as: user@example.com
📊 Usage today: 15,234 tokens ($0.31)
💳 Plan: Free tier (84,766 tokens remaining)

# Log out and clear credentials
$ co logout
✅ Logged out successfully

# Configure settings
$ co config set default_model co/claude-3-5-sonnet
✅ Default model updated
```

## Supported Models

All models are available with the `co/` prefix:

### OpenAI Models
```python
llm_do("Hello", model="co/gpt-4o")
llm_do("Hello", model="co/gpt-4o-mini")
llm_do("Hello", model="co/o1-preview")
llm_do("Hello", model="co/o1-mini")
```

### Anthropic Models
```python
llm_do("Hello", model="co/claude-3-5-sonnet")
llm_do("Hello", model="co/claude-3-5-haiku")
llm_do("Hello", model="co/claude-3-opus")
```

### Google Models
```python
llm_do("Hello", model="co/gemini-1.5-pro")
llm_do("Hello", model="co/gemini-1.5-flash")
llm_do("Hello", model="co/gemini-2.0-flash-exp")
```

## Real-World Examples

### Basic Usage

```python
from connectonion import llm_do, Agent

# Simple completion
response = llm_do("Explain quantum computing", model="co/gpt-4o")

# With structured output
from pydantic import BaseModel

class Summary(BaseModel):
    title: str
    key_points: list[str]
    complexity: int

result = llm_do(
    "Summarize this article about AI...",
    model="co/claude-3-5-sonnet",
    output=Summary
)
print(result.key_points)
```

### Using with Agents

```python
from connectonion import Agent

# Agent with managed keys
agent = Agent(
    name="assistant",
    model="co/gpt-4o",  # No API key needed!
    system_prompt="You are a helpful assistant"
)

response = agent.input("Help me write a Python function")
```

### Model Comparison

```python
# Compare responses from different models
models = ["co/gpt-4o", "co/claude-3-5-sonnet", "co/gemini-1.5-pro"]

for model in models:
    response = llm_do("What's the meaning of life?", model=model)
    print(f"{model}: {response[:100]}...")
```

### Mixing Keys

```python
# Use your own key for development
dev_response = llm_do("Test prompt", model="gpt-4o-mini")

# Use managed keys for production
prod_response = llm_do("Production prompt", model="co/gpt-4o")
```

## Developer Workflows

### Development Pattern

```python
import os
from connectonion import llm_do

def get_model():
    """Smart model selection based on environment."""
    if os.getenv("OPENAI_API_KEY"):
        return "gpt-4o"  # Use own key if available
    else:
        return "co/gpt-4o"  # Fall back to managed

response = llm_do("Hello", model=get_model())
```

### Cost Optimization

```python
# Use cheaper models for development/testing
DEV_MODEL = "co/gpt-4o-mini"  # Cheaper
PROD_MODEL = "co/gpt-4o"       # Better

model = DEV_MODEL if debug else PROD_MODEL
```

### Testing Multiple Models

```python
def test_all_models(prompt):
    """Test prompt across all providers."""
    models = {
        "OpenAI": "co/gpt-4o",
        "Anthropic": "co/claude-3-5-sonnet",
        "Google": "co/gemini-1.5-pro"
    }
    
    results = {}
    for provider, model in models.items():
        try:
            results[provider] = llm_do(prompt, model=model)
        except Exception as e:
            results[provider] = f"Error: {e}"
    
    return results
```

## Migration Guide

### From Environment Variables

**Before (with environment variables):**
```python
# .env file
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Python code
import os
from connectonion import llm_do

# Had to manage multiple keys
response = llm_do("Hello", model="gpt-4o")
```

**After (with managed keys):**
```python
# No .env needed!
from connectonion import llm_do

# Just add co/ prefix
response = llm_do("Hello", model="co/gpt-4o")
```

### Gradual Migration

```python
def smart_llm_do(prompt, preferred_model="gpt-4o"):
    """Gradually migrate to managed keys."""
    try:
        # Try with your own key first
        return llm_do(prompt, model=preferred_model)
    except Exception:
        # Fall back to managed keys
        return llm_do(prompt, model=f"co/{preferred_model}")
```

### Team Collaboration

```python
# Everyone on the team just needs to run:
# $ co auth

# Then everyone can use the same code:
agent = Agent("shared_bot", model="co/gpt-4o")

# No more "it works on my machine" issues!
```

## Error Handling

### Common Errors and Solutions

```python
try:
    response = llm_do("Hello", model="co/gpt-4o")
except Exception as e:
    if "Not authenticated" in str(e):
        print("Run 'co auth' to authenticate first")
    elif "Token expired" in str(e):
        print("Run 'co auth' to refresh your token")
    elif "Rate limit" in str(e):
        print("Rate limited. Try again in a few seconds")
    else:
        print(f"Unexpected error: {e}")
```

### Error Messages

| Error | Meaning | Solution |
|-------|---------|----------|
| `Not authenticated` | No auth token found | Run `co auth` |
| `Token expired` | Auth token is too old | Run `co auth` again |
| `Rate limit exceeded` | Too many requests | Wait and retry |
| `Model not found` | Invalid model name | Check supported models |
| `Network error` | Connection issues | Check internet connection |

## Security & Privacy

### Token Storage

- **Location**: `~/.co/auth.json`
- **Encryption**: Tokens are encrypted at rest
- **Permissions**: File is readable only by you (600)
- **Expiration**: Tokens expire after 30 days

### Data Handling

- **Requests**: Proxied through OpenOnion.ai servers
- **Logging**: Optional request logging (can be disabled)
- **Storage**: No prompt/response storage by default
- **Compliance**: SOC2 Type II compliant infrastructure

### Best Practices

1. **Don't commit tokens**: Add `~/.co/` to `.gitignore`
2. **Use environment-specific models**: Different models for dev/prod
3. **Monitor usage**: Check usage regularly with `co status` (coming soon)
4. **Rotate tokens**: Re-authenticate monthly for security

## Troubleshooting

### Authentication Issues

**Browser doesn't open:**
```bash
# Manually open the URL
$ co auth --no-browser
Visit: https://openonion.ai/auth?token=abc123...
```

**Token not saving:**
```bash
# Check permissions
$ ls -la ~/.co/
# Should show drwx------ (700) permissions

# Fix permissions if needed
$ chmod 700 ~/.co
$ chmod 600 ~/.co/auth.json
```

### Connection Issues

**Timeout errors:**
```python
# Increase timeout
response = llm_do(
    "Hello", 
    model="co/gpt-4o",
    timeout=60  # seconds
)
```

**Proxy issues:**
```bash
# If behind corporate proxy
$ export HTTPS_PROXY=http://proxy.company.com:8080
$ co auth
```

## API Reference

### Authentication Endpoint

```
POST https://api.openonion.ai/v1/auth
```

### Request Format

When using `co/` prefix, requests are automatically formatted:

```python
# Your code
llm_do("Hello", model="co/gpt-4o")

# What gets sent
{
  "model": "gpt-4o",
  "messages": [...],
  "auth_token": "your_token_here"
}
```

### Rate Limits

| Plan | Requests/min | Tokens/day |
|------|--------------|------------|
| Free | 20 | 10,000 |
| Pro | 100 | 100,000 |
| Team | 500 | 1,000,000 |

## Frequently Asked Questions

**Q: Is this free?**
A: Yes! Free tier includes 10,000 tokens/day. Paid plans available for higher usage.

**Q: Can I use my own keys alongside managed keys?**
A: Yes! Use `model="gpt-4o"` for your keys, `model="co/gpt-4o"` for managed keys.

**Q: What happens to my prompts?**
A: Prompts are proxied through OpenOnion servers but not stored by default. You can enable logging for debugging.

**Q: Can I use this in production?**
A: Yes! The platform is designed for production use with 99.9% uptime SLA for paid plans.

**Q: How do I monitor costs?**
A: Use `co status` (coming soon) or visit dashboard.openonion.ai

**Q: Can my team share access?**
A: Team features are coming soon. For now, each developer needs their own account.

**Q: What if OpenOnion is down?**
A: You can always fall back to your own API keys by removing the `co/` prefix.

## Getting Help

- **Documentation**: https://docs.connectonion.com/auth
- **Issues**: https://github.com/connectonion/connectonion/issues
- **Discord**: https://discord.gg/connectonion
- **Email**: support@openonion.ai

## Next Steps

1. Run `co auth` to get started
2. Try the [Quick Start examples](#quick-start-2-minutes)
3. Explore [all available models](#supported-models)
4. Join our [Discord community](https://discord.gg/connectonion)

---

*Note: This feature is currently in beta. Additional commands (`co status`, `co logout`, `co config`) are coming soon.*