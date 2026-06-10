"""
Tip system for ConnectOnion CLI
Shows helpful tips after command execution.
"""
import os
import json
import random
from pathlib import Path
from typing import Optional

TIPS_DIR = Path.home() / ".co"
TIPS_SEEN_FILE = TIPS_DIR / "tips_seen.json"
CONFIG_FILE = TIPS_DIR / "config.toml"

# All available tips - at least 15 covering major features
TIPS = [
    # Feature discovery tips
    {
        "text": "Use @xray decorator on any tool to pause and inspect agent state during execution.",
        "link": "docs.connectonion.com/xray",
        "context": ["create", "init", "run"],
    },
    {
        "text": "Try the event system for complex multi-agent workflows. Learn more: docs.connectonion.com/events",
        "link": "docs.connectonion.com/events",
        "context": ["create", "run"],
    },
    {
        "text": "Use co/ managed keys for free credits - learn more at docs.connectonion.com/managed-keys",
        "link": "docs.connectonion.com/managed-keys",
        "context": ["auth", "status", "keys"],
    },
    {
        "text": "host() and connect() enable multi-agent communication. See docs.connectonion.com/multi-agent",
        "link": "docs.connectonion.com/multi-agent",
        "context": ["create", "run"],
    },
    {
        "text": "Email and calendar integrations available - check docs.connectonion.com/integrations",
        "link": "docs.connectonion.com/integrations",
        "context": ["create", "config"],
    },
    {
        "text": "TUI components available for rich terminal UIs - docs.connectonion.com/tui",
        "link": "docs.connectonion.com/tui",
        "context": ["create", "init"],
    },
    
    # Best practices tips
    {
        "text": "Use type hints on tool functions for better LLM schema generation.",
        "link": "docs.connectonion.com/types",
        "context": ["create", "init"],
    },
    {
        "text": "Add docstrings to your tools - they help the LLM understand tool purpose.",
        "link": "docs.connectonion.com/tools",
        "context": ["create", "init"],
    },
    {
        "text": "Use Pydantic models for complex tool arguments - automatic validation and schema.",
        "link": "docs.connectonion.com/pydantic",
        "context": ["create", "init"],
    },
    
    # Shortcuts tips
    {
        "text": "co -b is short for co browser - saves keystrokes!",
        "link": "docs.connectonion.com/cli",
        "context": ["browser", "help"],
    },
    {
        "text": "Use --quiet or -q flag to suppress output and tips.",
        "link": "docs.connectonion.com/cli",
        "context": ["help", "status"],
    },
    {
        "text": "co --version shows installed version and available updates.",
        "link": "docs.connectonion.com/cli",
        "context": ["help", "version"],
    },
    
    # Community tips
    {
        "text": "Join our Discord for help and feature discussions: discord.gg/4xfD9k8AUF",
        "link": "docs.connectonion.com/community",
        "context": ["help", "status"],
    },
    {
        "text": "Star us on GitHub: github.com/openonion/connectonion",
        "link": "docs.connectonion.com/community",
        "context": ["help", "status"],
    },
    {
        "text": "Follow @connectonion on X for updates and tips",
        "link": "docs.connectonion.com/community",
        "context": ["help", "status"],
    },
    
    # Model tips
    {
        "text": 'Try model="co/gemini-2.5-pro" for free managed LLM access.',
        "link": "docs.connectonion.com/models",
        "context": ["auth", "status", "create"],
    },
    {
        "text": "Use co/gpt-4o for the best reasoning - learn more at docs.connectonion.com/models",
        "link": "docs.connectonion.com/models",
        "context": ["create", "auth"],
    },
]


def load_tips_seen() -> dict:
    """Load the tips that have been seen."""
    if TIPS_SEEN_FILE.exists():
        try:
            with open(TIPS_SEEN_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {"seen": [], "index": 0}
    return {"seen": [], "index": 0}


def save_tips_seen(data: dict) -> None:
    """Save the tips seen data."""
    TIPS_SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TIPS_SEEN_FILE, "w") as f:
        json.dump(data, f, indent=2)


def is_tips_enabled() -> bool:
    """Check if tips are enabled in config."""
    # Check for --quiet in sys.argv before loading config
    import sys
    if "--quiet" in sys.argv or "-q" in sys.argv:
        return False
    
    # Check config file
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                content = f.read()
                if "tips = false" in content or "tips=false" in content:
                    return False
        except Exception:
            pass
    
    return True


def get_tip(command: str) -> Optional[dict]:
    """Get a contextual tip for the given command."""
    if not is_tips_enabled():
        return None
    
    # Filter tips by context
    matching_tips = []
    for tip in TIPS:
        contexts = tip.get("context", [])
        if not contexts or any(c in command.lower() for c in contexts):
            matching_tips.append(tip)
    
    if not matching_tips:
        # Fall back to random tip if no contextual match
        matching_tips = TIPS
    
    # Get seen tips data
    data = load_tips_seen()
    seen_ids = set(data.get("seen", []))
    last_index = data.get("index", 0)
    
    # Find unseen tips
    unseen = [t for t in matching_tips if id(t) not in seen_ids]
    
    if not unseen:
        # Reset and show all tips again
        data = {"seen": [], "index": 0}
        save_tips_seen(data)
        unseen = matching_tips
    
    # Pick a random unseen tip
    tip = random.choice(unseen)
    
    # Mark as seen
    data["seen"].append(id(tip))
    data["index"] = (last_index + 1) % len(TIPS)
    save_tips_seen(data)
    
    return tip


def show_tip(command: str) -> None:
    """Display a tip after command execution."""
    tip = get_tip(command)
    if not tip:
        return
    
    print(f"\n💡 Tip: {tip['text']}")
    print(f"    Learn more: {tip['link']}")


def disable_tips() -> None:
    """Disable tips by updating config."""
    TIPS_DIR.mkdir(parents=True, exist_ok=True)
    
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            content = f.read()
    else:
        content = ""
    
    if "tips" not in content:
        content += "\n[cli]\ntips = false\n"
    
    with open(CONFIG_FILE, "w") as f:
        f.write(content)


def enable_tips() -> None:
    """Enable tips by updating config."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            content = f.read()
        
        content = content.replace("tips = false", "tips = true")
        
        with open(CONFIG_FILE, "w") as f:
            f.write(content)


def reset_tips() -> None:
    """Reset tips to show all from the beginning."""
    if TIPS_SEEN_FILE.exists():
        TIPS_SEEN_FILE.unlink()
