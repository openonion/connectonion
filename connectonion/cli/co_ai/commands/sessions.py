"""Session commands - /sessions, /new."""

from connectonion.cli.co_ai.sessions import get_session_manager

_agent = None


def set_agent(agent):
    global _agent
    _agent = agent


def cmd_sessions(args: str = "") -> str:
    manager = get_session_manager()
    sessions = manager.list_sessions(limit=10)
    
    if not sessions:
        return "No saved sessions. Start chatting to create one!"
    
    lines = ["**Recent Sessions:**\n"]
    for s in sessions:
        date = s["updated_at"][:10] if s.get("updated_at") else "unknown"
        title = s.get("title", "Untitled")[:40]
        lines.append(f"- `{s['id']}` - {title} ({date})")
    
    lines.append("\n*Use `/resume <id>` to continue a session*")
    return "\n".join(lines)


def cmd_new(args: str = "") -> str:
    manager = get_session_manager()
    model = _agent.llm.model if _agent and hasattr(_agent, 'llm') else ""
    session_id = manager.create_session(model=model)
    
    if _agent and hasattr(_agent, 'messages'):
        _agent.messages = []
    
    return f"Started new session: `{session_id}`"


def cmd_resume(args: str = "") -> str:
    if not args.strip():
        return "Usage: `/resume <session_id>`\n\nUse `/sessions` to see available sessions."
    
    session_id = args.strip()
    manager = get_session_manager()
    messages = manager.load_session(session_id)
    
    if messages is None:
        return f"Session `{session_id}` not found."
    
    if _agent and hasattr(_agent, 'messages'):
        _agent.messages = [{"role": m["role"], "content": m["content"]} for m in messages]
    
    return f"Resumed session `{session_id}` with {len(messages)} messages."
