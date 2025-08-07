# Natural Language Need

Describe what you need in plain language - no function names required.

## Overview

Instead of memorizing function names, just describe what you need naturally. The AI understands your intent and finds the right capability.

## Usage

```python
from connectonion import need

# Just describe what you need
translator = need("I need to translate text to Spanish")
result = translator("Hello world")  # "Hola mundo"

# Any natural description works
analyzer = need("figure out if this review is positive")
sentiment = analyzer("This product is amazing!")  # "positive"

# Context-aware
processor = need("help me analyze this")
# With text → sentiment analysis
# With numbers → statistical analysis  
# With images → image analysis
```

## Why Natural Language?

### No Function Names to Remember
```python
# ❌ Old way - need exact names
need("sentiment_analyzer_v2")
need("textSentimentAnalysis") 
need("analyze-sentiment")

# ✅ New way - just describe
need("is this customer happy?")
need("analyze emotions in this text")
need("what's the mood of this review?")
```

### Works in Any Language
```python
# English
need("translate to French")

# Spanish  
need("traducir al francés")

# Chinese
need("翻译成法语")

# All find translation capability!
```

### Handles Variations
```python
# All of these find the same capability
need("summarize this document")
need("make this shorter")
need("tl;dr this text")
need("give me the key points")
need("I don't have time to read all this")
```

## Smart Context Understanding

```python
# Same description, different context
helper = need("analyze this")

# Understands from your data
result1 = helper("I love it!")  # Sentiment: positive
result2 = helper([1,2,3,4,5])   # Stats: mean=3, std=1.41
result3 = helper(image_data)    # Objects: cat, sofa
```

## Progressive Understanding

```python
# Start vague
helper = need("I have customer data and need insights")

# AI helps clarify
helper.suggest()
"""
I can help with:
- Customer sentiment analysis
- Purchase pattern analysis
- Churn prediction
- Segmentation
What interests you most?
"""

# Refine your need
helper = need("which customers might leave us")
# Now it knows you want churn prediction
```

## Behind the Scenes

When you call `need()`:

1. **AI understands** your natural language
2. **Semantic search** finds matching capabilities  
3. **Smart testing** verifies they work
4. **Best match** returned ready to use

You never see this complexity!

## Examples

### Data Analysis
```python
# Instead of: need("pandas_dataframe_analyzer")
analyzer = need("help me understand this sales data")
insights = analyzer(sales_df)
```

### Image Processing
```python
# Instead of: need("image_resize_crop_tool")  
processor = need("make this image smaller for web")
thumbnail = processor(image, size="thumbnail")
```

### Text Processing
```python
# Instead of: need("nlp_entity_extractor")
extractor = need("find all the company names in this text")
companies = extractor(article)
```

### API Integration
```python
# Instead of: need("weather_api_wrapper")
weather = need("what's the weather like?")
forecast = weather("San Francisco")
```

## Learning Over Time

The more people use natural descriptions, the smarter it gets:

```
Day 1: need("translate") → Basic matching
Day 30: need("help me read this") → Understands: translation  
Day 90: need("what does this say?") → Understands: translation
Day 180: need("我看不懂英文") → Understands: needs translation
```

## Combining Needs

```python
# Describe complex needs
helper = need("translate this Spanish text and summarize the key points")
# Automatically composes translate + summarize

result = helper(spanish_document)
# Returns: English summary
```

## Error Handling

```python
# If unclear
helper = need("do something with this")
# Returns: "Could you be more specific? I can help with analysis, translation, summarization..."

# If nothing found
helper = need("quantum gravity calculations")  
# Returns: "I couldn't find that capability. Similar options: physics calculations, gravity simulations..."
```

## The Beauty

**Zero learning curve.** Users don't need to:
- Read documentation
- Learn function names
- Understand parameters
- Remember exact syntax

They just describe what they need, naturally.

## Future Possibilities

```python
# Conversational needs
need("I'm building a chatbot and need to understand what users want")

# Complex workflows
need("every morning, check my emails and summarize the important ones")

# Learning needs
need("help me learn Spanish by translating with explanations")
```

## Implementation Note

This feature requires:
- Natural language understanding (via LLM)
- Semantic embedding of capabilities
- Smart matching algorithm
- Context awareness

But users see none of this - just natural, simple interactions.