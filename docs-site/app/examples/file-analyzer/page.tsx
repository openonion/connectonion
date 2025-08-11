'use client'

import React, { useState } from 'react'
import { Copy, Check, FileText, ArrowRight, ArrowLeft, Download, Play, Terminal, Lightbulb, Search, FolderOpen, Shield } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'

const agentCode = `from connectonion import Agent
import os
from pathlib import Path

def analyze_file(filepath: str) -> str:
    """Analyze a file and return detailed information."""
    try:
        path = Path(filepath)
        if not path.exists():
            return f"File not found: {filepath}"
        
        # Get file stats
        stat = path.stat()
        size = stat.st_size
        
        # Determine file type
        suffix = path.suffix.lower()
        file_types = {
            '.py': 'Python source code',
            '.js': 'JavaScript source code',
            '.md': 'Markdown documentation',
            '.txt': 'Plain text file',
            '.json': 'JSON data file',
            '.csv': 'CSV data file'
        }
        
        file_type = file_types.get(suffix, f'File with {suffix} extension')
        
        return f"""File Analysis: {path.name}
Type: {file_type}
Size: {size} bytes
Full path: {path.absolute()}"""
        
    except Exception as e:
        return f"Analysis error: {str(e)}"

def search_files(directory: str, pattern: str) -> str:
    """Search for files matching a pattern in directory."""
    try:
        path = Path(directory)
        if not path.exists():
            return f"Directory not found: {directory}"
        
        matches = list(path.glob(pattern))[:10]  # Limit to 10 results
        
        if not matches:
            return f"No files matching '{pattern}' found in {directory}"
        
        result = f"Found {len(matches)} files matching '{pattern}':\\n"
        for match in matches:
            result += f"- {match.name} ({match.stat().st_size} bytes)\\n"
            
        return result
        
    except Exception as e:
        return f"Search error: {str(e)}"

# Create file analysis agent
agent = Agent(
    name="file_analyst",
    tools=[analyze_file, search_files]
)`

const fullExampleCode = `# file_analyzer_agent.py
import os
import mimetypes
from pathlib import Path
from datetime import datetime
from connectonion import Agent

# Set your OpenAI API key
os.environ['OPENAI_API_KEY'] = 'your-api-key-here'

def analyze_file(filepath: str) -> str:
    """Analyze a file and return comprehensive information about it."""
    try:
        path = Path(filepath)
        if not path.exists():
            return f"❌ File not found: {filepath}\\n\\nPlease check the file path and try again."
        
        # Get file statistics
        stat = path.stat()
        size_bytes = stat.st_size
        created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        
        # Convert size to human readable format
        def human_readable_size(bytes_size):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if bytes_size < 1024.0:
                    return f"{bytes_size:.1f} {unit}"
                bytes_size /= 1024.0
            return f"{bytes_size:.1f} TB"
        
        size_human = human_readable_size(size_bytes)
        
        # Determine file type and MIME type
        suffix = path.suffix.lower()
        mime_type, _ = mimetypes.guess_type(str(path))
        
        file_type_mapping = {
            '.py': '🐍 Python source code',
            '.js': '🟨 JavaScript source code',
            '.ts': '🔷 TypeScript source code', 
            '.html': '🌐 HTML document',
            '.css': '🎨 CSS stylesheet',
            '.md': '📝 Markdown documentation',
            '.txt': '📄 Plain text file',
            '.json': '📋 JSON data file',
            '.csv': '📊 CSV data file',
            '.xml': '🏷️ XML document',
            '.yml': '⚙️ YAML configuration',
            '.yaml': '⚙️ YAML configuration',
            '.pdf': '📚 PDF document',
            '.jpg': '🖼️ JPEG image',
            '.jpeg': '🖼️ JPEG image',
            '.png': '🖼️ PNG image',
            '.gif': '🖼️ GIF image',
            '.mp4': '🎥 MP4 video',
            '.mp3': '🎵 MP3 audio',
            '.zip': '📦 ZIP archive',
            '.tar': '📦 TAR archive',
            '.gz': '📦 GZIP archive'
        }
        
        file_type = file_type_mapping.get(suffix, f'📎 {suffix.upper()[1:]} file' if suffix else '📎 Unknown file type')
        
        # Try to read content preview for text files
        preview = ""
        text_extensions = {'.py', '.js', '.ts', '.html', '.css', '.md', '.txt', '.json', '.csv', '.xml', '.yml', '.yaml'}
        
        if suffix in text_extensions and size_bytes < 1024 * 100:  # Only for files < 100KB
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(500)  # First 500 characters
                    lines = content.split('\\n')[:10]  # First 10 lines
                    preview = '\\n'.join(lines)
                    if len(content) >= 500:
                        preview += "\\n\\n... (truncated)"
            except Exception:
                preview = "❌ Unable to read file content (binary or encoding issue)"
        elif suffix in {'.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mp3', '.pdf', '.zip', '.tar', '.gz'}:
            preview = f"📎 Binary file - content preview not available for {file_type}"
        
        # Security analysis for executable files
        security_note = ""
        executable_extensions = {'.exe', '.bat', '.sh', '.ps1', '.cmd', '.com', '.scr', '.pif'}
        if suffix in executable_extensions:
            security_note = "\\n⚠️  **Security Warning**: This is an executable file. Exercise caution when running."
        
        result = f"""📁 **File Analysis Report**

**Basic Information:**
• Name: {path.name}
• Type: {file_type}
• Size: {size_human} ({size_bytes:,} bytes)
• Location: {path.absolute()}

**Timestamps:**
• Created: {created}
• Modified: {modified}
• MIME Type: {mime_type or 'Unknown'}

**Content Preview:**
{preview if preview else "No preview available"}

{security_note}"""
        
        return result
        
    except PermissionError:
        return f"❌ Permission denied: Cannot access {filepath}\\n\\nYou may need elevated permissions to analyze this file."
    except Exception as e:
        return f"❌ Analysis error: {str(e)}\\n\\nPlease check the file path and try again."

def search_files(directory: str, pattern: str = "*", file_type: str = "") -> str:
    """Search for files in a directory with optional pattern and type filtering."""
    try:
        path = Path(directory)
        if not path.exists():
            return f"❌ Directory not found: {directory}\\n\\nPlease check the directory path."
        
        if not path.is_dir():
            return f"❌ Path is not a directory: {directory}"
        
        # Build search pattern
        search_pattern = pattern
        if file_type:
            if not file_type.startswith('.'):
                file_type = f'.{file_type}'
            search_pattern = f"*{file_type}"
        
        # Search for files (recursive)
        try:
            if '**' in search_pattern:
                matches = list(path.glob(search_pattern))
            else:
                matches = list(path.rglob(search_pattern))
        except Exception:
            matches = list(path.glob(search_pattern))
        
        # Filter out directories, keep only files
        file_matches = [m for m in matches if m.is_file()]
        
        if not file_matches:
            return f"📂 No files found matching pattern '{search_pattern}' in {directory}\\n\\n💡 Try using patterns like '*.py' for Python files or '**/*.txt' for recursive text file search."
        
        # Sort by modification time (newest first) and limit results
        file_matches.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        limited_matches = file_matches[:20]  # Limit to 20 results
        
        # Calculate total size
        total_size = sum(f.stat().st_size for f in file_matches)
        
        def human_readable_size(bytes_size):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if bytes_size < 1024.0:
                    return f"{bytes_size:.1f} {unit}"
                bytes_size /= 1024.0
            return f"{bytes_size:.1f} TB"
        
        result = f"""🔍 **Search Results**

Found **{len(file_matches)}** files matching '{search_pattern}' in {directory}
Total size: {human_readable_size(total_size)}

**Files (showing latest {len(limited_matches)}):**
"""
        
        for i, match in enumerate(limited_matches, 1):
            size = human_readable_size(match.stat().st_size)
            modified = datetime.fromtimestamp(match.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            relative_path = match.relative_to(path)
            result += f"{i:2d}. 📄 {relative_path} ({size}) - Modified: {modified}\\n"
        
        if len(file_matches) > 20:
            result += f"\\n... and {len(file_matches) - 20} more files"
        
        return result
        
    except PermissionError:
        return f"❌ Permission denied: Cannot access directory {directory}\\n\\nYou may need elevated permissions."
    except Exception as e:
        return f"❌ Search error: {str(e)}"

def get_directory_summary(directory: str) -> str:
    """Get a summary overview of a directory's contents."""
    try:
        path = Path(directory)
        if not path.exists():
            return f"❌ Directory not found: {directory}"
        
        if not path.is_dir():
            return f"❌ Path is not a directory: {directory}"
        
        # Count files and subdirectories
        files = []
        subdirs = []
        file_types = {}
        total_size = 0
        
        try:
            for item in path.iterdir():
                if item.is_file():
                    files.append(item)
                    total_size += item.stat().st_size
                    ext = item.suffix.lower()
                    file_types[ext] = file_types.get(ext, 0) + 1
                elif item.is_dir():
                    subdirs.append(item)
        except PermissionError:
            return f"❌ Permission denied: Cannot read directory contents of {directory}"
        
        def human_readable_size(bytes_size):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if bytes_size < 1024.0:
                    return f"{bytes_size:.1f} {unit}"
                bytes_size /= 1024.0
            return f"{bytes_size:.1f} TB"
        
        # Sort file types by count
        sorted_types = sorted(file_types.items(), key=lambda x: x[1], reverse=True)
        
        result = f"""📊 **Directory Summary: {path.name}**

**Overview:**
• Location: {path.absolute()}
• Files: {len(files)}
• Subdirectories: {len(subdirs)}
• Total size: {human_readable_size(total_size)}

**File Types:**"""
        
        for ext, count in sorted_types[:10]:  # Top 10 file types
            ext_name = ext.upper()[1:] if ext else "No extension"
            result += f"\\n• {ext_name}: {count} files"
        
        if len(sorted_types) > 10:
            result += f"\\n• ... and {len(sorted_types) - 10} more file types"
        
        # List subdirectories
        if subdirs:
            result += f"\\n\\n**Subdirectories:**"
            for subdir in sorted(subdirs)[:10]:  # First 10 subdirectories
                result += f"\\n• 📁 {subdir.name}"
            if len(subdirs) > 10:
                result += f"\\n• ... and {len(subdirs) - 10} more directories"
        
        return result
        
    except Exception as e:
        return f"❌ Directory analysis error: {str(e)}"

def find_large_files(directory: str, min_size_mb: float = 10.0) -> str:
    """Find large files in a directory tree."""
    try:
        path = Path(directory)
        if not path.exists():
            return f"❌ Directory not found: {directory}"
        
        min_size_bytes = int(min_size_mb * 1024 * 1024)  # Convert MB to bytes
        large_files = []
        
        def scan_directory(dir_path):
            try:
                for item in dir_path.rglob('*'):
                    if item.is_file():
                        try:
                            size = item.stat().st_size
                            if size >= min_size_bytes:
                                large_files.append((item, size))
                        except (PermissionError, FileNotFoundError):
                            continue
            except PermissionError:
                pass
        
        scan_directory(path)
        
        if not large_files:
            return f"📁 No files larger than {min_size_mb}MB found in {directory}\\n\\n💡 Try lowering the size threshold or checking a different directory."
        
        # Sort by size (largest first)
        large_files.sort(key=lambda x: x[1], reverse=True)
        
        def human_readable_size(bytes_size):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if bytes_size < 1024.0:
                    return f"{bytes_size:.1f} {unit}"
                bytes_size /= 1024.0
            return f"{bytes_size:.1f} TB"
        
        total_size = sum(size for _, size in large_files)
        result = f"""📏 **Large Files Report**

Found **{len(large_files)}** files larger than {min_size_mb}MB
Total size: {human_readable_size(total_size)}

**Largest Files:**
"""
        
        for i, (file_path, size) in enumerate(large_files[:15], 1):  # Show top 15
            relative_path = file_path.relative_to(path) if file_path.is_relative_to(path) else file_path
            size_str = human_readable_size(size)
            result += f"{i:2d}. {size_str:>8} - {relative_path}\\n"
        
        if len(large_files) > 15:
            result += f"\\n... and {len(large_files) - 15} more large files"
        
        return result
        
    except Exception as e:
        return f"❌ Large files search error: {str(e)}"

# Create the comprehensive file analyzer agent
agent = Agent(
    name="file_analyzer",
    system_prompt="""You are a helpful file analysis assistant with expertise in:
    
🔍 **File Analysis**: Detailed information about individual files including type, size, timestamps, and content preview
📂 **Directory Exploration**: Searching and summarizing directory contents  
🔎 **Pattern Matching**: Finding files by name patterns, extensions, or types
📏 **Size Analysis**: Identifying large files and disk usage patterns

Always provide clear, organized information and helpful suggestions for file management tasks.
Be security-conscious and warn about potentially dangerous file types.""",
    tools=[analyze_file, search_files, get_directory_summary, find_large_files]
)

if __name__ == "__main__":
    print("=== File Analyzer Agent Demo ===\\n")
    
    # Demo commands
    demo_commands = [
        "Analyze the file 'example.py' in the current directory",
        "Search for all Python files in the current directory", 
        "Give me a summary of the current directory",
        "Find files larger than 1MB in the current directory",
        "Search for all markdown files recursively"
    ]
    
    for i, command in enumerate(demo_commands, 1):
        print(f"Command {i}: {command}")
        response = agent.input(command)
        print(f"Response: {response}\\n")
        print("-" * 70)`

export default function FileAnalyzerPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# File Analyzer Agent - ConnectOnion Tutorial

Learn file system integration, security considerations, and advanced data processing by building a comprehensive file analysis agent.

## What You'll Learn

- File system integration and path handling
- Security considerations for file operations
- Content analysis and MIME type detection
- Recursive directory traversal and pattern matching
- Error handling for system-level operations

## Key Features

- 📁 Comprehensive file analysis with metadata and content preview
- 🔍 Advanced file searching with pattern matching and filtering
- 📊 Directory summarization with file type breakdown
- 📏 Large file detection and disk usage analysis
- 🔒 Security warnings for potentially dangerous files
- ⚡ Efficient recursive directory traversal

## Complete Example

\`\`\`python
${fullExampleCode}
\`\`\`

## System Integration Concepts

This example demonstrates:
- **File System Operations**: Safe file and directory access
- **Security Awareness**: Warnings for executable and potentially dangerous files
- **Performance Optimization**: Limiting results and handling large directories
- **Error Handling**: Graceful handling of permissions and missing files
- **Content Analysis**: MIME type detection and preview generation

Perfect foundation for building system integration and file management agents!`

  return (
    <div className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Header content similar to previous examples */}
      <nav className="flex items-center gap-2 text-sm text-gray-400 mb-8">
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/examples" className="hover:text-white transition-colors">Agent Building</Link>
        <ArrowRight className="w-4 h-4" />
        <span className="text-white">File Analyzer</span>
      </nav>

      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-purple-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">6</span>
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <FileText className="w-8 h-8 text-purple-400" />
                <h1 className="text-4xl font-bold text-white">File Analyzer Agent</h1>
                <span className="px-3 py-1 bg-purple-900/50 text-purple-300 rounded-full text-sm font-medium">
                  Advanced
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Learn file system integration and security considerations with a comprehensive file analysis system.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="file-analyzer-agent.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Key concepts and code sections similar to previous examples */}
      <div className="mb-12 p-6 bg-purple-900/20 border border-purple-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-purple-400" />
          What You'll Learn
        </h2>
        <div className="grid md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-purple-600 rounded-lg flex items-center justify-center">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">File System</h3>
            <p className="text-purple-200 text-sm">Safe file and directory operations</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-purple-600 rounded-lg flex items-center justify-center">
              <Shield className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Security</h3>
            <p className="text-purple-200 text-sm">Warnings and permission handling</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-purple-600 rounded-lg flex items-center justify-center">
              <Search className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Pattern Matching</h3>
            <p className="text-purple-200 text-sm">Advanced file search and filtering</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-purple-600 rounded-lg flex items-center justify-center">
              <FolderOpen className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Content Analysis</h3>
            <p className="text-purple-200 text-sm">MIME types and content preview</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex justify-between items-center pt-12 mt-12 border-t border-gray-800">
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Previous in series</p>
          <Link 
            href="/examples/math-tutor-agent" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            5. Math Tutor Agent
          </Link>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Next in series</p>
          <Link 
            href="/examples/api-client" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            7. API Client
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}