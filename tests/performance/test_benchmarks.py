"""Performance benchmarks for ConnectOnion."""

import pytest
import time
import psutil
import os
from unittest.mock import Mock
from connectonion import Agent
from tests.fixtures.test_tools import Calculator, CurrentTime, ReadFile
from tests.utils.mock_helpers import LLMResponseBuilder


@pytest.mark.benchmark
class TestPerformanceBenchmarks:
    """Performance benchmarks for ConnectOnion components."""
    
    def test_agent_response_time_simple(self, temp_dir):
        """Benchmark simple agent response time."""
        # Mock fast LLM response
        mock_llm = Mock()
        mock_llm.complete.return_value = LLMResponseBuilder.text_response("Quick response")
        
        # Create agent
        agent = Agent(name="perf_simple", llm=mock_llm)
        agent.history.save_dir = temp_dir
        
        # Benchmark multiple runs
        times = []
        for _ in range(10):
            start = time.time()
            agent.input("Simple task")
            end = time.time()
            times.append(end - start)
        
        avg_time = sum(times) / len(times)
        max_time = max(times)
        
        # Performance assertions
        assert avg_time < 0.1, f"Average response time too slow: {avg_time:.3f}s"
        assert max_time < 0.2, f"Max response time too slow: {max_time:.3f}s"
        
        print(f"Simple response - Avg: {avg_time:.3f}s, Max: {max_time:.3f}s")
    
    def test_agent_response_time_with_tools(self, temp_dir):
        """Benchmark agent response time with tool usage."""
        # Mock LLM with tool calling
        mock_llm = Mock()
        mock_llm.complete.side_effect = [
            LLMResponseBuilder.tool_call_response("calculator", {"expression": "2 + 2"}),
            LLMResponseBuilder.text_response("The result is 4")
        ]
        
        # Create agent with tools
        agent = Agent(name="perf_tools", llm=mock_llm, tools=[Calculator()])
        agent.history.save_dir = temp_dir
        
        # Benchmark multiple runs
        times = []
        for _ in range(10):
            # Reset mock for each run
            mock_llm.complete.side_effect = [
                LLMResponseBuilder.tool_call_response("calculator", {"expression": "2 + 2"}),
                LLMResponseBuilder.text_response("The result is 4")
            ]
            
            start = time.time()
            agent.input("Calculate something")
            end = time.time()
            times.append(end - start)
        
        avg_time = sum(times) / len(times)
        max_time = max(times)
        
        # Performance assertions (tool calls should be slightly slower)
        assert avg_time < 0.2, f"Average tool response time too slow: {avg_time:.3f}s"
        assert max_time < 0.5, f"Max tool response time too slow: {max_time:.3f}s"
        
        print(f"Tool response - Avg: {avg_time:.3f}s, Max: {max_time:.3f}s")
    
    def test_history_file_write_performance(self, temp_dir):
        """Benchmark history file writing performance."""
        from connectonion.history import History
        
        # Create history instance
        history = History("perf_test", save_dir=temp_dir)
        
        # Benchmark multiple records
        start = time.time()
        for i in range(100):
            history.record(
                user_prompt=f"Task {i}",
                tool_calls=[{
                    "name": "test_tool",
                    "arguments": {"param": f"value_{i}"},
                    "result": f"result_{i}",
                    "status": "success"
                }],
                result=f"Completed task {i}",
                duration=0.5
            )
        end = time.time()
        
        total_time = end - start
        avg_per_record = total_time / 100
        
        # Performance assertions
        assert total_time < 5.0, f"Total write time too slow: {total_time:.3f}s"
        assert avg_per_record < 0.1, f"Average per record too slow: {avg_per_record:.3f}s"
        
        print(f"History writes - Total: {total_time:.3f}s, Avg: {avg_per_record:.3f}s/record")
    
    def test_memory_usage_single_agent(self, temp_dir):
        """Benchmark memory usage for single agent."""
        import gc
        
        # Get initial memory
        gc.collect()
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create and use agent
        mock_llm = Mock()
        mock_llm.complete.return_value = LLMResponseBuilder.text_response("Response")
        
        agent = Agent(name="memory_test", llm=mock_llm, tools=[Calculator(), CurrentTime()])
        agent.history.save_dir = temp_dir
        
        # Run multiple tasks
        for i in range(50):
            agent.input(f"Task {i}")
        
        # Get final memory
        gc.collect()
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Memory assertions
        assert memory_increase < 50, f"Memory increase too high: {memory_increase:.1f}MB"
        
        print(f"Memory usage - Initial: {initial_memory:.1f}MB, "
              f"Final: {final_memory:.1f}MB, Increase: {memory_increase:.1f}MB")
    
    def test_concurrent_agents_performance(self, temp_dir):
        """Benchmark concurrent agent performance."""
        import threading
        import concurrent.futures
        
        def create_and_run_agent(agent_id):
            mock_llm = Mock()
            mock_llm.complete.return_value = LLMResponseBuilder.text_response(f"Agent {agent_id} response")
            
            agent = Agent(name=f"concurrent_{agent_id}", llm=mock_llm)
            agent.history.save_dir = temp_dir
            
            start = time.time()
            for i in range(10):
                agent.input(f"Task {i}")
            end = time.time()
            
            return end - start
        
        # Run multiple agents concurrently
        start_total = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_and_run_agent, i) for i in range(5)]
            times = [future.result() for future in concurrent.futures.as_completed(futures)]
        end_total = time.time()
        
        total_time = end_total - start_total
        avg_agent_time = sum(times) / len(times)
        
        # Performance assertions
        assert total_time < 10, f"Total concurrent time too slow: {total_time:.3f}s"
        assert avg_agent_time < 5, f"Average agent time too slow: {avg_agent_time:.3f}s"
        
        print(f"Concurrent agents - Total: {total_time:.3f}s, "
              f"Avg per agent: {avg_agent_time:.3f}s")
    
    def test_large_file_processing_performance(self, temp_dir):
        """Benchmark large file processing performance."""
        # Create large file (5MB)
        large_file = os.path.join(temp_dir, "large_perf.txt")
        with open(large_file, "w") as f:
            for i in range(100000):
                f.write(f"This is line {i} with some substantial content to make it realistic.\n")
        
        file_size = os.path.getsize(large_file) / 1024 / 1024  # MB
        
        # Test ReadFile tool performance
        read_tool = ReadFile()
        
        start = time.time()
        result = read_tool.input(filepath=large_file)
        end = time.time()
        
        processing_time = end - start
        throughput = file_size / processing_time  # MB/s
        
        # Performance assertions
        assert processing_time < 2.0, f"Large file processing too slow: {processing_time:.3f}s"
        assert throughput > 1.0, f"Throughput too low: {throughput:.1f}MB/s"
        assert len(result) > 1000000, "Should have read substantial content"
        
        print(f"Large file processing - Size: {file_size:.1f}MB, "
              f"Time: {processing_time:.3f}s, Throughput: {throughput:.1f}MB/s")
    
    def test_calculator_complex_expressions_performance(self):
        """Benchmark calculator performance with complex expressions."""
        calc = Calculator()
        
        # Complex expressions of varying difficulty
        expressions = [
            "2 + 2",
            "(10 + 5) * 3 - 8",
            "((15 + 25) * (30 - 10)) / (5 + 5)",
            "2 ** 10 + 3 ** 8 - 4 ** 6",
            "(((1 + 2) * (3 + 4)) + ((5 + 6) * (7 + 8))) * ((9 + 10) / (11 - 1))"
        ]
        
        times = []
        for expr in expressions:
            start = time.time()
            for _ in range(100):  # Run each expression 100 times
                calc.input(expression=expr)
            end = time.time()
            times.append((end - start) / 100)  # Average time per execution
        
        max_time = max(times)
        avg_time = sum(times) / len(times)
        
        # Performance assertions
        assert max_time < 0.001, f"Max calculation time too slow: {max_time:.6f}s"
        assert avg_time < 0.0005, f"Average calculation time too slow: {avg_time:.6f}s"
        
        print(f"Calculator performance - Avg: {avg_time:.6f}s, Max: {max_time:.6f}s")


@pytest.mark.slow
@pytest.mark.benchmark
class TestStressTests:
    """Stress tests for ConnectOnion components."""
    
    def test_agent_stress_many_tasks(self, temp_dir):
        """Stress test agent with many sequential tasks."""
        mock_llm = Mock()
        responses = [LLMResponseBuilder.text_response(f"Response {i}") for i in range(1000)]
        mock_llm.complete.side_effect = responses
        
        agent = Agent(name="stress_test", llm=mock_llm)
        agent.history.save_dir = temp_dir
        
        start = time.time()
        for i in range(1000):
            agent.input(f"Task {i}")
        end = time.time()
        
        total_time = end - start
        avg_per_task = total_time / 1000
        
        # Stress test assertions
        assert total_time < 60, f"1000 tasks took too long: {total_time:.1f}s"
        assert avg_per_task < 0.1, f"Average per task too slow: {avg_per_task:.3f}s"
        assert len(agent.history.records) == 1000
        
        print(f"Stress test - 1000 tasks in {total_time:.1f}s, "
              f"avg {avg_per_task:.3f}s/task")
    
    def test_history_file_stress(self, temp_dir):
        """Stress test history file with many concurrent writes."""
        from connectonion.history import History
        import threading
        
        def write_records(history, start_id, count):
            for i in range(count):
                history.record(
                    user_prompt=f"Stress task {start_id}_{i}",
                    tool_calls=[],
                    result=f"Result {start_id}_{i}",
                    duration=0.1
                )
        
        # Create history instance
        history = History("stress_history", save_dir=temp_dir)
        
        # Run concurrent writes
        threads = []
        start = time.time()
        for thread_id in range(10):
            thread = threading.Thread(
                target=write_records, 
                args=(history, thread_id, 100)
            )
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        end = time.time()
        
        total_time = end - start
        
        # Verify all records were written
        assert len(history.records) == 1000
        assert total_time < 30, f"Concurrent writes took too long: {total_time:.1f}s"
        
        print(f"History stress test - 1000 concurrent records in {total_time:.1f}s")