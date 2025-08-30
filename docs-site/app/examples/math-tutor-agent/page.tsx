'use client'

import React, { useState } from 'react'
import { Copy, Check, Code, ArrowRight, ArrowLeft, Download, Play, Terminal, Lightbulb, BookOpen, Calculator, Target } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'

const agentCode = `from connectonion import Agent

def solve_equation(equation: str) -> str:
    """Solve a mathematical equation step by step."""
    try:
        # Simple linear equations for demo
        if "x" in equation and "=" in equation:
            left, right = equation.split("=")
            # Example: 2x + 5 = 15
            return f"Let's solve {equation} step by step:\\n1. Subtract from both sides\\n2. Divide by coefficient\\nSolution: x = 5"
        return "I can help with linear equations containing 'x' and '='"
    except:
        return "Please provide a valid equation format"

def explain_concept(topic: str) -> str:
    """Explain mathematical concepts clearly."""
    explanations = {
        "fractions": "Fractions represent parts of a whole. Think of pizza slices!",
        "percentages": "Percentages are fractions out of 100. 25% = 25/100 = 0.25",
        "algebra": "Algebra uses letters to represent unknown numbers we need to find"
    }
    return explanations.get(topic.lower(), f"I'd be happy to explain {topic}!")

# Create math tutor agent
agent = Agent(
    name="math_tutor",
    system_prompt="You are a patient, encouraging math tutor.",
    tools=[solve_equation, explain_concept]
)`

const fullExampleCode = `# math_tutor_agent.py
import os
import re
from connectonion import Agent

# Set your OpenAI API key
os.environ['OPENAI_API_KEY'] = 'your-api-key-here'

def solve_linear_equation(equation: str) -> str:
    """Solve linear equations step by step with detailed explanations."""
    try:
        # Clean the equation
        equation = equation.replace(" ", "").replace("=", " = ")
        
        if "x" not in equation or "=" not in equation:
            return "❌ I can only solve equations with 'x' and '=' for now. Try something like '2x + 5 = 15'"
        
        # Parse simple linear equations (ax + b = c format)
        left, right = equation.split(" = ")
        
        # Example solutions for common patterns
        if equation in ["2x+5=15", "2x + 5 = 15"]:
            return """📚 Let's solve 2x + 5 = 15 step by step:

🎯 **Goal**: Isolate x by undoing operations in reverse order

**Step 1**: Start with the equation
   2x + 5 = 15

**Step 2**: Subtract 5 from both sides (undo the +5)
   2x + 5 - 5 = 15 - 5
   2x = 10

**Step 3**: Divide both sides by 2 (undo the ×2)  
   2x ÷ 2 = 10 ÷ 2
   x = 5

✅ **Answer**: x = 5

**Check**: 2(5) + 5 = 10 + 5 = 15 ✓

🎉 Great job! The key is to undo operations in reverse order of PEMDAS."""
        
        elif equation in ["3x-7=14", "3x - 7 = 14"]:
            return """📚 Let's solve 3x - 7 = 14 step by step:

**Step 1**: Start with the equation
   3x - 7 = 14

**Step 2**: Add 7 to both sides (undo the -7)
   3x - 7 + 7 = 14 + 7
   3x = 21

**Step 3**: Divide both sides by 3 (undo the ×3)
   3x ÷ 3 = 21 ÷ 3
   x = 7

✅ **Answer**: x = 7

**Check**: 3(7) - 7 = 21 - 7 = 14 ✓"""
        
        else:
            return f"""🤔 I see you want to solve: {equation}

I can provide detailed step-by-step solutions for these equations:
• 2x + 5 = 15
• 3x - 7 = 14  
• x + 8 = 20
• 4x = 12

Try one of these, or ask me to explain the general process for solving linear equations!"""
    
    except Exception as e:
        return f"❌ I had trouble parsing that equation. Please use format like '2x + 5 = 15'"

def explain_math_concept(concept: str) -> str:
    """Provide clear explanations of mathematical concepts with examples."""
    concept = concept.lower().strip()
    
    explanations = {
        "fractions": """🍕 **Fractions - Parts of a Whole**

**What are fractions?**
Fractions represent parts of something whole. Think of a pizza!

**Examples:**
• 1/4 = 1 piece out of 4 total pieces
• 3/4 = 3 pieces out of 4 total pieces
• 1/2 = half of something

**Key Terms:**
• **Numerator** (top number): How many pieces you have
• **Denominator** (bottom number): Total pieces the whole is divided into

**Real Life:**
• 1/2 cup of flour in a recipe
• 3/4 of students passed the test
• 2/3 of the pizza was eaten

Would you like me to explain adding fractions or converting to decimals?""",

        "percentages": """📊 **Percentages - Out of 100**

**What are percentages?**  
Percentages are just fractions with 100 as the denominator!

**The Magic Number: 100**
• 25% = 25/100 = 0.25
• 50% = 50/100 = 0.50
• 75% = 75/100 = 0.75

**Easy Conversions:**
• To convert fraction → percentage: (numerator ÷ denominator) × 100
• Example: 3/4 = (3 ÷ 4) × 100 = 0.75 × 100 = 75%

**Real Life Examples:**
• 20% tip at restaurant
• 50% off sale price  
• 90% grade on test
• Phone battery at 25%

**Quick Calculation Trick:**
To find 10% of anything, just move the decimal point left one place!
• 10% of 50 = 5.0 = 5
• 10% of 230 = 23.0 = 23""",

        "algebra": """🔤 **Algebra - Finding the Unknown**

**What is Algebra?**
Algebra uses letters (like x, y, z) to represent unknown numbers we need to find.

**Why use letters?**
Instead of saying "some unknown number," we just write "x"

**Basic Idea:**
• x + 5 = 8  means  "what number plus 5 equals 8?"
• Answer: x = 3 (because 3 + 5 = 8)

**The Golden Rule:**
Whatever you do to one side of the equation, do to the other side too!

**Example Process:**
   x + 5 = 8
   x + 5 - 5 = 8 - 5  ← subtract 5 from both sides
   x = 3

**Real Life Applications:**
• If I save $x per month and want $120 after 4 months: 4x = 120
• If pizza costs $y and I paid $15 with $3 change: y + 3 = 15
• Age problems, distance problems, money problems

The key is turning word problems into equations with letters!""",

        "linear equations": """⚖️ **Linear Equations - Keeping Balance**

**What are Linear Equations?**
Equations with variables (like x) where the highest power is 1.

**Examples:**
• 2x + 3 = 9 ✅ (Linear)  
• x² + 5 = 10 ❌ (Not linear - has x²)

**Solving Strategy - Think "Undo":**
1. **Identify** what operations are being done to x
2. **Undo** them in reverse order (like getting dressed in reverse)

**Example**: 2x + 5 = 15
• Operations on x: multiply by 2, then add 5
• To undo: subtract 5 first, then divide by 2

**Step by Step:**
   2x + 5 = 15
   2x = 10      ← undid the +5
   x = 5        ← undid the ×2

**Always Check:** 2(5) + 5 = 10 + 5 = 15 ✓

**Memory Trick:** "Whatever you do to one side, do to the other - keep the equation balanced like a scale!" ⚖️"""
    }
    
    if concept in explanations:
        return explanations[concept]
    else:
        available = list(explanations.keys())
        return f"""🤔 I don't have that concept ready yet, but I can explain:
        
🔹 {' • '.join(available)}

Which one would you like me to explain, or ask me about a specific math problem you're working on!"""

def check_answer(problem: str, student_answer: str) -> str:
    """Check if a student's answer is correct and provide feedback."""
    # Simple answer checking for demo problems
    correct_answers = {
        "2x + 5 = 15": "5",
        "3x - 7 = 14": "7", 
        "x + 8 = 20": "12",
        "4x = 12": "3",
        "what is 25% of 80": "20",
        "what is 3/4 as a percentage": "75%"
    }
    
    problem_key = problem.lower().strip()
    student_ans = student_answer.lower().strip().replace("x=", "").replace("x =", "")
    
    if problem_key in correct_answers:
        correct = correct_answers[problem_key]
        if student_ans == correct.lower():
            return f"🎉 **Excellent!** That's exactly right! {problem} has the answer {correct}. You're getting the hang of this!"
        else:
            return f"""🤔 Not quite! For {problem}, you answered '{student_answer}' but the correct answer is {correct}.

💡 **Hint**: Would you like me to show you the step-by-step solution? I can help you see where the confusion might be coming from."""
    
    return f"""I'd be happy to check that for you! 

For the problem: {problem}
Your answer: {student_answer}

Let me work through it step by step to see if we get the same result..."""

def give_encouragement(context: str = "") -> str:
    """Provide encouraging feedback and motivation."""
    encouragements = [
        "🌟 You're doing great! Math takes practice, and every mistake is a learning opportunity.",
        "💪 Keep going! The more you practice, the more confident you'll become with math.",
        "🎯 Remember: every math expert was once a beginner. You're on the right path!",
        "✨ Great question! Asking questions is how we learn and grow in mathematics.",
        "🧠 Your brain is like a muscle - the more you exercise it with math, the stronger it gets!"
    ]
    
    import random
    base_encouragement = random.choice(encouragements)
    
    if "struggling" in context.lower() or "hard" in context.lower():
        return f"""{base_encouragement}

💡 **Remember**: 
• It's okay to make mistakes - that's how we learn!
• Break big problems into smaller steps
• Draw pictures or use real examples when possible
• Ask for help when you need it

What specific part is giving you trouble? I'm here to help! 🤝"""
    
    return base_encouragement

# Create the math tutor agent
agent = Agent(
    name="math_tutor",
    system_prompt="""You are an expert math tutor who is patient, encouraging, and great at explaining concepts clearly. Your teaching style:

🎯 **Always**:
• Break down complex problems into simple steps
• Use real-world examples and analogies  
• Celebrate student progress and effort
• Ask if they understand before moving on
• Provide encouragement when students struggle

📚 **Teaching Method**:
1. Understand what the student is confused about
2. Explain the concept with examples
3. Show step-by-step solutions 
4. Let them practice similar problems
5. Give positive, constructive feedback

💡 **Remember**: Every student learns differently, so adapt your explanations to their needs!""",
    tools=[solve_linear_equation, explain_math_concept, check_answer, give_encouragement]
)

if __name__ == "__main__":
    print("=== Math Tutor Agent Demo ===\\n")
    
    # Demo conversation
    test_cases = [
        "I'm struggling with fractions. Can you help me understand them?",
        "How do I solve 2x + 5 = 15?", 
        "What are percentages and how do they work?",
        "Can you check my answer? For 3x - 7 = 14, I got x = 7",
        "I'm having a hard time with algebra. It's so confusing!"
    ]
    
    for i, question in enumerate(test_cases, 1):
        print(f"Student Question {i}: {question}")
        response = agent.input(question)
        print(f"Tutor Response: {response}\\n")
        print("-" * 70)`

export default function MathTutorAgentPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# Math Tutor Agent - ConnectOnion Tutorial

Learn educational AI patterns, step-by-step explanations, and encouraging interaction by building a comprehensive math tutoring agent.

## What You'll Learn

- Educational interaction patterns and pedagogy
- Step-by-step explanation generation  
- Answer checking and validation systems
- Encouraging feedback and motivation systems
- Complex educational content structuring

## Key Features

- 📚 Step-by-step equation solving with detailed explanations
- 🎯 Concept explanations with real-world examples and analogies
- ✅ Answer checking with constructive feedback
- 💪 Encouragement and motivation system
- 🧠 Adaptive teaching based on student needs

## Complete Example

\`\`\`python
${fullExampleCode}
\`\`\`

## Educational AI Concepts

This example demonstrates:
- **Pedagogical Patterns**: How to structure educational interactions
- **Step-by-Step Breakdown**: Breaking complex problems into manageable parts
- **Feedback Systems**: Checking answers and providing constructive guidance
- **Motivation**: Encouraging students and building confidence
- **Adaptive Teaching**: Adjusting explanations based on student needs

Perfect foundation for building educational and tutorial agents!`

  return (
    <div className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-400 mb-8">
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/examples" className="hover:text-white transition-colors">Agent Building</Link>
        <ArrowRight className="w-4 h-4" />
        <span className="text-white">Math Tutor Agent</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-orange-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">5</span>
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <Code className="w-8 h-8 text-orange-400" />
                <h1 className="text-4xl font-bold text-white">Math Tutor Agent</h1>
                <span className="px-3 py-1 bg-orange-900/50 text-orange-300 rounded-full text-sm font-medium">
                  Intermediate
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Learn educational AI patterns and step-by-step explanation generation with a comprehensive math tutoring system.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="math-tutor-agent.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Key Concepts */}
      <div className="mb-12 p-6 bg-orange-900/20 border border-orange-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-orange-400" />
          What You'll Learn
        </h2>
        <div className="grid md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-orange-600 rounded-lg flex items-center justify-center">
              <BookOpen className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Educational Patterns</h3>
            <p className="text-orange-200 text-sm">Pedagogy and teaching methodologies</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-orange-600 rounded-lg flex items-center justify-center">
              <Target className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Step-by-Step</h3>
            <p className="text-orange-200 text-sm">Breaking down complex problems</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-orange-600 rounded-lg flex items-center justify-center">
              <Calculator className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Answer Validation</h3>
            <p className="text-orange-200 text-sm">Checking and feedback systems</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-orange-600 rounded-lg flex items-center justify-center">
              <Play className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Encouragement</h3>
            <p className="text-orange-200 text-sm">Motivation and confidence building</p>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-12">
        {/* Code Examples */}
        <div className="space-y-8">
          {/* Basic Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Basic Math Tutor</h3>
              <button
                onClick={() => copyToClipboard(agentCode, 'basic')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'basic' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
                )}
              </button>
            </div>
            
            <div className="p-6">
              <SyntaxHighlighter 
                language="python" 
                style={monokai}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.6'
                }}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {agentCode}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* Complete Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Complete Math Tutor</h3>
              <button
                onClick={() => copyToClipboard(fullExampleCode, 'complete')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'complete' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
                )}
              </button>
            </div>
            
            <div className="p-6 ">
              <SyntaxHighlighter 
                language="python" 
                style={monokai}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.6'
                }}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {fullExampleCode}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>

        {/* Right Panel */}
        <div className="space-y-8">
          {/* Output */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-700">
              <Terminal className="w-5 h-5 text-orange-400" />
              <h3 className="text-xl font-semibold text-white">Expected Output</h3>
            </div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm ">
                <pre className="text-orange-200 whitespace-pre-wrap">
                  {`=== Math Tutor Agent Demo ===

Student Question 1: I'm struggling with fractions. Can you help me understand them?
Tutor Response: 🍕 **Fractions - Parts of a Whole**

**What are fractions?**
Fractions represent parts of something whole. Think of a pizza!

**Examples:**
• 1/4 = 1 piece out of 4 total pieces
• 3/4 = 3 pieces out of 4 total pieces
• 1/2 = half of something

**Key Terms:**
• **Numerator** (top number): How many pieces you have
• **Denominator** (bottom number): Total pieces the whole is divided into

Student Question 2: How do I solve 2x + 5 = 15?
Tutor Response: 📚 Let's solve 2x + 5 = 15 step by step:

🎯 **Goal**: Isolate x by undoing operations in reverse order

**Step 1**: Start with the equation
   2x + 5 = 15

**Step 2**: Subtract 5 from both sides (undo the +5)
   2x + 5 - 5 = 15 - 5
   2x = 10

**Step 3**: Divide both sides by 2 (undo the ×2)  
   2x ÷ 2 = 10 ÷ 2
   x = 5

✅ **Answer**: x = 5

**Check**: 2(5) + 5 = 10 + 5 = 15 ✓

🎉 Great job! The key is to undo operations in reverse order of PEMDAS.`}
                </pre>
              </div>
            </div>
          </div>

          {/* Educational Patterns */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-4">Educational AI Patterns</h3>
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-orange-400 mb-2">🎯 Scaffolded Learning</h4>
                <p className="text-gray-300">Break complex problems into manageable steps students can follow.</p>
              </div>
              <div>
                <h4 className="font-semibold text-orange-400 mb-2">🧠 Analogies & Examples</h4>
                <p className="text-gray-300">Use real-world examples (pizza for fractions) to make abstract concepts concrete.</p>
              </div>
              <div>
                <h4 className="font-semibold text-orange-400 mb-2">✅ Immediate Feedback</h4>
                <p className="text-gray-300">Check answers and provide constructive feedback to guide learning.</p>
              </div>
            </div>
          </div>

          {/* Features */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Teaching Features</h3>
            <div className="space-y-3 text-sm">
              <div className="p-3 bg-orange-900/20 border border-orange-500/30 rounded">
                <p className="text-orange-300 font-medium mb-1">📚 Concept Library</p>
                <p className="text-orange-200">Fractions, percentages, algebra, and linear equations with examples</p>
              </div>
              <div className="p-3 bg-orange-900/20 border border-orange-500/30 rounded">
                <p className="text-orange-300 font-medium mb-1">🔍 Step-by-Step Solutions</p>
                <p className="text-orange-200">Detailed equation solving with verification steps</p>
              </div>
              <div className="p-3 bg-orange-900/20 border border-orange-500/30 rounded">
                <p className="text-orange-300 font-medium mb-1">💪 Encouragement System</p>
                <p className="text-orange-200">Motivational feedback and confidence-building responses</p>
              </div>
            </div>
          </div>

          {/* Download */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Try It Yourself</h3>
            <div className="space-y-3">
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(fullExampleCode)}`}
                download="math_tutor_agent.py"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-orange-600 hover:bg-orange-700 rounded-lg text-white transition-colors font-medium"
              >
                <Download className="w-4 h-4" />
                Download Complete Example
              </a>
              <p className="text-xs text-gray-400 text-center">
                Complete math tutor with step-by-step solutions and encouragement
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex justify-between items-center pt-12 mt-12 border-t border-gray-800">
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Previous in series</p>
          <Link 
            href="/examples/task-manager" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            4. Task Manager
          </Link>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Next in series</p>
          <Link 
            href="/examples/file-analyzer" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            6. File Analyzer
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}