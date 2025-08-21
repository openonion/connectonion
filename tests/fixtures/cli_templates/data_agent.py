"""Data Analysis Agent Template"""

from connectonion import Agent
import json
from typing import List, Dict, Any


def analyze_data(data: str) -> str:
    """Analyze numerical data and provide statistics."""
    try:
        # Try to parse as JSON list of numbers
        numbers = json.loads(data)
        if not isinstance(numbers, list) or not all(isinstance(x, (int, float)) for x in numbers):
            return "Error: Please provide data as a JSON list of numbers, e.g., [1, 2, 3, 4, 5]"
        
        if not numbers:
            return "Error: Cannot analyze empty dataset"
        
        # Calculate basic statistics
        total = sum(numbers)
        count = len(numbers)
        mean = total / count
        sorted_nums = sorted(numbers)
        
        # Median
        if count % 2 == 0:
            median = (sorted_nums[count//2 - 1] + sorted_nums[count//2]) / 2
        else:
            median = sorted_nums[count//2]
        
        # Min, max
        minimum = min(numbers)
        maximum = max(numbers)
        
        return f"""Data Analysis Results:
        • Count: {count}
        • Sum: {total}
        • Mean: {mean:.2f}
        • Median: {median}
        • Min: {minimum}
        • Max: {maximum}
        • Range: {maximum - minimum}"""
        
    except json.JSONDecodeError:
        return "Error: Please provide data as valid JSON, e.g., [1, 2, 3, 4, 5]"
    except Exception as e:
        return f"Error analyzing data: {str(e)}"


def create_chart(data: str, chart_type: str = "bar") -> str:
    """Create a simple text-based chart visualization."""
    try:
        numbers = json.loads(data)
        if not isinstance(numbers, list) or not all(isinstance(x, (int, float)) for x in numbers):
            return "Error: Please provide data as a JSON list of numbers"
        
        if not numbers:
            return "Error: Cannot chart empty dataset"
        
        # Simple text bar chart
        max_val = max(numbers)
        chart_lines = []
        
        chart_lines.append(f"Text {chart_type.title()} Chart:")
        chart_lines.append("-" * 30)
        
        for i, val in enumerate(numbers):
            bar_length = int((val / max_val) * 20) if max_val > 0 else 0
            bar = "█" * bar_length
            chart_lines.append(f"{i+1:2d}: {bar} {val}")
        
        return "\n".join(chart_lines)
        
    except json.JSONDecodeError:
        return "Error: Please provide data as valid JSON"
    except Exception as e:
        return f"Error creating chart: {str(e)}"


def load_csv_data(filename: str) -> str:
    """Load and preview CSV data (simulated for this template)."""
    # In a real implementation, this would use pandas or csv module
    return f"""CSV Data Preview for '{filename}':
    (This is a simulated preview)
    
    Rows: 100
    Columns: 5
    Column names: Name, Age, Score, Category, Date
    
    Sample data:
    | Name    | Age | Score | Category | Date       |
    |---------|-----|-------|----------|------------|
    | Alice   | 25  | 85.5  | A        | 2024-01-15 |
    | Bob     | 30  | 92.3  | B        | 2024-01-16 |
    | Charlie | 28  | 78.9  | A        | 2024-01-17 |
    
    Use analyze_data() with a JSON list to perform statistical analysis."""


def export_results(results: str, format: str = "json") -> str:
    """Export analysis results in different formats."""
    timestamp = "2024-01-20 10:30:00"  # In real implementation, use datetime.now()
    
    if format.lower() == "json":
        return f"""Results exported as JSON:
        {{
            "timestamp": "{timestamp}",
            "analysis": "{results.replace(chr(10), '\\n')}",
            "format": "json"
        }}"""
    elif format.lower() == "csv":
        return f"""Results exported as CSV:
        timestamp,analysis_type,results
        {timestamp},statistical_analysis,"{results.replace(chr(10), ' | ')}" """
    else:
        return f"Exported results in {format} format at {timestamp}"


# Create a data analysis agent
# ConnectOnion best practice: Always use markdown files for system prompts
agent = Agent(
    name="data_analyst",
    system_prompt="prompt.md",  # System prompt loaded from markdown for better organization
    tools=[analyze_data, create_chart, load_csv_data, export_results]
)


if __name__ == "__main__":
    print("📊 Data Analysis Agent Ready!")
    print("I can help you analyze data, create charts, and export results.")
    print("Available tools:", agent.list_tools())
    
    # Example usage
    sample_data = "[10, 15, 8, 22, 18, 12, 25, 30, 7, 20]"
    print(f"\n🔍 Example analysis with sample data: {sample_data}")
    
    result = agent.input(f"Please analyze this data and create a chart: {sample_data}")
    print(f"\nAnalysis result:\n{result}")