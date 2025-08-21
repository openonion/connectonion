"""Additional Example Tools for ConnectOnion Agents"""

import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any


def generate_password(length: int = 12, include_symbols: bool = True) -> str:
    """Generate a secure random password."""
    import string
    
    chars = string.ascii_letters + string.digits
    if include_symbols:
        chars += "!@#$%^&*"
    
    if length < 4:
        length = 4
    if length > 50:
        length = 50
    
    password = ''.join(random.choice(chars) for _ in range(length))
    return f"Generated password: {password}"


def create_todo_list(tasks: str) -> str:
    """Create a formatted todo list from comma-separated tasks."""
    try:
        task_list = [task.strip() for task in tasks.split(',') if task.strip()]
        
        if not task_list:
            return "Error: Please provide at least one task"
        
        todo_items = []
        todo_items.append("📋 Todo List:")
        todo_items.append("=" * 20)
        
        for i, task in enumerate(task_list, 1):
            todo_items.append(f"{i}. [ ] {task}")
        
        todo_items.append("")
        todo_items.append(f"Total tasks: {len(task_list)}")
        
        return "\n".join(todo_items)
        
    except Exception as e:
        return f"Error creating todo list: {str(e)}"


def url_shortener(url: str) -> str:
    """Simulate URL shortening (generates fake short URL)."""
    if not url.startswith(('http://', 'https://')):
        return "Error: Please provide a valid URL starting with http:// or https://"
    
    # Generate a fake short code
    short_code = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))
    
    return f"""URL Shortened Successfully!
    Original: {url}
    Shortened: https://short.ly/{short_code}
    
    (Note: This is a simulated short URL for demonstration)"""


def color_palette_generator(theme: str = "random") -> str:
    """Generate a color palette based on a theme."""
    palettes = {
        "ocean": ["#0077be", "#00a8cc", "#7ed9e0", "#b8e6e6", "#d4f1f4"],
        "sunset": ["#ff6b6b", "#ffa726", "#ffcc02", "#ffeb3b", "#fff59d"],
        "forest": ["#2e7d32", "#43a047", "#66bb6a", "#81c784", "#a5d6a7"],
        "purple": ["#6a1b9a", "#8e24aa", "#ab47bc", "#ba68c8", "#ce93d8"],
        "monochrome": ["#212121", "#424242", "#616161", "#757575", "#9e9e9e"]
    }
    
    if theme.lower() == "random":
        theme = random.choice(list(palettes.keys()))
    
    if theme.lower() not in palettes:
        theme = "ocean"
    
    colors = palettes[theme.lower()]
    
    result = [f"🎨 {theme.title()} Color Palette:"]
    result.append("-" * 25)
    
    for i, color in enumerate(colors, 1):
        result.append(f"{i}. {color}")
    
    result.append(f"\nTheme: {theme.title()}")
    result.append("Copy any hex code to use in your designs!")
    
    return "\n".join(result)


def text_statistics(text: str) -> str:
    """Analyze text and provide detailed statistics."""
    if not text or not text.strip():
        return "Error: Please provide some text to analyze"
    
    # Basic counts
    char_count = len(text)
    char_count_no_spaces = len(text.replace(' ', ''))
    word_count = len(text.split())
    sentence_count = text.count('.') + text.count('!') + text.count('?')
    paragraph_count = len([p for p in text.split('\n\n') if p.strip()])
    
    # Average calculations
    avg_word_length = char_count_no_spaces / word_count if word_count > 0 else 0
    avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0
    
    # Reading time (average 200 words per minute)
    reading_time = word_count / 200
    
    stats = f"""📖 Text Statistics:
    ==================
    Characters (with spaces): {char_count:,}
    Characters (no spaces): {char_count_no_spaces:,}
    Words: {word_count:,}
    Sentences: {sentence_count}
    Paragraphs: {paragraph_count}
    
    📊 Averages:
    Average word length: {avg_word_length:.1f} characters
    Average sentence length: {avg_sentence_length:.1f} words
    
    ⏱️ Reading time: {reading_time:.1f} minutes
    """
    
    return stats


def unit_converter(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common units."""
    # Distance conversions (all to meters first)
    distance_to_meters = {
        "mm": 0.001, "cm": 0.01, "m": 1, "km": 1000,
        "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.34
    }
    
    # Weight conversions (all to grams first)
    weight_to_grams = {
        "mg": 0.001, "g": 1, "kg": 1000,
        "oz": 28.3495, "lb": 453.592
    }
    
    # Temperature conversion (special case)
    if from_unit.lower() in ["c", "celsius", "f", "fahrenheit", "k", "kelvin"]:
        if from_unit.lower() in ["c", "celsius"] and to_unit.lower() in ["f", "fahrenheit"]:
            result = (value * 9/5) + 32
            return f"{value}°C = {result:.2f}°F"
        elif from_unit.lower() in ["f", "fahrenheit"] and to_unit.lower() in ["c", "celsius"]:
            result = (value - 32) * 5/9
            return f"{value}°F = {result:.2f}°C"
        elif from_unit.lower() in ["c", "celsius"] and to_unit.lower() in ["k", "kelvin"]:
            result = value + 273.15
            return f"{value}°C = {result:.2f}K"
        elif from_unit.lower() in ["k", "kelvin"] and to_unit.lower() in ["c", "celsius"]:
            result = value - 273.15
            return f"{value}K = {result:.2f}°C"
    
    # Distance conversion
    if from_unit.lower() in distance_to_meters and to_unit.lower() in distance_to_meters:
        meters = value * distance_to_meters[from_unit.lower()]
        result = meters / distance_to_meters[to_unit.lower()]
        return f"{value} {from_unit} = {result:.4f} {to_unit}"
    
    # Weight conversion
    if from_unit.lower() in weight_to_grams and to_unit.lower() in weight_to_grams:
        grams = value * weight_to_grams[from_unit.lower()]
        result = grams / weight_to_grams[to_unit.lower()]
        return f"{value} {from_unit} = {result:.4f} {to_unit}"
    
    return f"Error: Cannot convert from '{from_unit}' to '{to_unit}'. Supported units: distance (mm, cm, m, km, in, ft, yd, mi), weight (mg, g, kg, oz, lb), temperature (C, F, K)"


def encode_decode_text(text: str, operation: str = "base64_encode") -> str:
    """Encode or decode text using various methods."""
    import base64
    
    try:
        if operation.lower() == "base64_encode":
            encoded = base64.b64encode(text.encode('utf-8')).decode('utf-8')
            return f"Base64 encoded: {encoded}"
        
        elif operation.lower() == "base64_decode":
            decoded = base64.b64decode(text.encode('utf-8')).decode('utf-8')
            return f"Base64 decoded: {decoded}"
        
        elif operation.lower() == "url_encode":
            import urllib.parse
            encoded = urllib.parse.quote(text)
            return f"URL encoded: {encoded}"
        
        elif operation.lower() == "url_decode":
            import urllib.parse
            decoded = urllib.parse.unquote(text)
            return f"URL decoded: {decoded}"
        
        elif operation.lower() == "reverse":
            return f"Reversed text: {text[::-1]}"
        
        elif operation.lower() == "uppercase":
            return f"Uppercase: {text.upper()}"
        
        elif operation.lower() == "lowercase":
            return f"Lowercase: {text.lower()}"
        
        else:
            return "Error: Supported operations: base64_encode, base64_decode, url_encode, url_decode, reverse, uppercase, lowercase"
    
    except Exception as e:
        return f"Error processing text: {str(e)}"


# Example agent using these tools
if __name__ == "__main__":
    print("🛠️  Extended Tools Example")
    print("These tools can be added to any ConnectOnion agent!")
    
    # Demonstrate a few tools
    print("\n1. Password Generator:")
    print(generate_password(16, True))
    
    print("\n2. Todo List:")
    print(create_todo_list("Buy groceries, Walk the dog, Finish project, Call mom"))
    
    print("\n3. Color Palette:")
    print(color_palette_generator("ocean"))
    
    print("\n4. Unit Conversion:")
    print(unit_converter(100, "cm", "in"))
    
    print("\n5. Text Encoding:")
    print(encode_decode_text("Hello World!", "base64_encode"))