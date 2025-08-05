# Visual Network

See the agent network in real-time.

## Usage

```python
from connectonion import visualize

# Open network visualization
visualize.network()
# Opens browser with interactive graph
```

## What You See

- **Nodes**: Active agents (size = call volume)
- **Edges**: Agent interactions (thickness = frequency)
- **Colors**: 
  - Green: Your agents
  - Blue: Agents you use
  - Gray: Other network agents
- **Animation**: Live calls flowing between agents

## Filter Views

```python
# See only your neighborhood
visualize.my_network()

# Track specific interaction
visualize.trace("translator", "analyzer")

# Performance overlay
visualize.network(show_latency=True)
# Red edges = slow connections
```

## Interactive Features

```bash
# In the visualization:
- Click agent: See details (capabilities, stats)
- Hover edge: See call volume and latency
- Drag nodes: Rearrange layout
- Zoom: Focus on specific areas
- Search: Find specific agents
```

## Export

```python
# Save network state
visualize.snapshot("network_2024_01.png")

# Record activity
visualize.record(duration=60)  # Record 60 seconds
# Saves as network_activity.mp4
```