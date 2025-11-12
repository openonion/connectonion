"""Test configuration for ConnectOnion tests."""

import os
from pathlib import Path

# Fixed test account details
TEST_ACCOUNT = {
    "public_key": "04e1c4ae3c57d716383153479dae869e51e86d43d88db8dfa22fba7533f3968d",
    "private_key": "test_private_key_do_not_use_in_production",
    "address": "0x04e1c4ae3c57d716383153479dae869e51e86d43d88db8dfa22fba7533f3968d",
    "short_address": "0x04e1c4ae",
    "email": "0x04e1c4ae@mail.openonion.ai",
    "email_active": True
}

# Test JWT token (for testing only, not valid for production)
TEST_JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJwdWJsaWNfa2V5IjoiMDRlMWM0YWUzYzU3ZDcxNjM4MzE1MzQ3OWRhZTg2OWU1MWU4NmQ0M2Q4OGRiOGRmYTIyZmJhNzUzM2YzOTY4ZCIsImV4cCI6OTk5OTk5OTk5OX0.test_signature"

# Test backend URL - defaults to production for real API tests
TEST_BACKEND_URL = os.getenv("TEST_BACKEND_URL", "https://oo.openonion.ai")

# Test configuration for .co directory
TEST_CONFIG_TOML = {
    "project": {
        "name": "test-project",
        "created": "2024-01-01T00:00:00",
        "framework_version": "0.0.5",
    },
    "cli": {
        "version": "1.0.0",
        "command": "co init",
        "template": "test",
    },
    "agent": {
        "address": TEST_ACCOUNT["address"],
        "short_address": TEST_ACCOUNT["short_address"],
        "email": TEST_ACCOUNT["email"],
        "email_active": TEST_ACCOUNT["email_active"],
        "created_at": "2024-01-01T00:00:00",
        "algorithm": "ed25519",
        "default_model": "gpt-4o-mini",
        "max_iterations": 10,
    },
    "auth": {
        "token": TEST_JWT_TOKEN,
        "public_key": TEST_ACCOUNT["public_key"],
        "authenticated_at": "2024-01-01T00:00:00"
    }
}

# Sample test emails
SAMPLE_EMAILS = [
    {
        "id": "msg_test_001",
        "from": "alice@example.com",
        "subject": "Test Email 1",
        "message": "This is test email number 1",
        "timestamp": "2024-01-15T10:00:00Z",
        "read": False
    },
    {
        "id": "msg_test_002",
        "from": "bob@example.com",
        "subject": "Test Email 2",
        "message": "This is test email number 2",
        "timestamp": "2024-01-15T11:00:00Z",
        "read": True
    },
    {
        "id": "msg_test_003",
        "from": "charlie@example.com",
        "subject": "Urgent: Test Email 3",
        "message": "This is an urgent test email",
        "timestamp": "2024-01-15T12:00:00Z",
        "read": False
    }
]


def create_test_project(base_dir: Path = None) -> Path:
    """Create a test ConnectOnion project with fixed test account.
    
    Args:
        base_dir: Base directory to create project in. Uses temp dir if None.
        
    Returns:
        Path to the created project directory
    """
    import tempfile
    import toml
    
    if base_dir is None:
        base_dir = Path(tempfile.mkdtemp(prefix="co_test_"))
    else:
        base_dir = Path(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
    
    # Create .co directory structure
    co_dir = base_dir / ".co"
    co_dir.mkdir(exist_ok=True)
    
    keys_dir = co_dir / "keys"
    keys_dir.mkdir(exist_ok=True)
    
    # Write test config
    config_path = co_dir / "config.toml"
    with open(config_path, "w") as f:
        toml.dump(TEST_CONFIG_TOML, f)
    
    # Write test keys (for testing only)
    public_key_path = keys_dir / "public_key.txt"
    public_key_path.write_text(TEST_ACCOUNT["public_key"])
    
    private_key_path = keys_dir / "private_key.txt"
    private_key_path.write_text(TEST_ACCOUNT["private_key"])
    
    # Create a sample agent.py
    agent_file = base_dir / "agent.py"
    agent_file.write_text("""#!/usr/bin/env python3
\"\"\"Test agent for ConnectOnion.\"\"\"

from connectonion import Agent, send_email, get_emails, mark_read

def main():
    agent = Agent(
        "test-agent",
        tools=[send_email, get_emails, mark_read],
        model="gpt-4o-mini"
    )
    
    # Test email functionality
    emails = get_emails()
    print(f"Found {len(emails)} emails")
    
    for email in emails[:3]:
        print(f"- {email['from']}: {email['subject']}")

if __name__ == "__main__":
    main()
""")
    
    # Don't create a fake .env - use environment variables from tests/.env
    # The tests/.env file is loaded by the module-level load_dotenv in __init__.py
    # and re-loaded by ProjectHelper.__enter__() to ensure test env vars are available
    
    return base_dir


def cleanup_test_project(project_dir: Path):
    """Clean up a test project directory.
    
    Args:
        project_dir: Path to the project directory to clean up
    """
    import shutil
    
    if project_dir.exists() and ".co" in os.listdir(project_dir):
        shutil.rmtree(project_dir)


# Context manager for test projects
class ProjectHelper:
    """Context manager for creating and cleaning up test projects."""
    
    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir
        self.project_dir = None
        self.original_cwd = None
    
    def __enter__(self):
        import os
        from dotenv import load_dotenv
        from pathlib import Path
        self.original_cwd = os.getcwd()
        self.project_dir = create_test_project(self.base_dir)
        os.chdir(self.project_dir)
        # Load environment variables from tests/.env
        # This ensures real API keys are available for integration tests
        tests_env = Path(__file__).parent.parent / ".env"
        if tests_env.exists():
            load_dotenv(tests_env, override=True)
        return self.project_dir
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import os
        os.chdir(self.original_cwd)
        if self.project_dir and self.project_dir.exists():
            cleanup_test_project(self.project_dir)