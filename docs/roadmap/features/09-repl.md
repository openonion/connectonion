# REPL

Interactive command line for agent development.

## Usage

```bash
$ connectonion repl

>>> discover translate
Found 3 agents:
1. babel_fish (45ms avg, 99% success)
2. polyglot (89ms avg, 95% success)
3. translator_pro (123ms avg, 97% success)

>>> test babel_fish "Hello" spanish
"Hola" (42ms)

>>> use babel_fish
Using babel_fish as default translator
```

## Common Commands

```bash
# Discovery
>>> find sentiment analysis
>>> discover all translators
>>> search "process images"

# Testing
>>> test agent_name "sample input"
>>> benchmark translator "Hello" x100

# Stats
>>> my agents
>>> stats translator
>>> network info

# Usage
>>> translate "Hello" spanish
>>> analyze "I love this product"
```

## Interactive Pipelines

```bash
>>> pipe translate spanish | analyze sentiment
Created pipeline: spanish_sentiment_analyzer

>>> run pipeline "I love this!" 
Step 1: translate → "¡Me encanta esto!"
Step 2: analyze → {"sentiment": "positive", "score": 0.95}
```

## Quick Experiments

```bash
>>> compare translate "Hello world" spanish
Comparing 3 translators:
1. babel_fish: "Hola mundo" (41ms) ✓
2. polyglot: "Hola mundo" (87ms) ✓
3. translator_pro: "Hola mundo" (122ms) ✓

>>> time discover image processor
Found image_analyzer in 12ms
```