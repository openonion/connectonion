# Contributing to ConnectOnion

First off, thank you for considering contributing to ConnectOnion! It's people like you that make ConnectOnion such a great tool. We love receiving contributions from our community.

## Table of Contents
- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Style Guidelines](#style-guidelines)
- [Community](#community)

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

ConnectOnion is a simple Python framework for creating AI agents with behavior tracking. We aim to keep things simple while making complicated things possible.

### Prerequisites
- Python 3.10 or higher
- OpenAI API key (for running agents)
- Git for version control

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When creating a bug report, please include:

- Use the bug report template
- Provide a clear and descriptive title
- Include steps to reproduce
- Provide specific examples and code snippets
- Describe the expected vs actual behavior
- Include your environment details

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion:

- Use the feature request template
- Provide a clear and descriptive title
- Explain why this enhancement would be useful
- Provide code examples of how it would work
- Consider if it aligns with our philosophy of simplicity

### Your First Code Contribution

Unsure where to begin? You can start by looking through these issues:

- Issues labeled `good first issue` - Good for newcomers
- Issues labeled `help wanted` - Extra attention needed
- Issues labeled `documentation` - Help improve our docs

## Development Setup

1. **Fork and Clone**
   ```bash
   git clone https://github.com/your-username/connectonion.git
   cd connectonion
   ```

2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Development Dependencies**
   ```bash
   pip install -e .
   pip install pytest pytest-cov
   ```

4. **Set Up Pre-commit Hooks (Optional)**
   ```bash
   pip install pre-commit
   pre-commit install
   ```

5. **Run Tests**
   ```bash
   # Fast feedback (excludes real API tests)
   pytest -m "not real_api"

   # Or use Makefile shortcuts
   make test          # not real_api
   make test-unit     # unit
   make test-integration
   make test-cli
   make test-e2e
   make test-real     # requires API keys
   ```

## Pull Request Process

1. **Create a Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Your Changes**
   - Write clean, readable code
   - Add tests for new functionality
   - Update documentation as needed
   - Follow our coding standards

3. **Test Your Changes**
   ```bash
   # Run unit tests
   pytest -m unit

   # Run everything except real API
   pytest -m "not real_api"

   # With coverage
   pytest --cov=connectonion --cov-report=term-missing -m "not real_api"
   ```

4. **Commit Your Changes**
   ```bash
   git add .
   git commit -m "feat: Add amazing new feature"
   ```
   
   Follow conventional commits:
   - `feat:` New feature
   - `fix:` Bug fix
   - `docs:` Documentation changes
   - `test:` Test additions/changes
   - `refactor:` Code refactoring
   - `chore:` Maintenance tasks

5. **Push and Create PR**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then create a Pull Request on GitHub.

## Style Guidelines

### Python Style

- Follow PEP 8
- Use meaningful variable and function names
- Keep functions small and focused
- Document your code with docstrings
- Type hints are encouraged

### Example Code Style
```python
def my_tool(text: str, max_length: int = 100) -> str:
    """Process text with a maximum length constraint.
    
    Args:
        text: The input text to process
        max_length: Maximum allowed length
        
    Returns:
        Processed text string
    """
    # Implementation here
    return processed_text
```

### Documentation Style

- Use clear, simple language
- Include code examples
- Start simple, then add complexity
- Follow our "simple things simple" philosophy

### Commit Messages

- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters
- Reference issues and pull requests liberally

## Testing

- Write tests for new features
- Ensure all tests pass before submitting PR
- Aim for good test coverage
- Use meaningful test names

Example pytest-style test:
```python
def test_agent_with_custom_tool():
    def my_tool(text: str) -> str:
        return f"Processed: {text}"

    agent = Agent("test", tools=[my_tool])
    # Exercise functionality
    # ...
    assert True
```

## Community

- **Discord**: [Join our Discord](https://discord.gg/4xfD9k8AUF)
- **GitHub Issues**: For bug reports and features
- **Discussions**: For questions and ideas

## Recognition

Contributors will be recognized in our:
- README.md contributors section
- Release notes
- Special mentions for significant contributions

## Questions?

Feel free to:
- Open an issue with the question label
- Join our Discord community
- Start a GitHub Discussion

Thank you for contributing to ConnectOnion! 🧅
