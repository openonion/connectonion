"""
Purpose: Provide experimental debugging tools to understand and fix unwanted tool calls via prompt testing
LLM-Note:
  Dependencies: imports from [typing, pathlib, pydantic, ../llm_do.py] | imported by [explain_agent.py] | no dedicated tests found
  Data flow: explain_tool_choice() creates RuntimeContext(breakpoint_context, agent) → stores bp_ctx and agent state → methods test_system_prompt_variation(new_prompt), suggest_prompt_improvements(), verify_stability() call llm_do() with modified prompts → returns RootCauseAnalysis (Pydantic model with primary_cause_source, influential_text, explanation, is_correct_choice, suggested_fix)
  State/Effects: stores breakpoint_context and agent_instance | no file I/O | calls llm_do() for LLM analysis (multiple LLM requests per method) | no global state
  Integration: exposes RuntimeContext class, RootCauseAnalysis (Pydantic model) | used by explain_agent.py to provide experimental debugging | methods help developers understand why agent chose specific tool and how to fix unwanted choices via prompt engineering
  Performance: each method makes 1+ LLM calls via llm_do() | no caching | synchronous execution
  Errors: LLM call failures propagate from llm_do() | Pydantic validation errors if LLM returns invalid structure
"""

from typing import Dict, List, Any
from pathlib import Path
from pydantic import BaseModel
from ..llm_do import llm_do


class RootCauseAnalysis(BaseModel):
    """Structured output for root cause analysis."""
    primary_cause_source: str  # "system_prompt" | "user_message" | "tool_results" | "available_tools"
    influential_text: str  # The exact sentence/phrase that caused this
    explanation: str  # Why this text led to choosing this tool
    is_correct_choice: bool  # Is this the right tool for the task?
    suggested_fix: str  # How to prevent if unwanted (be specific)


class RuntimeContext:
    """Experimental debugger for fixing unwanted tool calls.

    Primary use case: "Agent called tool X but I didn't want it to - how do I fix this?"

    All static context is already in the prompt. This class provides experiments to:
    1. Test different system prompts - would they prevent this call?
    2. Suggest prompt improvements - what changes would help?
    3. Verify stability - is the decision consistent?
    """

    def __init__(self, breakpoint_context, agent_instance):
        """Initialize with breakpoint and agent runtime state.

        Args:
            breakpoint_context: BreakpointContext with execution data
            agent_instance: The Agent instance being debugged
        """
        self.bp_ctx = breakpoint_context
        self.agent = agent_instance

    def test_with_different_system_prompt(self, new_system_prompt: str) -> str:
        """Test if different system prompt would prevent this tool call.

        Use case: "Would modifying the system prompt prevent calling this unwanted tool?"

        Args:
            new_system_prompt: Alternative system prompt to test

        Returns:
            What the agent would do with the modified prompt
        """
        # Get messages up to the decision point
        temp_messages = self.agent.current_session['messages'].copy()

        # Remove the assistant message that made this tool call
        if temp_messages and temp_messages[-1].get('role') == 'assistant':
            temp_messages = temp_messages[:-1]

        # Replace system prompt
        for msg in temp_messages:
            if msg.get('role') == 'system':
                msg['content'] = new_system_prompt
                break
        else:
            # No system message exists, add one
            temp_messages.insert(0, {"role": "system", "content": new_system_prompt})

        # See what agent would do with new prompt
        tool_schemas = [tool.to_function_schema() for tool in self.agent.tools] if self.agent.tools else None
        response = self.agent.llm.complete(temp_messages, tools=tool_schemas)

        if response.tool_calls:
            new_choices = [f"{tc.name}({tc.arguments})" for tc in response.tool_calls]
            still_calls_this = any(tc.name == self.bp_ctx.tool_name for tc in response.tool_calls)
        else:
            new_choices = ["No tools - would answer directly"]
            still_calls_this = False

        result = f"**Current system prompt**: {self.agent.system_prompt[:200]}...\n"
        result += f"**Current choice**: {self.bp_ctx.tool_name}({self.bp_ctx.tool_args})\n\n"
        result += f"**New system prompt**: {new_system_prompt[:200]}...\n"
        result += f"**Would choose**: {', '.join(new_choices)}\n\n"

        if still_calls_this:
            result += "❌ Still calls the same tool - prompt change didn't help"
        else:
            result += "✓ Different choice - prompt change would prevent this call"

        return result

    def test_stability_with_current_prompt(self, num_trials: int = 3) -> str:
        """Test if current decision is stable or random.

        Use case: "Is this tool choice consistent or does it vary randomly?"

        Args:
            num_trials: Number of times to test (default: 3)

        Returns:
            Analysis of decision stability
        """
        # Get messages up to decision point
        temp_messages = self.agent.current_session['messages'].copy()
        if temp_messages and temp_messages[-1].get('role') == 'assistant':
            temp_messages = temp_messages[:-1]

        # Run multiple trials
        tool_schemas = [tool.to_function_schema() for tool in self.agent.tools] if self.agent.tools else None
        decisions = []

        for _ in range(num_trials):
            response = self.agent.llm.complete(temp_messages, tools=tool_schemas)
            if response.tool_calls:
                decision = response.tool_calls[0].name
            else:
                decision = "No tool"
            decisions.append(decision)

        # Analyze
        unique = set(decisions)
        is_stable = len(unique) == 1

        result = f"**Tested {num_trials} times**: {', '.join(decisions)}\n\n"

        if is_stable:
            result += "✓ STABLE - Always chooses same tool\n"
            result += "Conclusion: Decision is consistent, not random"
        else:
            result += f"❌ UNSTABLE - {len(unique)} different choices\n"
            result += "Conclusion: Decision varies - system prompt may need to be more directive"

        return result

    def test_with_different_result(self, hypothetical_result: Any) -> str:
        """Test if different tool result changes next action.

        Use case: "Would a different result change what the agent does next?"

        System prompt and messages stay the same, only the tool result changes.

        Args:
            hypothetical_result: Alternative result to test

        Returns:
            Analysis of whether next action would change
        """
        current_next = self.bp_ctx.next_actions or []

        # Build modified message history with different result
        temp_messages = self.agent.current_session['messages'].copy()

        # Find the assistant message with tool calls and add modified result
        for msg in reversed(temp_messages):
            if msg.get('role') == 'assistant' and msg.get('tool_calls'):
                for tool_call in msg.get('tool_calls', []):
                    if tool_call.get('function', {}).get('name') == self.bp_ctx.tool_name:
                        # Add modified result message
                        temp_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call['id'],
                            "content": str(hypothetical_result)
                        })
                        break
                break

        # See what agent would do with modified result
        tool_schemas = [tool.to_function_schema() for tool in self.agent.tools] if self.agent.tools else None
        response = self.agent.llm.complete(temp_messages, tools=tool_schemas)

        if response.tool_calls:
            new_actions = [f"{tc.name}({tc.arguments})" for tc in response.tool_calls]
        else:
            new_actions = ["Finish - no more tools"]

        current_actions = [f"{a['name']}({a['args']})" for a in current_next] if current_next else ["Finish"]

        result = f"**Current result**: {self.bp_ctx.trace_entry.get('result')}\n"
        result += f"**Current next action**: {', '.join(current_actions)}\n\n"
        result += f"**If result was**: {hypothetical_result}\n"
        result += f"**Would do**: {', '.join(new_actions)}\n\n"

        if new_actions == current_actions:
            result += "✓ Same action - result doesn't affect decision"
        else:
            result += "⚠️ Different action - result is critical to decision chain"

        return result

    def analyze_why_this_tool(self) -> str:
        """Simple analysis: Ask why this specific tool was chosen.

        Use case: "Why did you choose this tool?" - in the agent's own words

        Uses the same system prompt and messages as the agent, just asks
        the agent to explain its own reasoning.

        Returns:
            Agent's explanation of why it chose this tool
        """
        # Use the agent's current messages up to this point
        temp_messages = self.agent.current_session['messages'].copy()

        # Remove the assistant message that made the tool call
        if temp_messages and temp_messages[-1].get('role') == 'assistant':
            temp_messages = temp_messages[:-1]

        # Add a question asking why it would choose this tool
        temp_messages.append({
            "role": "user",
            "content": f"Why would you choose to call the tool '{self.bp_ctx.tool_name}' with arguments {self.bp_ctx.tool_args} for this task? Explain your reasoning."
        })

        # Get the agent's own explanation using its model
        response = self.agent.llm.complete(temp_messages, tools=None)

        return response.content

    def analyze_root_cause(self) -> RootCauseAnalysis:
        """Deep reasoning: WHY was this specific tool chosen?

        Use case: "What caused the agent to choose this unwanted tool?"

        Analyzes:
        - Which parts of system prompt influenced this?
        - What in user request triggered this?
        - What reasoning chain led here?
        - Root cause and how to fix

        Returns:
            Structured analysis with causal factors and suggested fixes
        """
        # Just provide the data - analysis framework is in the system prompt
        data = f"""**Agent System Prompt:**
{self.agent.system_prompt}

**User Request:**
{self.bp_ctx.user_prompt}

**Tool Chosen:**
{self.bp_ctx.tool_name} with arguments {self.bp_ctx.tool_args}

**Available Tools:**
{', '.join([t.name for t in self.agent.tools]) if self.agent.tools else 'None'}

**Previous Tools Called:**
{', '.join(self.bp_ctx.previous_tools) if self.bp_ctx.previous_tools else 'None'}"""

        prompt_file = Path(__file__).parent / "root_cause_analysis_prompt.md"

        # Use the same model as the agent being debugged
        return llm_do(
            data,
            output=RootCauseAnalysis,
            system_prompt=prompt_file,
            model=self.agent.llm.model
        )
