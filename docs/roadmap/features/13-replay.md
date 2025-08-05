# Replay

Time-travel debugging for agent interactions.

## Usage

```python
from connectonion import replay

# Something went wrong?
replay.last_error()
"""
Error Timeline:
10:32:01.234 > Request: analyze(large_dataset)
10:32:01.245 > Discovered: analyzer_v2
10:32:01.267 > Sandbox test: passed
10:32:01.289 > Execution started
10:32:03.445 > ERROR: Memory limit exceeded
10:32:03.446 > Fallback attempted: analyzer_v1
10:32:03.890 > Success with fallback
"""
```

## Interactive Replay

```python
# Step through execution
session = replay.last()

session.play()  # Watch it happen
session.pause() # Pause at any point
session.step()  # Go step by step

# Jump to specific moment
session.goto("10:32:03.445")
print(session.state)  # See exact state at that moment
```

## Debug at Point

```python
# Replay and debug
error_session = replay.last_error()

# Re-run from any point
error_session.goto("before_error")
error_session.debug()  # Opens debugger at that state

# Try different inputs
error_session.replay_with(different_data)
```

## Save Sessions

```python
# Save interesting sessions
session = replay.last()
session.save("bug_reproduction.replay")

# Share with team
replay.load("bug_reproduction.replay")
replay.play()  # They see exactly what you saw
```