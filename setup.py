"""Setup configuration for ConnectOnion."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

requirements = [
    "openai>=1.0.0",
    "pydantic>=2.0.0", 
    "python-dotenv>=1.0.0",
    "click>=8.0.0",
    "toml>=0.10.2"
]

setup(
    name="connectonion",
    # Version numbering strategy:
    # - Now in production: 0.0.6
    # - Follow semantic versioning: increment PATCH until 10, then roll to MINOR
    # - See VERSIONING.md for detailed versioning rules
    version="0.0.6",
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