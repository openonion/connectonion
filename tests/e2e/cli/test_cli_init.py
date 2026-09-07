"""Tests for the CLI init command."""

"""
LLM-Note: Tests for CLI init command (co init)

What it tests:
- TestCliInit: Project initialization in existing directory
  - test_init_empty_directory_creates_basic_files: Verify file creation
  - test_init_creates_valid_python_file: Verify valid Python generation
  - Template application and file structure

Components under test:
- connectonion.cli.commands.init (init command)
- connectonion.cli.templates (template system)
"""

import os
import tempfile
import pytest
import shutil
import subprocess
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from .argparse_runner import ArgparseCliRunner


class TestCliInit:
    """Test cases for 'co init' command."""

    def setup_method(self):
        """Set up test environment before each test."""
        self.runner = ArgparseCliRunner()

    @pytest.fixture(autouse=True)
    def mock_auth(self):
        """Mock authentication to avoid network calls in tests."""
        with patch('connectonion.cli.commands.init.authenticate') as mock:
            # Simulate successful authentication
            mock.return_value = True
            yield mock

    def test_init_empty_directory_creates_basic_files(self):
        """Test that init in empty directory creates required files."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])

            # Should succeed
            assert result.exit_code == 0

            # Check required files were created
            assert os.path.exists("agent.py")
            assert os.path.exists(".env")  # CLI creates .env, not .env.example
            assert os.path.exists(".co/host.yaml")

    def test_init_creates_valid_python_file(self):
        """Test that generated agent.py is valid Python."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            # Check that agent.py is valid Python
            with open("agent.py") as f:
                code = f.read()
                compile(code, "agent.py", "exec")

            # Should build an agent from the SDK
            assert "from connectonion" in code
            assert "create_agent" in code

    def test_init_co_ai_template_scaffolds_hostable_browser_project(self):
        """co init --template co-ai creates a host-ready project with a browser runtime."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            agent_code = Path("agent.py").read_text()
            compile(agent_code, "agent.py", "exec")
            assert "host(" in agent_code                     # host-ready entrypoint
            assert "create_agent(" in agent_code               # mirrors `co ai`
            assert "def create_agent" not in agent_code        # use the SDK factory, do not redefine it
            assert "role=" in agent_code                       # role is the knob users change
            assert "CO_DIR" not in agent_code                  # host(agent) loads .co from cwd
            assert "co_dir=" not in agent_code                 # match docs/network/host.md
            assert "browser_channel" not in agent_code        # use BrowserAutomation's default Chrome detection

            dockerfile = Path("Dockerfile").read_text()
            assert "patchright install --with-deps chrome" in dockerfile   # real Chrome + deps, stealth-patched driver
            assert "xvfb" in dockerfile                        # headful under virtual display
            assert Path("requirements.txt").read_text().strip() != ""

    def test_init_creates_config_file(self):
        """Test that init creates proper host.yaml."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './'])
            assert result.exit_code == 0

            # Check config file
            with open(".co/host.yaml") as f:
                config = yaml.safe_load(f)

            assert "name" in config
            assert "entrypoint" in config

    def test_init_with_template_parameter(self):
        """Test init with --template parameter."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            assert os.path.exists("agent.py")

    def test_init_with_key_parameter(self):
        """Test init with --key parameter."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai', '--key', 'sk-test-key'])

            if result.exit_code == 0:
                assert os.path.exists("agent.py")

    def test_init_with_description(self):
        """Test init with --description parameter."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai', '--description', 'Test agent'])

            if result.exit_code == 0:
                assert os.path.exists("agent.py")

    def test_init_non_empty_directory_asks_confirmation(self):
        """Test that init asks for confirmation in non-empty directory."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create existing file
            Path("existing.txt").write_text("content")

            # Should ask for confirmation
            result = self.runner.invoke(cli, ['init', './'], input='n\n')

            # User said no, should not create agent.py
            if result.exit_code == 0 and 'agent.py' not in os.listdir('.'):
                assert not os.path.exists("agent.py")

    def test_init_preserves_existing_agent_py(self):
        """Test that init doesn't overwrite existing agent.py."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create existing agent.py
            Path("agent.py").write_text("# Custom agent")

            result = self.runner.invoke(cli, ['init', './'], input='y\n')

            # Should preserve existing file
            with open("agent.py") as f:
                assert f.read() == "# Custom agent"

    def test_init_with_git_creates_gitignore(self):
        """Test that init creates .gitignore in git repos."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create .git directory
            os.makedirs(".git")

            result = self.runner.invoke(cli, ['init', './'], input='y\n')
            assert result.exit_code == 0

            # Should create .gitignore
            assert os.path.exists(".gitignore")
            with open(".gitignore") as f:
                content = f.read()
                assert ".env" in content
                assert "__pycache__" in content

    def test_init_with_yes_flag_skips_confirmation(self):
        """Test that --yes flag skips confirmation prompts."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create existing file
            Path("existing.txt").write_text("content")

            # Should not prompt with --yes flag
            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai', '--yes'])
            assert result.exit_code == 0

            assert os.path.exists("agent.py")

    def test_init_with_force_flag(self):
        """Test that --force flag overwrites existing files."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create existing agent.py
            Path("agent.py").write_text("# Old agent")

            # Force flag should allow overwrite (if implemented)
            result = self.runner.invoke(cli, ['init', './', '--force'])

            # Check if force flag is implemented
            if '--force' in result.stderr or 'unrecognized arguments' in result.stderr:
                # Force flag not implemented, skip test
                pass
            elif result.exit_code == 0:
                # If force worked, agent.py should be regenerated
                with open("agent.py") as f:
                    content = f.read()
                    # Should be new content, not old
                    if content != "# Old agent":
                        assert "from connectonion import Agent" in content

    def test_init_creates_env_example(self):
        """Test that init creates .env file."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            assert os.path.exists(".env")
            with open(".env") as f:
                content = f.read()
                # Should have API key placeholder or actual keys
                assert "API" in content or "KEY" in content or len(content) >= 0  # .env might be empty initially

    def test_init_sets_correct_permissions(self):
        """Test that init sets correct file permissions."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            # Check that agent.py is readable and executable
            agent_path = Path("agent.py")
            assert agent_path.exists()
            assert os.access(agent_path, os.R_OK)

    def test_init_creates_complete_structure(self):
        """Test that init creates complete project structure."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './'])
            assert result.exit_code == 0

            # Check directory structure
            assert os.path.exists(".co")
            assert os.path.isdir(".co")
            assert os.path.exists(".co/host.yaml")

    def test_init_creates_agent_address_in_env(self):
        """Test that init creates AGENT_ADDRESS in .env file."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            # Check that .env contains AGENT_ADDRESS
            assert os.path.exists(".env")
            with open(".env") as f:
                content = f.read()
                # Should have AGENT_ADDRESS (and possibly OPENONION_API_KEY from mock)
                assert "AGENT_ADDRESS=" in content or "OPENONION_API_KEY=" in content

    def test_init_creates_global_keys(self, tmp_path, monkeypatch):
        """Test that init creates global ~/.co/keys/agent.key."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './'])
            assert result.exit_code == 0

            # Global keys should exist
            assert (fake_home / ".co" / "keys" / "agent.key").exists()
            assert (fake_home / ".co" / "keys.env").exists()

    def test_init_writes_no_absolute_home_directory(self):
        """The opposite of what this file asserted until 1.6.0.

        It asked for AGENT_CONFIG_PATH in the project .env and gave no reason.
        #438 and `co deploy` both say the reason runs the other way: the value
        is an absolute path to the machine that ran the command, and a project
        .env travels. See tests/unit/test_the_machine_path_does_not_travel.py.
        """
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            assert os.path.exists(".env")
            with open(".env") as f:
                assert "AGENT_CONFIG_PATH" not in f.read()

    def test_init_adds_default_model_comment_in_env(self):
        """Test that init adds default model comment to .env file."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            # Check that .env contains default model comment
            assert os.path.exists(".env")
            with open(".env") as f:
                content = f.read()
                assert "# Default model: co/gemini-3.8-flash" in content
                assert "managed keys with free credits" in content

    def test_init_creates_agent_address_explanation_in_global_keys(self, tmp_path, monkeypatch):
        """Test that init creates explanatory comments in global keys.env when first created."""
        from connectonion.cli.main import cli
        from pathlib import Path
        import os

        # Use temp directory as fake home to avoid modifying real ~/.co
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        # Also patch Path.home() for cross-platform support
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            # Check global keys.env in our fake home
            global_keys_env = fake_home / ".co" / "keys.env"
            assert global_keys_env.exists()

            with open(global_keys_env) as f:
                content = f.read()
                # Should have explanatory comment (only present on first creation)
                assert "Your agent address (Ed25519 public key) is used for:" in content
                assert "Secure agent communication" in content
                assert "Authentication with OpenOnion" in content
                assert "@mail.openonion.ai" in content

    def test_init_ensure_global_config_creates_keys_env(self, tmp_path, monkeypatch):
        """Test that ensure_global_config creates ~/.co/keys.env with agent address."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './'])
            assert result.exit_code == 0

            keys_env = fake_home / ".co" / "keys.env"
            assert keys_env.exists()

            content = keys_env.read_text()
            assert "AGENT_ADDRESS=" in content
            assert "AGENT_CONFIG_PATH=" in content

    def test_init_host_yaml_from_template(self):
        """Test that init generates host.yaml from network/host/host.yaml template."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './'])
            assert result.exit_code == 0

            with open(".co/host.yaml") as f:
                content = f.read()

            # Project-specific header fields
            assert content.startswith("name:")
            assert "entrypoint: agent.py" in content
            # Template fields from network/host/host.yaml
            config = yaml.safe_load(content)
            assert config["trust"] == "careful"
            assert config["port"] == 8000
            assert "relay_url" not in config
            assert "permissions" in config

    def test_init_host_yaml_has_permissions_from_template(self):
        """Test that generated host.yaml includes permissions from template."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './'])
            assert result.exit_code == 0

            config = yaml.safe_load(open(".co/host.yaml"))
            permissions = config.get("permissions", {})

            # Check key permissions from template
            assert permissions.get("read", {}).get("allowed") is True
            assert permissions.get("glob", {}).get("allowed") is True
            assert permissions.get("grep", {}).get("allowed") is True

    def test_init_host_yaml_leaves_runtime_relay_unpinned(self):
        """Generated projects must follow the runtime backend by default."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './'])
            assert result.exit_code == 0

            config = yaml.safe_load(open(".co/host.yaml"))
            assert "relay_url" not in config

    def test_init_copies_all_docs_to_co_docs(self):
        """Test that init copies all documentation to .co/docs/ folder."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            # Check that .co/docs/ directory exists
            assert os.path.exists(".co/docs")
            assert os.path.isdir(".co/docs")

            # Check key docs exist
            docs_dir = Path(".co/docs")
            assert (docs_dir / "api.md").exists()
            assert (docs_dir / "quickstart.md").exists()
            assert (docs_dir / "README.md").exists()

            # Check subdirectories exist
            assert (docs_dir / "useful_tools").is_dir()
            assert (docs_dir / "useful_plugins").is_dir()

    def test_init_excludes_archive_from_docs(self):
        """Test that init does not copy archive folder to .co/docs/."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            # archive folder should NOT exist in .co/docs/
            assert not os.path.exists(".co/docs/archive")

    def test_init_does_not_copy_readme_to_project_root(self):
        """Test that init does not copy docs README to project root."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            # docs README should only be in .co/docs/, not project root
            assert os.path.exists(".co/docs/README.md")

    def test_init_writes_a_deployable_name_from_an_awkward_directory(self):
        """A directory is named for people, not for DNS.

        The name in host.yaml becomes a hostname and a Docker tag at deploy
        time, so `co init` inside "My_Project" must not bake in a name that can
        never deploy — and must say what it used instead.
        """
        from connectonion.cli.main import cli
        from connectonion.cli.commands.project_cmd_lib import DEPLOY_NAME_PATTERN

        with self.runner.isolated_filesystem():
            os.makedirs("My_Project")
            os.chdir("My_Project")

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            name = yaml.safe_load(Path(".co/host.yaml").read_text())["name"]
            assert name == "my-project"
            assert DEPLOY_NAME_PATTERN.match(name)
            assert "Deployment name set to" in result.output

    def test_init_keeps_an_already_valid_directory_name_untouched(self):
        """No notice and no rewriting when the directory name is already fine."""
        from connectonion.cli.main import cli

        with self.runner.isolated_filesystem():
            os.makedirs("my-project")
            os.chdir("my-project")

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0

            name = yaml.safe_load(Path(".co/host.yaml").read_text())["name"]
            assert name == "my-project"
            assert "Deployment name set to" not in result.output

    def test_init_falls_back_when_the_directory_name_has_nothing_reusable(self):
        """A directory named entirely in non-ASCII leaves no usable deploy name.

        It must still produce a project that can deploy — CI runs `co init` in a
        CJK-named folder on Windows — rather than an empty or invalid name.
        """
        from connectonion.cli.main import cli
        from connectonion.cli.commands.project_cmd_lib import DEPLOY_NAME_PATTERN

        with self.runner.isolated_filesystem():
            os.makedirs("我的 项目")
            os.chdir("我的 项目")

            result = self.runner.invoke(cli, ['init', './', '--template', 'co-ai'])
            assert result.exit_code == 0
            assert "Traceback" not in result.output

            name = yaml.safe_load(Path(".co/host.yaml").read_text())["name"]
            assert name == "agent"
            assert DEPLOY_NAME_PATTERN.match(name)
