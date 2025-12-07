"""
Purpose: Gmail integration tool for reading, sending, and managing emails via Google API
LLM-Note:
  Dependencies: imports from [os, base64, google.oauth2.credentials, googleapiclient.discovery, googleapiclient.errors] | imported by [useful_tools/__init__.py] | requires OAuth tokens from 'co auth google' | tested by [tests/unit/test_gmail.py]
  Data flow: Agent calls Gmail methods → _get_credentials() loads tokens from env → builds Gmail API service → API calls to Gmail REST endpoints → returns formatted results (email summaries, bodies, send confirmations)
  State/Effects: reads GOOGLE_* env vars for OAuth tokens | makes HTTP calls to Gmail API | can modify mailbox state (mark read/unread, archive, star, send emails) | no local file persistence
  Integration: exposes Gmail class with read_inbox(), get_sent_emails(), search_emails(), get_email_body(), send(), reply(), mark_read(), mark_unread(), archive_email(), star_email(), get_labels(), add_label(), count_unread(), get_all_contacts(), analyze_contact(), get_unanswered_emails(), update_contact() | used as agent tool via Agent(tools=[Gmail()])
  Performance: network I/O per API call | batch fetching for list operations | email body fetched separately (lazy loading)
  Errors: raises ValueError if OAuth not configured | HttpError from Google API propagates | returns error strings for display to user

Gmail tool for reading and managing Gmail emails.

Usage:
    from connectonion import Agent, Gmail

    gmail = Gmail()
    agent = Agent("assistant", tools=[gmail])

    # Agent can now use:
    # - read_inbox(last, unread)
    # - get_sent_emails(max_results)
    # - get_all_emails(max_results)
    # - search_emails(query, max_results)
    # - get_email_body(email_id)
    # - get_email_attachments(email_id)
    # - send(to, subject, body, cc, bcc)
    # - reply(email_id, body)
    # - mark_read(email_id)
    # - mark_unread(email_id)
    # - archive_email(email_id)
    # - star_email(email_id)
    # - get_labels()
    # - add_label(email_id, label)
    # - get_emails_with_label(label, max_results)
    # - count_unread()
    # - get_all_contacts(max_emails)
    # - analyze_contact(email, max_emails)
    # - get_unanswered_emails(older_than_days, max_results)
    # - update_contact(email, type, priority, deal, next_contact_date, ...)

Example:
    from connectonion import Agent, Gmail

    gmail = Gmail()
    agent = Agent(
        name="gmail-assistant",
        system_prompt="You are a Gmail assistant.",
        tools=[gmail]
    )

    agent.input("Show me my recent emails")
    agent.input("Search for emails from alice@example.com")
"""

import os
import base64
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class Gmail:
    """Gmail tool for reading and managing emails."""

    def __init__(self, emails_csv: str = "data/emails.csv", contacts_csv: str = "data/contacts.csv"):
        """Initialize Gmail tool.

        Args:
            emails_csv: Path to CSV file for email caching (default: "data/emails.csv")
            contacts_csv: Path to CSV file for contact caching (default: "data/contacts.csv")

        Validates that gmail.readonly scope is authorized.
        Raises ValueError if scope is missing.
        """
        scopes = os.getenv("GOOGLE_SCOPES", "")
        if "gmail.readonly" not in scopes:
            raise ValueError(
                "Missing 'gmail.readonly' scope.\n"
                f"Current scopes: {scopes}\n"
                "Please authorize Gmail access:\n"
                "  co auth google"
            )
        if "gmail.send" not in scopes:
            raise ValueError(
                "Missing 'gmail.send' scope.\n"
                f"Current scopes: {scopes}\n"
                "Please authorize Gmail send access:\n"
                "  co auth google"
            )

        self._service = None
        self.emails_csv = emails_csv
        self.contacts_csv = contacts_csv

    def _get_service(self):
        """Get Gmail API service (lazy load with auto-refresh)."""
        access_token = os.getenv("GOOGLE_ACCESS_TOKEN")
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        expires_at_str = os.getenv("GOOGLE_TOKEN_EXPIRES_AT")

        if not access_token or not refresh_token:
            raise ValueError(
                "Google OAuth credentials not found.\n"
                "Run: co auth google"
            )

        # Check if token is expired or about to expire (within 5 minutes)
        # Always check before returning cached service
        if expires_at_str:
            from datetime import datetime, timedelta
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            now = datetime.utcnow().replace(tzinfo=expires_at.tzinfo) if expires_at.tzinfo else datetime.utcnow()

            if now >= expires_at - timedelta(minutes=5):
                # Token expired or about to expire, refresh via backend
                access_token = self._refresh_via_backend(refresh_token)
                # Clear cached service to use new token
                self._service = None

        # Return cached service if available
        if self._service:
            return self._service

        # Create credentials without client_id/client_secret
        # Backend handles token refresh, so we don't need auto-refresh
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=None,
            client_secret=None,
            scopes=["https://www.googleapis.com/auth/gmail.readonly",
                   "https://www.googleapis.com/auth/gmail.modify",
                   "https://www.googleapis.com/auth/gmail.send"]
        )

        self._service = build('gmail', 'v1', credentials=creds)
        return self._service

    def _refresh_via_backend(self, refresh_token: str) -> str:
        """Refresh access token via backend API.

        Args:
            refresh_token: The refresh token

        Returns:
            New access token
        """
        import httpx

        # Get backend URL and auth
        backend_url = os.getenv("OPENONION_API_URL", "https://oo.openonion.ai")
        api_key = os.getenv("OPENONION_API_KEY")

        if not api_key:
            raise ValueError(
                "OPENONION_API_KEY not found.\n"
                "This is needed to refresh tokens via backend."
            )

        # Call backend refresh endpoint
        response = httpx.post(
            f"{backend_url}/api/v1/oauth/google/refresh",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"refresh_token": refresh_token}
        )

        if response.status_code != 200:
            raise ValueError(
                f"Failed to refresh token via backend: {response.text}"
            )

        data = response.json()
        new_access_token = data["access_token"]
        expires_at = data["expires_at"]

        # Update environment variables for this session
        os.environ["GOOGLE_ACCESS_TOKEN"] = new_access_token
        os.environ["GOOGLE_TOKEN_EXPIRES_AT"] = expires_at

        # Update .env file if it exists
        env_file = os.path.join(os.getenv("AGENT_CONFIG_PATH", os.path.expanduser("~/.co")), "keys.env")
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                lines = f.readlines()

            with open(env_file, 'w') as f:
                for line in lines:
                    if line.startswith("GOOGLE_ACCESS_TOKEN="):
                        f.write(f"GOOGLE_ACCESS_TOKEN={new_access_token}\n")
                    elif line.startswith("GOOGLE_TOKEN_EXPIRES_AT="):
                        f.write(f"GOOGLE_TOKEN_EXPIRES_AT={expires_at}\n")
                    else:
                        f.write(line)

        return new_access_token

    def _format_emails(self, messages, max_results=10):
        """Helper to format email list."""
        if not messages:
            return "No emails found."

        service = self._get_service()
        emails = []

        for msg in messages[:max_results]:
            message = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']
            ).execute()

            headers = message['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')

            snippet = message.get('snippet', '')
            is_unread = 'UNREAD' in message.get('labelIds', [])

            emails.append({
                'id': msg['id'],
                'from': from_email,
                'subject': subject,
                'date': date,
                'snippet': snippet,
                'unread': is_unread
            })

        # Format output
        output = [f"Found {len(emails)} email(s):\n"]
        for i, email in enumerate(emails, 1):
            status = "[UNREAD]" if email['unread'] else ""
            output.append(f"{i}. {status} From: {email['from']}")
            output.append(f"   Subject: {email['subject']}")
            output.append(f"   Date: {email['date']}")
            output.append(f"   Preview: {email['snippet'][:80]}...")
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
        service = self._get_service()

        query = "is:unread in:inbox" if unread else "in:inbox"

        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=last
        ).execute()

        messages = results.get('messages', [])
        return self._format_emails(messages, last)

    def get_sent_emails(self, max_results: int = 10) -> str:
        """Get emails you sent.

        Args:
            max_results: Number of emails to retrieve (default: 10)

        Returns:
            Formatted string with sent email list
        """
        service = self._get_service()

        results = service.users().messages().list(
            userId='me',
            q="in:sent",
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])
        return self._format_emails(messages, max_results)

    def get_all_emails(self, max_results: int = 50) -> str:
        """Get emails from all folders.

        Args:
            max_results: Number of emails to retrieve (default: 50)

        Returns:
            Formatted string with email list
        """
        service = self._get_service()

        results = service.users().messages().list(
            userId='me',
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])
        return self._format_emails(messages, max_results)

    # === Search ===

    def search_emails(self, query: str, max_results: int = 10) -> str:
        """Search emails using Gmail query syntax.

        Args:
            query: Gmail search query (e.g., "from:alice@example.com", "subject:meeting")
            max_results: Number of results to return (default: 10)

        Returns:
            Formatted string with matching emails
        """
        service = self._get_service()

        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])

        if not messages:
            return f"No emails found matching query: {query}"

        return self._format_emails(messages, max_results)

    # === Content ===

    def _extract_body(self, payload) -> str:
        """Extract body from email payload, preferring text/plain, falling back to stripped HTML."""
        import re
        from html import unescape

        def strip_html(html: str) -> str:
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', '', html)
            text = unescape(text)
            return re.sub(r'\s+', ' ', text).strip()

        # Single part email
        if 'body' in payload and payload['body'].get('data'):
            data = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='replace')
            if payload.get('mimeType') == 'text/html':
                return strip_html(data)
            return data

        # Multipart email
        if 'parts' in payload:
            plain_body = None
            html_body = None
            for part in payload['parts']:
                mime = part.get('mimeType', '')
                if mime == 'text/plain' and part['body'].get('data'):
                    plain_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                elif mime == 'text/html' and part['body'].get('data'):
                    html_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                elif 'parts' in part:
                    nested = self._extract_body(part)
                    if nested:
                        return nested
            if plain_body:
                return plain_body
            if html_body:
                return strip_html(html_body)
        return ''

    def get_email_body(self, email_id: str) -> str:
        """Get full email body.

        Args:
            email_id: Gmail message ID

        Returns:
            Full email content with headers
        """
        service = self._get_service()

        message = service.users().messages().get(
            userId='me',
            id=email_id,
            format='full'
        ).execute()

        headers = message['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        to_email = next((h['value'] for h in headers if h['name'] == 'To'), 'Unknown')
        date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')

        body = self._extract_body(message['payload'])
        if not body:
            body = message.get('snippet', 'No body content')

        output = [
            f"From: {from_email}",
            f"To: {to_email}",
            f"Subject: {subject}",
            f"Date: {date}",
            "\n--- Email Body ---\n",
            body
        ]

        return "\n".join(output)

    def get_email_attachments(self, email_id: str) -> str:
        """List attachments in email.

        Args:
            email_id: Gmail message ID

        Returns:
            List of attachment names and sizes
        """
        service = self._get_service()

        message = service.users().messages().get(
            userId='me',
            id=email_id,
            format='full'
        ).execute()

        attachments = []

        if 'parts' in message['payload']:
            for part in message['payload']['parts']:
                if part.get('filename'):
                    size = part['body'].get('size', 0)
                    attachments.append({
                        'filename': part['filename'],
                        'size': size,
                        'id': part['body'].get('attachmentId', '')
                    })

        if not attachments:
            return "No attachments in this email."

        output = [f"Found {len(attachments)} attachment(s):\n"]
        for i, att in enumerate(attachments, 1):
            size_kb = att['size'] / 1024
            output.append(f"{i}. {att['filename']} ({size_kb:.1f} KB)")
            output.append(f"   ID: {att['id']}\n")

        return "\n".join(output)

    def send(self, to: str, subject: str, body: str, cc: str = None, bcc: str = None) -> str:
        """Send email via Gmail API.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            cc: Optional CC recipients (comma-separated)
            bcc: Optional BCC recipients (comma-separated)

        Returns:
            Confirmation message with sent message ID
        """
        from email.mime.text import MIMEText

        service = self._get_service()

        # Create message
        message = MIMEText(body)
        message['To'] = to
        message['Subject'] = subject

        if cc:
            message['Cc'] = cc
        if bcc:
            message['Bcc'] = bcc

        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

        # Send via Gmail API
        sent_message = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()

        return f"Email sent successfully to {to}. Message ID: {sent_message['id']}"

    def reply(self, email_id: str, body: str) -> str:
        """Reply to an email via Gmail API.

        Args:
            email_id: Gmail message ID to reply to
            body: Reply message body (plain text)

        Returns:
            Confirmation message with sent message ID
        """
        from email.mime.text import MIMEText

        service = self._get_service()

        # Get original message to extract headers
        original = service.users().messages().get(
            userId='me',
            id=email_id,
            format='metadata',
            metadataHeaders=['From', 'To', 'Subject', 'Message-ID']
        ).execute()

        headers = {h['name']: h['value'] for h in original['payload']['headers']}
        original_subject = headers.get('Subject', '')
        original_from = headers.get('From', '')
        original_message_id = headers.get('Message-ID', '')
        thread_id = original.get('threadId', '')

        # Create reply
        message = MIMEText(body)
        message['To'] = original_from
        message['Subject'] = original_subject if original_subject.startswith('Re: ') else f"Re: {original_subject}"

        if original_message_id:
            message['In-Reply-To'] = original_message_id
            message['References'] = original_message_id

        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

        # Send as reply in same thread
        sent_message = service.users().messages().send(
            userId='me',
            body={'raw': raw_message, 'threadId': thread_id}
        ).execute()

        return f"Reply sent successfully. Message ID: {sent_message['id']}"

    # === Actions ===

    def mark_read(self, email_id: str) -> str:
        """Mark email as read.

        Args:
            email_id: Gmail message ID

        Returns:
            Confirmation message
        """
        service = self._get_service()

        service.users().messages().modify(
            userId='me',
            id=email_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()

        return f"Marked email as read: {email_id}"

    def mark_unread(self, email_id: str) -> str:
        """Mark email as unread.

        Args:
            email_id: Gmail message ID

        Returns:
            Confirmation message
        """
        service = self._get_service()

        service.users().messages().modify(
            userId='me',
            id=email_id,
            body={'addLabelIds': ['UNREAD']}
        ).execute()

        return f"Marked email as unread: {email_id}"

    def archive_email(self, email_id: str) -> str:
        """Archive email (remove from inbox).

        Args:
            email_id: Gmail message ID

        Returns:
            Confirmation message
        """
        service = self._get_service()

        service.users().messages().modify(
            userId='me',
            id=email_id,
            body={'removeLabelIds': ['INBOX']}
        ).execute()

        return f"Archived email: {email_id}"

    def star_email(self, email_id: str) -> str:
        """Add star to email.

        Args:
            email_id: Gmail message ID

        Returns:
            Confirmation message
        """
        service = self._get_service()

        service.users().messages().modify(
            userId='me',
            id=email_id,
            body={'addLabelIds': ['STARRED']}
        ).execute()

        return f"Starred email: {email_id}"

    # === Labels ===

    def get_labels(self) -> str:
        """List all Gmail labels.

        Returns:
            List of label names and IDs
        """
        service = self._get_service()

        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])

        if not labels:
            return "No labels found."

        output = [f"Found {len(labels)} label(s):\n"]
        for label in labels:
            label_type = label.get('type', 'user')
            output.append(f"- {label['name']} (ID: {label['id']}, Type: {label_type})")

        return "\n".join(output)

    def add_label(self, email_id: str, label: str) -> str:
        """Add label to email.

        Args:
            email_id: Gmail message ID
            label: Label name or ID

        Returns:
            Confirmation message
        """
        service = self._get_service()

        # Try to find label by name first
        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])

        label_id = label
        for lbl in labels:
            if lbl['name'].lower() == label.lower():
                label_id = lbl['id']
                break

        service.users().messages().modify(
            userId='me',
            id=email_id,
            body={'addLabelIds': [label_id]}
        ).execute()

        return f"Added label '{label}' to email: {email_id}"

    def get_emails_with_label(self, label: str, max_results: int = 10) -> str:
        """Get emails with specific label.

        Args:
            label: Label name (e.g., "Important", "Work")
            max_results: Number of emails to retrieve (default: 10)

        Returns:
            Formatted string with email list
        """
        service = self._get_service()

        # Find label ID by name
        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])

        label_id = None
        for lbl in labels:
            if lbl['name'].lower() == label.lower():
                label_id = lbl['id']
                break

        if not label_id:
            return f"Label not found: {label}"

        results = service.users().messages().list(
            userId='me',
            labelIds=[label_id],
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])

        if not messages:
            return f"No emails with label: {label}"

        return self._format_emails(messages, max_results)

    # === Stats ===

    def count_unread(self) -> str:
        """Count unread emails.

        Returns:
            Number of unread emails
        """
        service = self._get_service()

        results = service.users().messages().list(
            userId='me',
            q="is:unread",
            maxResults=1
        ).execute()

        # Get total from resultSizeEstimate
        count = results.get('resultSizeEstimate', 0)

        return f"You have {count} unread email(s)."

    def get_my_identity(self) -> str:
        """Get the user's email address and aliases (who am I?).

        Returns:
            User's primary email and all send-as aliases (their organization domains)
        """
        service = self._get_service()

        # Get primary email
        profile = service.users().getProfile(userId='me').execute()
        primary_email = profile.get('emailAddress', '')

        # Get all send-as aliases
        send_as = service.users().settings().sendAs().list(userId='me').execute()
        aliases = []
        domains = set()
        for alias in send_as.get('sendAs', []):
            email = alias.get('sendAsEmail', '')
            if email and email != primary_email:
                aliases.append(email)
            # Extract domains
            if '@' in email:
                domain = email.split('@')[1]
                if domain not in ['gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com']:
                    domains.add(domain)

        result = f"Primary email: {primary_email}\n"
        if aliases:
            result += f"Aliases: {', '.join(aliases)}\n"
        if domains:
            result += f"Organization domains: {', '.join(sorted(domains))}\n"
            result += f"\nUse exclude_domains=\"{','.join(sorted(domains))}\" to exclude your own addresses from contact lists."

        return result

    def detect_all_my_emails(self, max_emails: int = 100) -> str:
        """Detect all email addresses receiving mail (including routed aliases).

        Uses simple rule: if email was forwarded to our Gmail (X-Forwarded-To),
        the FIRST address in To header (that's not our Gmail) is our routed address.

        Args:
            max_emails: Number of recent emails to scan (default 100)

        Returns:
            All detected email addresses (primary + aliases + routed addresses)
        """
        routed_emails, primary_email, known_emails = self._detect_routed_addresses(max_emails)

        # Extract org domains
        detected_org_domains = {email.split('@')[1] for email in routed_emails if '@' in email}

        result = f"Primary email: {primary_email}\n"
        if known_emails - {primary_email}:
            result += f"Send-as aliases: {', '.join(sorted(known_emails - {primary_email}))}\n"
        if detected_org_domains:
            result += f"Organization domains: {', '.join(sorted(detected_org_domains))}\n"
        if routed_emails:
            result += f"Routed addresses detected: {', '.join(sorted(routed_emails))}\n"

        all_my_emails = known_emails | routed_emails
        result += f"\nAll your addresses ({len(all_my_emails)}): {', '.join(sorted(all_my_emails))}"

        return result

    def _detect_routed_addresses(self, max_emails: int = 100) -> tuple:
        """Internal: Detect routed addresses using simple first-address rule.

        Rule: If X-Forwarded-To points to our Gmail, the FIRST address in To header
        (that's not our Gmail) is our routed address.

        Returns:
            tuple: (routed_emails set, primary_email str, known_emails set)
        """
        import re
        service = self._get_service()

        # Get primary email
        profile = service.users().getProfile(userId='me').execute()
        primary_email = profile.get('emailAddress', '').lower()

        # Get send-as aliases
        send_as = service.users().settings().sendAs().list(userId='me').execute()
        known_emails = {primary_email}
        for alias in send_as.get('sendAs', []):
            email = alias.get('sendAsEmail', '').lower()
            if email:
                known_emails.add(email)

        # Scan forwarded emails
        routed_emails = set()
        results = service.users().messages().list(
            userId='me',
            maxResults=max_emails,
            q='in:inbox'
        ).execute()

        for msg_meta in results.get('messages', []):
            msg = service.users().messages().get(
                userId='me',
                id=msg_meta['id'],
                format='metadata',
                metadataHeaders=['To', 'X-Forwarded-To']
            ).execute()

            headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}

            # Check if this email was forwarded to our Gmail
            forwarded_to = headers.get('X-Forwarded-To', '').lower()
            if primary_email not in forwarded_to:
                continue

            # Get FIRST email in To header - that's the routed address
            to_header = headers.get('To', '')
            to_emails = re.findall(r'[\w.+-]+@[\w.-]+\.\w+', to_header.lower())
            if to_emails:
                first_email = to_emails[0]
                # If first email is not our Gmail, it's a routed address
                if first_email not in known_emails:
                    routed_emails.add(first_email)

        return routed_emails, primary_email, known_emails

    def get_all_my_emails(self, max_emails: int = 100) -> set:
        """Return set of all email addresses associated with this account.

        Combines:
        - Primary Gmail address
        - Send-as aliases configured in Gmail
        - Addresses detected from forwarded emails (Cloudflare routes)

        Uses simple rule: for forwarded emails, the FIRST address in To header is our routed address.

        Args:
            max_emails: Number of emails to scan for detecting routed addresses

        Returns:
            Set of email addresses (lowercase)
        """
        routed_emails, primary_email, known_emails = self._detect_routed_addresses(max_emails)
        return known_emails | routed_emails

    # === CRM ===

    def _scan_contacts(self, max_emails: int = 500, exclude_automated: bool = True, exclude_domains: str = "") -> tuple:
        """Internal helper: scan emails and return contact data (no CSV writing).

        Returns:
            tuple: (contacts_dict, email_records) where contacts_dict maps email -> {name, frequency, last_contact}
        """
        import re
        from collections import defaultdict

        service = self._get_service()

        # Get user's email addresses to exclude self
        profile = service.users().getProfile(userId='me').execute()
        user_email = profile.get('emailAddress', '').lower()

        # Get user's send-as addresses (aliases)
        user_addresses = {user_email}
        user_domains = set()

        # Add explicitly excluded domains
        if exclude_domains:
            for domain in exclude_domains.split(','):
                user_domains.add(domain.strip().lower())

        send_as = service.users().settings().sendAs().list(userId='me').execute()
        for alias in send_as.get('sendAs', []):
            alias_email = alias.get('sendAsEmail', '').lower()
            user_addresses.add(alias_email)
            if '@' in alias_email:
                domain = alias_email.split('@')[1]
                if domain not in ['gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com']:
                    user_domains.add(domain)

        automated_patterns = [
            'mailer-daemon', 'postmaster@', 'bounce@', 'bounces@',
            'unsubscribe', 'unsub-', 'optout@', 'opt-out@',
            'noreply@', 'no-reply@', 'donotreply@', 'do-not-reply@',
            'mailchimp.com', 'sendgrid.net', 'amazonses.com', 'mailjet.com',
            'customer.io', 'responsys', 'oraclecloud.com',
        ]

        def is_automated(email_addr: str) -> bool:
            return any(pattern in email_addr.lower() for pattern in automated_patterns)

        # Get emails with pagination
        messages = []
        page_token = None
        while len(messages) < max_emails:
            results = service.users().messages().list(
                userId='me',
                maxResults=min(100, max_emails - len(messages)),
                pageToken=page_token
            ).execute()
            messages.extend(results.get('messages', []))
            page_token = results.get('nextPageToken')
            if not page_token:
                break

        contacts = defaultdict(lambda: {'name': '', 'threads': set(), 'last_contact': None})
        email_records = []

        for msg in messages:
            message = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='metadata',
                metadataHeaders=['From', 'To', 'Cc', 'Subject', 'Date']
            ).execute()

            headers = message['payload']['headers']
            headers_dict = {h['name']: h['value'] for h in headers}

            email_records.append({
                'id': msg['id'],
                'thread_id': message.get('threadId', ''),
                'from_email': headers_dict.get('From', ''),
                'to_email': headers_dict.get('To', ''),
                'subject': headers_dict.get('Subject', ''),
                'date': headers_dict.get('Date', ''),
                'snippet': message.get('snippet', '')[:200]
            })

            seen_in_msg = set()
            for header in headers:
                if header['name'] in ['From', 'To', 'Cc']:
                    value = header['value']
                    email_pattern = r'<([^>]+)>|([^\s<>,]+@[^\s<>,]+)'
                    matches = re.findall(email_pattern, value)

                    for match in matches:
                        email = match[0] or match[1]
                        email = email.strip('"\'<> ')
                        if email and '@' in email and email not in seen_in_msg:
                            email_lower = email.lower()

                            if email_lower in user_addresses:
                                continue
                            email_domain = email_lower.split('@')[1] if '@' in email_lower else ''
                            if email_domain in user_domains:
                                continue
                            if exclude_automated and is_automated(email):
                                continue

                            seen_in_msg.add(email)

                            name_match = re.search(rf'([^<>]+)<{re.escape(email)}>', value)
                            name = name_match.group(1).strip() if name_match else email.split('@')[0]

                            thread_id = message.get('threadId', msg['id'])
                            if not contacts[email]['name']:
                                contacts[email]['name'] = name
                            contacts[email]['threads'].add(thread_id)

                            email_date = headers_dict.get('Date', '')
                            if email_date and not contacts[email]['last_contact']:
                                from email.utils import parsedate_to_datetime
                                try:
                                    dt = parsedate_to_datetime(email_date)
                                    contacts[email]['last_contact'] = dt.strftime('%Y-%m-%d')
                                except:
                                    contacts[email]['last_contact'] = email_date[:10]

        # Convert to simple dict format
        result = {}
        for email, info in contacts.items():
            result[email] = {
                'email': email,
                'name': info['name'],
                'frequency': len(info['threads']),
                'last_contact': info.get('last_contact', ''),
                'type': '',
                'company': '',
                'relationship': '',
                'priority': '',
                'deal': '',
                'next_contact_date': '',
                'tags': '',
                'notes': ''
            }

        return result, email_records

    def get_all_contacts(self, max_emails: int = 500, exclude_automated: bool = True, exclude_domains: str = "") -> str:
        """Get all unique contacts from emails with frequency count. OVERWRITES contacts.csv.

        Use this for initial setup. For regular updates that preserve CRM data, use sync_contacts().

        Args:
            max_emails: Maximum emails to scan (default: 500)
            exclude_automated: Filter out no-reply, system, and automated senders (default: True)
            exclude_domains: Comma-separated domains to exclude (e.g. "mycompany.com,myorg.ai")

        Returns:
            List of contacts sorted by frequency with email, name, and count
        """
        import csv

        # Scan emails using helper
        contacts, email_records = self._scan_contacts(max_emails, exclude_automated, exclude_domains)

        # Sort by frequency descending
        sorted_contacts = sorted(contacts.values(), key=lambda x: int(x['frequency']), reverse=True)

        # Write emails CSV
        if self.emails_csv:
            with open(self.emails_csv, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['id', 'thread_id', 'from_email', 'to_email', 'subject', 'date', 'snippet'])
                writer.writeheader()
                writer.writerows(email_records)

        # Write contacts CSV (OVERWRITES - use sync_contacts to preserve CRM data)
        if self.contacts_csv:
            fieldnames = ['email', 'name', 'frequency', 'last_contact', 'type', 'company', 'relationship', 'priority', 'deal', 'next_contact_date', 'tags', 'notes']
            with open(self.contacts_csv, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(sorted_contacts)

        # Format output
        output = [f"Found {len(contacts)} unique contacts (sorted by thread count):\n"]
        for c in sorted_contacts:
            output.append(f"- {c['name']} <{c['email']}> ({c['frequency']} threads)")

        return "\n".join(output)

    def analyze_contact(self, email: str, max_emails: int = 50) -> str:
        """Analyze a specific contact using LLM to extract context and relationship info.

        Args:
            email: Contact's email address to analyze
            max_emails: Number of recent emails to analyze (default: 50)

        Returns:
            LLM-generated analysis with context, tags, and relationship notes
        """
        from connectonion.llm_do import llm_do

        # Search for emails from this contact
        emails_result = self.search_emails(query=f"from:{email} OR to:{email}", max_results=max_emails)

        # Use LLM to analyze with markdown system prompt
        from pathlib import Path

        input_data = f"""Contact: {email}

Emails:
{emails_result}"""

        # Get path to prompt file relative to this module
        # gmail.py is in connectonion/useful_tools/, prompt_files/ is in connectonion/prompt_files/
        prompt_path = Path(__file__).parent.parent / "prompt_files" / "analyze_contact.md"

        analysis = llm_do(
            input_data,
            system_prompt=prompt_path
        )

        return f"Analysis for {email}:\n\n{analysis}"

    def get_unanswered_emails(self, within_days: int = 120, max_results: int = 20) -> str:
        """Find emails from the last N days that we haven't replied to.

        Useful for CRM to identify conversations that need follow-up.
        Checks threads where the last message is FROM someone else (not us).

        Args:
            within_days: Look back this many days (default: 120 = ~4 months)
            max_results: Maximum emails to return (default: 20)

        Returns:
            List of unanswered emails with sender, subject, date, and age
        """
        import re
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime

        service = self._get_service()

        # Get ALL user email addresses including Cloudflare routed addresses (auto-detected)
        user_emails = self.get_all_my_emails(max_emails=50)

        # Search for inbox emails from the last N days
        # Use pagination to ensure we find enough unanswered emails
        query = f"in:inbox newer_than:{within_days}d"
        unanswered = []
        seen_threads = set()
        page_token = None
        max_pages = 10  # Safety limit to avoid infinite loops
        pages_fetched = 0

        while len(unanswered) < max_results and pages_fetched < max_pages:
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=100,  # Fetch in larger batches for efficiency
                pageToken=page_token
            ).execute()

            messages = results.get('messages', [])
            if not messages:
                break

            for msg in messages:
                # Get thread to check if we replied
                thread_id = msg.get('threadId')
                if thread_id in seen_threads:
                    continue
                seen_threads.add(thread_id)

                # Get full thread
                thread = service.users().threads().get(
                    userId='me',
                    id=thread_id,
                    format='metadata',
                    metadataHeaders=['From', 'Subject', 'Date']
                ).execute()

                thread_messages = thread.get('messages', [])
                if not thread_messages:
                    continue

                # Check the last message in thread
                last_msg = thread_messages[-1]
                headers = last_msg['payload']['headers']
                last_from = next((h['value'] for h in headers if h['name'] == 'From'), '')

                # Extract email from "Name <email>" format
                email_match = re.search(r'<([^>]+)>', last_from)
                last_from_email = email_match.group(1).lower() if email_match else last_from.lower()

                # Skip if last message is from us (we already replied)
                # Check against ALL our email addresses (primary + aliases)
                if any(email in last_from_email for email in user_emails):
                    continue

                # Get first message details
                first_msg = thread_messages[0]
                first_headers = first_msg['payload']['headers']
                first_from = next((h['value'] for h in first_headers if h['name'] == 'From'), '')
                first_email_match = re.search(r'<([^>]+)>', first_from)
                first_from_email = first_email_match.group(1).lower() if first_email_match else first_from.lower()
                subject = next((h['value'] for h in first_headers if h['name'] == 'Subject'), 'No Subject')
                subject_lower = subject.lower()

                # Skip if WE sent the first message (we initiated, not awaiting reply)
                # Check against ALL our email addresses (primary + aliases)
                if any(email in first_from_email for email in user_emails):
                    continue

                # Skip automated senders by email patterns
                automated_email_patterns = [
                    # Generic automated prefixes
                    'noreply', 'no-reply', 'donotreply', 'do-not-reply',
                    'notifications@', 'notification@', 'newsletter@', 'news@',
                    'alerts@', 'alert@', 'updates@', 'update@',
                    'security@', 'team@', 'support@', 'help@', 'info@',
                    'marketing@', 'promo@', 'promotions@', 'offers@',
                    'billing@', 'invoice@', 'receipt@', 'order@',
                    'feedback@', 'survey@', 'announce@', 'digest@',
                    'hello@',  # Common marketing prefix
                    # Common automated domains/subdomains
                    'mail.instagram.com', 'mail.linkedin.com', 'mail.facebook.com',
                    'mail.twitter.com', 'mail.x.com', 'mail.google.com',
                    'facebookmail.com', 'linkedin.com', 'glassdoor.com',
                    'calendly.com', 'zoom.us', 'mailchimp', 'sendgrid',
                    'amazonses', 'postmark', 'intercom', 'hubspot',
                    'mailgun', 'sparkpost', 'constantcontact', 'campaign-archive',
                    'vimeo.com', 'vimeo@',  # Video platforms
                    'mongodb.com', 'mongodb@', 'atlassian.com', 'github.com',
                    'aws.amazon.com', 'cloud.google.com', 'azure.microsoft.com',
                    # Subdomain patterns (careful - these match anywhere in domain)
                    'mail.', 'send.', 'email.', 'mailer.', 'bounce.',
                    'notify.', 'msg.', 'campaigns.',
                ]
                if any(p in last_from_email for p in automated_email_patterns):
                    continue

                # Skip by subject line patterns (common automated email subjects)
                automated_subject_patterns = [
                    'your job', 'job alert', 'new jobs', 'jobs for you',
                    'password reset', 'verify your', 'confirm your',
                    'security alert', 'new sign-in', 'new login', 'login attempt',
                    'weekly digest', 'daily digest', 'monthly digest',
                    'newsletter', 'unsubscribe', 'subscription',
                    'receipt for', 'invoice', 'payment confirmation', 'order confirmation',
                    'your order', 'shipping confirmation', 'delivery update',
                    'welcome to', 'thanks for signing up', 'account created',
                    'is active', 'expiring soon', 'expires', 'renew',
                    # Calendar/meeting related
                    'invitation:', 'invitation from', 'canceled event', 'accepted:', 'declined:',
                    'updated invitation', 'event canceled', 'meeting canceled',
                    'from an unknown sender',
                    # Account related
                    'account registration', 'registration complete', 'verify your email',
                    'confirm your email', 'activate your account', 'action required',
                    'build your first', 'getting started with', 'complete your setup',
                    # Monthly/periodic reports
                    'in january', 'in february', 'in march', 'in april', 'in may',
                    'in june', 'in july', 'in august', 'in september', 'in october',
                    'in november', 'in december', 'this month', 'last month',
                    'pro tips', 'tips to', 'getting started',
                ]
                if any(p in subject_lower for p in automated_subject_patterns):
                    continue
                from_email = next((h['value'] for h in first_headers if h['name'] == 'From'), 'Unknown')
                date_str = next((h['value'] for h in first_headers if h['name'] == 'Date'), '')

                # Calculate age
                age_days = within_days  # Default fallback
                if date_str:
                    date_obj = parsedate_to_datetime(date_str)
                    now = datetime.now(timezone.utc)
                    age_days = (now - date_obj).days

                unanswered.append({
                    'thread_id': thread_id,
                    'from': from_email,
                    'subject': subject,
                    'date': date_str,
                    'age_days': age_days,
                    'messages_in_thread': len(thread_messages)
                })

                if len(unanswered) >= max_results:
                    break

            # Pagination: get next page
            page_token = results.get('nextPageToken')
            pages_fetched += 1
            if not page_token:
                break

        if not unanswered:
            return f"No unanswered emails found in the last {within_days} days."

        # Format output
        output = [f"Found {len(unanswered)} unanswered email(s) from the last {within_days} days:\n"]
        for i, email in enumerate(unanswered, 1):
            output.append(f"{i}. From: {email['from']}")
            output.append(f"   Subject: {email['subject']}")
            output.append(f"   Age: {email['age_days']} days ({email['messages_in_thread']} messages in thread)")
            output.append(f"   Thread ID: {email['thread_id']}\n")

        return "\n".join(output)

    # === CSV Caching ===

    def sync_emails(self, days_back: int = 300) -> str:
        """Sync emails to CSV cache file with full content (incremental).

        First run: fetches all emails from last N days with full body.
        Subsequent runs: only fetches new emails not already in cache.

        Args:
            days_back: How many days of email history to sync (default: 300)

        Returns:
            Summary of sync operation
        """
        if not self.emails_csv:
            return "No emails_csv path configured. Initialize Gmail with emails_csv parameter."

        import csv
        import base64
        from datetime import datetime, timedelta

        service = self._get_service()

        # Get existing email IDs from cache
        existing_ids = set()
        if os.path.exists(self.emails_csv):
            with open(self.emails_csv, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_ids.add(row['id'])

        # Build query for date range
        after_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y/%m/%d')
        query = f"after:{after_date}"

        # Fetch ALL email IDs in date range with pagination
        messages = []
        page_token = None
        while True:
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=100,
                pageToken=page_token
            ).execute()
            messages.extend(results.get('messages', []))
            page_token = results.get('nextPageToken')
            if not page_token:
                break

        # Filter out already cached emails
        new_msg_ids = [msg for msg in messages if msg['id'] not in existing_ids]

        def get_email_body(payload):
            """Extract plain text body from email payload."""
            if 'body' in payload and payload['body'].get('data'):
                return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='replace')

            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain' and part['body'].get('data'):
                        return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                    # Recurse into nested parts
                    if 'parts' in part:
                        result = get_email_body(part)
                        if result:
                            return result
            return ''

        new_emails = []
        for msg in new_msg_ids:
            message = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='full'
            ).execute()

            headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
            body = get_email_body(message['payload'])

            new_emails.append({
                'id': msg['id'],
                'thread_id': message.get('threadId', ''),
                'from_email': headers.get('From', ''),
                'to_email': headers.get('To', ''),
                'subject': headers.get('Subject', ''),
                'date': headers.get('Date', ''),
                'body': body,
                'snippet': message.get('snippet', '')
            })

        # Append new emails to CSV
        fieldnames = ['id', 'thread_id', 'from_email', 'to_email', 'subject', 'date', 'body', 'snippet']
        file_exists = os.path.exists(self.emails_csv) and os.path.getsize(self.emails_csv) > 0
        with open(self.emails_csv, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerows(new_emails)

        return f"Synced {len(new_emails)} new emails (from {len(messages)} total in last {days_back} days). Cache now has {len(existing_ids) + len(new_emails)} emails."

    def sync_contacts(self, max_emails: int = 500, exclude_domains: str = "") -> str:
        """Sync contacts - adds new, updates existing, KEEPS all contacts, PRESERVES CRM data.

        Unlike get_all_contacts() which overwrites everything, sync_contacts():
        - Adds NEW contacts with empty CRM fields
        - Updates frequency and last_contact for existing contacts
        - KEEPS contacts not in recent scan (they're still valid, just no recent emails)
        - PRESERVES existing CRM fields (type, priority, company, relationship, etc.)

        Use get_all_contacts() for initial setup, sync_contacts() for regular updates.

        Args:
            max_emails: Maximum emails to scan (default: 500)
            exclude_domains: Comma-separated domains to exclude

        Returns:
            Summary of sync operation
        """
        if not self.contacts_csv:
            return "No contacts_csv path configured. Initialize Gmail with contacts_csv parameter."

        import csv

        # Step 1: Load existing contacts with ALL data
        existing = {}
        if os.path.exists(self.contacts_csv):
            with open(self.contacts_csv, 'r') as f:
                for row in csv.DictReader(f):
                    existing[row['email'].lower()] = dict(row)

        old_count = len(existing)

        # Step 2: Scan emails using helper (no CSV write)
        fresh, _ = self._scan_contacts(max_emails, True, exclude_domains)

        # Step 3: Merge - update existing, add new, KEEP contacts not in scan
        new_count = 0
        updated_count = 0
        for email, data in fresh.items():
            email_key = email.lower()
            if email_key in existing:
                # Update frequency and last_contact, keep CRM fields
                existing[email_key]['frequency'] = str(data['frequency'])
                existing[email_key]['last_contact'] = data['last_contact']
                if not existing[email_key].get('name'):
                    existing[email_key]['name'] = data['name']
                updated_count += 1
            else:
                # New contact
                existing[email_key] = data
                new_count += 1

        # Step 4: Write merged data (sorted by frequency)
        fieldnames = ['email', 'name', 'frequency', 'last_contact', 'type', 'company',
                      'relationship', 'priority', 'deal', 'next_contact_date', 'tags', 'notes']
        sorted_contacts = sorted(existing.values(), key=lambda x: int(x.get('frequency', 0)), reverse=True)

        with open(self.contacts_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sorted_contacts)

        return f"Synced {len(existing)} contacts ({new_count} new, {updated_count} updated, {old_count - updated_count} unchanged)"

    def get_cached_contacts(self) -> str:
        """Get contacts from CSV cache (fast, no API call).

        Returns:
            List of cached contacts sorted by frequency
        """
        if not self.contacts_csv or not os.path.exists(self.contacts_csv):
            return "No cached contacts. Run sync_contacts() first."

        import csv

        contacts = []
        with open(self.contacts_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                contacts.append(row)

        if not contacts:
            return "No contacts in cache. Run sync_contacts() first."

        result = [f"Cached contacts ({len(contacts)}):\n"]
        for c in contacts[:50]:
            result.append(f"- {c['name']} <{c['email']}> ({c['frequency']} emails)")

        return "\n".join(result)

    def update_contact(self, email: str, type: str = None, company: str = None,
                       relationship: str = None, priority: str = None, deal: str = None,
                       next_contact_date: str = None, tags: str = None, notes: str = None,
                       last_contact: str = None) -> str:
        """Update CRM fields for a contact in contacts.csv.

        Args:
            email: Contact email address (required)
            type: Contact type - PERSON, SERVICE, or NOTIFICATION
            company: Company/organization name
            relationship: e.g., "applicant", "vendor", "investor", "friend"
            priority: high, medium, or low
            deal: Active opportunity/project name
            next_contact_date: When to follow up (YYYY-MM-DD)
            tags: Comma-separated tags
            notes: Additional context
            last_contact: Date of last contact (YYYY-MM-DD)

        Returns:
            Confirmation message
        """
        if not self.contacts_csv or not os.path.exists(self.contacts_csv):
            return f"Contact {email} not found. Run sync_contacts() first."

        import csv

        # Read existing contacts
        contacts = []
        found = False
        with open(self.contacts_csv, 'r') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row['email'] == email:
                    found = True
                    if type is not None:
                        row['type'] = type
                    if company is not None:
                        row['company'] = company
                    if relationship is not None:
                        row['relationship'] = relationship
                    if priority is not None:
                        row['priority'] = priority
                    if deal is not None:
                        row['deal'] = deal
                    if next_contact_date is not None:
                        row['next_contact_date'] = next_contact_date
                    if tags is not None:
                        row['tags'] = tags
                    if notes is not None:
                        row['notes'] = notes
                    if last_contact is not None:
                        row['last_contact'] = last_contact
                contacts.append(row)

        if not found:
            return f"Contact {email} not found in contacts.csv"

        # Write back
        with open(self.contacts_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(contacts)

        updates = []
        if type:
            updates.append(f"type={type}")
        if priority:
            updates.append(f"priority={priority}")
        if deal:
            updates.append(f"deal={deal}")
        if next_contact_date:
            updates.append(f"next_contact_date={next_contact_date}")
        if relationship:
            updates.append(f"relationship={relationship}")
        if company:
            updates.append(f"company={company}")
        if last_contact:
            updates.append(f"last_contact={last_contact}")

        return f"Updated {email}: {', '.join(updates) if updates else 'no changes'}"

    def bulk_update_contacts(self, updates: list) -> str:
        """Update multiple contacts in one operation (efficient batch update).

        Args:
            updates: List of dicts, each with 'email' (required) and optional fields:
                     type, company, relationship, priority, deal, next_contact_date, tags, notes
                     Example: [{"email": "foo@bar.com", "type": "PERSON", "priority": "high"},
                              {"email": "baz@qux.com", "type": "NOTIFICATION", "priority": "low"}]

        Returns:
            Summary of updates made
        """
        if not self.contacts_csv or not os.path.exists(self.contacts_csv):
            return "No contacts.csv found. Run sync_contacts() first."

        import csv

        # Build lookup map from updates list
        updates_map = {}
        for u in updates:
            if 'email' in u:
                updates_map[u['email'].lower()] = u

        # Read all contacts
        contacts = []
        fieldnames = None
        with open(self.contacts_csv, 'r') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                email_key = row['email'].lower()
                if email_key in updates_map:
                    update = updates_map[email_key]
                    for field in ['type', 'company', 'relationship', 'priority', 'deal', 'next_contact_date', 'tags', 'notes', 'last_contact']:
                        if field in update and update[field] is not None:
                            row[field] = update[field]
                contacts.append(row)

        # Write back
        with open(self.contacts_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(contacts)

        return f"Bulk updated {len(updates_map)} contacts"
