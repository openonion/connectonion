"""Performance benchmarks for ConnectOnion."""

import pytest
import time
import psutil
import os
from unittest.mock import Mock
from connectonion import Agent
from tests.fixtures.test_tools import calculator, current_time, read_file
from tests.utils.mock_helpers import LLMResponseBuilder, MockLLM


@pytest.mark.benchmark
class TestPerformanceBenchmarks:
    """Performance benchmarks for ConnectOnion components."""
    
    def test_agent_response_time_simple(self, temp_dir):
        """Benchmark simple agent response time."""
        # Mock fast LLM response - need 10 responses for 10 runs
        responses = [LLMResponseBuilder.text_response("Quick response") for _ in range(10)]
        mock_llm = MockLLM(responses=responses)

        # Create agent
        agent = Agent(name="perf_simple", llm=mock_llm, log=False)

        # Benchmark multiple runs
        times = []
        for _ in range(10):
            start = time.time()
            agent.input("Simple task")
            end = time.time()
            times.append(end - start)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # Log timing for observability (no strict assertions - timing varies by machine)
        print(f"Simple response - Avg: {avg_time:.3f}s, Max: {max_time:.3f}s")
        # Only fail if extremely slow (>5s indicates something broken, not just slow machine)
        assert avg_time < 5.0, f"Response took way too long: {avg_time:.3f}s - likely broken"
    
    def test_agent_response_time_with_tools(self, temp_dir):
        """Benchmark agent response time with tool usage."""
        # Mock LLM with tool calling - need 2 responses per run (tool call + final), 10 runs
        responses = []
        for _ in range(10):
            responses.append(LLMResponseBuilder.tool_call_response("calculator", {"expression": "2 + 2"}))
            responses.append(LLMResponseBuilder.text_response("The result is 4"))
        mock_llm = MockLLM(responses=responses)

        # Create agent with tools
        agent = Agent(name="perf_tools", llm=mock_llm, tools=[calculator], log=False)

        # Benchmark multiple runs
        times = []
        for _ in range(10):
            start = time.time()
            agent.input("Calculate something")
            end = time.time()
            times.append(end - start)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # Log timing for observability (no strict assertions - timing varies by machine)
        print(f"Tool response - Avg: {avg_time:.3f}s, Max: {max_time:.3f}s")
        # Only fail if extremely slow (>5s indicates something broken, not just slow machine)
        assert avg_time < 5.0, f"Response took way too long: {avg_time:.3f}s - likely broken"
    
    @pytest.mark.skip(reason="History class removed")
    def test_history_file_write_performance(self, temp_dir):
        """Benchmark history file writing performance."""

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

        # Create and use agent - need 50 responses for 50 runs
        responses = [LLMResponseBuilder.text_response("Response") for _ in range(50)]
        mock_llm = MockLLM(responses=responses)

        agent = Agent(name="memory_test", llm=mock_llm, tools=[calculator, current_time], log=False)

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
            # Each agent needs 10 responses for 10 runs
            responses = [LLMResponseBuilder.text_response(f"Agent {agent_id} response") for _ in range(10)]
            mock_llm = MockLLM(responses=responses)

            agent = Agent(name=f"concurrent_{agent_id}", llm=mock_llm, log=False)

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

        # Test read_file function performance
        start = time.time()
        result = read_file(filepath=large_file)
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
        # calculator is a function, call it directly

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
                calculator(expression=expr)
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
        responses = [LLMResponseBuilder.text_response(f"Response {i}") for i in range(1000)]
        mock_llm = MockLLM(responses=responses)

        agent = Agent(name="stress_test", llm=mock_llm, log=False)

        start = time.time()
        for i in range(1000):
            agent.input(f"Task {i}")
        end = time.time()

        total_time = end - start
        avg_per_task = total_time / 1000

        # Stress test assertions (120s threshold for slower CI runners)
        assert total_time < 120, f"1000 tasks took too long: {total_time:.1f}s"
        assert avg_per_task < 0.2, f"Average per task too slow: {avg_per_task:.3f}s"
        # History removed

        print(f"Stress test - 1000 tasks in {total_time:.1f}s, "
              f"avg {avg_per_task:.3f}s/task")
    
    @pytest.mark.skip(reason="History class removed")
    def test_history_file_stress(self, temp_dir):
        """Stress test history file with many concurrent writes."""
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