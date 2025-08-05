# Test Before Trust

Try agents before using them in production.

## Usage

```python
# Test an agent
translator = discover("translate")
result = translator.test("Hello", to_lang="es")

if result == "Hola":
    # It works! Use it for real
    translation = translator(important_text, to_lang="es")
```

## Batch Testing

```python
def find_best_translator():
    translators = discover.all("translate")
    
    for t in translators:
        try:
            # Test with known input/output
            result = t.test("Hello", to_lang="es")
            if result == "Hola":
                return t
        except:
            continue  # Try next one
```

## Performance Testing

```python
# Test speed and quality
analyzer = discover("sentiment analysis")

# Run test with timing
result = analyzer.test("I love this!", measure_time=True)
print(result.output)  # "positive"
print(result.time_ms)  # 45
```

## Sandbox Testing

```python
# Safe testing with limits
untrusted = discover("data processor")

# Test with resource limits
result = untrusted.test(
    sample_data,
    timeout_ms=1000,  # Max 1 second
    memory_mb=100,    # Max 100MB
)
```