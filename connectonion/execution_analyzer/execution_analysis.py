"""Post-execution analysis for completed agent runs.

Analyzes the entire execution trace and provides suggestions for improvement.
"""

from pathlib import Path
from pydantic import BaseModel
from typing import List
from ..llm_do import llm_do


class ExecutionAnalysis(BaseModel):
    """Structured output for post-execution analysis."""
    task_completed: bool
    completion_explanation: str
    problems_identified: List[str]
    system_prompt_suggestions: List[str]
    overall_quality: str  # "excellent" | "good" | "fair" | "poor"
    key_insights: List[str]


def analyze_execution(
    user_prompt: str,
    agent_instance,
    final_result: str,
    execution_trace: List,
    max_iterations_reached: bool
) -> ExecutionAnalysis:
    """Analyze completed execution and suggest improvements.

    Args:
        user_prompt: The original user request
        agent_instance: The Agent that executed
        final_result: Final response from agent
        execution_trace: Complete trace of execution
        max_iterations_reached: Whether agent hit iteration limit

    Returns:
        Structured analysis with improvement suggestions
    """
    # Build execution summary
    tools_called = [
        entry for entry in execution_trace
        if entry.get('type') == 'tool_execution'
    ]

    tools_summary = []
    for entry in tools_called:
        status = "✓" if entry.get('status') == 'success' else "✗"
        tools_summary.append(
            f"{status} {entry.get('tool_name')}({entry.get('args')}) → {entry.get('result')}"
        )

    # Create analysis input
    data = f"""**User Request:**
{user_prompt}

**Agent System Prompt:**
{agent_instance.system_prompt}

**Available Tools:**
{', '.join([t.name for t in agent_instance.tools]) if agent_instance.tools else 'None'}

**Execution Summary:**
- Max iterations reached: {max_iterations_reached}
- Tools called ({len(tools_called)}):
{chr(10).join(f"  {i+1}. {s}" for i, s in enumerate(tools_summary))}

**Final Result:**
{final_result}

**Complete Trace:**
{execution_trace}"""

    prompt_file = Path(__file__).parent / "execution_analysis_prompt.md"

    # Use same model as agent
    return llm_do(
        data,
        output=ExecutionAnalysis,
        system_prompt=prompt_file,
        model=agent_instance.llm.model
    )
