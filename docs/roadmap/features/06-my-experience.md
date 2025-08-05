# my_experience

Track your personal history with agents.

## Usage

```python
translator = discover("translate")

# Use it a few times
translator("Hello", to_lang="es")
translator("World", to_lang="es")

# Check your experience
print(translator.my_experience)
"""
{
  "uses": 2,
  "success_rate": 1.0,
  "avg_time_ms": 47,
  "last_used": "2024-01-10T10:30:00"
}
"""
```

## Trust Based on Experience

```python
# Discover prefers agents you've used successfully
translator = discover("translate", prefer_trusted=True)
# Automatically returns your most reliable translator
```

## Experience Details

```python
analyzer = discover("analyze")

# After using it
experience = analyzer.my_experience
print(f"Success rate: {experience.success_rate:.1%}")
print(f"Average time: {experience.avg_time_ms}ms")
print(f"Total uses: {experience.uses}")

# See recent interactions
for interaction in experience.recent(5):
    print(f"{interaction.time}: {interaction.result}")
```

## Reset Experience

```python
# Start fresh with an agent
translator.reset_experience()

# Or forget an unreliable agent
if analyzer.my_experience.success_rate < 0.5:
    analyzer.forget()  # Won't be preferred anymore
```