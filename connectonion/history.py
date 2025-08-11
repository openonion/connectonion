"""History tracking for agent behaviors."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class BehaviorRecord:
    """Record of a single agent behavior."""
    timestamp: str
    user_prompt: str
    tool_calls: List[Dict[str, Any]]
    result: str
    duration_seconds: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class History:
    """Tracks and persists agent behavior history."""
    
    def __init__(self, agent_name: str, save_dir: Optional[str] = None):
        self.agent_name = agent_name
        self.records: List[BehaviorRecord] = []
        
        # Set up save directory
        if save_dir:
            self.save_dir = Path(save_dir)
        else:
            self.save_dir = Path.home() / ".connectonion" / "agents" / agent_name
        
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.save_dir / "behavior.json"
        
        # Load existing history if available
        self._load_history()
    
    def record(self, user_prompt: str, tool_calls: List[Dict[str, Any]], result: str, duration: float):
        """Record a new behavior."""
        record = BehaviorRecord(
            timestamp=datetime.now().isoformat(),
            user_prompt=user_prompt,
            tool_calls=tool_calls,
            result=result,
            duration_seconds=duration
        )
        self.records.append(record)
        
        # Auto-save after each record
        self.save_to_file()
    
    def save_to_file(self):
        """Save history to JSON file."""
        try:
            data = {
                "agent_name": self.agent_name,
                "records": [r.to_dict() for r in self.records],
                "total_records": len(self.records),
                "last_updated": datetime.now().isoformat()
            }
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"Warning: Failed to save history: {str(e)}")
    
    def _load_history(self):
        """Load existing history from file."""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                for record_data in data.get("records", []):
                    self.records.append(BehaviorRecord(**record_data))
                    
            except Exception as e:
                print(f"Warning: Failed to load history: {str(e)}")
    
    def summary(self) -> str:
        """Get a summary of the agent's behavior."""
        if not self.records:
            return "No behaviors recorded yet."
        
        total_tasks = len(self.records)
        total_tool_calls = sum(len(r.tool_calls) for r in self.records)
        total_time = sum(r.duration_seconds for r in self.records)
        
        # Count tool usage
        tool_usage = {}
        for record in self.records:
            for tool_call in record.tool_calls:
                tool_name = tool_call.get("name", "unknown")
                tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1
        
        summary_lines = [
            f"Agent: {self.agent_name}",
            f"Total tasks completed: {total_tasks}",
            f"Total tool calls: {total_tool_calls}",
            f"Total execution time: {total_time:.2f} seconds",
            f"History file: {self.history_file}"
        ]
        
        if tool_usage:
            summary_lines.append("\nTool usage:")
            for tool, count in sorted(tool_usage.items(), key=lambda x: x[1], reverse=True):
                summary_lines.append(f"  {tool}: {count} calls")
        
        return "\n".join(summary_lines)
    
    def get_recent(self, n: int = 10) -> List[BehaviorRecord]:
        """Get n most recent records."""
        return self.records[-n:] if self.records else []