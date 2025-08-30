'use client'

import React, { useState } from 'react'
import { Copy, Check, FileText, ArrowRight, ArrowLeft, Download, Play, Terminal, Lightbulb, CheckSquare, Clock, Plus } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'

const agentCode = `from connectonion import Agent
from datetime import datetime

# Simple in-memory storage (use database in production)
tasks = []
task_counter = 1

def add_task(title: str, priority: str = "medium") -> str:
    """Add a new task to the list."""
    global task_counter
    task = {
        "id": task_counter,
        "title": title,
        "priority": priority,
        "completed": False,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    tasks.append(task)
    task_counter += 1
    return f"✅ Added task #{task['id']}: '{title}' (Priority: {priority})"

def list_tasks(status: str = "all") -> str:
    """List tasks with optional filtering."""
    if not tasks:
        return "📝 No tasks found."
    
    filtered = tasks
    if status == "pending":
        filtered = [t for t in tasks if not t["completed"]]
    elif status == "completed":
        filtered = [t for t in tasks if t["completed"]]
    
    result = f"📋 Tasks ({status}):\\n"
    for task in filtered:
        icon = "✅" if task["completed"] else "⭕"
        result += f"{icon} #{task['id']} {task['title']} [{task['priority']}]\\n"
    return result

def complete_task(task_id: int) -> str:
    """Mark a task as completed."""
    for task in tasks:
        if task["id"] == task_id:
            if task["completed"]:
                return f"Task #{task_id} is already completed!"
            task["completed"] = True
            return f"🎉 Completed task #{task_id}: '{task['title']}'"
    return f"❌ Task #{task_id} not found"

# Create task manager agent  
agent = Agent(
    name="task_manager",
    tools=[add_task, list_tasks, complete_task],
    max_iterations=10  # Task management may need multiple operations
)`

const fullExampleCode = `# task_manager_agent.py
import os
from connectonion import Agent
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Set your OpenAI API key
os.environ['OPENAI_API_KEY'] = 'your-api-key-here'

# Global task storage (in production, use a database)
tasks_database = []
task_id_counter = 1

def add_task(title: str, priority: str = "medium", due_date: str = "") -> str:
    """Add a new task with optional due date."""
    global task_id_counter
    
    # Validate priority
    valid_priorities = ["low", "medium", "high", "urgent"]
    if priority.lower() not in valid_priorities:
        priority = "medium"
    
    task = {
        "id": task_id_counter,
        "title": title.strip(),
        "priority": priority.lower(),
        "completed": False,
        "created": datetime.now().isoformat(),
        "due_date": due_date if due_date else None,
        "completed_at": None
    }
    
    tasks_database.append(task)
    task_id_counter += 1
    
    due_text = f" (Due: {due_date})" if due_date else ""
    return f"✅ Added task #{task['id']}: '{title}' [Priority: {priority.upper()}]{due_text}"

def list_tasks(filter_type: str = "all") -> str:
    """List tasks with various filtering options."""
    if not tasks_database:
        return "📝 No tasks found. Add some tasks to get started!"
    
    # Filter tasks based on type
    filtered_tasks = []
    if filter_type == "pending":
        filtered_tasks = [t for t in tasks_database if not t["completed"]]
    elif filter_type == "completed":
        filtered_tasks = [t for t in tasks_database if t["completed"]]
    elif filter_type == "high-priority":
        filtered_tasks = [t for t in tasks_database if t["priority"] in ["high", "urgent"] and not t["completed"]]
    elif filter_type == "overdue":
        today = datetime.now().date()
        filtered_tasks = [
            t for t in tasks_database 
            if not t["completed"] and t["due_date"] 
            and datetime.fromisoformat(t["due_date"]).date() < today
        ]
    else:
        filtered_tasks = tasks_database
    
    if not filtered_tasks:
        return f"📝 No {filter_type} tasks found."
    
    # Sort by priority and due date
    priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    filtered_tasks.sort(key=lambda x: (priority_order.get(x["priority"], 2), x["created"]))
    
    result = f"📋 Tasks ({filter_type.upper()}): {len(filtered_tasks)} items\\n\\n"
    
    for task in filtered_tasks:
        # Priority emoji
        priority_emoji = {
            "urgent": "🚨", "high": "🔴", "medium": "🟡", "low": "🟢"
        }.get(task["priority"], "⚪")
        
        # Status emoji
        status = "✅" if task["completed"] else "⭕"
        
        # Due date info
        due_info = ""
        if task["due_date"]:
            due_date = datetime.fromisoformat(task["due_date"]).date()
            today = datetime.now().date()
            if due_date < today:
                due_info = f" 🚨 OVERDUE ({task['due_date']})"
            elif due_date == today:
                due_info = f" 📅 DUE TODAY"
            else:
                due_info = f" 📅 Due {task['due_date']}"
        
        result += f"{status} {priority_emoji} #{task['id']} {task['title']}{due_info}\\n"
    
    return result

def complete_task(task_id: int) -> str:
    """Mark a task as completed."""
    for task in tasks_database:
        if task["id"] == task_id:
            if task["completed"]:
                return f"⚠️  Task #{task_id} is already completed!"
            
            task["completed"] = True
            task["completed_at"] = datetime.now().isoformat()
            return f"🎉 Completed task #{task_id}: '{task['title']}'!"
    
    available_ids = [str(t["id"]) for t in tasks_database]
    return f"❌ Task #{task_id} not found. Available task IDs: {', '.join(available_ids) if available_ids else 'None'}"

def update_task_priority(task_id: int, new_priority: str) -> str:
    """Update the priority of an existing task."""
    valid_priorities = ["low", "medium", "high", "urgent"]
    
    if new_priority.lower() not in valid_priorities:
        return f"❌ Invalid priority '{new_priority}'. Use: {', '.join(valid_priorities)}"
    
    for task in tasks_database:
        if task["id"] == task_id:
            old_priority = task["priority"]
            task["priority"] = new_priority.lower()
            return f"📝 Updated task #{task_id} priority: {old_priority.upper()} → {new_priority.upper()}"
    
    return f"❌ Task #{task_id} not found"

def delete_task(task_id: int) -> str:
    """Delete a task permanently."""
    for i, task in enumerate(tasks_database):
        if task["id"] == task_id:
            deleted_task = tasks_database.pop(i)
            return f"🗑️  Deleted task #{task_id}: '{deleted_task['title']}'"
    
    return f"❌ Task #{task_id} not found"

def get_task_stats() -> str:
    """Get overall task statistics."""
    if not tasks_database:
        return "📊 No tasks to analyze."
    
    total = len(tasks_database)
    completed = len([t for t in tasks_database if t["completed"]])
    pending = total - completed
    
    # Priority breakdown
    priority_counts = {}
    for task in tasks_database:
        if not task["completed"]:
            priority = task["priority"]
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
    
    # Overdue tasks
    today = datetime.now().date()
    overdue = len([
        t for t in tasks_database 
        if not t["completed"] and t["due_date"] 
        and datetime.fromisoformat(t["due_date"]).date() < today
    ])
    
    completion_rate = (completed / total * 100) if total > 0 else 0
    
    stats = f"""📊 Task Statistics
    
📈 Overall Progress:
   • Total Tasks: {total}
   • Completed: {completed} ({completion_rate:.1f}%)
   • Pending: {pending}
   
🔥 Priority Breakdown (Pending):"""
    
    for priority in ["urgent", "high", "medium", "low"]:
        count = priority_counts.get(priority, 0)
        emoji = {"urgent": "🚨", "high": "🔴", "medium": "🟡", "low": "🟢"}[priority]
        stats += f"\\n   • {emoji} {priority.title()}: {count}"
    
    if overdue > 0:
        stats += f"\\n\\n⚠️  Overdue Tasks: {overdue}"
    
    return stats

# Create the task manager agent
agent = Agent(
    name="task_manager",
    system_prompt="""You are a helpful personal task manager. You help users:
    1. Add and organize tasks with priorities and due dates
    2. Track task completion and progress
    3. Filter and view tasks by status, priority, or due date
    4. Update task priorities and delete tasks
    5. Provide task statistics and insights
    
    Always be encouraging and help users stay organized and productive!""",
    tools=[add_task, list_tasks, complete_task, update_task_priority, delete_task, get_task_stats]
)

if __name__ == "__main__":
    print("=== Task Manager Agent Demo ===\\n")
    
    # Demo workflow
    commands = [
        "Add a high priority task to review quarterly reports with due date 2024-03-15",
        "Add a task to call dentist",  
        "Add a low priority task to organize photos",
        "Show me all my tasks",
        "Complete task 1",
        "Show me pending tasks",
        "Update task 2 priority to high",
        "Give me task statistics"
    ]
    
    for i, command in enumerate(commands, 1):
        print(f"Step {i}: {command}")
        response = agent.input(command)
        print(f"Response: {response}\\n")
        print("-" * 60)`

export default function TaskManagerPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# Task Manager Agent - ConnectOnion Tutorial

Learn state management, data persistence, and CRUD operations by building a comprehensive task management agent.

## What You'll Learn

- State management with global variables
- CRUD operations (Create, Read, Update, Delete)  
- Data filtering and sorting
- Status tracking and progress monitoring
- Advanced data structures and statistics

## Key Features

- ✅ Task creation with priority levels and due dates
- 📋 Multiple filtering options (all, pending, completed, high-priority, overdue)
- 🔄 Task status updates and priority changes
- 🗑️ Task deletion capabilities
- 📊 Comprehensive task statistics and insights
- 🚨 Overdue task detection

## Complete Example

\`\`\`python
${fullExampleCode}
\`\`\`

## Advanced Concepts

This example demonstrates:
- **State Management**: Global variables for data persistence
- **CRUD Operations**: Complete task lifecycle management
- **Data Filtering**: Multiple view modes for different needs
- **Statistics**: Analytics and progress tracking
- **Error Handling**: Graceful handling of invalid operations

Perfect foundation for building stateful agents with data management!`

  return (
    <div className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-400 mb-8">
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/examples" className="hover:text-white transition-colors">Agent Building</Link>
        <ArrowRight className="w-4 h-4" />
        <span className="text-white">Task Manager</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-yellow-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">4</span>
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <FileText className="w-8 h-8 text-yellow-400" />
                <h1 className="text-4xl font-bold text-white">Task Manager Agent</h1>
                <span className="px-3 py-1 bg-yellow-900/50 text-yellow-300 rounded-full text-sm font-medium">
                  Intermediate
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Learn state management, CRUD operations, and data persistence with a full-featured task management system.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="task-manager-agent.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Key Concepts */}
      <div className="mb-12 p-6 bg-yellow-900/20 border border-yellow-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-yellow-400" />
          What You'll Learn
        </h2>
        <div className="grid md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-yellow-600 rounded-lg flex items-center justify-center">
              <Plus className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">CRUD Operations</h3>
            <p className="text-yellow-200 text-sm">Create, Read, Update, Delete data</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-yellow-600 rounded-lg flex items-center justify-center">
              <CheckSquare className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">State Management</h3>
            <p className="text-yellow-200 text-sm">Persistent data across interactions</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-yellow-600 rounded-lg flex items-center justify-center">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Data Filtering</h3>
            <p className="text-yellow-200 text-sm">Multiple view modes and sorting</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-yellow-600 rounded-lg flex items-center justify-center">
              <Clock className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Analytics</h3>
            <p className="text-yellow-200 text-sm">Progress tracking and statistics</p>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-12">
        {/* Code Examples */}
        <div className="space-y-8">
          {/* Basic Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Basic Task Manager</h3>
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
                {agentCode}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* Complete Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Complete Task Manager</h3>
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
              <Terminal className="w-5 h-5 text-yellow-400" />
              <h3 className="text-xl font-semibold text-white">Expected Output</h3>
            </div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm ">
                <pre className="text-yellow-200 whitespace-pre-wrap">
                  {`=== Task Manager Agent Demo ===

Step 1: Add a high priority task to review quarterly reports
Response: ✅ Added task #1: 'review quarterly reports' [Priority: HIGH] (Due: 2024-03-15)

Step 4: Show me all my tasks  
Response: 📋 Tasks (ALL): 3 items

⭕ 🚨 #1 review quarterly reports 📅 Due 2024-03-15
⭕ 🟡 #2 call dentist
⭕ 🟢 #3 organize photos

Step 5: Complete task 1
Response: 🎉 Completed task #1: 'review quarterly reports'!

Step 8: Give me task statistics
Response: 📊 Task Statistics
    
📈 Overall Progress:
   • Total Tasks: 3
   • Completed: 1 (33.3%)
   • Pending: 2
   
🔥 Priority Breakdown (Pending):
   • 🚨 Urgent: 0
   • 🔴 High: 1
   • 🟡 Medium: 0  
   • 🟢 Low: 1`}
                </pre>
              </div>
            </div>
          </div>

          {/* State Management */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-4">State Management</h3>
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-yellow-400 mb-2">📦 Persistent Data</h4>
                <p className="text-gray-300">Tasks remain in memory across agent interactions, simulating database persistence.</p>
              </div>
              <div>
                <h4 className="font-semibold text-yellow-400 mb-2">🔄 CRUD Operations</h4>
                <p className="text-gray-300">Complete Create, Read, Update, Delete lifecycle for task management.</p>
              </div>
              <div>
                <h4 className="font-semibold text-yellow-400 mb-2">📊 Analytics</h4>
                <p className="text-gray-300">Real-time statistics and progress tracking with completion rates.</p>
              </div>
            </div>
          </div>

          {/* Features */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Advanced Features</h3>
            <div className="space-y-3 text-sm">
              <div className="p-3 bg-yellow-900/20 border border-yellow-500/30 rounded">
                <p className="text-yellow-300 font-medium mb-1">🎯 Priority Management</p>
                <p className="text-yellow-200">Four priority levels: Low, Medium, High, Urgent with visual indicators</p>
              </div>
              <div className="p-3 bg-yellow-900/20 border border-yellow-500/30 rounded">
                <p className="text-yellow-300 font-medium mb-1">📅 Due Date Tracking</p>
                <p className="text-yellow-200">Due dates with overdue detection and alerts</p>
              </div>
              <div className="p-3 bg-yellow-900/20 border border-yellow-500/30 rounded">
                <p className="text-yellow-300 font-medium mb-1">🔍 Smart Filtering</p>
                <p className="text-yellow-200">Filter by status, priority, or due date for focused task management</p>
              </div>
            </div>
          </div>

          {/* Download */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Try It Yourself</h3>
            <div className="space-y-3">
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(fullExampleCode)}`}
                download="task_manager_agent.py"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-yellow-600 hover:bg-yellow-700 rounded-lg text-white transition-colors font-medium"
              >
                <Download className="w-4 h-4" />
                Download Complete Example
              </a>
              <p className="text-xs text-gray-400 text-center">
                Full-featured task manager with priorities, due dates, and analytics
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
            href="/examples/weather-bot" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            3. Weather Bot
          </Link>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Next in series</p>
          <Link 
            href="/examples/math-tutor-agent" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            5. Math Tutor Agent
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}