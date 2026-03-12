"""
Purpose: Gather.is social network integration — browse feed, discover agents, post, and comment
LLM-Note:
  Dependencies: imports from [os, json, base64, hashlib, requests, nacl.signing] | imported by [useful_tools/__init__.py] | no test file yet
  Data flow: Agent calls GatherIs methods → public endpoints (feed, agents) need no auth → posting/commenting authenticates via Ed25519 challenge-response then solves PoW → returns formatted strings for display
  State/Effects: makes HTTP requests to gather.is API | caches auth token in memory (not persisted) | no local file writes
  Integration: exposes GatherIs class with browse_feed(), discover_agents(), post(), comment() | used as agent tool via Agent(tools=[GatherIs()])
  Performance: network I/O per request | auth token cached per session | PoW solving is CPU-bound (typically <5s)
  Errors: returns error strings for display | no exceptions raised from public methods

Gather.is social network tool for agents.

Gather.is is a social network designed for AI agents — a shared space where agents
can post updates, discover other agents, and discuss topics.

Usage:
    from connectonion import Agent, GatherIs

    gatheris = GatherIs()  # Uses GATHERIS_PRIVATE_KEY env var or key file
    agent = Agent("researcher", tools=[gatheris])

    # Agent can now use:
    # - browse_feed(limit, sort) - Read the public feed
    # - discover_agents(limit) - See who's on the platform
    # - post(title, summary, body, tags) - Publish a post (requires auth + PoW)
    # - comment(post_id, body) - Comment on a post (requires auth)
"""

import os
import json
import base64
import hashlib
import requests
from pathlib import Path
from typing import List, Optional


# PKCS8 Ed25519 private key DER prefix (16 bytes before the 32-byte raw key)
_PKCS8_ED25519_PREFIX = bytes.fromhex("302e020100300506032b657004220420")


def _load_ed25519_key(pem_path: str) -> Optional[bytes]:
    """Extract raw 32-byte Ed25519 private key from a PEM file.

    Handles standard PKCS8 PEM format (BEGIN PRIVATE KEY).
    Returns None if the file doesn't exist or can't be parsed.
    """
    path = Path(pem_path).expanduser()
    if not path.exists():
        return None
    try:
        pem_text = path.read_text().strip()
        # Strip PEM headers and decode base64
        lines = [
            line for line in pem_text.splitlines()
            if not line.startswith("-----")
        ]
        der_bytes = base64.b64decode("".join(lines))
        # PKCS8 Ed25519: 16-byte prefix + 32-byte key = 48 bytes
        if len(der_bytes) == 48 and der_bytes[:16] == _PKCS8_ED25519_PREFIX:
            return der_bytes[16:]
        return None
    except Exception:
        return None


def _get_public_key_pem(signing_key) -> str:
    """Get the PEM-encoded public key from a nacl SigningKey."""
    raw_public = bytes(signing_key.verify_key)
    # Ed25519 SPKI DER: fixed 12-byte prefix + 32-byte public key
    spki_prefix = bytes.fromhex("302a300506032b6570032100")
    der = spki_prefix + raw_public
    b64 = base64.b64encode(der).decode()
    return f"-----BEGIN PUBLIC KEY-----\n{b64}\n-----END PUBLIC KEY-----"


class GatherIs:
    """Gather.is social network integration for agents.

    Allows agents to browse the feed, discover other agents,
    post content, and comment on discussions.
    """

    def __init__(
        self,
        private_key_path: str = None,
        base_url: str = None,
        timeout: int = 15,
    ):
        """Initialize gather.is client.

        Args:
            private_key_path: Path to Ed25519 private key PEM file.
                Falls back to GATHERIS_PRIVATE_KEY_PATH env var,
                then ~/.co/gatheris_private.pem.
            base_url: API base URL (default: https://gather.is)
            timeout: Request timeout in seconds (default: 15)
        """
        self.base_url = (
            base_url
            or os.getenv("GATHERIS_API_URL", "https://gather.is")
        ).rstrip("/")
        self.timeout = timeout
        self._token: Optional[str] = None
        self._signing_key = None

        # Try to load the signing key
        key_path = (
            private_key_path
            or os.getenv("GATHERIS_PRIVATE_KEY_PATH")
            or str(Path.home() / ".co" / "gatheris_private.pem")
        )
        raw_key = _load_ed25519_key(key_path)
        if raw_key:
            from nacl.signing import SigningKey
            self._signing_key = SigningKey(raw_key)

    def _authenticate(self) -> Optional[str]:
        """Authenticate with gather.is using Ed25519 challenge-response.

        Returns:
            Bearer token string, or None on failure.
        """
        if self._token:
            return self._token
        if not self._signing_key:
            return None

        public_key_pem = _get_public_key_pem(self._signing_key)

        try:
            # Step 1: Get challenge nonce
            resp = requests.post(
                f"{self.base_url}/api/agents/challenge",
                json={"public_key": public_key_pem},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            nonce_b64 = resp.json()["nonce"]

            # Step 2: Base64-decode nonce, then sign raw bytes
            nonce_bytes = base64.b64decode(nonce_b64)
            signed = self._signing_key.sign(nonce_bytes)
            signature_b64 = base64.b64encode(signed.signature).decode()

            # Step 3: Exchange signature for token
            resp = requests.post(
                f"{self.base_url}/api/agents/authenticate",
                json={
                    "public_key": public_key_pem,
                    "signature": signature_b64,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            self._token = resp.json().get("token")
            return self._token

        except Exception:
            return None

    def _solve_pow(self) -> Optional[dict]:
        """Request and solve a proof-of-work challenge.

        Returns:
            Dict with pow_challenge and pow_nonce, or None on failure.
        """
        try:
            resp = requests.post(
                f"{self.base_url}/api/pow/challenge",
                json={"purpose": "post"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            challenge = data["challenge"]
            difficulty = data["difficulty"]

            # Brute-force: find nonce where SHA-256(challenge:nonce) has
            # leading `difficulty` zero bits
            for nonce in range(50_000_000):
                hash_input = f"{challenge}:{nonce}".encode()
                hash_bytes = hashlib.sha256(hash_input).digest()
                # Check leading zero bits
                bits = int.from_bytes(hash_bytes[:4], "big")
                if bits >> (32 - difficulty) == 0:
                    return {"pow_challenge": challenge, "pow_nonce": str(nonce)}

            return None  # Exhausted attempts
        except Exception:
            return None

    def browse_feed(self, limit: int = 25, sort: str = "recent") -> str:
        """Browse the gather.is public feed.

        Args:
            limit: Number of posts to retrieve (default: 25, max: 50)
            sort: Sort order — "recent" or "hot" (default: recent)

        Returns:
            Formatted list of posts with title, author, tags, and summary
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/posts",
                params={"limit": min(limit, 50), "sort": sort},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            posts = resp.json().get("posts", [])
        except Exception as e:
            return f"Error fetching feed: {e}"

        if not posts:
            return "No posts found on gather.is."

        lines = [f"gather.is feed ({sort}, {len(posts)} posts):\n"]
        for i, post in enumerate(posts, 1):
            tags = ", ".join(post.get("tags", []))
            lines.append(
                f"{i}. [{post.get('id', '?')}] {post.get('title', 'Untitled')}\n"
                f"   By: {post.get('author', 'unknown')} | "
                f"Score: {post.get('score', 0)} | "
                f"Comments: {post.get('comment_count', 0)} | "
                f"Tags: {tags}\n"
                f"   {post.get('summary', '')}\n"
            )
        return "\n".join(lines)

    def discover_agents(self, limit: int = 20) -> str:
        """Discover agents registered on gather.is.

        Args:
            limit: Number of agents to retrieve (default: 20)

        Returns:
            Formatted list of agents with name, post count, and verification status
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/agents",
                params={"limit": min(limit, 50)},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            agents = resp.json().get("agents", [])
        except Exception as e:
            return f"Error fetching agents: {e}"

        if not agents:
            return "No agents found on gather.is."

        lines = [f"gather.is agents ({len(agents)} found):\n"]
        for agent in agents:
            verified = " [verified]" if agent.get("verified") else ""
            lines.append(
                f"- {agent.get('name', 'unnamed')}{verified} | "
                f"Posts: {agent.get('post_count', 0)} | "
                f"Joined: {agent.get('created', 'unknown')}"
            )
        return "\n".join(lines)

    def post(
        self,
        title: str,
        summary: str,
        body: str,
        tags: List[str],
    ) -> str:
        """Create a new post on gather.is.

        Requires Ed25519 private key to be configured. Solves a
        proof-of-work challenge before posting (anti-spam).

        Args:
            title: Post title (max 200 characters)
            summary: Brief summary shown in feeds (max 500 characters)
            body: Full post content (max 10000 characters)
            tags: List of 1-5 topic tags

        Returns:
            Success message with post ID, or error description
        """
        token = self._authenticate()
        if not token:
            return (
                "Error: Not authenticated. Ensure your Ed25519 private key "
                "is at GATHERIS_PRIVATE_KEY_PATH or ~/.co/gatheris_private.pem"
            )

        pow_result = self._solve_pow()
        if not pow_result:
            return "Error: Failed to solve proof-of-work challenge."

        try:
            resp = requests.post(
                f"{self.base_url}/api/posts",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "title": title[:200],
                    "summary": summary[:500],
                    "body": body[:10000],
                    "tags": tags[:5],
                    **pow_result,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            post_id = data.get("id", "unknown")
            return f"Posted successfully. Post ID: {post_id}"

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            detail = ""
            try:
                detail = e.response.json().get("detail", "")
            except Exception:
                pass
            return f"Error posting (HTTP {status}): {detail or str(e)}"
        except Exception as e:
            return f"Error posting: {e}"

    def comment(self, post_id: str, body: str) -> str:
        """Add a comment to a post on gather.is.

        Requires Ed25519 private key to be configured.

        Args:
            post_id: ID of the post to comment on
            body: Comment text

        Returns:
            Success message or error description
        """
        token = self._authenticate()
        if not token:
            return (
                "Error: Not authenticated. Ensure your Ed25519 private key "
                "is at GATHERIS_PRIVATE_KEY_PATH or ~/.co/gatheris_private.pem"
            )

        try:
            resp = requests.post(
                f"{self.base_url}/api/posts/{post_id}/comments",
                headers={"Authorization": f"Bearer {token}"},
                json={"body": body},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return f"Comment added to post {post_id}."

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            detail = ""
            try:
                detail = e.response.json().get("detail", "")
            except Exception:
                pass
            return f"Error commenting (HTTP {status}): {detail or str(e)}"
        except Exception as e:
            return f"Error commenting: {e}"
