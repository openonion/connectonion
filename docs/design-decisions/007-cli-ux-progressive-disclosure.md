# Why We Choose Progressive Disclosure Over Configuration Questionnaires

*Date: 2025-09-04*

## The Problem with Traditional CLI Tools

Most framework CLIs suffer from what we call "initialization fatigue" - they bombard users with questions that don't matter yet:
- What's your project description? (I don't know, I just started)
- Choose your testing framework? (Let me build something first)
- Configure your linter settings? (Please, just let me code)
- Set up CI/CD pipeline? (It's my first 5 seconds with this tool)

This approach assumes users know everything upfront. Reality: they don't, and they shouldn't have to.

## Our Philosophy: Progressive Disclosure

### Core Principle: Start Fast, Decide Later

We designed ConnectOnion's CLI around three principles:
1. **Get to working code in < 30 seconds**
2. **Make smart defaults, not lengthy questionnaires**
3. **Respect the user's time and intelligence**

### The Two-Command Strategy: Why Both `create` and `init`

We deliberately offer two commands instead of forcing one workflow:

```bash
co create my-agent  # Creates new directory 
co init            # Uses current directory
```

**Why?** Because context matters:
- **Outside a project**: Users want `co create my-agent` - it's natural to create a new space
- **Inside a project**: Users want `co init` - they've already decided where to work

This isn't redundancy; it's respecting user intent. Django does this (`django-admin startproject` vs `manage.py startapp`), Rails does this (`rails new` vs `rails generate`), and for good reason.

### Minimal Questions, Maximum Intelligence

Our setup flow asks only what matters RIGHT NOW:
1. **Enable AI?** - Determines available templates
2. **API key** - Only if AI enabled, with auto-detection
3. **Template** - With previews so users know what they get

That's it. Three decisions max.

Compare to typical CLIs:
- Create-react-app: 5+ questions
- Vue CLI: 10+ questions  
- Yeoman generators: Often 15+ questions

### Smart API Key Detection

Instead of asking "Which provider are you using?", we detect it:

```python
if api_key.startswith('sk-proj-'):
    # OpenAI project key
elif api_key.startswith('sk-ant-'):
    # Anthropic  
elif api_key.startswith('gsk_'):
    # Groq
```

**Why?** The key format already tells us. Why make users answer what we can infer?

This extends to environment variables too. If `OPENAI_API_KEY` is set, we use it. No questions asked.

### Template Preview, Not Template Guessing

Instead of cryptic template names, we show exactly what users get:

```
📦 Minimal - Simple starting point
  ├── agent.py (50 lines) - Basic agent with example tool
  ├── .env - API key configuration
  └── .co/ - Agent identity & metadata
```

**Why?** Users shouldn't have to guess. Show them, let them choose, move on.

### Silent Excellence: Auto-Generated Agent Keys

We generate cryptographic keys for agents automatically. No prompt, no explanation, just done.

```python
# This happens silently during init
addr_data = address.generate()
address.save(addr_data, co_dir)
```

**Why?** 99% of users don't care about Ed25519 vs secp256k1. The 1% who do can read the docs.

## The "No BS" Commitment

### What We Don't Ask
- Project description (write code first, document later)
- Author name (use git config if needed)
- License type (add it when you're ready to share)
- Version number (it's 0.0.1, always)
- Test framework (we include examples, you choose)
- Package manager (pip is fine)

### What We Do Instead
- Create working code immediately
- Use sensible defaults everywhere
- Show clear next steps
- Get out of the way

### Beautiful by Default

We use colors, emojis, and formatting not for decoration, but for clarity:
- ✅ Green = Success
- ⚠️ Yellow = Warning  
- ❌ Red = Error
- 📁 Icons = Visual scanning

But we also respect terminal preferences:
- Works in non-color terminals
- Copy-paste friendly output
- No ASCII art or unnecessary flair

## Results: User Delight, Not User Fatigue

Our approach means:
- **30 seconds** from install to running agent
- **3 questions** maximum during setup
- **0 required** configuration files to edit
- **1 command** to start coding

Users consistently report that our CLI "just works" and "doesn't get in the way."

## Technical Implementation Notes

### Progressive Enhancement Pattern
```python
# Start with minimum viable
if not yes:
    ai = click.confirm("Enable AI features?", default=True)
    
# Enhance if enabled
if ai:
    templates.append('custom')
    
# But don't block progress
if not api_key:
    # Still create project, just remind them later
```

### Fail Gracefully, Suggest Clearly
```python
if project_dir.exists():
    click.echo(f"❌ Directory '{name}' already exists!")
    click.echo(f"💡 Suggestions:")
    click.echo(f"   • Use different name: co create {name}-v2")
    click.echo(f"   • Remove existing: rm -rf {name}")
    click.echo(f"   • Initialize existing: cd {name} && co init")
```

### Environment Intelligence
```python
# Check environment first, ask second
env_result = check_environment_for_api_keys()
if env_result:
    click.echo(f"✓ Found {provider} API key in environment")
    # Use it unless user objects
```

## Conclusion

Good CLI UX isn't about asking fewer questions - it's about asking the RIGHT questions at the RIGHT time. Everything else should be invisible, automatic, or optional.

Our CLI embodies this philosophy: Start fast, enhance progressively, respect user intelligence.

The best tool is one you forget you're using. That's what we built.