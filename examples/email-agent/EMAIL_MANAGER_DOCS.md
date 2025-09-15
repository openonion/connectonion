# EmailManager - Tools for AI Agents

> A collection of email tools designed specifically for AI agents to handle email tasks autonomously.

---

## Core Concept

**This class is FOR AI agents, not humans.**

The EmailManager provides tools that AI agents use to complete email-related tasks. When a user asks "Find emails from John", the AI agent uses these tools to search, process, and respond.

```python
# The AI agent receives the EmailManager as a tool
agent = Agent(
    name="email_assistant",
    tools=[email_manager],  # Pass the whole class instance
    system_prompt="You handle email tasks using the available tools."
)

# User interacts naturally, AI uses the tools
user: "Find emails about the invoice"
# AI internally calls: email_manager.search_emails("invoice")
```

---

## Why These 6 Functions for AI Agents

### 1. `search_emails(query: str) -> str`
**Why AI needs it**: To find specific emails based on user's natural language requests.

**When AI uses it**:
- User: "Find emails from John" → AI calls `search_emails("from:John")`
- User: "Any emails about the project?" → AI calls `search_emails("project")`
- User: "Show last week's emails" → AI calls `search_emails("date:last_week")`

**What AI receives**: Formatted list of matching emails with IDs for further actions.

### 2. `send_email(to: str, subject: str, body: str) -> str`
**Why AI needs it**: To compose and send emails based on user instructions.

**When AI uses it**:
- User: "Email Alice about the meeting" → AI composes and calls `send_email()`
- User: "Send update to the team" → AI drafts appropriate content and sends

**What AI receives**: Success confirmation with message ID, or error details.

### 3. `reply_to_email(email_id: int, message: str) -> str`
**Why AI needs it**: To respond to specific emails in context.

**When AI uses it**:
- User: "Reply to email 2 saying yes" → AI calls `reply_to_email(2, "Yes, I agree")`
- User: "Respond to John's email" → AI finds John's email ID, then replies

**What AI receives**: Confirmation that reply was sent and original marked as read.

### 4. `draft_email(to: str, subject: str, body: str) -> str`
**Why AI needs it**: To prepare emails for user review before sending.

**When AI uses it**:
- User: "Draft a resignation letter" → AI composes but doesn't send
- User: "Prepare email to client" → AI creates draft for review

**What AI receives**: Draft ID and preview for user confirmation.

### 5. `get_unread_emails() -> str`
**Why AI needs it**: To check inbox and prioritize what needs attention.

**When AI uses it**:
- User: "What's new?" → AI calls `get_unread_emails()`
- User: "Check my emails" → AI gets unread first
- AI proactively checks when asked to "handle my emails"

**What AI receives**: List of unread emails with sender, subject, and preview.

### 6. `mark_email_read(email_id: int) -> str`
**Why AI needs it**: To track processed emails and maintain inbox hygiene.

**When AI uses it**:
- After showing email content to user
- After replying to an email
- User: "Mark all newsletters as read" → AI marks each one

**What AI receives**: Confirmation of marked emails.

---

## How AI Agents Should Use These Tools

### 1. **Chain Operations Intelligently**
```python
# User: "Reply to any urgent emails"
# AI's internal process:
1. unread = get_unread_emails()
2. for email in unread:
3.    if "urgent" in email.subject:
4.        reply_to_email(email.id, "I'm on it")
```

### 2. **Translate Natural Language to Tool Calls**
```python
# User says: "Did John send anything about the budget?"
# AI translates to: search_emails("from:John AND budget")

# User says: "Tell Sarah I'll be late"
# AI translates to: send_email("sarah@company.com", "Running Late", "Hi Sarah, I'll be about 15 minutes late.")
```

### 3. **Maintain Context Between Calls**
```python
# Conversation flow:
User: "Check my emails"
AI: [calls get_unread_emails()] "You have 3 unread emails..."

User: "Read the second one"
AI: [remembers email IDs from previous call, reads email 2]

User: "Reply saying I agree"
AI: [calls reply_to_email(2, "I agree with your proposal")]
```

### 4. **Handle Errors Gracefully**
```python
# If search returns no results:
AI: "No emails found about 'budget'. Would you like to search for something else?"

# If send fails:
AI: "Failed to send. Should I save as draft instead?"
```

---

## Tool Design Principles for AI

### Each Tool Returns Structured Information
```python
def search_emails(self, query: str) -> str:
    # Returns formatted string the AI can parse:
    # "Found 3 emails:
    #  [1] John Smith - Budget Report - 2 hours ago
    #  [2] John Smith - Q4 Planning - Yesterday"
    # AI can extract IDs, senders, subjects for follow-up actions
```

### Tools Handle One Responsibility
- `search_emails` - ONLY searches, doesn't mark as read
- `send_email` - ONLY sends, doesn't search for recipients
- `mark_email_read` - ONLY marks, doesn't reply

This allows AI to compose complex workflows from simple tools.

### Tools Accept Natural Input
```python
# AI doesn't need to format special syntax
search_emails("John budget")  # Not "from:john AND subject:budget"
# The tool handles query parsing internally
```

---

## Complete Implementation Example

```python
class EmailManager:
    """Email tools designed for AI agent use."""

    def search_emails(self, query: str) -> str:
        """Search emails and return formatted results for AI processing."""
        emails = get_emails(last=100)  # Search recent emails
        matches = []

        query_lower = query.lower()
        for email in emails:
            # Simple matching - AI provides natural language
            if (query_lower in email['from'].lower() or
                query_lower in email['subject'].lower() or
                query_lower in email.get('message', '').lower()):
                matches.append(email)

        if not matches:
            return f"No emails found matching '{query}'"

        # Format for AI to parse and use
        result = f"Found {len(matches)} emails matching '{query}':\n"
        for i, email in enumerate(matches[:10], 1):
            result += f"[{email['id']}] {email['from']} - {email['subject']}\n"

        return result

    def send_email(self, to: str, subject: str, body: str) -> str:
        """Send email and return status for AI."""
        result = send_email(to, subject, body)
        if result.get('success'):
            return f"✓ Email sent to {to} (ID: {result.get('message_id')})"
        return f"Failed to send: {result.get('error')}"

    def reply_to_email(self, email_id: int, message: str) -> str:
        """Reply and mark original as read."""
        # Get the original email
        emails = get_emails(last=50)
        original = None
        for email in emails:
            if email['id'] == email_id:
                original = email
                break

        if not original:
            return f"Email {email_id} not found"

        # Send reply
        result = send_email(
            original['from'],
            f"Re: {original['subject']}",
            message
        )

        if result.get('success'):
            mark_read(str(email_id))
            return f"✓ Replied to {original['from']}"
        return f"Failed to reply: {result.get('error')}"

    def draft_email(self, to: str, subject: str, body: str) -> str:
        """Create draft for user review."""
        # Store draft (in real implementation, save to drafts folder)
        draft = {
            'to': to,
            'subject': subject,
            'body': body,
            'id': 'draft_' + str(int(time.time()))
        }

        return f"Draft created:\nTo: {to}\nSubject: {subject}\n---\n{body[:200]}..."

    def get_unread_emails(self) -> str:
        """Get unread emails formatted for AI."""
        emails = get_emails(unread=True)

        if not emails:
            return "No unread emails"

        result = f"You have {len(emails)} unread emails:\n"
        for i, email in enumerate(emails[:20], 1):
            time_str = email.get('timestamp', 'Unknown')
            result += f"[{email['id']}] {email['from']} - {email['subject']} ({time_str})\n"

        return result

    def mark_email_read(self, email_id: int) -> str:
        """Mark as read and confirm to AI."""
        success = mark_read(str(email_id))
        if success:
            return f"✓ Marked email {email_id} as read"
        return f"Failed to mark email {email_id} as read"
```

---

## Key Insight: Tools Are For AI, Not Humans

The user never calls these functions directly. They speak naturally:
- "Find that email from John"
- "Reply saying I'll be there"
- "Send the report to my boss"

The AI agent translates these requests into tool calls, processes the results, and responds naturally. The tools are designed to make the AI's job easier, not to be a human-friendly API.

This is why we:
- Return formatted strings (AI parses them)
- Use simple parameters (AI provides them)
- Include IDs in responses (AI uses for follow-up)
- Keep functions focused (AI chains them together)