# Authentication & Managed Keys

Zero-configuration LLM access with ConnectOnion's managed keys. Use any LLM model without managing API keys.

## Quick Start (2 minutes)

Get started with managed keys in three simple steps:

### 1. Authenticate Once

```bash
$ co auth
📂 Using global ConnectOnion keys (~/.co)
✓ Saved to ~/.co/keys.env
✓ Saved to .env
✓ Authenticated (Balance: $0.10)
```

`co auth` signs in with your local ConnectOnion identity. If you do not have keys yet, the CLI creates `~/.co/keys/` automatically, authenticates with OpenOnion, then stores `OPENONION_API_KEY` where the runtime can load it.

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

1. **Identity**: `co auth` loads or creates an Ed25519 agent keypair in `.co/keys/` or `~/.co/keys/`.
2. **Signed auth**: the CLI signs a timestamped authentication message with that keypair.
3. **Token storage**: the backend returns an API token, saved as `OPENONION_API_KEY` in `~/.co/keys.env` and, for projects, `.env`.
4. **Email activation**: the response includes the agent email (`AGENT_EMAIL`) used by supported integrations.
5. **Request flow**: when you use the `co/` model prefix, ConnectOnion reads `OPENONION_API_KEY` and routes the request through OpenOnion's proxy.

## Available Commands

### `co auth` — get or refresh managed-key access

```bash
co auth
```

What it does:

1. Loads your local project identity from `.co/keys/`, or falls back to `~/.co/keys/`.
2. Creates a keypair automatically if neither exists.
3. Signs a short authentication message with that identity.
4. Calls the OpenOnion auth API.
5. Saves `OPENONION_API_KEY`, `AGENT_EMAIL`, and `AGENT_ADDRESS` to the appropriate env files.

### `co status` — check account and deployment status

```bash
co status
```

Use this after `co auth` to confirm the CLI can load your API key and reach the backend.

### `co keys` — inspect local credentials

```bash
co keys
co keys --reveal  # only when you intentionally need full values
```

`co keys` shows where identity files and env files are being loaded from, without exposing secrets by default.

### OAuth integrations

```bash
co auth google
co auth microsoft
```

These commands connect Gmail/Calendar or Microsoft integrations. They require OpenOnion auth first because the OAuth tokens are stored through the authenticated account flow.

## Supported Models

All models are available with the `co/` prefix:

### OpenAI Models
```python
llm_do("Hello", model="co/gpt-5")
llm_do("Hello", model="co/gpt-5-mini")
llm_do("Hello", model="co/gpt-4o")
llm_do("Hello", model="co/o4-mini")
```

### Anthropic Models
```python
llm_do("Hello", model="co/claude-opus-4-5")
llm_do("Hello", model="co/claude-sonnet-4-5")
llm_do("Hello", model="co/claude-haiku-4-5")
```

### Google Models
```python
llm_do("Hello", model="co/gemini-3-pro-preview")
llm_do("Hello", model="co/gemini-3-flash-preview")
llm_do("Hello", model="co/gemini-2.5-pro")
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
    model="co/claude-sonnet-4-5",
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
models = ["co/gpt-4o", "co/claude-sonnet-4-5", "co/gemini-2.5-pro"]

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
        "Anthropic": "co/claude-sonnet-4-5",
        "Google": "co/gemini-2.5-pro"
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

- **Global location**: `~/.co/keys.env`
- **Project location**: `.env` when authenticating inside a project
- **Variable name**: `OPENONION_API_KEY`
- **Companion values**: `AGENT_ADDRESS`, `AGENT_EMAIL`, and `IS_EMAIL_ACTIVE` when available
- **Permissions**: keep these env files private and never commit them

### Data Handling

- **Requests**: Proxied through OpenOnion.ai servers
- **Logging**: Optional request logging (can be disabled)
- **Storage**: No prompt/response storage by default
- **Compliance**: SOC2 Type II compliant infrastructure

### Best Practices

1. **Don't commit tokens**: Add `~/.co/` to `.gitignore`
2. **Use environment-specific models**: Different models for dev/prod
3. **Monitor usage**: Check account status with `co status`
4. **Inspect safely**: Use `co keys` before `co keys --reveal`; avoid exposing tokens in logs or screenshots

## Troubleshooting

### Authentication Issues

**No agent keys found:**
```bash
# Create global identity and authenticate
co auth

# Or initialize a project first, then authenticate with project keys
co init
co auth
```

**Token not loading:**
```bash
# Show which files are being read without revealing secrets
co keys

# Confirm account access
co status
```

**Need the exact env var for deployment or CI:**
```bash
co keys --reveal
# Copy OPENONION_API_KEY only into your secret manager. Do not commit it.
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
POST https://oo.openonion.ai/api/v1/auth
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
A: Yes, but keep a fallback path for critical workloads by supporting your own provider keys and removing the `co/` prefix if needed.

**Q: How do I monitor costs?**
A: Use `co status` to check the account information available to the CLI.

**Q: Can my team share access?**
A: Team features are coming soon. For now, each developer needs their own account.

**Q: What if OpenOnion is down?**
A: You can always fall back to your own API keys by removing the `co/` prefix.

## Getting Help

- **Documentation**: https://docs.connectonion.com/auth
- **Issues**: https://github.com/openonion/connectonion/issues
- **Discord**: https://discord.gg/4xfD9k8AUF
- **Email**: support@openonion.ai

## Next Steps

1. Run `co auth` to get managed-key access
2. Run `co status` to confirm account access
3. Use `co keys` to verify which env files are active
4. Try the [Quick Start examples](#quick-start-2-minutes)
