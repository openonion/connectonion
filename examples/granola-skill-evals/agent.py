"""Minimal Agent entry point for the Granola Skill benchmarks.

The benchmark runner imports this file without starting a server.  It uses the
same Agent factory as ``co ai`` so the built-in Granola Skills can be invoked
explicitly.  Benchmark prompts are synthetic and runs remain non-live unless a
caller deliberately supplies ``--live``.
"""

from connectonion import host
from connectonion.cli.co_ai.agent import create_agent


host(lambda: create_agent(role=None))
