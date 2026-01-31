"""
Purpose: Execution analyzer module for post-run analysis and improvement suggestions
LLM-Note:
  Dependencies: imports from [execution_analysis.py] | imported by [debug/__init__.py, user code] | tested by [tests/debug/test_execution_analyzer.py]
  Data flow: re-exports analyze_execution function and ExecutionAnalysis model
  State/Effects: no state
  Integration: exposes analyze_execution(session_file) → ExecutionAnalysis with suggestions for prompt improvements | used after agent runs for optimization
  Performance: trivial
  Errors: none
Execution analyzer - Post-execution analysis and improvement suggestions.

Analyzes completed agent runs and provides suggestions for improving
system prompts and agent behavior.
"""

from .execution_analysis import analyze_execution, ExecutionAnalysis

__all__ = ["analyze_execution", "ExecutionAnalysis"]
