"""Tests for new CLI create command and updated init command."""

import os
import tempfile
import shutil
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
import pytest
import re


class TestCliCreate:
    """Test the co create command."""
    
    def setup_method(self):
        """Setup test environment."""
        self.runner = CliRunner()
        
    def test_create_with_name_creates_directory(self):
        """Test that create with name creates a new directory."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            # Create project with name
            result = self.runner.invoke(cli, ['create', 'my-agent'], 
                                       input='n\nminimal\n')  # No AI, minimal template
            assert result.exit_code == 0
            
            # Check directory was created
            assert os.path.exists('my-agent')
            assert os.path.exists('my-agent/agent.py')
            assert os.path.exists('my-agent/.env')
            assert os.path.exists('my-agent/.co/config.toml')
            assert os.path.exists('my-agent/.co/keys/')
            
    def test_create_without_name_prompts(self):
        """Test that create without name prompts for project name."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            # Create project without name (interactive)
            result = self.runner.invoke(cli, ['create'], 
                                       input='test-project\nn\nminimal\n')
            assert result.exit_code == 0
            
            # Check directory was created with provided name
            assert os.path.exists('test-project')
            assert os.path.exists('test-project/agent.py')
            
    def test_create_ai_enabled_shows_custom_option(self):
        """Test that enabling AI shows custom template option."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            # Mock AI generation
            with patch('connectonion.cli.commands.project_commands.generate_custom_template') as mock_gen:
                mock_gen.return_value = "# Generated agent code"
                
                result = self.runner.invoke(cli, ['create', 'ai-agent'],
                    input='y\nsk-proj-test123\ncustom\nI want a slack bot\n')
                
                # Should show custom option and accept it
                assert 'Custom' in result.output
                assert 'Generating custom template' in result.output or result.exit_code == 0
                
    def test_create_no_ai_hides_custom_option(self):
        """Test that disabling AI doesn't show custom template."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            result = self.runner.invoke(cli, ['create', 'simple-agent'],
                                       input='n\n')  # No AI
            
            # Should not show custom option
            assert 'Custom' not in result.output or 'custom' not in result.output.lower()
            
    def test_api_key_detection_openai(self):
        """Test API key detection for OpenAI."""
        from connectonion.cli.commands.project_commands import detect_api_provider
        
        # Test OpenAI formats
        provider, key_type = detect_api_provider('sk-1234567890abcdef')
        assert provider == 'openai'
        
        provider, key_type = detect_api_provider('sk-proj-1234567890abcdef')
        assert provider == 'openai'
        assert key_type == 'project'
        
    def test_api_key_detection_anthropic(self):
        """Test API key detection for Anthropic."""
        from connectonion.cli.commands.project_commands import detect_api_provider
        
        provider, _ = detect_api_provider('sk-ant-api03-xxx')
        assert provider == 'anthropic'
        
    def test_api_key_detection_google(self):
        """Test API key detection for Google."""
        from connectonion.cli.commands.project_commands import detect_api_provider
        
        provider, _ = detect_api_provider('AIzaSyAbc123def456')
        assert provider == 'google'
        
    def test_api_key_detection_groq(self):
        """Test API key detection for Groq."""
        from connectonion.cli.commands.project_commands import detect_api_provider
        
        provider, _ = detect_api_provider('gsk_abc123def456')
        assert provider == 'groq'
        
    def test_create_with_all_flags(self):
        """Test create with all command-line flags."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            result = self.runner.invoke(cli, [
                'create', 'flagged-agent',
                '--no-ai',
                '--template', 'minimal',
                '--yes'
            ])
            assert result.exit_code == 0
            assert os.path.exists('flagged-agent')
            
    def test_create_directory_exists_error(self):
        """Test that create fails if directory already exists."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            # Create directory first
            os.makedirs('existing-dir')
            
            result = self.runner.invoke(cli, ['create', 'existing-dir'],
                                       input='n\nminimal\n')
            
            # Should show error
            assert 'already exists' in result.output.lower() or result.exit_code != 0
            
    def test_templates_structure(self):
        """Test that templates have correct structure."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            # Test minimal template
            result = self.runner.invoke(cli, ['create', 'minimal-test'],
                                       input='n\nminimal\n')
            assert result.exit_code == 0
            assert os.path.exists('minimal-test/agent.py')
            
            # Clean up
            shutil.rmtree('minimal-test')
            
            # Test web-research template
            result = self.runner.invoke(cli, ['create', 'research-test'],
                                       input='n\nweb-research\n')
            assert result.exit_code == 0
            assert os.path.exists('research-test/agent.py')
            

class TestCliInitUpdated:
    """Test the updated co init command."""
    
    def setup_method(self):
        """Setup test environment."""
        self.runner = CliRunner()
        
    def test_init_uses_current_directory(self):
        """Test that init uses current directory name."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            # Create and enter directory
            os.makedirs('my-project')
            os.chdir('my-project')
            
            result = self.runner.invoke(cli, ['init'],
                                       input='n\nminimal\n')
            assert result.exit_code == 0
            
            # Should use current directory
            assert os.path.exists('agent.py')
            assert os.path.exists('.co/config.toml')
            
            # Check project name in config
            import toml
            with open('.co/config.toml') as f:
                config = toml.load(f)
                assert config['project']['name'] == 'my-project'
                
    def test_init_backward_compatibility_meta_agent(self):
        """Test that old meta-agent template still works."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            # Use old-style command
            result = self.runner.invoke(cli, ['init', '--template', 'meta-agent'])
            assert result.exit_code == 0
            
            # Should create meta-agent template files
            assert os.path.exists('agent.py')
            assert os.path.exists('prompts/')
            assert os.path.exists('prompts/metagent.md')
            
    def test_init_ai_flow(self):
        """Test init with AI enabled flow."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            result = self.runner.invoke(cli, ['init'],
                input='y\nsk-proj-test123\nminimal\n')  # Yes to AI, API key, minimal
            
            assert result.exit_code == 0
            
            # Check .env has API key
            with open('.env') as f:
                content = f.read()
                assert 'OPENAI_API_KEY=sk-proj-test123' in content
                
    def test_init_no_ai_flow(self):
        """Test init without AI enabled."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            result = self.runner.invoke(cli, ['init'],
                                       input='n\nminimal\n')  # No to AI, minimal
            
            assert result.exit_code == 0
            assert os.path.exists('agent.py')
            
            # .env should exist with commented placeholders (no fake keys)
            with open('.env') as f:
                content = f.read()
                assert '# OPENAI_API_KEY=' in content
                assert '# Optional: Override default model' in content
                
    def test_init_creates_agent_keys(self):
        """Test that init creates agent cryptographic keys."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            result = self.runner.invoke(cli, ['init'],
                                       input='n\nminimal\n')
            assert result.exit_code == 0
            
            # Check keys were created
            assert os.path.exists('.co/keys/agent.key')
            assert os.path.exists('.co/keys/recovery.txt')
            assert os.path.exists('.co/keys/DO_NOT_SHARE')
            
            # Check agent address in config
            import toml
            with open('.co/config.toml') as f:
                config = toml.load(f)
                assert 'address' in config['agent']
                assert config['agent']['address'].startswith('0x')
                assert len(config['agent']['address']) == 66  # 0x + 64 chars
                

class TestCommandSeparation:
    """Test that create and init behave differently."""
    
    def setup_method(self):
        """Setup test environment."""
        self.runner = CliRunner()
        
    def test_create_makes_directory_init_uses_current(self):
        """Test the fundamental difference between create and init."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            # create should make a new directory
            result = self.runner.invoke(cli, ['create', 'new-dir'],
                                       input='n\nminimal\n')
            assert result.exit_code == 0
            assert os.path.exists('new-dir/agent.py')
            assert not os.path.exists('agent.py')  # Not in current dir
            
            # init should use current directory
            os.makedirs('init-test')
            os.chdir('init-test')
            result = self.runner.invoke(cli, ['init'],
                                       input='n\nminimal\n')
            assert result.exit_code == 0
            assert os.path.exists('agent.py')  # In current dir
            
            
class TestAPIKeyIntegration:
    """Test API key detection and configuration."""
    
    def test_environment_variable_detection(self):
        """Test environment variable detection for API keys."""
        from connectonion.cli.commands.project_commands import check_environment_for_api_keys
        import os
        
        # Save current env
        old_env = os.environ.copy()
        
        try:
            # Test no keys found
            for key in ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GROQ_API_KEY']:
                os.environ.pop(key, None)
            result = check_environment_for_api_keys()
            assert result is None
            
            # Test OpenAI key found
            os.environ['OPENAI_API_KEY'] = 'sk-test123'
            result = check_environment_for_api_keys()
            assert result == ('openai', 'sk-test123')
            
            # Test Anthropic key found
            os.environ.pop('OPENAI_API_KEY')
            os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-test'
            result = check_environment_for_api_keys()
            assert result == ('anthropic', 'sk-ant-test')
            
            # Test ignoring placeholder values
            os.environ['OPENAI_API_KEY'] = 'sk-your-api-key-here'
            result = check_environment_for_api_keys()
            assert result == ('anthropic', 'sk-ant-test')  # Should still find Anthropic
            
        finally:
            # Restore environment
            os.environ.clear()
            os.environ.update(old_env)
    
    def test_api_key_patterns(self):
        """Test all API key pattern detection."""
        from connectonion.cli.commands.project_commands import detect_api_provider
        
        test_cases = [
            ('sk-1234567890abcdef', 'openai'),
            ('sk-proj-1234567890abcdef', 'openai'),
            ('sk-ant-api03-1234567890abcdef', 'anthropic'),
            ('AIzaSyA-1234567890abcdef', 'google'),
            ('gsk_1234567890abcdef', 'groq'),
            ('unknown-format-key', 'openai'),  # Default fallback
        ]
        
        for key, expected_provider in test_cases:
            provider, _ = detect_api_provider(key)
            assert provider == expected_provider
            
    def test_env_file_generation_per_provider(self):
        """Test that .env file is correctly generated for each provider."""
        with CliRunner().isolated_filesystem():
            from connectonion.cli.commands.project_commands import configure_env_for_provider
            
            # Test OpenAI
            env_content = configure_env_for_provider('openai', 'sk-test123')
            assert 'OPENAI_API_KEY=sk-test123' in env_content
            assert 'MODEL=gpt-4o-mini' in env_content
            
            # Test Anthropic
            env_content = configure_env_for_provider('anthropic', 'sk-ant-test')
            assert 'ANTHROPIC_API_KEY=sk-ant-test' in env_content
            assert 'MODEL=claude-3-haiku' in env_content
            
            # Test Google
            env_content = configure_env_for_provider('google', 'AIza-test')
            assert 'GEMINI_API_KEY=AIza-test' in env_content
            assert 'MODEL=gemini-pro' in env_content
