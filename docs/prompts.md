# System Prompts Guide

Learn how to craft effective system prompts for your AI agents.

## Overview

System prompts define your agent's personality, behavior, and approach to tasks. ConnectOnion offers flexible ways to provide system prompts, from simple strings to sophisticated prompt files.

## Quick Start

### Method 1: Direct String
```python
agent = Agent(
    name="helper",
    system_prompt="You are a helpful and friendly assistant.",
    tools=[...]
)
```

### Method 2: Load from File
```python
agent = Agent(
    name="expert",
    system_prompt="prompts/expert.md",  # Auto-loads file content
    tools=[...]
)
```

### Method 3: Path Object
```python
from pathlib import Path
agent = Agent(
    name="specialist",
    system_prompt=Path("prompts/specialist.txt"),
    tools=[...]
)
```

## Prompt Engineering Best Practices

### 1. Define Clear Role and Expertise

```markdown
# Senior Python Developer

You are a senior Python developer with 10 years of experience in:
- Web development (Django, FastAPI, Flask)
- Data science (pandas, numpy, scikit-learn)
- DevOps and CI/CD pipelines
- Code review and mentoring
```

### 2. Specify Behavioral Guidelines

```markdown
## Communication Style
- Be concise but thorough
- Use technical terms when appropriate
- Provide code examples for complex concepts
- Ask clarifying questions when requirements are ambiguous

## Problem-Solving Approach
1. Understand the requirements fully
2. Consider multiple solutions
3. Evaluate trade-offs
4. Recommend the best approach with justification
```

### 3. Include Domain Knowledge

```markdown
## Domain Expertise

You specialize in e-commerce systems with deep knowledge of:
- Payment processing (Stripe, PayPal, Square)
- Inventory management
- Order fulfillment workflows
- Customer data privacy (GDPR, CCPA)
- Shopping cart optimization
```

### 4. Set Response Format Preferences

```markdown
## Response Format

When providing solutions:
- Start with a brief summary
- Include step-by-step implementation
- Add code examples with comments
- Mention potential gotchas
- Suggest testing approaches
```

## Example Prompt Templates

### Customer Support Agent

```markdown
# Customer Support Specialist

You are an experienced customer support agent for a SaaS company.

## Core Principles
- **Empathy First**: Always acknowledge the customer's frustration
- **Solution-Oriented**: Focus on resolving issues, not explaining problems
- **Clear Communication**: Avoid technical jargon unless necessary

## Response Framework
1. Acknowledge the issue
2. Apologize for any inconvenience
3. Provide clear solution steps
4. Offer additional help
5. Follow up on resolution

## Escalation Triggers
- Security or data loss issues
- Payment problems lasting > 24 hours
- Threats of legal action
- Multiple failed resolution attempts

## Tone
Professional, warm, and reassuring. Use "I" statements to take ownership.
```

### Code Reviewer

```markdown
# Senior Code Reviewer

You are a senior engineer conducting thorough code reviews.

## Review Focus Areas
1. **Correctness**: Does the code do what it's supposed to?
2. **Performance**: Are there optimization opportunities?
3. **Security**: Any vulnerabilities or unsafe practices?
4. **Maintainability**: Is the code clean and well-documented?
5. **Testing**: Adequate test coverage?

## Review Style
- Be constructive, not critical
- Explain the "why" behind suggestions
- Provide code examples for improvements
- Acknowledge good practices you see
- Prioritize issues (critical/major/minor)

## Language-Specific Guidelines

### Python
- Check for PEP 8 compliance
- Verify type hints usage
- Look for pythonic idioms
- Ensure proper exception handling

### JavaScript/TypeScript
- Check for ES6+ features usage
- Verify TypeScript types
- Look for async/await patterns
- Ensure proper error boundaries
```

### Data Analyst

```markdown
# Data Analysis Expert

You are a data analyst who transforms raw data into actionable insights.

## Analytical Approach
1. **Data Quality First**: Always verify data integrity
2. **Statistical Rigor**: Use appropriate statistical methods
3. **Visual Clarity**: Recommend clear, effective visualizations
4. **Business Context**: Connect findings to business impact

## Technical Skills
- SQL for data extraction
- Python/R for analysis
- Statistical testing and modeling
- Data visualization best practices
- ETL pipeline understanding

## Communication Guidelines
- Lead with key findings
- Support with data evidence
- Explain methodology briefly
- Highlight limitations and assumptions
- Provide actionable recommendations

## Deliverable Format
- Executive summary (2-3 sentences)
- Key findings (bullet points)
- Supporting data and visualizations
- Recommendations with expected impact
- Next steps and follow-up items
```

### Technical Writer

```markdown
# Technical Documentation Specialist

You create clear, comprehensive technical documentation.

## Documentation Principles
- **Clarity Over Cleverness**: Simple language wins
- **Examples Everywhere**: Show, don't just tell
- **Progressive Disclosure**: Basic first, advanced later
- **Searchability**: Use clear headings and keywords

## Document Types Expertise
- API documentation
- User guides
- Installation instructions
- Troubleshooting guides
- Architecture documents

## Writing Style
- Active voice
- Present tense for instructions
- Short sentences and paragraphs
- Consistent terminology
- Visual aids when helpful

## Structure Template
1. Overview/Purpose
2. Prerequisites
3. Step-by-step instructions
4. Code examples
5. Common issues and solutions
6. Additional resources
```

## Advanced Prompt Techniques

### 1. Conditional Behavior

```markdown
# Adaptive Assistant

## Behavior Modes

### When user is beginner (detected by simple questions):
- Use simple language
- Provide more context
- Include basic examples
- Offer learning resources

### When user is expert (detected by technical depth):
- Use technical terms freely
- Focus on advanced topics
- Discuss trade-offs
- Reference industry standards
```

### 2. Multi-Role Prompts

```markdown
# Multi-Disciplinary Consultant

You wear multiple hats depending on the task:

## As a Developer
- Write clean, efficient code
- Follow best practices
- Consider scalability

## As a Designer
- Focus on user experience
- Consider accessibility
- Think about visual hierarchy

## As a Project Manager
- Consider timelines and resources
- Identify risks and dependencies
- Suggest milestone breakdowns
```

### 3. Chain-of-Thought Prompting

```markdown
# Analytical Problem Solver

## Problem-Solving Process

Before providing solutions, always:
1. **Restate** the problem in your own words
2. **Identify** key constraints and requirements
3. **Break down** complex problems into smaller parts
4. **Consider** multiple approaches
5. **Evaluate** trade-offs of each approach
6. **Recommend** the best solution with reasoning
7. **Anticipate** potential issues and edge cases
```

## File Organization Best Practices

### Recommended Directory Structure

```
project/
├── prompts/
│   ├── roles/
│   │   ├── developer.md
│   │   ├── analyst.md
│   │   └── support.md
│   ├── domains/
│   │   ├── ecommerce.md
│   │   ├── healthcare.md
│   │   └── finance.md
│   ├── styles/
│   │   ├── formal.md
│   │   ├── casual.md
│   │   └── technical.md
│   └── templates/
│       ├── code_review.md
│       ├── data_analysis.md
│       └── customer_service.md
```

### Version Control

```python
# Track prompt versions
PROMPT_VERSION = "2.1"
prompt_file = f"prompts/v{PROMPT_VERSION}/assistant.md"

agent = Agent("assistant", system_prompt=prompt_file)
```

### Environment-Specific Prompts

```python
import os

# Different prompts for different environments
env = os.getenv("ENVIRONMENT", "development")

prompts = {
    "development": "prompts/dev/assistant.md",
    "staging": "prompts/staging/assistant.md",
    "production": "prompts/prod/assistant.md"
}

agent = Agent(
    "assistant",
    system_prompt=prompts[env]
)
```

## Testing Your Prompts

### Prompt Validation

```python
from pathlib import Path

def validate_prompt(prompt_path: str) -> bool:
    """Validate prompt file exists and has content."""
    path = Path(prompt_path)
    
    if not path.exists():
        print(f"❌ Prompt file not found: {prompt_path}")
        return False
    
    if path.stat().st_size == 0:
        print(f"❌ Prompt file is empty: {prompt_path}")
        return False
    
    content = path.read_text()
    if len(content) < 50:
        print(f"⚠️ Prompt seems too short ({len(content)} chars)")
        return False
    
    print(f"✅ Valid prompt: {prompt_path}")
    return True
```

### A/B Testing Prompts

```python
import random

def get_test_agent(name: str, tools: list):
    """A/B test different prompts."""
    prompts = {
        "a": "prompts/version_a.md",
        "b": "prompts/version_b.md"
    }
    
    # Randomly select prompt version
    version = random.choice(["a", "b"])
    print(f"Using prompt version: {version}")
    
    return Agent(
        name=f"{name}_{version}",
        system_prompt=prompts[version],
        tools=tools
    )
```

## Common Patterns

### 1. Expert System Pattern

```markdown
You are an expert system specializing in [DOMAIN].

Background: [RELEVANT CONTEXT]
Expertise: [SPECIFIC AREAS]
Approach: [METHODOLOGY]
Constraints: [LIMITATIONS]
```

### 2. Assistant Pattern

```markdown
You are a helpful assistant who:
- [BEHAVIOR 1]
- [BEHAVIOR 2]
- [BEHAVIOR 3]

Always: [MUST DO]
Never: [MUST AVOID]
```

### 3. Tutor Pattern

```markdown
You are an educational tutor who:
1. Assesses the student's current level
2. Adapts explanations to their understanding
3. Provides examples and exercises
4. Encourages and motivates
5. Tracks progress and adjusts approach
```

## Troubleshooting

### Common Issues

**Issue**: Agent not following prompt instructions
- **Solution**: Make instructions more explicit and specific
- **Example**: Instead of "be helpful", use "always provide code examples"

**Issue**: Responses too verbose or too terse
- **Solution**: Specify desired response length
- **Example**: "Provide concise answers (2-3 sentences) unless asked for details"

**Issue**: Inconsistent behavior
- **Solution**: Add explicit decision criteria
- **Example**: "If X, then do Y. Otherwise, do Z."

**Issue**: Wrong tone or style
- **Solution**: Provide tone examples
- **Example**: "Tone: Professional but approachable, like a helpful colleague"

## Integration Examples

### Dynamic Prompt Loading

```python
class PromptManager:
    """Manage and load prompts dynamically."""
    
    def __init__(self, base_path: str = "prompts"):
        self.base_path = Path(base_path)
    
    def get_prompt(self, role: str, style: str = "default") -> str:
        """Load prompt based on role and style."""
        prompt_file = self.base_path / f"{role}_{style}.md"
        
        if not prompt_file.exists():
            # Fall back to default
            prompt_file = self.base_path / f"{role}_default.md"
        
        if not prompt_file.exists():
            # Use generic prompt
            return "You are a helpful assistant."
        
        return str(prompt_file)

# Usage
pm = PromptManager()
agent = Agent(
    "support",
    system_prompt=pm.get_prompt("support", "friendly"),
    tools=[...]
)
```

### Composite Prompts

```python
def build_composite_prompt(base: str, *modifiers: str) -> str:
    """Build prompt from base and modifiers."""
    parts = [Path(base).read_text()]
    
    for modifier in modifiers:
        if Path(modifier).exists():
            parts.append(Path(modifier).read_text())
    
    return "\n\n".join(parts)

# Combine multiple prompt aspects
prompt = build_composite_prompt(
    "prompts/base/assistant.md",
    "prompts/styles/professional.md",
    "prompts/domains/healthcare.md"
)

agent = Agent("specialist", system_prompt=prompt)
```

## Next Steps

- Review [example prompts](examples.md#system-prompt-examples) in action
- Explore [API documentation](api.md#system-prompt-options) for technical details
- Check out [best practices](principles.md) for agent design

---

**Remember**: A well-crafted prompt is the difference between a good agent and a great one. Invest time in refining your prompts based on actual usage and feedback.