"""Execution analyzer - Post-execution analysis and improvement suggestions.

Analyzes completed agent runs and provides suggestions for improving
system prompts and agent behavior.
"""

from .execution_analysis import analyze_execution, ExecutionAnalysis

__all__ = ["analyze_execution", "ExecutionAnalysis"]
