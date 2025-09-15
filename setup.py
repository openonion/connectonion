"""Setup configuration for ConnectOnion."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Core dependencies that are always required
requirements = [
    "openai>=1.0.0",
    "anthropic>=0.18.0",
    "google-generativeai>=0.3.0",
    "litellm>=1.0.0",  # For llm_do function supporting 100+ providers
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
    "click>=8.0.0",
    "toml>=0.10.2",
    "requests>=2.25.0",
    "rich>=13.0.0",  # For CLI formatting
]

# Optional dependencies for specific features
# These are handled gracefully with try/except in the code
optional_deps = {
    "auth": [
        "PyNaCl>=1.5.0",  # For Ed25519 key generation
        "mnemonic>=0.20",  # For seed phrase generation
    ],
    "cli": [
        "questionary>=2.0.0",  # For interactive CLI prompts
    ],
    "browser": [
        "playwright>=1.40.0",  # For browser automation
    ],
    "all": [
        "PyNaCl>=1.5.0",
        "mnemonic>=0.20",
        "questionary>=2.0.0",
        "playwright>=1.40.0",
    ],
}

setup(
    name="connectonion",
    # Version numbering strategy:
    # - Current: 0.1.1
    # - Increment PATCH for bug fixes: 0.1.1, 0.1.2, ..., 0.1.9
    # - At 0.1.10, roll to MINOR: 0.2.0
    # - At 0.10.0, roll to MAJOR: 1.0.0
    # - Example progression: 0.1.0 -> 0.1.1 -> ... -> 0.1.9 -> 0.1.10 -> 0.2.0
    version="0.1.1",
    author="ConnectOnion Team",
    author_email="pypi@connectonion.com",
    description="A simple Python framework for creating AI agents with behavior tracking",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/connectonion/connectonion",
    packages=find_packages(),
    package_data={
        'connectonion.cli': [
            'docs.md',  # Include docs.md in the package
            'templates/**/*',  # Include all files in template folders recursively
            'templates/**/.env.example',  # Include hidden files like .env.example
        ],
    },
    include_package_data=True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require=optional_deps,
    keywords="ai, agent, llm, tools, openai, automation",
    project_urls={
        "Bug Reports": "https://github.com/connectonion/connectonion/issues",
        "Source": "https://github.com/connectonion/connectonion",
        "Documentation": "https://github.com/connectonion/connectonion#readme",
    },
    entry_points={
        "console_scripts": [
            "co=connectonion.cli.main:cli",
            "connectonion=connectonion.cli.main:cli",
        ],
    },
)