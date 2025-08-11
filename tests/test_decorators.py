"""
Unit tests for ConnectOnion debugging decorators.

Tests cover:
- @xray decorator functionality
- @replay decorator functionality
- Context injection and cleanup
- Thread safety
- Edge cases and error handling
"""

import unittest
from unittest.mock import Mock, patch, call
import threading
import time

# Add parent directory to path for imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectonion.decorators import (
    xray, replay, xray_replay,
    _inject_context_for_tool, _clear_context_after_tool,
    _is_xray_enabled, _is_replay_enabled,
    XrayContext
)


class TestXrayDecorator(unittest.TestCase):
    """Test the @xray decorator functionality."""
    
    def setUp(self):
        """Clear any existing context before each test."""
        _clear_context_after_tool()
    
    def tearDown(self):
        """Clean up after each test."""
        _clear_context_after_tool()
    
    def test_xray_decorator_marks_function(self):
        """Test that @xray marks functions as xray-enabled."""
        @xray
        def test_func():
            return "test"
        
        self.assertTrue(_is_xray_enabled(test_func))
        self.assertEqual(test_func(), "test")
    
    def test_xray_context_without_agent(self):
        """Test xray context when no agent context is set."""
        @xray
        def test_func():
            # Access context attributes
            self.assertIsNone(xray.agent)
            self.assertIsNone(xray.user_prompt)
            self.assertEqual(xray.messages, [])
            self.assertIsNone(xray.iteration)
            self.assertEqual(xray.previous_tools, [])
            return "success"
        
        result = test_func()
        self.assertEqual(result, "success")
    
    def test_xray_context_with_agent(self):
        """Test xray context when agent context is injected."""
        # Mock agent
        mock_agent = Mock()
        mock_agent.name = "test_agent"
        
        # Inject context
        _inject_context_for_tool(
            agent=mock_agent,
            user_prompt="Test task",
            messages=[{"role": "user", "content": "Hello"}],
            iteration=1,
            previous_tools=["tool1"]
        )
        
        @xray
        def test_func():
            # Verify context is accessible
            self.assertEqual(xray.agent.name, "test_agent")
            self.assertEqual(xray.user_prompt, "Test task")
            self.assertEqual(len(xray.messages), 1)
            self.assertEqual(xray.iteration, 1)
            self.assertEqual(xray.previous_tools, ["tool1"])
            
            # Test xray() to get full context
            context = xray()
            self.assertIn("agent", context)
            self.assertIn("user_prompt", context)
            return "success"
        
        result = test_func()
        self.assertEqual(result, "success")
        
        # Verify context is cleared after execution
        self.assertIsNone(xray.agent)
    
    def test_xray_repr(self):
        """Test xray context representation."""
        # Without context
        repr_str = repr(xray)
        self.assertIn("no active context", repr_str)
        
        # With context
        mock_agent = Mock()
        mock_agent.name = "test_bot"
        
        _inject_context_for_tool(
            agent=mock_agent,
            user_prompt="Very long task description that should be truncated in the representation",
            messages=[{"role": "user", "content": "msg1"}, {"role": "assistant", "content": "msg2"}],
            iteration=2,
            previous_tools=["tool1", "tool2"]
        )
        
        @xray
        def test_func():
            repr_str = repr(xray)
            self.assertIn("XrayContext active", repr_str)
            self.assertIn("test_bot", repr_str)
            self.assertIn("...", repr_str)  # Task should be truncated
            self.assertIn("2 items", repr_str)  # Messages count
            self.assertIn("previous_tools", repr_str)
            return repr_str
        
        test_func()
    
    def test_xray_function_preserves_metadata(self):
        """Test that @xray preserves function metadata."""
        @xray
        def test_func(x: int, y: str = "default") -> str:
            """Test function docstring."""
            return f"{x}-{y}"
        
        self.assertEqual(test_func.__name__, "test_func")
        self.assertEqual(test_func.__doc__, "Test function docstring.")
        self.assertEqual(test_func(1, "test"), "1-test")


class TestReplayDecorator(unittest.TestCase):
    """Test the @replay decorator functionality."""
    
    def test_replay_decorator_marks_function(self):
        """Test that @replay marks functions as replay-enabled."""
        @replay
        def test_func():
            return "test"
        
        self.assertTrue(_is_replay_enabled(test_func))
        self.assertEqual(test_func(), "test")
    
    def test_replay_function_basic(self):
        """Test basic replay functionality."""
        call_count = 0
        
        @replay
        def test_func(x: int, y: int = 10) -> int:
            nonlocal call_count
            call_count += 1
            return x + y
        
        # First call
        result = test_func(5)
        self.assertEqual(result, 15)
        self.assertEqual(call_count, 1)
        
        # Note: Replay only works during actual debugging with breakpoints
        # Here we test that the function still works normally
        result2 = test_func(5, y=20)
        self.assertEqual(result2, 25)
        self.assertEqual(call_count, 2)
    
    def test_replay_with_mock_debugging(self):
        """Test replay during simulated debugging."""
        results = []
        
        @replay
        def test_func(text: str, multiplier: int = 2) -> str:
            result = text * multiplier
            results.append(result)
            return result
        
        # In actual debugging, replay would be available in the debugger
        # Here we verify the function works correctly
        result1 = test_func("a", 3)
        self.assertEqual(result1, "aaa")
        self.assertEqual(len(results), 1)
    
    def test_replay_preserves_metadata(self):
        """Test that @replay preserves function metadata."""
        @replay
        def test_func(x: int) -> int:
            """Test function with replay."""
            return x * 2
        
        self.assertEqual(test_func.__name__, "test_func")
        self.assertEqual(test_func.__doc__, "Test function with replay.")


class TestCombinedDecorators(unittest.TestCase):
    """Test using @xray and @replay together."""
    
    def setUp(self):
        """Clear context before each test."""
        _clear_context_after_tool()
    
    def tearDown(self):
        """Clean up after each test."""
        _clear_context_after_tool()
    
    def test_xray_replay_combination(self):
        """Test using both decorators together."""
        @xray
        @replay
        def test_func(value: int) -> int:
            # Should have access to xray context
            # Should be replay-enabled
            return value * 2
        
        self.assertTrue(_is_xray_enabled(test_func))
        self.assertTrue(_is_replay_enabled(test_func))
        
        result = test_func(5)
        self.assertEqual(result, 10)
    
    def test_xray_replay_convenience_decorator(self):
        """Test the xray_replay convenience decorator."""
        @xray_replay
        def test_func(value: str) -> str:
            return value.upper()
        
        self.assertTrue(_is_xray_enabled(test_func))
        self.assertTrue(_is_replay_enabled(test_func))
        
        result = test_func("hello")
        self.assertEqual(result, "HELLO")


class TestThreadSafety(unittest.TestCase):
    """Test thread safety of context management."""
    
    def setUp(self):
        """Clear context before each test."""
        _clear_context_after_tool()
    
    def tearDown(self):
        """Clean up after each test."""
        _clear_context_after_tool()
    
    def test_thread_local_context_isolation(self):
        """Test that contexts are isolated between threads."""
        results = {}
        
        @xray
        def test_func(thread_id: int):
            # Each thread should see its own context
            results[thread_id] = {
                'agent': xray.agent.name if xray.agent else None,
                'task': xray.user_prompt
            }
        
        def thread_work(thread_id: int):
            # Inject unique context for this thread
            mock_agent = Mock()
            mock_agent.name = f"agent_{thread_id}"
            
            _inject_context_for_tool(
                agent=mock_agent,
                user_prompt=f"Task {thread_id}",
                messages=[],
                iteration=thread_id,
                previous_tools=[]
            )
            
            test_func(thread_id)
        
        # Run in multiple threads
        threads = []
        for i in range(3):
            t = threading.Thread(target=thread_work, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Verify each thread saw its own context
        self.assertEqual(len(results), 3)
        for i in range(3):
            self.assertEqual(results[i]['agent'], f"agent_{i}")
            self.assertEqual(results[i]['task'], f"Task {i}")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""
    
    def test_xray_on_class_method(self):
        """Test @xray on class methods."""
        class TestClass:
            @xray
            def method(self, value: str) -> str:
                return f"Method: {value}"
        
        obj = TestClass()
        result = obj.method("test")
        self.assertEqual(result, "Method: test")
        self.assertTrue(_is_xray_enabled(obj.method))
    
    def test_xray_on_static_method(self):
        """Test @xray on static methods."""
        class TestClass:
            @staticmethod
            @xray
            def static_method(value: str) -> str:
                return f"Static: {value}"
        
        result = TestClass.static_method("test")
        self.assertEqual(result, "Static: test")
    
    def test_empty_context_handling(self):
        """Test handling of empty or None context values."""
        _inject_context_for_tool(
            agent=None,
            user_prompt=None,
            messages=None,  # This will be stored as None in context
            iteration=None,
            previous_tools=None
        )
        
        @xray
        def test_func():
            # Should handle None values gracefully
            self.assertIsNone(xray.agent)
            self.assertIsNone(xray.user_prompt)
            # When None is stored in context, get() returns None, not the default
            self.assertIsNone(xray.messages)
            self.assertIsNone(xray.iteration)
            self.assertIsNone(xray.previous_tools)
            return "handled"
        
        result = test_func()
        self.assertEqual(result, "handled")
    
    def test_xray_context_get_context_method(self):
        """Test the get_context() method returns a copy."""
        mock_agent = Mock()
        mock_agent.name = "test"
        
        _inject_context_for_tool(
            agent=mock_agent,
            user_prompt="Test",
            messages=[{"role": "user", "content": "Hi"}],
            iteration=1,
            previous_tools=[]
        )
        
        @xray
        def test_func():
            context1 = xray.get_context()
            context2 = xray.get_context()
            
            # Should be equal but different objects
            self.assertEqual(context1, context2)
            self.assertIsNot(context1, context2)
            
            # Modifying one shouldn't affect the other
            context1['user_prompt'] = "Modified"
            self.assertEqual(context2['user_prompt'], "Test")
            
            return "success"
        
        test_func()


if __name__ == "__main__":
    unittest.main()