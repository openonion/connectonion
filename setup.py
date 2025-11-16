"""Setup configuration for ConnectOnion."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Core dependencies - we install everything by default for simplicity
requirements = [
    "openai>=1.0.0",  # Also used for Gemini via OpenAI-compatible endpoint
    "anthropic>=0.18.0",
    "litellm>=1.0.0",  # For llm_do function supporting 100+ providers
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
    "click>=8.0.0",
    "toml>=0.10.2",
    "requests>=2.25.0",
    "rich>=13.0.0",  # For CLI formatting
    "PyNaCl>=1.5.0",  # For Ed25519 key generation (needed for global config)
    "mnemonic>=0.20",  # For recovery phrase generation (needed for global config)
    "questionary>=2.0.0",  # For interactive CLI prompts (arrow key navigation)
    "websockets>=11.0.0",  # For network features (agent.serve() and connect())
]

# Note: playwright is the only one we keep optional since it's large and requires browser binaries
# Users who need browser automation can install it separately: pip install playwright
optional_deps = {
    "browser": [
        "playwright>=1.40.0",  # For browser automation (large, requires browser binaries)
    ],
}

setup(
    name="connectonion",
    # Version numbering strategy:
    # - Current: 0.1.9
    # - Increment PATCH for bug fixes: 0.1.1, 0.1.2, ..., 0.1.9
    # - At 0.1.10, roll to MINOR: 0.2.0
    # - At 0.10.0, roll to MAJOR: 1.0.0
    # - Example progression: 0.1.0 -> 0.1.1 -> ... -> 0.1.9 -> 0.1.10 -> 0.2.0
    version="0.4.2",
    author="ConnectOnion Team",
    author_email="pypi@connectonion.com",
    description="A simple Python framework for creating AI agents with behavior tracking",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/openonion/connectonion",
    packages=find_packages(),
    package_data={
        'connectonion.cli': [
            'docs.md',  # Include docs.md in the package
            'docs/*.md',  # Include all markdown files in docs directory
            'templates/**/*',  # Include all files in template folders recursively
            'templates/**/.env.example',  # Include hidden files like .env.example
        ],
        'connectonion.debug_agent': [
            'prompts/*.md',  # Include debug assistant prompts
        ],
        'connectonion.debug_explainer': [
            '*.md',  # Include all markdown prompts for debug explainer
        ],
        'connectonion.execution_analyzer': [
            '*.md',  # Include all markdown prompts for execution analyzer
        ],
    },
    include_package_data=True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require=optional_deps,
    keywords="ai, agent, llm, tools, openai, automation, debugging, interactive-debugging, breakpoints, xray",
    project_urls={
        "Bug Reports": "https://github.com/openonion/connectonion/issues",
        "Source": "https://github.com/openonion/connectonion",
        "Documentation": "https://github.com/openonion/connectonion#readme",
    },
    entry_points={
        "console_scripts": [
            "co=connectonion.cli.main:cli",
            "connectonion=connectonion.cli.main:cli",
        ],
    },
)