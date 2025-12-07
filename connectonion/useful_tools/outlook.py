"""
Purpose: Outlook integration tool for reading, sending, and managing emails via Microsoft Graph API
LLM-Note:
  Dependencies: imports from [os, datetime, httpx] | imported by [useful_tools/__init__.py] | requires OAuth tokens from 'co auth microsoft' | tested by [tests/unit/test_outlook.py]
  Data flow: Agent calls Outlook methods → _get_headers() loads MICROSOFT_ACCESS_TOKEN from env → HTTP calls to Graph API (https://graph.microsoft.com/v1.0) → returns formatted results (email summaries, bodies, send confirmations)
  State/Effects: reads MICROSOFT_* env vars for OAuth tokens | makes HTTP calls to Microsoft Graph API | can modify mailbox state (mark read, archive, send emails) | no local file persistence
  Integration: exposes Outlook class with read_inbox(), get_sent_emails(), search_emails(), get_email_body(), send(), reply(), mark_read(), archive_email() | used as agent tool via Agent(tools=[Outlook()])
  Performance: network I/O per API call | batch fetching for list operations | email body fetched separately
  Errors: raises ValueError if OAuth not configured | HTTP errors from Graph API propagate | returns error strings for display to user

Outlook tool for reading and managing Outlook emails via Microsoft Graph API.

Usage:
    from connectonion import Agent, Outlook

    outlook = Outlook()
    agent = Agent("assistant", tools=[outlook])

    # Agent can now use:
    # - read_inbox(last, unread)
    # - get_sent_emails(max_results)
    # - search_emails(query, max_results)
    # - get_email_body(email_id)
    # - send(to, subject, body, cc, bcc)
    # - reply(email_id, body)
    # - mark_read(email_id)
    # - archive_email(email_id)

Example:
    from connectonion import Agent, Outlook

    outlook = Outlook()
    agent = Agent(
        name="outlook-assistant",
        system_prompt="You are an Outlook assistant.",
        tools=[outlook]
    )

    agent.input("Show me my recent emails")
    agent.input("Send an email to alice@example.com saying hello")
"""

import os
from datetime import datetime, timedelta
import httpx


class Outlook:
    """Outlook tool for reading and managing emails via Microsoft Graph API."""

    GRAPH_API_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self):
        """Initialize Outlook tool.

        Validates that Microsoft OAuth is configured.
        Raises ValueError if credentials are missing.
        """
        scopes = os.getenv("MICROSOFT_SCOPES", "")
        if not scopes or "Mail" not in scopes:
            raise ValueError(
                "Missing Microsoft Mail scopes.\n"
                f"Current scopes: {scopes}\n"
                "Please authorize Microsoft access:\n"
                "  co auth microsoft"
            )

        self._access_token = None

    def _get_access_token(self) -> str:
        """Get Microsoft access token (with auto-refresh)."""
        access_token = os.getenv("MICROSOFT_ACCESS_TOKEN")
        refresh_token = os.getenv("MICROSOFT_REFRESH_TOKEN")
        expires_at_str = os.getenv("MICROSOFT_TOKEN_EXPIRES_AT")

        if not access_token or not refresh_token:
            raise ValueError(
                "Microsoft OAuth credentials not found.\n"
                "Run: co auth microsoft"
            )

        # Check if token is expired or about to expire (within 5 minutes)
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            now = datetime.utcnow().replace(tzinfo=expires_at.tzinfo) if expires_at.tzinfo else datetime.utcnow()

            if now >= expires_at - timedelta(minutes=5):
                # Token expired or about to expire, refresh via backend
                access_token = self._refresh_via_backend(refresh_token)
                self._access_token = None

        if self._access_token:
            return self._access_token

        self._access_token = access_token
        return self._access_token

    def _refresh_via_backend(self, refresh_token: str) -> str:
        """Refresh access token via backend API.

        Args:
            refresh_token: The refresh token

        Returns:
            New access token
        """
        backend_url = os.getenv("OPENONION_API_URL", "https://oo.openonion.ai")
        api_key = os.getenv("OPENONION_API_KEY")

        if not api_key:
            raise ValueError(
                "OPENONION_API_KEY not found.\n"
                "This is needed to refresh tokens via backend."
            )

        response = httpx.post(
            f"{backend_url}/api/v1/oauth/microsoft/refresh",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"refresh_token": refresh_token}
        )

        if response.status_code != 200:
            raise ValueError(
                f"Failed to refresh Microsoft token via backend: {response.text}"
            )

        data = response.json()
        new_access_token = data["access_token"]
        expires_at = data["expires_at"]

        # Update environment variables for this session
        os.environ["MICROSOFT_ACCESS_TOKEN"] = new_access_token
        os.environ["MICROSOFT_TOKEN_EXPIRES_AT"] = expires_at

        # Update .env file if it exists
        env_file = os.path.join(os.getenv("AGENT_CONFIG_PATH", os.path.expanduser("~/.co")), "keys.env")
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                lines = f.readlines()

            with open(env_file, 'w') as f:
                for line in lines:
                    if line.startswith("MICROSOFT_ACCESS_TOKEN="):
                        f.write(f"MICROSOFT_ACCESS_TOKEN={new_access_token}\n")
                    elif line.startswith("MICROSOFT_TOKEN_EXPIRES_AT="):
                        f.write(f"MICROSOFT_TOKEN_EXPIRES_AT={expires_at}\n")
                    else:
                        f.write(line)

        return new_access_token

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make authenticated request to Microsoft Graph API."""
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        url = f"{self.GRAPH_API_URL}{endpoint}"
        response = httpx.request(method, url, headers=headers, **kwargs)

        if response.status_code == 401:
            # Token might have expired, try refreshing
            refresh_token = os.getenv("MICROSOFT_REFRESH_TOKEN")
            if refresh_token:
                self._access_token = None
                token = self._refresh_via_backend(refresh_token)
                headers["Authorization"] = f"Bearer {token}"
                response = httpx.request(method, url, headers=headers, **kwargs)

        if response.status_code not in [200, 201, 202, 204]:
            raise ValueError(f"Microsoft Graph API error: {response.status_code} - {response.text}")

        if response.status_code == 204:
            return {}
        return response.json()

    def _format_emails(self, messages: list, max_results: int = 10) -> str:
        """Helper to format email list."""
        if not messages:
            return "No emails found."

        emails = []
        for msg in messages[:max_results]:
            emails.append({
                'id': msg['id'],
                'from': msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown'),
                'from_name': msg.get('from', {}).get('emailAddress', {}).get('name', ''),
                'subject': msg.get('subject', 'No Subject'),
                'date': msg.get('receivedDateTime', 'Unknown'),
                'snippet': msg.get('bodyPreview', '')[:100],
                'unread': not msg.get('isRead', True)
            })

        output = [f"Found {len(emails)} email(s):\n"]
        for i, email in enumerate(emails, 1):
            status = "[UNREAD]" if email['unread'] else ""
            from_display = f"{email['from_name']} <{email['from']}>" if email['from_name'] else email['from']
            output.append(f"{i}. {status} From: {from_display}")
            output.append(f"   Subject: {email['subject']}")
            output.append(f"   Date: {email['date']}")
            output.append(f"   Preview: {email['snippet']}...")
            output.append(f"   ID: {email['id']}\n")

        return "\n".join(output)

    # === Reading ===

    def read_inbox(self, last: int = 10, unread: bool = False) -> str:
        """Read emails from inbox.

        Args:
            last: Number of emails to retrieve (default: 10)
            unread: Only get unread emails (default: False)

        Returns:
            Formatted string with email list
        """
        endpoint = "/me/mailFolders/inbox/messages"
        params = {
            "$top": last,
            "$orderby": "receivedDateTime desc",
            "$select": "id,from,subject,receivedDateTime,bodyPreview,isRead"
        }

        if unread:
            params["$filter"] = "isRead eq false"

        result = self._request("GET", endpoint, params=params)
        messages = result.get('value', [])
        return self._format_emails(messages, last)

    def get_sent_emails(self, max_results: int = 10) -> str:
        """Get emails you sent.

        Args:
            max_results: Number of emails to retrieve (default: 10)

        Returns:
            Formatted string with sent email list
        """
        endpoint = "/me/mailFolders/sentitems/messages"
        params = {
            "$top": max_results,
            "$orderby": "sentDateTime desc",
            "$select": "id,toRecipients,subject,sentDateTime,bodyPreview"
        }

        result = self._request("GET", endpoint, params=params)
        messages = result.get('value', [])

        if not messages:
            return "No sent emails found."

        output = [f"Found {len(messages)} sent email(s):\n"]
        for i, msg in enumerate(messages[:max_results], 1):
            to_list = msg.get('toRecipients', [])
            to_emails = [r.get('emailAddress', {}).get('address', '') for r in to_list]
            output.append(f"{i}. To: {', '.join(to_emails)}")
            output.append(f"   Subject: {msg.get('subject', 'No Subject')}")
            output.append(f"   Date: {msg.get('sentDateTime', 'Unknown')}")
            output.append(f"   ID: {msg['id']}\n")

        return "\n".join(output)

    # === Search ===

    def search_emails(self, query: str, max_results: int = 10) -> str:
        """Search emails.

        Args:
            query: Search query (searches subject and body)
            max_results: Number of results to return (default: 10)

        Returns:
            Formatted string with matching emails
        """
        endpoint = "/me/messages"
        params = {
            "$top": max_results,
            "$search": f'"{query}"',
            "$select": "id,from,subject,receivedDateTime,bodyPreview,isRead"
        }

        result = self._request("GET", endpoint, params=params)
        messages = result.get('value', [])

        if not messages:
            return f"No emails found matching query: {query}"

        return self._format_emails(messages, max_results)

    # === Content ===

    def get_email_body(self, email_id: str) -> str:
        """Get full email body.

        Args:
            email_id: Outlook message ID

        Returns:
            Full email content with headers
        """
        endpoint = f"/me/messages/{email_id}"
        params = {
            "$select": "from,toRecipients,subject,receivedDateTime,body"
        }

        message = self._request("GET", endpoint, params=params)

        from_email = message.get('from', {}).get('emailAddress', {})
        from_addr = f"{from_email.get('name', '')} <{from_email.get('address', '')}>"

        to_list = message.get('toRecipients', [])
        to_addrs = ', '.join([r.get('emailAddress', {}).get('address', '') for r in to_list])

        body_content = message.get('body', {}).get('content', 'No body')
        body_type = message.get('body', {}).get('contentType', 'text')

        # Strip HTML if present
        if body_type == 'html':
            import re
            from html import unescape
            body_content = re.sub(r'<style[^>]*>.*?</style>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
            body_content = re.sub(r'<[^>]+>', '', body_content)
            body_content = unescape(body_content)
            body_content = re.sub(r'\s+', ' ', body_content).strip()

        output = [
            f"From: {from_addr}",
            f"To: {to_addrs}",
            f"Subject: {message.get('subject', 'No Subject')}",
            f"Date: {message.get('receivedDateTime', 'Unknown')}",
            "\n--- Email Body ---\n",
            body_content
        ]

        return "\n".join(output)

    # === Sending ===

    def send(self, to: str, subject: str, body: str, cc: str = None, bcc: str = None) -> str:
        """Send email via Microsoft Graph API.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            cc: Optional CC recipients (comma-separated)
            bcc: Optional BCC recipients (comma-separated)

        Returns:
            Confirmation message
        """
        message = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": body
                },
                "toRecipients": [
                    {"emailAddress": {"address": addr.strip()}}
                    for addr in to.split(',')
                ]
            }
        }

        if cc:
            message["message"]["ccRecipients"] = [
                {"emailAddress": {"address": addr.strip()}}
                for addr in cc.split(',')
            ]

        if bcc:
            message["message"]["bccRecipients"] = [
                {"emailAddress": {"address": addr.strip()}}
                for addr in bcc.split(',')
            ]

        self._request("POST", "/me/sendMail", json=message)

        return f"Email sent successfully to {to}"

    def reply(self, email_id: str, body: str) -> str:
        """Reply to an email.

        Args:
            email_id: Outlook message ID to reply to
            body: Reply message body (plain text)

        Returns:
            Confirmation message
        """
        endpoint = f"/me/messages/{email_id}/reply"
        data = {
            "comment": body
        }

        self._request("POST", endpoint, json=data)

        return f"Reply sent successfully"

    # === Actions ===

    def mark_read(self, email_id: str) -> str:
        """Mark email as read.

        Args:
            email_id: Outlook message ID

        Returns:
            Confirmation message
        """
        endpoint = f"/me/messages/{email_id}"
        data = {"isRead": True}

        self._request("PATCH", endpoint, json=data)

        return f"Marked email as read: {email_id}"

    def mark_unread(self, email_id: str) -> str:
        """Mark email as unread.

        Args:
            email_id: Outlook message ID

        Returns:
            Confirmation message
        """
        endpoint = f"/me/messages/{email_id}"
        data = {"isRead": False}

        self._request("PATCH", endpoint, json=data)

        return f"Marked email as unread: {email_id}"

    def archive_email(self, email_id: str) -> str:
        """Archive email (move to archive folder).

        Args:
            email_id: Outlook message ID

        Returns:
            Confirmation message
        """
        endpoint = f"/me/messages/{email_id}/move"
        data = {"destinationId": "archive"}

        self._request("POST", endpoint, json=data)

        return f"Archived email: {email_id}"

    # === Stats ===

    def count_unread(self) -> str:
        """Count unread emails in inbox.

        Returns:
            Number of unread emails
        """
        endpoint = "/me/mailFolders/inbox"
        params = {"$select": "unreadItemCount"}

        result = self._request("GET", endpoint, params=params)
        count = result.get('unreadItemCount', 0)

        return f"You have {count} unread email(s) in your inbox."

    def get_my_email(self) -> str:
        """Get the user's email address.

        Returns:
            User's Microsoft email address
        """
        email = os.getenv("MICROSOFT_EMAIL", "")
        if email:
            return f"Connected as: {email}"

        # Fallback: fetch from API
        endpoint = "/me"
        params = {"$select": "mail,userPrincipalName"}

        result = self._request("GET", endpoint, params=params)
        email = result.get('mail') or result.get('userPrincipalName', 'Unknown')

        return f"Connected as: {email}"
