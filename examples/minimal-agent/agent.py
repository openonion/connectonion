#!/usr/bin/env python3
"""Minimal ConnectOnion agent example."""

import os
from connectonion import Agent, llm_do


def load_env(path: str = ".env", override: bool = False) -> None:
    """Load key=value pairs from a .env file into os.environ.

    Args:
        path: Path to the .env file.
        override: If True, overwrite existing environment variables.
    """
    try:
        if not os.path.isfile(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    val = val[1:-1]
                if not override and key in os.environ:
                    continue
                os.environ[key] = val
    except Exception:
        # Be silent on dotenv load errors in minimal example
        pass


@xray
def hello_world(name: str = "World") -> str:
    """Simple greeting function.
    
    Args:
        name: Name to greet
        
    Returns:
        A greeting message
    """
    return f"Hello, {name}! Welcome to ConnectOnion."


def main():
    """Run the minimal agent."""
    # Load environment variables from .env before creating the agent
    load_env()
    # Create agent with a simple tool
    agent = Agent(
        name="minimal-agent",
        tools=[hello_world],
        model="o4-mini"
    )
    
    # Example interaction
    response = agent.auto_debug("Say hello to the user")
    print(response)
    

if __name__ == "__main__":
    main()
