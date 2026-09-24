"""
Purpose: Skill benchmarks — a frozen set of cases a skill is measured against, a runner that scores the real Agent on them, and saved reports to compare
LLM-Note:
  Dependencies: imports from [benchmark/suite.py] | imported by [cli/commands/benchmark_commands.py] | tested by [tests/unit/test_benchmark_suite.py, tests/unit/test_benchmark_runner.py, tests/unit/test_benchmark_report.py, tests/unit/test_benchmark_commands.py]
  Data flow: .co/benchmarks/<name>.yaml → suite.load → runner.run(real agent.py) → report.save → .co/eval-runs/<name>/<run-id>/report.json
  State/Effects: reads .co/benchmarks, writes only .co/eval-runs
  Integration: `co benchmark list|check` and `co eval run|report` (#1642)
  Errors: see each module
"""

from .suite import EXAMPLE, MIN_CASES, Case, Problem, Suite, list_suites, load

__all__ = ["EXAMPLE", "MIN_CASES", "Case", "Problem", "Suite", "list_suites", "load"]
