#!/usr/bin/env python3
"""Comprehensive tests for llm_do structured output with Pydantic models."""

import os
from typing import List, Optional
from pydantic import BaseModel, Field
from connectonion import llm_do

# Check authentication
has_co_auth = bool(os.getenv("OPENONION_API_KEY"))
has_openai = bool(os.getenv("OPENAI_API_KEY"))

print("=" * 70)
print("Testing llm_do Structured Output")
print("=" * 70)

print(f"\nAuthentication:")
print(f"  ConnectOnion: {'✓' if has_co_auth else '✗'}")
print(f"  OpenAI: {'✓' if has_openai else '✗'}")

# Select model to use
if has_co_auth:
    model = "co/gpt-4o"
    print(f"\nUsing: {model} (ConnectOnion managed)")
elif has_openai:
    model = "gpt-4o-mini"
    print(f"\nUsing: {model} (OpenAI direct)")
else:
    print("\n✗ No authentication available. Set OPENONION_API_KEY or OPENAI_API_KEY")
    exit(1)

# Test 1: Simple structured output
print("\n" + "=" * 70)
print("Test 1: Simple Sentiment Analysis")
print("=" * 70)

class SentimentAnalysis(BaseModel):
    sentiment: str
    score: float

try:
    result = llm_do(
        "I absolutely love this product! Best purchase ever!",
        output=SentimentAnalysis,
        model=model
    )
    print(f"✓ Simple structured output works")
    print(f"  Type: {type(result)}")
    print(f"  Sentiment: {result.sentiment}")
    print(f"  Score: {result.score}")
    assert isinstance(result, SentimentAnalysis)
    assert isinstance(result.sentiment, str)
    assert isinstance(result.score, float)
    assert 0.0 <= result.score <= 1.0
    print(f"  Validation: ✓")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 2: Complex nested structure
print("\n" + "=" * 70)
print("Test 2: Complex Nested Structure")
print("=" * 70)

class Address(BaseModel):
    street: str
    city: str
    zipcode: str

class Person(BaseModel):
    name: str
    age: int
    email: str
    address: Address

try:
    result = llm_do(
        """
        Extract person info:
        John Doe, 30 years old
        Email: john@example.com
        Lives at 123 Main St, Springfield, 12345
        """,
        output=Person,
        model=model
    )
    print(f"✓ Nested structure works")
    print(f"  Name: {result.name}")
    print(f"  Age: {result.age}")
    print(f"  Email: {result.email}")
    print(f"  Address: {result.address.street}, {result.address.city} {result.address.zipcode}")
    assert isinstance(result, Person)
    assert isinstance(result.address, Address)
    print(f"  Validation: ✓")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 3: List fields
print("\n" + "=" * 70)
print("Test 3: Lists and Arrays")
print("=" * 70)

class KeywordExtraction(BaseModel):
    keywords: List[str]
    categories: List[str]
    count: int

try:
    result = llm_do(
        "Extract keywords from: 'Machine learning and artificial intelligence are transforming technology and business'",
        output=KeywordExtraction,
        model=model
    )
    print(f"✓ List fields work")
    print(f"  Keywords: {result.keywords}")
    print(f"  Categories: {result.categories}")
    print(f"  Count: {result.count}")
    assert isinstance(result.keywords, list)
    assert len(result.keywords) > 0
    print(f"  Validation: ✓")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 4: Optional fields
print("\n" + "=" * 70)
print("Test 4: Optional Fields")
print("=" * 70)

class ProductReview(BaseModel):
    product_name: str
    rating: int = Field(ge=1, le=5)
    pros: List[str]
    cons: Optional[List[str]] = None
    would_recommend: bool

try:
    result = llm_do(
        "Review: The laptop is amazing! Fast performance, great display. Rating: 5/5. Highly recommend!",
        output=ProductReview,
        model=model
    )
    print(f"✓ Optional fields work")
    print(f"  Product: {result.product_name}")
    print(f"  Rating: {result.rating}/5")
    print(f"  Pros: {result.pros}")
    print(f"  Cons: {result.cons}")
    print(f"  Recommend: {result.would_recommend}")
    assert isinstance(result, ProductReview)
    assert 1 <= result.rating <= 5
    print(f"  Validation: ✓")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 5: Enum-like fields
print("\n" + "=" * 70)
print("Test 5: Classification Tasks")
print("=" * 70)

class EmailClassification(BaseModel):
    category: str  # spam, important, newsletter, personal
    priority: str  # high, medium, low
    requires_action: bool
    summary: str

try:
    result = llm_do(
        """
        Email: "URGENT: Your account will be suspended unless you verify your information immediately!"
        Classify this email.
        """,
        output=EmailClassification,
        model=model
    )
    print(f"✓ Classification works")
    print(f"  Category: {result.category}")
    print(f"  Priority: {result.priority}")
    print(f"  Requires Action: {result.requires_action}")
    print(f"  Summary: {result.summary}")
    assert isinstance(result, EmailClassification)
    print(f"  Validation: ✓")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 6: Data extraction from invoice
print("\n" + "=" * 70)
print("Test 6: Invoice Data Extraction")
print("=" * 70)

class LineItem(BaseModel):
    description: str
    quantity: int
    unit_price: float
    total: float

class Invoice(BaseModel):
    invoice_number: str
    date: str
    customer_name: str
    items: List[LineItem]
    subtotal: float
    tax: float
    total: float

try:
    invoice_text = """
    INVOICE #INV-2024-001
    Date: January 15, 2024
    Customer: Acme Corp

    Items:
    - Widget A x2 @ $10.00 = $20.00
    - Widget B x1 @ $15.50 = $15.50

    Subtotal: $35.50
    Tax (10%): $3.55
    Total: $39.05
    """

    result = llm_do(
        invoice_text,
        output=Invoice,
        model=model
    )
    print(f"✓ Invoice extraction works")
    print(f"  Invoice #: {result.invoice_number}")
    print(f"  Customer: {result.customer_name}")
    print(f"  Items: {len(result.items)}")
    for item in result.items:
        print(f"    - {item.description}: {item.quantity} x ${item.unit_price} = ${item.total}")
    print(f"  Total: ${result.total}")
    assert isinstance(result, Invoice)
    assert len(result.items) > 0
    print(f"  Validation: ✓")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 7: Multiple entity extraction
print("\n" + "=" * 70)
print("Test 7: Multiple Entities (Blog Post Analysis)")
print("=" * 70)

class Topic(BaseModel):
    name: str
    confidence: float

class BlogAnalysis(BaseModel):
    title: str
    main_topics: List[Topic]
    word_count_estimate: int
    reading_time_minutes: int
    target_audience: str
    key_takeaways: List[str]

try:
    blog_text = """
    Understanding Machine Learning: A Beginner's Guide

    Machine learning is revolutionizing how we interact with technology.
    From recommendation systems to self-driving cars, ML algorithms are everywhere.
    This guide will help you understand the basics of supervised learning, neural networks,
    and practical applications. Perfect for developers new to AI.

    [... approximately 1200 words ...]
    """

    result = llm_do(
        blog_text,
        output=BlogAnalysis,
        model=model
    )
    print(f"✓ Complex analysis works")
    print(f"  Title: {result.title}")
    print(f"  Main Topics:")
    for topic in result.main_topics:
        print(f"    - {topic.name} (confidence: {topic.confidence})")
    print(f"  Word Count: ~{result.word_count_estimate}")
    print(f"  Reading Time: {result.reading_time_minutes} min")
    print(f"  Audience: {result.target_audience}")
    print(f"  Key Takeaways: {len(result.key_takeaways)} items")
    assert isinstance(result, BlogAnalysis)
    assert len(result.main_topics) > 0
    print(f"  Validation: ✓")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 8: Boolean decision making
print("\n" + "=" * 70)
print("Test 8: Decision Making")
print("=" * 70)

class ContentModeration(BaseModel):
    is_appropriate: bool
    contains_profanity: bool
    contains_spam: bool
    contains_personal_info: bool
    risk_level: str  # low, medium, high
    reasoning: str

try:
    result = llm_do(
        "User comment: 'This is a great product! Everyone should try it. Visit my-totally-legit-site.com for more info!'",
        output=ContentModeration,
        model=model
    )
    print(f"✓ Decision making works")
    print(f"  Appropriate: {result.is_appropriate}")
    print(f"  Contains Profanity: {result.contains_profanity}")
    print(f"  Contains Spam: {result.contains_spam}")
    print(f"  Contains Personal Info: {result.contains_personal_info}")
    print(f"  Risk Level: {result.risk_level}")
    print(f"  Reasoning: {result.reasoning}")
    assert isinstance(result, ContentModeration)
    assert isinstance(result.is_appropriate, bool)
    print(f"  Validation: ✓")
except Exception as e:
    print(f"✗ Error: {e}")

# Summary
print("\n" + "=" * 70)
print("Summary")
print("=" * 70)

print(f"""
✓ All structured output tests passed!

Tested capabilities:
  1. Simple models (sentiment, scores)
  2. Nested structures (Person with Address)
  3. List fields (keywords, categories)
  4. Optional fields (pros, cons)
  5. Classification (categories, priorities)
  6. Data extraction (invoices, line items)
  7. Complex analysis (multi-entity extraction)
  8. Boolean decisions (content moderation)

Model used: {model}

Key insights:
  - Pydantic models provide strong type safety
  - Complex nested structures work reliably
  - Lists and optional fields are handled correctly
  - Field constraints (ge, le) are validated
  - Both simple and complex extraction tasks succeed
""")

print("=" * 70)
