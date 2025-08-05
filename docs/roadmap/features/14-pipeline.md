# Pipeline

Build reusable agent compositions.

## Usage

```python
from connectonion import pipeline

# Create a pipeline
translate_analyze = pipeline(
    discover("translate to english"),
    discover("sentiment analysis"),
    discover("summarize")
)

# Use it
result = translate_analyze("Bonjour, j'adore ce produit!")
# Result: "Positive sentiment: Customer loves product"
```

## Visual Builder

```python
# Build pipelines interactively
from connectonion import pipeline_builder

builder = pipeline_builder()
builder.add("translate")
builder.add("clean text")
builder.add("analyze")
builder.save("my_pipeline")

# Use saved pipeline
my_pipeline = pipeline.load("my_pipeline")
result = my_pipeline(input_data)
```

## Branching Pipelines

```python
# Conditional flows
sentiment_router = pipeline(
    discover("sentiment analysis"),
    branch={
        "positive": discover("thank you generator"),
        "negative": discover("apology crafter"),
        "neutral": discover("clarification asker")
    }
)

response = sentiment_router("I hate waiting!")
# Routes to apology crafter
```

## Parallel Execution

```python
# Run agents in parallel
multi_analyzer = pipeline.parallel(
    discover("sentiment analysis"),
    discover("topic extraction"),
    discover("language detection")
)

results = multi_analyzer(text)
# {
#   "sentiment": "positive",
#   "topics": ["product", "quality"],
#   "language": "en"
# }
```