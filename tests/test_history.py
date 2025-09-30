"""Unit tests for connectonion/history.py"""

import unittest
import tempfile
import os
import json
from pathlib import Path
from connectonion.history import BehaviorHistory, BehaviorRecord


class TestBehaviorHistory(unittest.TestCase):
    """Test behavior history tracking."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.history_file = os.path.join(self.temp_dir, "test_history.json")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_behavior_record(self):
        """Test creating a behavior record."""
        record = BehaviorRecord(
            user_prompt="Test task",
            model="gpt-4o-mini",
            tool_calls=[],
            result="Success"
        )

        self.assertEqual(record.user_prompt, "Test task")
        self.assertEqual(record.model, "gpt-4o-mini")
        self.assertEqual(record.result, "Success")

    def test_save_and_load_history(self):
        """Test saving and loading history."""
        history = BehaviorHistory("test_agent", self.history_file)

        record = BehaviorRecord(
            user_prompt="Test task",
            model="gpt-4o-mini",
            tool_calls=[],
            result="Success"
        )

        history.add_record(record)
        history.save()

        # Load history from file
        with open(self.history_file, 'r') as f:
            data = json.load(f)

        self.assertIn("records", data)
        self.assertEqual(len(data["records"]), 1)
        self.assertEqual(data["records"][0]["user_prompt"], "Test task")

    def test_history_persistence(self):
        """Test that history persists across instances."""
        history1 = BehaviorHistory("test_agent", self.history_file)
        record = BehaviorRecord(
            user_prompt="First task",
            model="gpt-4o-mini",
            tool_calls=[],
            result="Success"
        )
        history1.add_record(record)
        history1.save()

        # Create new history instance
        history2 = BehaviorHistory("test_agent", self.history_file)
        history2.load()

        self.assertEqual(len(history2.records), 1)
        self.assertEqual(history2.records[0].user_prompt, "First task")


if __name__ == '__main__':
    unittest.main()