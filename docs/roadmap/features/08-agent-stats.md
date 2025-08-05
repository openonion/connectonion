# Agent Stats

See how your agents are being used.

## Usage

```python
from connectonion import my_agent

# See your agent's statistics
my_agent.stats()
"""
Agent: translator
Status: Active ✓

Today:
- Calls: 1,234
- Unique users: 67  
- Success rate: 99.2%
- Avg response: 45ms
- Earnings: $12.34
"""
```

## Detailed Analytics

```python
# Get specific metrics
stats = my_agent.get_stats()

print(f"Total calls: {stats.total_calls}")
print(f"This hour: {stats.hourly_calls}")
print(f"Success rate: {stats.success_rate:.1%}")

# Top users of your agent
for user in stats.top_users(5):
    print(f"{user.agent_name}: {user.call_count} calls")
```

## Real-time Monitoring

```python
# Watch live activity
my_agent.monitor()
"""
[10:23:45] research_bot called translate("Hello", "es") - 43ms ✓
[10:23:47] analyzer called translate("Data", "fr") - 51ms ✓
[10:23:52] chatbot called translate("Help", "de") - 39ms ✓
"""
```

## Export Stats

```python
# Daily report
report = my_agent.daily_report()
report.save("stats_2024_01_10.json")

# Weekly summary
summary = my_agent.weekly_summary()
print(summary.total_calls)  # 8,932
print(summary.total_earnings)  # $89.32
```