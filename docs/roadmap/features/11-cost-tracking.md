# Cost Tracking

Monitor and control spending on agent calls.

## Usage

```python
# See cost before using
translator = discover("translate")
print(translator.cost_per_call)  # $0.002

# Track costs
result = translator("Long text...", track_cost=True)
print(result.cost)  # $0.003
```

## Set Limits

```python
# Discover with cost limit
analyzer = discover("analyze data", max_cost=0.10)

# Set monthly budget
from connectonion import set_budget
set_budget(monthly=50.00)  # $50/month max

# Warning when approaching limit
if get_spending().month_to_date > 40:
    print("Warning: 80% of budget used")
```

## Cost-Aware Agents

```python
@agent
def budget_analyzer(data, max_spend=1.00):
    """I respect your budget"""
    
    # Try expensive option first
    if max_spend > 0.10:
        try:
            premium = discover("gpt-4 analyzer", max_cost=0.10)
            return premium(data)
        except CostLimitExceeded:
            pass
    
    # Fall back to cheaper option
    basic = discover("basic analyzer", max_cost=0.01)
    return basic(data)
```

## Cost Reports

```python
from connectonion import costs

# Daily breakdown
costs.today()
"""
Total: $4.32
By agent:
- gpt4_analyzer: $3.20 (32 calls)
- translator_pro: $0.89 (445 calls)  
- basic_search: $0.23 (230 calls)
"""

# Export for accounting
costs.export_csv("january_2024.csv")
```