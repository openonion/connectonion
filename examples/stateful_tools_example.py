#!/usr/bin/env python3
"""
Example: Stateful Tools with ConnectOnion

This example demonstrates how to use class instances as tools, enabling
shared state between tool calls. This is useful for scenarios like:
- Web scraping (shared browser session)
- Database operations (shared connection)
- File processing (maintaining file handles)
- API clients (maintaining authentication)
"""

from connectonion import Agent
import time
import json


class WebScraper:
    """Web scraping tools that share browser state."""
    
    def __init__(self):
        self.current_url = None
        self.page_data = []
        self.session_active = False
    
    def start_session(self) -> str:
        """Start a web scraping session."""
        self.session_active = True
        return "Web scraping session started"
    
    def navigate(self, url: str) -> str:
        """Navigate to a URL."""
        if not self.session_active:
            return "Error: Session not started. Please start session first."
        
        self.current_url = url
        return f"Navigated to {url}"
    
    def scrape_data(self, data_type: str) -> str:
        """Scrape specific type of data from current page."""
        if not self.current_url:
            return "Error: No page loaded. Please navigate to a URL first."
        
        # Simulate scraping different types of data
        if data_type == "title":
            scraped = f"Title of {self.current_url}"
        elif data_type == "links":
            scraped = f"5 links found on {self.current_url}"
        elif data_type == "images":
            scraped = f"3 images found on {self.current_url}"
        else:
            scraped = f"Unknown data type: {data_type}"
        
        self.page_data.append({
            'url': self.current_url,
            'type': data_type,
            'data': scraped,
            'timestamp': time.time()
        })
        
        return scraped
    
    def get_session_summary(self) -> str:
        """Get summary of scraping session."""
        if not self.page_data:
            return "No data scraped yet"
        
        summary = {
            'pages_visited': len(set(item['url'] for item in self.page_data)),
            'total_items': len(self.page_data),
            'current_url': self.current_url,
            'session_active': self.session_active
        }
        
        return f"Session summary: {json.dumps(summary, indent=2)}"


class DatabaseManager:
    """Database tools that share connection state."""
    
    def __init__(self):
        self.connected = False
        self.queries_executed = []
        self.transaction_active = False
    
    def connect(self) -> str:
        """Connect to database."""
        self.connected = True
        return "Connected to database"
    
    def begin_transaction(self) -> str:
        """Begin a database transaction."""
        if not self.connected:
            return "Error: Not connected to database"
        
        self.transaction_active = True
        return "Transaction started"
    
    def execute_query(self, sql: str) -> str:
        """Execute a SQL query."""
        if not self.connected:
            return "Error: Not connected to database"
        
        # Simulate query execution
        result = f"Query executed: {sql}"
        self.queries_executed.append({
            'sql': sql,
            'timestamp': time.time(),
            'in_transaction': self.transaction_active
        })
        
        return result
    
    def commit_transaction(self) -> str:
        """Commit current transaction."""
        if not self.transaction_active:
            return "Error: No active transaction"
        
        self.transaction_active = False
        return "Transaction committed"
    
    def get_query_history(self) -> str:
        """Get history of executed queries."""
        if not self.queries_executed:
            return "No queries executed yet"
        
        history = []
        for query in self.queries_executed:
            history.append(f"- {query['sql']} (transaction: {query['in_transaction']})")
        
        return "Query history:\n" + "\n".join(history)


def simple_calculator(expression: str) -> str:
    """Simple calculator function (stateless tool)."""
    try:
        result = eval(expression)  # Don't use eval in production!
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {e}"


def demo_web_scraping():
    """Demonstrate web scraping with shared state."""
    print("=== Web Scraping Demo ===")
    
    # Create scraper instance
    scraper = WebScraper()
    
    # Create agent with scraper as tools
    agent = Agent(
        name="web_scraper", 
        tools=scraper,  # Pass class instance directly!
        system_prompt="You are a web scraping assistant. Follow user instructions step by step.",
        max_iterations=12,  # Web scraping often needs multiple steps
        api_key="fake_key_for_demo"  # Just for demo - won't actually call LLM
    )
    
    print(f"Agent has {len(agent.tools)} tools available:")
    for tool_name in agent.tool_map.keys():
        print(f"  - {tool_name}")
    
    # Demonstrate manual tool usage (since we can't call the LLM without a real key)
    print("\n--- Simulating Agent Tool Calls ---")
    
    # Call tools directly to show state sharing
    result1 = agent.tool_map['start_session']()
    print(f"1. start_session(): {result1}")
    
    result2 = agent.tool_map['navigate'](url="https://example.com")
    print(f"2. navigate(): {result2}")
    
    result3 = agent.tool_map['scrape_data'](data_type="title")
    print(f"3. scrape_data(): {result3}")
    
    result4 = agent.tool_map['scrape_data'](data_type="links")
    print(f"4. scrape_data(): {result4}")
    
    result5 = agent.tool_map['get_session_summary']()
    print(f"5. get_session_summary(): {result5}")
    
    print("\n--- Scraper State After Tool Calls ---")
    print(f"Current URL: {scraper.current_url}")
    print(f"Data collected: {len(scraper.page_data)} items")
    print(f"Session active: {scraper.session_active}")
    
    # User can still access and manipulate the scraper directly
    print("\n--- Direct Access to Scraper ---")
    print("All scraped data:")
    for item in scraper.page_data:
        print(f"  {item}")


def demo_mixed_tools():
    """Demonstrate mixing stateful and stateless tools."""
    print("\n=== Mixed Tools Demo ===")
    
    # Create instances
    db = DatabaseManager()
    scraper = WebScraper()
    
    # Create agent with mixed tools: class instances AND functions
    agent = Agent(
        name="mixed_agent",
        tools=[db, scraper, simple_calculator],  # Mix everything!
        system_prompt="You are a versatile assistant with database, web scraping, and calculation capabilities.",
        max_iterations=15,  # Complex data operations need more iterations
        api_key="fake_key_for_demo"  # Just for demo
    )
    
    print(f"Agent has {len(agent.tools)} tools available:")
    for tool_name in agent.tool_map.keys():
        print(f"  - {tool_name}")
    
    # Demonstrate tool usage without calling LLM
    print("\n--- Simulating Mixed Tool Calls ---")
    calc_result = agent.tool_map['simple_calculator'](expression="2+2*3")
    print(f"Calculator: {calc_result}")
    
    db_result = agent.tool_map['connect']()
    print(f"Database: {db_result}")
    
    scraper_result = agent.tool_map['start_session']()
    print(f"Scraper: {scraper_result}")
    
    print("\n--- State After Mixed Operations ---")
    print(f"Database connected: {db.connected}")
    print(f"Scraper session active: {scraper.session_active}")


def demo_resource_cleanup():
    """Demonstrate resource cleanup patterns."""
    print("\n=== Resource Cleanup Demo ===")
    
    class FileProcessor:
        def __init__(self):
            self.files_opened = []
            self.processing_active = False
        
        def open_file(self, filename: str) -> str:
            """Open a file for processing."""
            self.files_opened.append(filename)
            self.processing_active = True
            return f"Opened file: {filename}"
        
        def process_data(self, operation: str) -> str:
            """Process data in opened files."""
            if not self.processing_active:
                return "Error: No files opened"
            
            return f"Performed {operation} on {len(self.files_opened)} files"
        
        def cleanup(self):
            """Cleanup resources (user calls this manually)."""
            self.files_opened.clear()
            self.processing_active = False
            print("Resources cleaned up!")
    
    processor = FileProcessor()
    agent = Agent(
        name="file_agent", 
        tools=processor, 
        max_iterations=8,  # File operations usually don't need many iterations
        api_key="fake_key_for_demo"
    )
    
    # Demonstrate tool usage
    print("\n--- Simulating File Processing ---")
    result1 = agent.tool_map['open_file'](filename="data.txt")
    print(f"1. {result1}")
    
    result2 = agent.tool_map['open_file'](filename="report.csv")
    print(f"2. {result2}")
    
    result3 = agent.tool_map['process_data'](operation="analyze")
    print(f"3. {result3}")
    
    print(f"Files opened: {processor.files_opened}")
    print(f"Processing active: {processor.processing_active}")
    
    # User controls cleanup
    processor.cleanup()


if __name__ == "__main__":
    # Note: This example uses mock implementations
    # In real usage, you'd integrate with actual libraries like:
    # - playwright for web scraping
    # - psycopg2 for PostgreSQL
    # - requests for API calls
    # etc.
    
    demo_web_scraping()
    demo_mixed_tools()
    demo_resource_cleanup()
    
    print("\n=== Key Benefits Demonstrated ===")
    print("✅ Methods share state through 'self'")
    print("✅ User has full access to object state")
    print("✅ Can mix stateful and stateless tools")
    print("✅ Clean resource management patterns")
    print("✅ No magic - just regular Python classes!")