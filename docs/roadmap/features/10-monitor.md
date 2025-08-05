# Monitor

Track health and performance of agents you use.

## Usage

```python
from connectonion import monitor

@agent
def smart_service(data):
    """I monitor the agents I depend on"""
    
    with monitor() as m:
        processor = discover("data processor")
        result = processor(data)
    
    # Check performance
    if m.response_time > 1000:
        print(f"Warning: processor slow ({m.response_time}ms)")
    
    return result
```

## Automatic Adaptation

```python
@agent
def adaptive_service(data):
    """I adapt based on agent performance"""
    
    processor = discover("processor")
    
    with monitor(processor) as m:
        result = processor(data)
        
        # Track performance over time
        if m.rolling_avg_time > 500:
            # Find faster alternative next time
            self.mark_slow(processor)
    
    return result
```

## Health Tracking

```python
# Monitor agent health over time
translator = discover("translate")

health = translator.health_check()
print(f"Status: {health.status}")  # "healthy", "degraded", "unhealthy"
print(f"Uptime: {health.uptime_percent:.1%}")
print(f"Recent errors: {health.error_count}")
```

## Alert on Issues

```python
@agent
def vigilant_service(data):
    """I alert on problems"""
    
    analyzer = discover("analyzer")
    
    # Set up monitoring
    monitor.watch(analyzer, 
        alert_on_error_rate=0.1,  # >10% errors
        alert_on_latency=2000,     # >2 seconds
    )
    
    try:
        return analyzer(data)
    except MonitorAlert as e:
        # Automatically find alternative
        backup = discover("analyzer", exclude=analyzer)
        return backup(data)
```